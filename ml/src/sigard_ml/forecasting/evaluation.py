"""Métricas pareadas; totales de Capital sólo con todos sus radios elegibles."""

import math

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, mean_poisson_deviance

from sigard_ml.forecasting.contracts import nonnegative, require


def count_metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    require(actual.shape == predicted.shape and actual.ndim == 1 and len(actual) > 0, "Métrica sin observaciones pareadas")
    nonnegative(pd.Series(actual), integer=True)
    nonnegative(pd.Series(predicted))
    require(np.isfinite(actual).all() and np.isfinite(predicted).all(), "Predicción o etiqueta no finita")
    error = predicted - actual
    positive = actual > 0
    # Desviancia indefinida con mu=0: se informa null, sin epsilon oculto.
    return {"n": len(actual), "mae": float(np.abs(error).mean()),
            "rmse": float(math.sqrt(np.mean(error ** 2))), "mean_bias": float(error.mean()),
            "mae_positive": float(np.abs(error[positive]).mean()) if positive.any() else None,
            "zero_fraction": float(np.mean(actual == 0)),
            "poisson_deviance": float(mean_poisson_deviance(actual, predicted)) if (predicted > 0).all() else None}


def evaluate(frame, predicted, radios, *, observed_only=False):
    require(len(frame) == len(predicted) and not frame.duplicated(["radio_id", "target_week"]).any(), "Claves de evaluación inválidas")
    require(set(frame.radio_id) <= set(radios), "Evaluación territorial ajena")
    result = frame[["radio_id", "target_week", "target_count"]].copy()
    result["predicted_count"] = np.asarray(predicted)
    overall = count_metrics(result.target_count, result.predicted_count)
    per_radio = {radio: count_metrics(group.target_count, group.predicted_count)
                 for radio, group in result.groupby("radio_id", sort=True)}
    capital = []
    for target, group in result.groupby("target_week", sort=True):
        complete = not observed_only and set(group.radio_id) == set(radios)
        capital.append({"target_week": target.isoformat(), "eligible_radios": len(group), "complete": complete,
                        "actual_total": float(group.target_count.sum()) if complete else None,
                        "predicted_total": float(group.predicted_count.sum()) if complete else None,
                        "eligible_subset_actual": float(group.target_count.sum()),
                        "eligible_subset_predicted": float(group.predicted_count.sum())})
    complete_weeks = [row for row in capital if row["complete"]]
    capital_metrics = count_metrics([row["actual_total"] for row in complete_weeks],
                                    [row["predicted_total"] for row in complete_weeks]) if complete_weeks else None
    return {"territorial": overall, "per_radio": per_radio,
            "macro_radio_mae": float(np.mean([row["mae"] for row in per_radio.values()])),
            "capital": capital_metrics, "weekly": capital}


def poisson_presence_diagnostic(actual, means):
    """P(Y>=1)=1-exp(-mu) sólo como hipótesis Poisson, nunca calibración.

    La pérdida Poisson de una media no acredita la distribución de los conteos.
    Ceros excesivos/sobredispersión y calibración requieren estudio independiente.
    """
    count_metrics(actual, means)
    probability = -np.expm1(-np.asarray(means, dtype=float))
    observed = np.asarray(actual) > 0
    return {"method": "unverified_poisson_assumption", "brier": float(brier_score_loss(observed, probability)),
            "mean_probability": float(probability.mean()), "observed_presence": float(observed.mean()),
            "probabilities_accredited": False}
