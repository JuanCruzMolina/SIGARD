"""Iteración 8.2: Random Forest del cambio logarítmico departamental."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sigard_ml.evaluation.department_temporal_variants import regression_metrics, run as run_previous, walk_forward as previous_walk_forward
from sigard_ml.models.random_forest import build_random_forest


def add_change_features(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    current = result["cases_current_week"].astype(float)
    lag = result["cases_lag_1"].astype(float)
    result["log_cases_current"] = np.log1p(current)
    result["growth_ratio"] = (current + 1.0) / (lag + 1.0)
    result["log_growth"] = np.log1p(current) - np.log1p(lag)
    result["relative_trend_1"] = (current - lag) / (lag + 1.0)
    result["target_log_delta"] = np.log1p(result["target_cases_next_week"].astype(float)) - np.log1p(current)
    return result


def reconstruct_cases(current: np.ndarray, predicted_delta: np.ndarray) -> np.ndarray:
    predicted_log_next = np.log1p(current.astype(float)) + predicted_delta.astype(float)
    # Restricción de dominio fija: log1p(casos) no puede ser menor que cero.
    predicted = np.expm1(np.maximum(predicted_log_next, 0.0))
    if not np.isfinite(predicted).all() or (predicted < 0).any():
        raise ValueError("La reconstrucción produjo predicciones no finitas o negativas; no se aplica clipping")
    return predicted


def delta_walk_forward(data: pd.DataFrame, features: list[str], parameters: dict[str, Any], start: int, stop: int) -> np.ndarray:
    predictions = []
    for index in range(start, stop):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = build_random_forest(parameters)
        model.fit(train[features], train["target_log_delta"])
        delta = model.predict(test[features])
        predictions.append(float(reconstruct_cases(test.cases_current_week.to_numpy(float), delta)[0]))
    return np.asarray(predictions)


def _select(data: pd.DataFrame, features: list[str], config: dict[str, Any], start: int, stop: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actual = data.iloc[start:stop].target_cases_next_week.to_numpy(float)
    trials = []
    for candidate in config["search"]:
        parameters = {**candidate, **config["model_defaults"]}
        prediction = delta_walk_forward(data, features, parameters, start, stop)
        trials.append({"parameters": candidate, "metrics": regression_metrics(actual, prediction)})
    trials.sort(key=lambda x: (x["metrics"]["mae"], x["metrics"]["rmse"], x["metrics"]["median_absolute_error"], abs(x["metrics"]["bias"]), json.dumps(x["parameters"], sort_keys=True)))
    return {**trials[0]["parameters"], **config["model_defaults"]}, trials


def _direction(current: np.ndarray, following: np.ndarray) -> np.ndarray:
    return np.sign(following - current)


def diagnostic_metrics(current: np.ndarray, actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    low = actual <= 1
    descending = actual < current
    return {"direction_accuracy": float(np.mean(_direction(current, actual) == _direction(current, predicted))),
            "descent_mae": float(np.mean(np.abs(predicted[descending] - actual[descending]))) if descending.any() else None,
            "mean_overestimation": float(np.mean(predicted - actual)),
            "low_values_mae_target_le_1": float(np.mean(np.abs(predicted[low] - actual[low]))) if low.any() else None,
            "low_values_mean_prediction_target_le_1": float(np.mean(predicted[low])) if low.any() else None}


def run(config: dict[str, Any], root: Path) -> dict[str, Any]:
    data = add_change_features(pd.read_parquet(root / config["input_dataset"]).sort_values("cutoff_week").reset_index(drop=True))
    previous_config = json.loads((root / config["previous_variants_config"]).read_text(encoding="utf-8"))
    previous = run_previous(previous_config, root)
    frozen = previous["frozen_evaluation"]
    if frozen["development_weeks_sha256"] != config["expected_hashes"]["development"] or frozen["holdout_weeks_sha256"] != config["expected_hashes"]["holdout"]:
        raise ValueError("Los splits no coinciden con Iteración 8.1")
    minimum, holdout = config["evaluation"]["minimum_training_weeks"], config["evaluation"]["holdout_weeks"]
    stop = len(data) - holdout
    minimal, climate = config["minimal_features"], config["minimal_climate_features"]
    minimal_params, minimal_trials = _select(data, minimal, config, minimum, stop)
    climate_params, climate_trials = _select(data, climate, config, minimum, stop)
    dev_actual = data.iloc[minimum:stop].target_cases_next_week.to_numpy(float)
    development = {
        "rf_reduced": previous["development_metrics"]["rf_reduced"],
        "rf_reduced_log_target": previous["development_metrics"]["rf_reduced_log_target"],
        "rf_minimal_log_delta": minimal_trials[0]["metrics"],
        "rf_minimal_climate_log_delta": climate_trials[0]["metrics"],
    }
    final = data.iloc[stop:]
    actual, current = final.target_cases_next_week.to_numpy(float), final.cases_current_week.to_numpy(float)
    reduced_features = previous_config["reduced_features"]
    previous_params = previous["chosen_hyperparameters"]
    predictions = {
        "persistence_baseline": current,
        "rf_reduced": previous_walk_forward(data, reduced_features, previous_params["rf_reduced"], stop, len(data), False),
        "rf_reduced_log_target": previous_walk_forward(data, reduced_features, previous_params["rf_reduced_log_target"], stop, len(data), True),
        "rf_minimal_log_delta": delta_walk_forward(data, minimal, minimal_params, stop, len(data)),
        "rf_minimal_climate_log_delta": delta_walk_forward(data, climate, climate_params, stop, len(data)),
    }
    metrics = {name: regression_metrics(actual, pred) for name, pred in predictions.items()}
    directions = {name: diagnostic_metrics(current, actual, pred) for name, pred in predictions.items()}
    weekly = []
    for position, (_, row) in enumerate(final.iterrows()):
        record = {"cutoff_date": row.cutoff_date.date().isoformat(), "target_week_start": row.target_week_start.date().isoformat(), "target_week_end": row.target_week_end.date().isoformat(), "official_cases": float(actual[position])}
        for name, pred in predictions.items():
            record[f"{name}_prediction"] = float(pred[position]); record[f"{name}_absolute_error"] = float(abs(pred[position] - actual[position]))
        weekly.append(record)
    rf_names = ["rf_reduced", "rf_reduced_log_target", "rf_minimal_log_delta", "rf_minimal_climate_log_delta"]
    winner = min(rf_names, key=lambda name: (development[name]["mae"], development[name]["rmse"], development[name]["median_absolute_error"], abs(development[name]["bias"])))
    baseline_mae, winner_mae = metrics["persistence_baseline"]["mae"], metrics[winner]["mae"]
    ratio, difference = winner_mae / baseline_mae, winner_mae - baseline_mae
    classification = "A. RF supera baseline" if metrics[winner]["mae"] < baseline_mae and metrics[winner]["rmse"] < metrics["persistence_baseline"]["rmse"] else "B. RF queda comparable" if ratio <= 1.10 else "C. RF sigue peor"
    return {
        "pipeline": config["pipeline"], "dataset": {"official_supported_weeks": 41, "modeling_rows": len(data), "source": config["input_dataset"], "new_data_added": False},
        "splits": frozen, "feature_sets": {"rf_reduced": reduced_features, "rf_reduced_log_target": reduced_features, "rf_minimal_log_delta": minimal, "rf_minimal_climate_log_delta": climate},
        "derived_feature_definitions": {"log_cases_current": "log1p(cases_current_week)", "growth_ratio": "(cases_current_week + 1) / (cases_lag_1 + 1)", "log_growth": "log1p(cases_current_week) - log1p(cases_lag_1)", "relative_trend_1": "(cases_current_week - cases_lag_1) / (cases_lag_1 + 1)"},
        "target_definitions": {"official_target": "target_cases_next_week", "delta_target": "log1p(target_cases_next_week) - log1p(cases_current_week)", "reconstruction": "expm1(max(0, log1p(cases_current_week) + predicted_log_delta))", "nonnegative_policy": "Restricción fija del dominio log1p(casos)>=0, aplicada por igual en development y holdout; no depende del holdout ni calibra magnitudes."},
        "development_metrics": development, "development_search": {"rf_minimal_log_delta": minimal_trials, "rf_minimal_climate_log_delta": climate_trials},
        "selected_hyperparameters": {"rf_reduced": previous_params["rf_reduced"], "rf_reduced_log_target": previous_params["rf_reduced_log_target"], "rf_minimal_log_delta": minimal_params, "rf_minimal_climate_log_delta": climate_params},
        "holdout_metrics": metrics, "weekly_predictions": weekly, "direction_analysis": directions,
        "best_rf_by_development": winner, "comparison_vs_baseline": {"classification": classification, "mae_ratio_rf_to_baseline": float(ratio), "mae_absolute_difference": float(difference), "approved_as_primary_mvp_predictor": classification == "A. RF supera baseline"},
        "limitations": ["Sólo hay 41 semanas oficiales y 32 filas modelables.", "El holdout contiene seis semanas y la evaluación es exploratoria.", "Las discontinuidades y missing_record se conservan sin imputación.", "La dirección correcta no sustituye las métricas de magnitud.", "El modelo temporal no valida distribución territorial."]
    }


def write_report(report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    path = root / config["output"]
    if path.exists() and not overwrite: raise FileExistsError(f"No se sobrescribe {path}")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = json.loads(args.config.read_text(encoding="utf-8")); root = args.repo_root.resolve(); write_report(run(config, root), config, root, args.overwrite)


if __name__ == "__main__": main()
