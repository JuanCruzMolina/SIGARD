"""Separate experimental A/B dataset and fixed temporal evaluation helpers.

No source ingestion, permission inference, file IO, UI registration or changes to
the original 2024 scenario. Callers must authorize and verify their derivatives.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import KEYS, calendar_predictors
from sigard_ml.official.spatial_ml.research_training import classification_metrics
from sigard_ml.official.spatial_ml.temporal_history import lookup

VERSION = "sigard-ab-historical-experimental-1"
LAGS = [f"local_presencia_exp_rezago_{lag}" for lag in range(1, 5)]
MISSING = [name + "_missing" for name in LAGS]
FEATURES = {"A": BASE, "B": BASE + LAGS + MISSING}
THRESHOLD = 0.5


def prepare_ab(labels, predictors):
    """Reuse labels unchanged; construct binary t-k history by exact week keys."""
    for frame in (labels, predictors):
        if frame.duplicated(KEYS).any() or frame[KEYS].isna().any().any():
            raise ValueError("Duplicate or missing radio-origin key")
    if list(predictors.columns) != KEYS + BASE:
        raise ValueError("A feature schema changed")
    if not labels.objetivo_semana_siguiente.dropna().isin([0, 1]).all():
        raise ValueError("Presence labels must be binary or unknown")
    if not labels.fecha_inicio_semana_objetivo.eq(labels.fecha_inicio_semana.map(lambda d: d + timedelta(weeks=1))).all():
        raise ValueError("Target must be exact t+1")
    positive = labels.objetivo_semana_siguiente.eq(1).fillna(False)
    negative = labels.objetivo_semana_siguiente.eq(0).fillna(False)
    if not labels.loc[positive, "tipo_etiqueta"].eq("positivo_provisional").all():
        raise ValueError("Unsupported positive label")
    if (not labels.loc[negative, "tipo_etiqueta"].eq("cero_asumido_experimental").all()
            or not labels.loc[negative, "en_intervalo_autorizado"].eq(True).all()
            or not labels.loc[negative, "pendientes_semana_objetivo"].eq(0).all()
            or not labels.loc[negative, "semana_objetivo_parcial"].eq(False).all()):
        raise ValueError("Negative without existing experimental coverage")
    if not np.isfinite(predictors[BASE].to_numpy(float)).all():
        raise ValueError("Mandatory A predictors missing or infinite")
    if predictors.groupby("radio_censal")[BASE[:4]].nunique(dropna=False).ne(1).any().any():
        raise ValueError("Static context varies over time")
    calendar = predictors[KEYS].copy()
    year_week = calendar.fecha_inicio_semana.map(DEFAULT_CALENDAR.date_week)
    calendar["anio_epidemiologico"] = year_week.map(lambda p: p[0])
    calendar["semana_epidemiologica"] = year_week.map(lambda p: p[1])
    expected = calendar_predictors(calendar)
    for name in BASE[4:]:
        if not np.allclose(predictors[name].to_numpy(float), expected[name].to_numpy(float), rtol=0, atol=1e-12):
            raise ValueError("Seasonality differs from existing origin calendar")
    frame = labels.merge(predictors, on=KEYS, how="outer", validate="one_to_one", indicator=True)
    if not frame._merge.eq("both").all():
        raise ValueError("Labels and predictors cover different grids")
    frame = frame.drop(columns="_merge").sort_values(KEYS).reset_index(drop=True)
    source = labels[["radio_censal", "fecha_inicio_semana_objetivo", "objetivo_semana_siguiente"]].rename(
        columns={"fecha_inicio_semana_objetivo": "fecha_inicio_semana"})
    if source.duplicated(KEYS).any():
        raise ValueError("Duplicate source week")
    source_values = pd.Series(source.objetivo_semana_siguiente.array, index=pd.MultiIndex.from_frame(source[KEYS]))
    for lag, name in enumerate(LAGS, 1):
        frame[name] = lookup(source_values, frame[KEYS], lag)
        frame[name + "_missing"] = frame[name].isna().astype("int8")
    frame["target_end"] = frame.fecha_inicio_semana_objetivo.map(lambda d: d + timedelta(days=6))
    frame["target_year"] = frame.fecha_inicio_semana_objetivo.map(lambda d: DEFAULT_CALENDAR.date_week(d)[0])
    frame["experimental_fit_eligible"] = frame.objetivo_semana_siguiente.notna()
    return frame


def ab_matrix(frame, model):
    matrix = frame[FEATURES[model]].astype("float64")
    if np.isinf(matrix.to_numpy()).any() or matrix[BASE].isna().any().any():
        raise ValueError("Invalid predictor matrix")
    if model == "B":
        if not matrix[MISSING].eq(matrix[LAGS].isna().to_numpy()).all().all():
            raise ValueError("Missingness indicators changed")
    return matrix


def fit_ab(frame, model):
    if frame.objetivo_semana_siguiente.isna().any() or set(frame.objetivo_semana_siguiente.unique()) != {0, 1}:
        raise ValueError("Fit requires known labels and both classes")
    matrix = ab_matrix(frame, model)
    estimator = RandomForestClassifier(**RF_PARAMETERS)
    estimator.fit(matrix, frame.objetivo_semana_siguiente.to_numpy(int))
    return estimator


def positive_score(estimator, matrix):
    index = list(estimator.classes_).index(1)
    values = estimator.predict_proba(matrix)[:, index]
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("Invalid score")
    return values


def prior_score(train, evaluation):
    estimator = DummyClassifier(strategy="prior", random_state=RF_PARAMETERS["random_state"])
    estimator.fit(np.zeros((len(train), 1)), train.objetivo_semana_siguiente.to_numpy(int))
    return positive_score(estimator, np.zeros((len(evaluation), 1)))


def temporal_split(frame, first_target, last_target, *, target="fecha_inicio_semana_objetivo", origin="fecha_inicio_semana", outcome="objetivo_semana_siguiente"):
    """Purge all training outcomes not closed before the earliest evaluated origin."""
    evaluation = frame.loc[frame[target].between(first_target, last_target) & frame[outcome].notna()].copy()
    if evaluation.empty:
        return frame.iloc[:0].copy(), evaluation
    train = frame.loc[frame.target_end.lt(min(evaluation[origin])) & frame[outcome].notna()].copy()
    if len(train) and not max(train.target_end) < min(evaluation[origin]):
        raise ValueError("Temporal leakage")
    return train, evaluation


def binary_metrics(frame, score):
    result = classification_metrics(frame.objetivo_semana_siguiente.to_numpy(int), np.asarray(score, dtype=float), THRESHOLD)
    result["origin_weeks"] = int(frame.fecha_inicio_semana.nunique())
    result["independent_evaluation"] = False
    if not result["ranking_metrics_defined"]:
        result["single_class_warning"] = "ROC/AP undefined; recall/precision do not establish discrimination"
    return result
