"""Experimentos V2 sobre el circuito principal: diagnóstico, selección y snapshot.

Sin IO ni publicación. Reutiliza features, estimadores Poisson, baselines,
particiones y métricas existentes. Prueba V1 sólo como comparación ya observada.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from sigard_ml.forecasting.contracts import nonnegative, require, snapshot_scenario, week
from sigard_ml.forecasting.dataset import FEATURES, build_dataset
from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.training import SEED, estimator, matrix, partition, predict, training_labels
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
from sigard_ml.official.spatial_ml.research_training import classification_metrics, reliability_bins

VERSION = "sigard-principal-v2-experimental"
COUNT_CANDIDATES = ("poisson_boosting", "poisson_native", "poisson_weighted", "poisson_glm",
                    "lag_1_or_training_mean", "training_radio_mean")
PROTOCOL = {
    "version": VERSION, "seed": SEED, "horizons": [1, 2, 4], "count_candidates": list(COUNT_CANDIDATES),
    "native_parameters": {"loss": "poisson", "max_iter": 120, "max_leaf_nodes": 7,
        "min_samples_leaf": 8, "l2_regularization": 2.0, "learning_rate": .05, "early_stopping": False},
    "weighting": "sqrt(1+y_train) clipped to [1,3], training labels only",
    "folds": "expanding, chronological observed development target-week blocks at 1/2,2/3,5/6,1; purge labels through first validation origin",
    "selection": "0.25 MAE ratio + 0.25 RMSE ratio + 0.20 absolute bias/mean(actual) + 0.20 high-count MAE ratio + 0.10 weekly RMSE ratio",
    "guardrails": "relative to persistence: MAE<=1.10; RMSE<=1.05; high-count MAE<=1.10; |bias|<=|baseline bias|+0.10*mean(actual)",
    "high_count": "max(2, training-label 90th percentile), each fold; final threshold from development",
    "high_week": "training known-subset weekly total 80th percentile, each fold",
    "minimum_support": {"development_weeks": 18, "comparison_weeks": 4, "development_positive": 30},
    "predictor_admissibility": "snapshot: origin/target and intervening weeks in covered set, at least 50% radios with lag1 count, lag1 climate complete",
    "presence": "existing RF parameters; chronological last max(4,20%) development weeks sigmoid calibration; threshold 0.5 fixed; always experimental score",
    "test_status": "previously_observed_V1_period_not_independent_for_V2",
    "no_test_tuning": True, "production_inference_authorized": False,
}


def snapshot_grid(positive, quality, radios, covered_weeks):
    """Grilla de snapshot con ceros asumidos únicamente en semanas explícitas.

    Preserva conteo registrado incluso en celdas excluidas por calidad. Un null
    supervisado no se reemplaza por ese límite observado. 2022 queda separado.
    El llamador aporta autorización y hashes de los agregados/máscaras existentes.
    """
    radios, covered_weeks = tuple(radios), tuple(sorted(covered_weeks))
    require(len(radios) == 256 and len(set(radios)) == 256, "Universo snapshot inválido")
    require(covered_weeks and len(set(covered_weeks)) == len(covered_weeks), "Semanas snapshot inválidas")
    for value in covered_weeks:
        require(week(value)[0] != 2022, "2022 requiere política separada")
    keys = ["radio_id", "week_start"]
    require(not positive.duplicated(keys).any() and not quality.duplicated(keys).any(), "Celdas agregadas duplicadas")
    require(set(positive.radio_id) <= set(radios) and set(positive.week_start) <= set(covered_weeks), "Positivos fuera de cobertura")
    require(set(quality.radio_id) <= set(radios) and set(quality.week_start) <= set(covered_weeks), "Máscaras fuera de cobertura")
    nonnegative(positive.provisional_positive_records, integer=True)
    for name in ("pending_mentions", "approximate_date_records"):
        nonnegative(quality[name], integer=True)
    require(quality.partial_week.map(lambda value: isinstance(value, (bool, np.bool_))).all(), "Máscara temporal debe ser booleana")
    require(positive.provisional_positive_records.gt(0).all(), "Se requieren positivos registrados")
    index = pd.MultiIndex.from_product([radios, covered_weeks], names=keys)
    result = index.to_frame(index=False).merge(positive[keys + ["provisional_positive_records", "source_id", "source_version"]],
                                              on=keys, how="left", validate="one_to_one")
    result = result.merge(quality, on=keys, how="left", validate="one_to_one")
    require(result[["pending_mentions", "approximate_date_records", "partial_week"]].notna().all().all(), "Faltan máscaras de calidad")
    result["recorded_positive_count"] = result.provisional_positive_records.fillna(0).astype(int)
    result["pending_mask"] = result.pending_mentions.gt(0)
    result["temporal_mask"] = result.approximate_date_records.gt(0) | result.partial_week
    result["label_usable"] = ~result.pending_mask & ~result.temporal_mask
    result["snapshot_count"] = result.recorded_positive_count.where(result.label_usable, np.nan)
    result["quality_state"] = np.select([result.pending_mask & result.temporal_mask, result.pending_mask, result.temporal_mask,
                                         result.recorded_positive_count.gt(0)],
                                        ["unknown_pending_and_temporal", "unknown_pending", "unknown_temporal", "recorded_positive"],
                                        default="assumed_snapshot_zero")
    result["zero_is_epidemiological_absence"] = False
    result["scenario_version"] = "confirmed-snapshot-observed-weeks-2"
    result["source_id"] = result.source_id.fillna("snapshot_filtered_export_assumption")
    result["source_version"] = result.source_version.fillna("project-owner-V2-snapshot-declaration")
    return result.drop(columns="provisional_positive_records").sort_values(keys).reset_index(drop=True)


def diagnose_v1(predictions, panel, *, fitted=None):
    """Asociaciones agregadas de errores: no selecciona variables ni parámetros."""
    frame = predictions.merge(panel[["radio_id", "origin_week", *FEATURES]], on=["radio_id", "origin_week"], validate="one_to_one")
    frame["error"] = frame.model - frame.target_count
    frame["absolute_error"] = frame.error.abs()
    frame["squared_error"] = frame.error ** 2
    frame["underprediction"] = (-frame.error).clip(lower=0)
    frame["count_range"] = pd.cut(frame.target_count, [0, 1, 2, 4, 9, 19, np.inf],
                                   labels=["1", "2", "3-4", "5-9", "10-19", "20+"])
    ranges = []
    for label, group in frame.groupby("count_range", observed=True):
        ranges.append(dict(count_range=str(label), actual=int(group.target_count.sum()),
                           **count_metrics(group.target_count, group.model),
                           underprediction=float(group.underprediction.sum()),
                           persistence=count_metrics(group.target_count, group.lag_1_or_training_mean)))
    aggregates = {}
    for key in ("radio_id", "target_week"):
        grouped = frame.groupby(key).agg(n=("error", "size"), recorded_total=("target_count", "sum"),
            predicted_total=("model", "sum"), signed_error=("error", "sum"),
            absolute_error=("absolute_error", "sum"), underprediction=("underprediction", "sum"))
        aggregates[key] = grouped.sort_values("absolute_error", ascending=False).reset_index()
    weekly = aggregates["target_week"]
    feature_associations = []
    sensitivity = []
    development = panel[panel.partition.isin(["train", "validation"]) & panel.target_count.notna()]
    for feature in FEATURES:
        observed = development[feature].dropna()
        test = frame[feature]
        feature_associations.append(dict(feature=feature, development_min=float(observed.min()) if len(observed) else None,
            development_max=float(observed.max()) if len(observed) else None,
            comparison_missing=int(test.isna().sum()),
            comparison_outside_development_range=int((test.lt(observed.min()) | test.gt(observed.max())).sum()) if len(observed) else None,
            missing_group_bias=float(frame.loc[test.isna(), "error"].mean()) if test.isna().any() else None,
            observed_group_bias=float(frame.loc[test.notna(), "error"].mean()) if test.notna().any() else None))
        if fitted is not None:
            # Diagnóstico exclusivamente de la prueba ya vista. La lista de
            # candidatos/features/protocolo ya está congelada; no se selecciona.
            rng = np.random.default_rng(SEED)
            changes = []
            for _ in range(3):
                permuted = frame.copy()
                permuted[feature] = rng.permutation(frame[feature].to_numpy())
                values = predict(fitted.model, permuted)
                changes.append(count_metrics(frame.target_count, values))
            sensitivity.append(dict(feature=feature,
                permuted_mae=float(np.mean([m["mae"] for m in changes])),
                permuted_rmse=float(np.mean([m["rmse"] for m in changes])),
                permuted_bias=float(np.mean([m["mean_bias"] for m in changes]))))
    return dict(ranges=ranges, weekly=weekly, radios=aggregates["radio_id"],
        feature_associations=feature_associations, diagnostic_only_permutation=sensitivity,
        weekly_volume_absolute_error_correlation=float(weekly.recorded_total.corr(weekly.absolute_error)),
        development_target_max=float(development.target_count.max()), comparison_target_max=float(frame.target_count.max()),
        comparison_prediction_max=float(frame.model.max()),
        interpretation="Descriptive associations only. Imputation of missing count features is not an observed zero; tree extrapolation and temporal distribution shift can limit large predictions. No parameters selected from this comparison.")


@dataclass
class CountModel:
    name: str
    estimator: object
    radio_means: dict
    global_mean: float
    fit_cutoff: object
    horizon_weeks: int

    def predict_frame(self, frame):
        if self.estimator is not None:
            return predict(self.estimator, frame)
        prior = frame.radio_id.map(self.radio_means).fillna(self.global_mean).to_numpy(dtype=float)
        return np.where(frame.cases_lag_1.notna(), frame.cases_lag_1, prior) if self.name == "lag_1_or_training_mean" else prior


class EmptyFeatureFallback(TransformerMixin, BaseEstimator):
    """Evita el fallo de binning instalado con columnas enteramente NaN.

    Aprende sólo en entrenamiento qué columnas están vacías. Las demás conservan
    NaN nativos; no cambia etiquetas ni elimina un predictor mirando comparación.
    """

    def fit(self, X, y=None):
        self.empty_columns_ = list(X.columns[X.isna().all()])
        return self

    def transform(self, X):
        result = X.copy()
        result[self.empty_columns_] = result[self.empty_columns_].fillna(0.)
        return result


def fit_count(name, train, *, horizon_weeks=1, seed=SEED):
    require(name in COUNT_CANDIDATES and len(train) and train.target_count.notna().all(), "Ajuste V2 inválido")
    means = train.groupby("radio_id").target_count.mean().to_dict()
    if name in ("training_radio_mean", "lag_1_or_training_mean"):
        model = None
    elif name in ("poisson_native", "poisson_weighted"):
        model = make_pipeline(EmptyFeatureFallback(), HistGradientBoostingRegressor(**PROTOCOL["native_parameters"], random_state=seed))
    else:
        model = estimator(name, seed)
    if model is not None:
        weights = np.clip(np.sqrt(1 + train.target_count.to_numpy()), 1, 3) if name == "poisson_weighted" else None
        kwargs = {model.steps[-1][0] + "__sample_weight": weights} if weights is not None else {}
        require(train.target_count.sum() > 0, "Sin registros positivos para Poisson")
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(matrix(train), train.target_count, **kwargs)
    return CountModel(name, model, means, float(train.target_count.mean()), max(train.target_end), horizon_weeks)


def summary_metrics(frame, values, *, tail_threshold, high_week_threshold):
    result = count_metrics(frame.target_count, values)
    positive = frame.target_count.gt(0)
    result["positive_cells"] = count_metrics(frame.loc[positive, "target_count"], np.asarray(values)[positive]) if positive.any() else None
    mask = frame.target_count.ge(tail_threshold)
    result["high_count"] = count_metrics(frame.loc[mask, "target_count"], np.asarray(values)[mask]) if mask.any() else None
    copy = frame[["target_week", "target_count"]].copy()
    copy["predicted"] = values
    weekly = copy.groupby("target_week").agg(actual=("target_count", "sum"), predicted=("predicted", "sum"))
    weekly["error"] = weekly.predicted - weekly.actual
    result["weekly_known_subset_rmse"] = float(np.sqrt((weekly.error ** 2).mean()))
    result["weekly_known_subset_bias_sd"] = float(weekly.error.std(ddof=0))
    high = weekly.actual.ge(high_week_threshold)
    result["high_week_known_subset"] = count_metrics(weekly.loc[high, "actual"], weekly.loc[high, "predicted"]) if high.any() else None
    result["weeks"] = len(weekly)
    return result


def development_metrics(oof, names, *, tail_threshold, high_week_threshold):
    metrics = {}
    for name in names:
        value = summary_metrics(oof, oof[name], tail_threshold=tail_threshold, high_week_threshold=high_week_threshold)
        high = oof.target_count.ge(oof.high_count_threshold)
        value["high_count"] = count_metrics(oof.loc[high, "target_count"], oof.loc[high, name]) if high.any() else None
        weekly = oof.groupby("target_week").agg(actual=("target_count", "sum"), predicted=(name, "sum"), threshold=("high_week_threshold", "first"))
        high_week = weekly.actual.ge(weekly.threshold)
        value["high_week_known_subset"] = count_metrics(weekly.loc[high_week, "actual"], weekly.loc[high_week, "predicted"]) if high_week.any() else None
        metrics[name] = value
    return metrics


def select_candidate(metrics, mean_actual):
    """Regla fijada antes del diagnóstico. Persistencia es respaldo explícito."""
    baseline = metrics["lag_1_or_training_mean"]
    scores = {}
    ratio = lambda value, reference: value / max(reference, 1e-9)
    for name, value in metrics.items():
        tail = value["high_count"]["mae"] if value["high_count"] else value["mae"]
        baseline_tail = baseline["high_count"]["mae"] if baseline["high_count"] else baseline["mae"]
        allowed = (value["mae"] <= 1.10 * baseline["mae"] + 1e-9
            and value["rmse"] <= 1.05 * baseline["rmse"] + 1e-9
            and tail <= 1.10 * baseline_tail + 1e-9
            and abs(value["mean_bias"]) <= abs(baseline["mean_bias"]) + .10 * mean_actual + 1e-9)
        score = (.25 * ratio(value["mae"], baseline["mae"]) + .25 * ratio(value["rmse"], baseline["rmse"])
            + .20 * abs(value["mean_bias"]) / max(mean_actual, 1e-9) + .20 * ratio(tail, baseline_tail)
            + .10 * ratio(value["weekly_known_subset_rmse"], baseline["weekly_known_subset_rmse"]))
        scores[name] = dict(score=score, guardrails_passed=bool(allowed))
    eligible = [name for name in COUNT_CANDIDATES if name in scores and scores[name]["guardrails_passed"]]
    require(eligible, "Sin respaldo de validación, incluida persistencia")
    return min(eligible, key=lambda name: (scores[name]["score"], COUNT_CANDIDATES.index(name))), scores


def predictor_weeks(frame):
    """Disponibilidad del origen únicamente; no inspecciona etiquetas objetivo."""
    known = frame.groupby("origin_week").cases_lag_1.apply(lambda s: s.notna().mean())
    climate = frame.groupby("origin_week")[["temperature_lag_1", "humidity_lag_1", "precipitation_lag_1"]].count().min(axis=1)
    size = frame.groupby("origin_week").size()
    return set(known.index[known.ge(.5) & climate.eq(size)])


def run_counts(inputs, *, start, end, validation_start, test_start, evaluation_as_of, horizon_weeks=1, origin_weeks=None):
    inputs.validate()
    require(inputs.training_authorized and inputs.evaluation_authorized, "Falta permiso experimental V2")
    frame = build_dataset(inputs, start=start, end=end, evaluation_as_of=evaluation_as_of,
                          horizon_weeks=horizon_weeks, origin_weeks=origin_weeks)
    frame["partition"] = partition(frame, validation_start, test_start)
    if snapshot_scenario(inputs):
        covered = {date.fromisoformat(value) for value in inputs.input_evidence["snapshot_scenario"]["covered_weeks"]}
        possible = {origin for origin in frame.origin_week.unique()
                    if all(origin + timedelta(weeks=i) in covered for i in range(horizon_weeks + 1))}
        admissible = possible & predictor_weeks(frame)
        frame["predictor_admissible"] = frame.origin_week.isin(admissible)
    else:
        frame["predictor_admissible"] = True
    development = training_labels(frame.loc[frame.partition.isin(["train", "validation"]) & frame.predictor_admissible], inputs, test_start)
    comparison = frame.loc[frame.partition.eq("test") & frame.predictor_admissible & frame.target_count.notna()].copy()
    require(development.target_week.nunique() >= PROTOCOL["minimum_support"]["development_weeks"]
            and comparison.target_week.nunique() >= PROTOCOL["minimum_support"]["comparison_weeks"]
            and development.target_count.gt(0).sum() >= PROTOCOL["minimum_support"]["development_positive"],
            "Historia insuficiente para entrenar/evaluar este horizonte")
    dates = sorted(development.target_week.unique())
    boundaries = [int(len(dates)*fraction) for fraction in (.5, 2/3, 5/6, 1)]
    oof, folds, failures = [], [], {}
    for fold, (left, right) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        validation = development.loc[development.target_week.isin(dates[left:right])].copy()
        cutoff = min(validation.origin_week)
        train = development.loc[development.target_end.lt(cutoff)]
        require(train.target_week.nunique() >= 8 and validation.target_week.nunique() >= 2, "Pliegue cronológico insuficiente")
        tail = max(2., float(train.target_count.quantile(.9)))
        high_week = float(train.groupby("target_week").target_count.sum().quantile(.8))
        part = validation[["radio_id", "origin_week", "target_week", "target_count"]].copy()
        part["fold"] = fold
        part["high_count_threshold"] = tail
        part["high_week_threshold"] = high_week
        for name in COUNT_CANDIDATES:
            try:
                model = fit_count(name, train, horizon_weeks=horizon_weeks)
                part[name] = model.predict_frame(validation)
            except (ValueError, ConvergenceWarning) as error:
                failures[name] = type(error).__name__
        folds.append(dict(fold=fold, training_rows=len(train), validation_rows=len(validation),
            training_target_end=max(train.target_end).isoformat(), validation_first_origin=cutoff.isoformat(),
            validation_last_target=max(validation.target_week).isoformat(), tail_threshold=tail, high_week_threshold=high_week))
        oof.append(part)
    oof = pd.concat(oof, ignore_index=True)
    tail = max(2., float(development.target_count.quantile(.9)))
    high_week = float(development.groupby("target_week").target_count.sum().quantile(.8))
    # Cada máscara de colas se aprendió sólo con el entrenamiento de ese pliegue.
    available_names = [name for name in COUNT_CANDIDATES if name not in failures and name in oof and oof[name].notna().all()]
    metrics = development_metrics(oof, available_names, tail_threshold=tail, high_week_threshold=high_week)
    selected, scores = select_candidate(metrics, float(oof.target_count.mean()))
    fitted = fit_count(selected, development, horizon_weeks=horizon_weeks)
    predicted = comparison[["radio_id", "origin_week", "target_week", "target_count"]].copy()
    final_metrics = {}
    for name in dict.fromkeys([selected, "poisson_boosting", "lag_1_or_training_mean", "training_radio_mean"]):
        model = fitted if name == selected else fit_count(name, development, horizon_weeks=horizon_weeks)
        values = model.predict_frame(comparison)
        predicted[name] = values
        final_metrics[name] = summary_metrics(comparison, values, tail_threshold=tail, high_week_threshold=high_week)
    predicted["model"] = predicted[selected]
    # Predicciones para todos los radios de cada origen admisible de comparación.
    territory = frame.loc[frame.partition.eq("test") & frame.predictor_admissible].copy()
    territory["expected_count"] = fitted.predict_frame(territory)
    territory["available_features"] = territory[list(FEATURES)].notna().sum(axis=1)
    territory["missing_features"] = territory[list(FEATURES)].apply(lambda row: [name for name, value in row.items() if pd.isna(value)], axis=1)
    territory["predictor_status"] = np.where(territory.cases_lag_1.isna(), "partial_missing_recent_radio_counts", "recent_radio_counts_available")
    territory["horizon_weeks"] = horizon_weeks
    territory["model_version"] = VERSION
    territory["fit_cutoff"] = fitted.fit_cutoff
    territory["retrospective"] = True
    territory["quality_warning"] = "experimental_snapshot_filters_pending_masks_approximate_geocoding_not_infection_risk" if snapshot_scenario(inputs) else "conditional_positive_cells_only"
    report = dict(version=VERSION, horizon_weeks=horizon_weeks, selected=selected, selection_scores=scores,
        validation=metrics, folds=folds, candidate_failures=failures,
        comparison_previously_observed=final_metrics, comparison_is_independent_test=False,
        development_rows=len(development), development_weeks=int(development.target_week.nunique()),
        comparison_rows=len(comparison), comparison_weeks=int(comparison.target_week.nunique()),
        tail_threshold_from_development=tail, high_week_threshold_from_development=high_week,
        conditional_on_positive_cells=not snapshot_scenario(inputs),
        feature_order=list(FEATURES), model_fit_cutoff=fitted.fit_cutoff.isoformat(),
        model_parameters=str(fitted.estimator.get_params()) if fitted.estimator is not None else "training-only radio means and lag1 persistence",
        experiment_mode=inputs.experiment_mode, production_inference_authorized=False)
    return dict(fitted=fitted, frame=frame, development=development, comparison=comparison,
                oof=oof, predictions=predicted, territory=territory, report=report)


@dataclass
class PresenceModel:
    estimator: object
    calibrator: object
    fit_cutoff: object
    calibration_cutoff: object

    def score(self, frame, *, calibrated=True):
        with threadpool_limits(limits=1):
            values = self.estimator.predict_proba(matrix(frame))[:, 1]
            if self.calibrator is not None and calibrated:
                logits = np.log(np.clip(values, 1e-6, 1-1e-6) / (1-np.clip(values, 1e-6, 1-1e-6)))
                values = self.calibrator.predict_proba(logits.reshape(-1, 1))[:, 1]
        return values


def run_presence(count_result):
    development = count_result["development"]
    dates = sorted(development.target_week.unique())
    ncal = max(4, int(len(dates)*.2))
    calibration = development.loc[development.target_week.isin(dates[-ncal:])]
    base = development.loc[development.target_end.lt(min(calibration.origin_week))]
    require(base.target_count.gt(0).nunique() == 2 and calibration.target_count.gt(0).nunique() == 2,
            "Sin ambas clases en ajuste/calibración cronológicos")
    model = make_pipeline(SimpleImputer(strategy="constant", fill_value=0, add_indicator=True, keep_empty_features=True),
                          RandomForestClassifier(**dict(RF_PARAMETERS, random_state=SEED)))
    with threadpool_limits(limits=1):
        model.fit(matrix(base), base.target_count.gt(0).astype(int))
    fitted = PresenceModel(model, None, max(base.target_end), max(calibration.target_end))
    raw = fitted.score(calibration)
    logits = np.log(np.clip(raw, 1e-6, 1-1e-6) / (1-np.clip(raw, 1e-6, 1-1e-6)))
    with threadpool_limits(limits=1):
        calibrator = LogisticRegression(C=1.0, random_state=SEED).fit(logits.reshape(-1, 1), calibration.target_count.gt(0).astype(int))
    fitted.calibrator = calibrator
    comparison, territory = count_result["comparison"], count_result["territory"]
    frames, report = {}, {}
    for label, frame in (("calibration_in_sample_not_validation", calibration), ("comparison_previously_observed", comparison)):
        scores = {"raw_RF": fitted.score(frame, calibrated=False), "sigmoid_experimental_score": fitted.score(frame),
                  "training_prevalence": np.full(len(frame), base.target_count.gt(0).mean())}
        entry = {}
        rows = frame[["radio_id", "origin_week", "target_week", "target_count"]].copy()
        for name, values in scores.items():
            y = frame.target_count.gt(0).astype(int).to_numpy()
            entry[name] = dict(overall=classification_metrics(y, values), reliability=reliability_bins(y, values),
                weekly=[dict(target_week=str(target), **classification_metrics(group.target_count.gt(0).astype(int),
                    values[frame.target_week.eq(target).to_numpy()])) for target, group in frame.groupby("target_week")])
            rows[name] = values
        report[label], frames[label] = entry, rows
    territory["experimental_presence_score"] = fitted.score(territory)
    territory["presence_output_kind"] = "experimental_score_sigmoid_fit_on_development_not_accredited_probability"
    report.update(classifier="RandomForestClassifier", parameters=dict(RF_PARAMETERS, random_state=SEED),
        base_rows=len(base), calibration_rows=len(calibration), base_fit_cutoff=fitted.fit_cutoff.isoformat(),
        calibration_cutoff=fitted.calibration_cutoff.isoformat(), calibration_weeks=ncal,
        probability_calibrated_claim=False, infection_risk=False,
        explanation="Sigmoid fitted only on chronological development; labels depend on snapshot zero assumption, masked pending cells and retrospective availability. Comparison previously observed; reliability is descriptive, not accredited calibration.")
    return dict(fitted=fitted, report=report, predictions=frames, territory=territory)
