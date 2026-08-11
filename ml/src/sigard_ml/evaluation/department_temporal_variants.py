"""Iteración 8.1: variantes RF departamentales sobre evaluación congelada."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sigard_ml.models.random_forest import build_random_forest


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    positive = actual > 0
    return {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "median_absolute_error": float(np.median(np.abs(error))), "bias": float(np.mean(error)),
            "mae_target_gt_0": float(np.mean(np.abs(error[positive]))) if positive.any() else None,
            "mean_weekly_absolute_error": float(np.mean(np.abs(error)))}


def transform_target(values: np.ndarray, use_log_target: bool) -> np.ndarray:
    return np.log1p(values) if use_log_target else values


def inverse_target(values: np.ndarray, use_log_target: bool) -> np.ndarray:
    result = np.expm1(values) if use_log_target else values
    if not np.isfinite(result).all() or (result < 0).any():
        raise ValueError("Predicciones no finitas o negativas; no se aplica clipping")
    return result


def walk_forward(data: pd.DataFrame, features: list[str], parameters: dict[str, Any], start: int, stop: int, use_log_target: bool) -> np.ndarray:
    predictions = []
    for index in range(start, stop):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = build_random_forest(parameters)
        y = transform_target(train.target_cases_next_week.to_numpy(float), use_log_target)
        model.fit(train[features], y)
        predictions.append(float(inverse_target(model.predict(test[features]), use_log_target)[0]))
    return np.asarray(predictions)


def _params(candidate: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    return {**candidate, **defaults}


def _select(data: pd.DataFrame, features: list[str], config: dict[str, Any], start: int, stop: int, log_target: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actual = data.iloc[start:stop].target_cases_next_week.to_numpy(float)
    trials = []
    for candidate in config["search"]:
        prediction = walk_forward(data, features, _params(candidate, config["model_defaults"]), start, stop, log_target)
        score = regression_metrics(actual, prediction)
        trials.append({"parameters": candidate, "metrics": score})
    trials.sort(key=lambda x: (x["metrics"]["mae"], x["metrics"]["rmse"], abs(x["metrics"]["bias"]), x["metrics"]["median_absolute_error"], json.dumps(x["parameters"], sort_keys=True)))
    return _params(trials[0]["parameters"], config["model_defaults"]), trials


def _date_hash(values: pd.Series) -> str:
    payload = "\n".join(pd.to_datetime(values).dt.strftime("%Y-%m-%d")) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def missing_record_audit() -> dict[str, Any]:
    return {
        "row_semantics": "Cada fila publicada es un estrato departamento-semana-grupo etario con cantidad positiva de casos de dengue.",
        "explicit_zero_rows_in_sources": 0,
        "complete_jurisdiction_week_enumeration": False,
        "absence_meaning": "desconocido; la fuente no declara que una combinación ausente equivalga a cero",
        "evidence": ["Ninguno de los dos CSV contiene filas con cantidad=0.", "El número de departamentos presentes cambia entre semanas, por lo que no hay un universo completo enumerado.", "El pipeline agrega sólo estratos publicados y conserva las combinaciones ausentes como nulas."],
        "conclusion": "No existe evidencia suficiente para reclasificar missing_record como explicit_zero.",
        "states_changed": 0, "scenario_executed": "SCENARIO ORIGINAL", "verified_zeros_scenario_executed": False,
    }


def run(config: dict[str, Any], root: Path) -> dict[str, Any]:
    data = pd.read_parquet(root / config["input_dataset"]).sort_values("cutoff_week").reset_index(drop=True)
    full, reduced = config["full_features"], config["reduced_features"]
    if reduced != ["cases_current_week", "cases_lag_1", "cases_rolling_mean_2", "cases_trend_1", "temperature_mean", "relative_humidity_mean", "precipitation_sum", "week_sin", "week_cos"]:
        raise ValueError("El feature set reducido no coincide con el contrato de Iteración 8.1")
    if data[full].isna().any().any(): raise ValueError("Hay nulos en features congeladas")
    minimum, holdout = config["evaluation"]["minimum_training_weeks"], config["evaluation"]["holdout_weeks"]
    holdout_start = len(data) - holdout
    dev_slice, final_slice = data.iloc[minimum:holdout_start], data.iloc[holdout_start:]
    full_params = config["rf_full_parameters"]
    full_dev_pred = walk_forward(data, full, full_params, minimum, holdout_start, False)
    reduced_params, reduced_trials = _select(data, reduced, config, minimum, holdout_start, False)
    log_params, log_trials = _select(data, reduced, config, minimum, holdout_start, True)
    development = {
        "rf_full": regression_metrics(dev_slice.target_cases_next_week.to_numpy(float), full_dev_pred),
        "rf_reduced": reduced_trials[0]["metrics"], "rf_reduced_log_target": log_trials[0]["metrics"],
    }
    frozen = {"minimum_training_weeks": minimum, "development_rows": len(dev_slice), "holdout_rows": len(final_slice),
              "development_target_weeks": pd.to_datetime(dev_slice.target_week).dt.strftime("%Y-%m-%d").tolist(),
              "holdout_target_weeks": pd.to_datetime(final_slice.target_week).dt.strftime("%Y-%m-%d").tolist(),
              "development_weeks_sha256": _date_hash(dev_slice.target_week), "holdout_weeks_sha256": _date_hash(final_slice.target_week)}
    predictions = {
        "persistence_baseline": final_slice.cases_current_week.to_numpy(float),
        "rf_full": walk_forward(data, full, full_params, holdout_start, len(data), False),
        "rf_reduced": walk_forward(data, reduced, reduced_params, holdout_start, len(data), False),
        "rf_reduced_log_target": walk_forward(data, reduced, log_params, holdout_start, len(data), True),
    }
    actual = final_slice.target_cases_next_week.to_numpy(float)
    holdout_metrics = {name: regression_metrics(actual, value) for name, value in predictions.items()}
    weekly = []
    for pos, (_, row) in enumerate(final_slice.iterrows()):
        record = {"cutoff_date": row.cutoff_date.date().isoformat(), "target_week_start": row.target_week_start.date().isoformat(), "target_week_end": row.target_week_end.date().isoformat(), "official_cases": float(actual[pos])}
        for name, values in predictions.items():
            short = {"persistence_baseline": "persistence", "rf_full": "rf_full", "rf_reduced": "rf_reduced", "rf_reduced_log_target": "rf_log"}[name]
            record[f"{short}_prediction"] = float(values[pos]); record[f"{short}_absolute_error"] = float(abs(values[pos] - actual[pos]))
            record[f"{short}_percentage_error"] = None if actual[pos] == 0 else float(abs(values[pos] - actual[pos]) / actual[pos] * 100)
        weekly.append(record)
    rf_names = ["rf_full", "rf_reduced", "rf_reduced_log_target"]
    winner = min(rf_names, key=lambda name: (development[name]["mae"], development[name]["rmse"], abs(development[name]["bias"]), development[name]["median_absolute_error"]))
    baseline, best_holdout = holdout_metrics["persistence_baseline"], holdout_metrics[winner]
    all_better = best_holdout["mae"] < baseline["mae"] and best_holdout["rmse"] < baseline["rmse"]
    comparable = best_holdout["mae"] <= baseline["mae"] * 1.10 and best_holdout["rmse"] <= baseline["rmse"] * 1.10
    classification = "A. RF supera claramente baseline" if all_better else "B. RF es comparable al baseline" if comparable else "C. RF sigue por debajo del baseline"
    mean_bias = {name: float(np.mean(values - actual)) for name, values in predictions.items()}
    best_fall = min(predictions, key=lambda name: holdout_metrics[name]["mae"])
    greatest_inertia = max(predictions, key=lambda name: mean_bias[name])
    return {
        "pipeline": config["pipeline"], "scenario": "SCENARIO ORIGINAL",
        "dataset_summary": {"official_supported_weeks": 41, "modeling_rows": len(data), "target_is_official": True, "unit": "departamento Capital - semana epidemiológica"},
        "missing_record_audit": missing_record_audit(), "frozen_evaluation": frozen,
        "feature_sets": {"rf_full": full, "rf_reduced": reduced, "rf_reduced_log_target": reduced},
        "development_metrics": development, "development_search": {"rf_reduced": reduced_trials, "rf_reduced_log_target": log_trials},
        "chosen_hyperparameters": {"rf_full": full_params, "rf_reduced": reduced_params, "rf_reduced_log_target": log_params},
        "holdout_metrics": holdout_metrics, "weekly_predictions": weekly, "winner_among_rf_variants": winner,
        "comparison_vs_baseline": {"classification": classification, "best_rf": winner, "best_rf_holdout_metrics": best_holdout, "baseline_holdout_metrics": baseline, "approved_as_primary_mvp_predictor": all_better},
        "epidemic_decline_analysis": {"official_sequence": actual.tolist(), "best_tracks_decline_by_mae": best_fall, "greatest_positive_inertia": greatest_inertia, "mean_bias": mean_bias, "interpretation": "El mayor bias positivo identifica la mayor inercia/sobreestimación durante el descenso."},
        "error_relative_policy": "No es métrica principal; es null si official_cases=0 y puede ser engañoso para valores iguales o cercanos a 1.",
        "limitations": ["Sólo existen 41 semanas oficiales y 32 filas modelables.", "La serie presenta discontinuidades.", "missing_record no equivale a cero.", "El holdout contiene seis semanas y la evaluación es exploratoria.", "El modelo temporal no valida distribución territorial."]
    }


def write_report(report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    path = root / config["output"]
    if path.exists() and not overwrite: raise FileExistsError(f"No se sobrescribe {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = json.loads(args.config.read_text(encoding="utf-8")); root = args.repo_root.resolve(); write_report(run(config, root), config, root, args.overwrite)


if __name__ == "__main__": main()
