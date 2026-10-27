"""Selección temporal; fixtures o experimento provisional con permiso específico.

Sin carga/serialización de modelos o fuentes ni habilitación de producción.
"""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import warnings

import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from sigard_ml.forecasting import VERSION
from sigard_ml.forecasting.contracts import ForecastError, experimental, nonnegative, require, snapshot_scenario, usable_count, week
from sigard_ml.forecasting.dataset import FEATURES, build_dataset, input_snapshots
from sigard_ml.forecasting.evaluation import count_metrics, evaluate, poisson_presence_diagnostic
from sigard_ml.models.persistence import PersistenceBaseline

SEED = 20261021
CANDIDATES = ("poisson_glm", "poisson_boosting")


def matrix(frame):
    # Lista cerrada: ni ID, clasificación, cobertura, objetivo, coordenadas o
    # metadatos de disponibilidad del desenlace pueden entrar al estimador.
    result = frame[list(FEATURES)].astype(float)
    require(not np.isinf(result.to_numpy()).any(), "Feature infinita")
    return result


def estimator(name, seed=SEED):
    require(name in CANDIDATES, "Candidato desconocido")
    imputer = SimpleImputer(strategy="constant", fill_value=0, add_indicator=True, keep_empty_features=True)
    if name == "poisson_glm":
        return make_pipeline(imputer, StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=1000, tol=1e-7))
    # Sin early stopping aleatorio: validación externa por semanas completas.
    return make_pipeline(imputer, HistGradientBoostingRegressor(
        loss="poisson", max_iter=60, max_leaf_nodes=7, min_samples_leaf=10,
        l2_regularization=1.0, early_stopping=False, random_state=seed))


def partition(frame, validation_start, test_start):
    week(validation_start)
    week(test_start)
    require(validation_start < test_start, "Cortes temporales invertidos")
    assignment = pd.Series("purged", index=frame.index)
    assignment.loc[frame.target_end.lt(validation_start)] = "train"
    assignment.loc[frame.origin_week.ge(validation_start) & frame.target_end.lt(test_start)] = "validation"
    assignment.loc[frame.origin_week.ge(test_start)] = "test"
    require(all(assignment.eq(part).any() for part in ("train", "validation", "test")), "Particiones vacías")
    return assignment


def training_labels(frame, inputs, cutoff):
    """Reconstruye etiquetas al ajuste, incluyendo revisiones conocidas entonces.

    No filtra la exportación final por fecha: usa la versión exacta de cada
    desenlace que ya podía conocerse al ajustar el modelo.
    Excepción explícita: el experimento retrospectivo usa la exportación única
    y filtra semanas cerradas, sin afirmar conocimiento histórico de su revisión.
    """
    result = frame.copy(deep=True)
    labels = input_snapshots(inputs, inputs.counts, ["radio_id", "week_start"], cutoff)
    values = []
    for row in result.itertuples():
        source = labels.get((row.radio_id, row.target_week))
        values.append(float(source.count) if usable_count(inputs, source) and row.target_end <= cutoff else np.nan)
    result["target_count"] = values
    return result.loc[result.target_count.notna()].copy()


def _fit(name, frame, seed):
    require(len(frame) > 0, "Sin etiquetas maduras para ajustar")
    nonnegative(frame.target_count, integer=True)
    # Poisson no admite entrenamiento de suma cero; el modelo nulo queda explícito.
    model = estimator(name, seed) if frame.target_count.sum() > 0 else make_pipeline(
        SimpleImputer(strategy="constant", fill_value=0, keep_empty_features=True), DummyRegressor(strategy="constant", constant=0.0))
    try:
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(matrix(frame), frame.target_count)
    except ConvergenceWarning as error:
        raise ForecastError("El candidato no convergió; no se acepta su evaluación") from error
    return model


def predict(model, frame):
    with threadpool_limits(limits=1):
        values = np.asarray(model.predict(matrix(frame)), dtype=float)
    require(values.shape == (len(frame),) and np.isfinite(values).all() and (values >= 0).all(), "Salida de conteo inválida")
    return values


def baseline_predictions(train, frame):
    by_radio = train.groupby("radio_id").target_count.mean()
    prior = frame.radio_id.map(by_radio).fillna(float(train.target_count.mean())).to_numpy(dtype=float)
    features = frame[["cases_lag_1"]].copy()
    features["cases_lag_1"] = features.cases_lag_1.fillna(pd.Series(prior, index=features.index))
    persistence = PersistenceBaseline("cases_lag_1").predict(features).to_numpy(dtype=float)
    return {"training_radio_mean": prior, "lag_1_or_training_mean": persistence}


@dataclass
class FittedCounts:
    model: object
    model_id: str
    selected: str
    fit_cutoff: object
    radios: tuple[str, ...]
    dataset_version: str
    seed: int
    data_kind: str = "fictional"
    horizon_weeks: int = 1


@dataclass
class Experiment:
    fitted: FittedCounts
    panel: pd.DataFrame
    report: dict
    evaluation_predictions: pd.DataFrame


def run_experiment(inputs, *, start, end, validation_start, test_start, evaluation_as_of, seed=SEED):
    """Train -> validación congelada -> selección -> refit -> test reservado.

    La selección conoce sólo desenlaces maduros al inicio de prueba. El test
    evalúa orígenes móviles con modelo fijo; nunca actualiza sus parámetros.
    La independencia científica del período debe acreditarse externamente.
    """
    inputs.validate()
    require(not snapshot_scenario(inputs), "El escenario snapshot requiere la evaluación V2 separada")
    provisional = experimental(inputs)
    require(inputs.data_kind == "fictional" or (provisional and inputs.training_authorized
                                               and inputs.evaluation_authorized),
            "Entrenamiento real deshabilitado: requiere modalidad y autorización experimental de entrenamiento/evaluación")
    require(type(seed) is int and seed >= 0, "Semilla inválida")
    panel = build_dataset(inputs, start=start, end=end, evaluation_as_of=evaluation_as_of)
    require(evaluation_as_of >= end + timedelta(days=13), "Congelamiento anterior al último desenlace")
    panel["partition"] = partition(panel, validation_start, test_start)
    fit_cutoff = validation_start + timedelta(days=6)
    refit_cutoff = test_start + timedelta(days=6)
    train = training_labels(panel.loc[panel.partition.eq("train")], inputs, fit_cutoff)
    validation = training_labels(panel.loc[panel.partition.eq("validation")], inputs, refit_cutoff)
    test = panel.loc[panel.partition.eq("test") & panel.target_count.notna()].copy()
    require(all(len(frame) for frame in (train, validation, test)), "Sin observaciones elegibles en alguna partición")
    metrics, models = {}, {}
    for name in CANDIDATES:
        models[name] = _fit(name, train, seed)
        metrics[name] = {"train": count_metrics(train.target_count, predict(models[name], train)),
                         "validation": count_metrics(validation.target_count, predict(models[name], validation))}
    # Desempate estable favorece GLM. No consulta la prueba.
    selected = min(CANDIDATES, key=lambda name: (metrics[name]["validation"]["mae"], CANDIDATES.index(name)))
    development = training_labels(panel.loc[panel.partition.isin(["train", "validation"])], inputs, refit_cutoff)
    model = _fit(selected, development, seed)
    predictions = predict(model, test)
    evaluation_predictions = test[["radio_id", "origin_week", "target_week", "target_count"]].copy()
    evaluation_predictions["model"] = predictions
    comparisons = {"model": evaluate(test, predictions, inputs.radios, observed_only=provisional)}
    for name, values in baseline_predictions(development, test).items():
        evaluation_predictions[name] = values
        comparisons[name] = evaluate(test, values, inputs.radios, observed_only=provisional)
    validation_baselines = {name: count_metrics(validation.target_count, values)
                            for name, values in baseline_predictions(train, validation).items()}
    # La huella incluye matrices reales de ajuste y protocolo/hiperparámetros;
    # excluye resultados de test para que éstos no definan el modelo.
    training_hash = hashlib.sha256(pd.util.hash_pandas_object(
        development[["radio_id", "origin_week", "target_count", *FEATURES]], index=False).values.tobytes()).hexdigest()
    identity = dict(version=VERSION, dataset_version=inputs.dataset_version, selected=selected, seed=seed,
                    fit_cutoff=refit_cutoff.isoformat(), features=FEATURES, training_sha256=training_hash,
                    sklearn_version=sklearn.__version__, parameters=str(model.get_params()))
    if provisional:
        identity.update(experiment_mode=inputs.experiment_mode, count_unit=inputs.count_unit,
                        input_evidence=inputs.input_evidence)
    model_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    fitted = FittedCounts(model, model_id, selected, refit_cutoff, inputs.radios, inputs.dataset_version, seed,
                          data_kind=inputs.data_kind)
    report = {"version": VERSION, "data_kind": inputs.data_kind, "scientific_performance": False,
              "real_training_enabled": provisional, "selected": selected, "model_id": model_id,
              "seed": seed, "sklearn_version": sklearn.__version__, "model_metadata": identity,
              "selection_metric": "validation_mae", "candidates": metrics,
              "validation_baselines": validation_baselines, "test": comparisons,
              "poisson_presence_diagnostic": poisson_presence_diagnostic(test.target_count, predictions) if selected == "poisson_glm" and not provisional else None,
              "rows": {"train_fit": len(train), "validation_selection": len(validation), "refit": len(development), "test": len(test),
                       "purged": int(panel.partition.eq("purged").sum()), "unknown_outcomes": int(panel.target_count.isna().sum())},
              "partition_rows": panel.partition.value_counts().to_dict(),
              "information_cutoffs": {"initial_fit": fit_cutoff.isoformat(), "selection_and_refit": refit_cutoff.isoformat(),
                                      "outcome_freeze": evaluation_as_of.isoformat()},
              "test_independence": "fictional_technical_reservation_only",
              "uncertainty": {"intervals": None, "reason": "No calibrated interval method or independent calibration period"}}
    if provisional:
        report.update(experiment_mode=inputs.experiment_mode, target_unit=inputs.count_unit,
            training_authorized=inputs.training_authorized, evaluation_authorized=inputs.evaluation_authorized,
            authorization_basis=inputs.input_evidence["authorization_basis"],
            authorization_ref=inputs.input_evidence["authorization_ref"],
            evaluation_mode="retrospective_event_time", historical_availability_accredited=False,
            production_inference_authorized=False, conditional_on_observed_cells=True,
            test_independence="chronological_technical_holdout_not_accredited_independent_evidence",
            limits=["Positive observed cells only; missing outcomes remain unknown, never zero",
                    "Final retrospective export; lagged event weeks do not establish point-in-time availability",
                    "No population-wide occurrence probabilities or complete Capital totals",
                    "Unresolved episodes and approximate territorial attribution are preserved"],
            partition_weeks={part: sorted(value.isoformat() for value in group.origin_week.unique())
                             for part, group in panel.groupby("partition")},
            observed_partition_weeks={part: sorted(value.isoformat() for value in frame.target_week.unique())
                                      for part, frame in (("train", train), ("validation", validation), ("test", test))})
    return Experiment(fitted, panel, report, evaluation_predictions)
