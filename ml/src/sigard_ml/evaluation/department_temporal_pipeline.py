"""Random Forest temporal departamental con walk-forward y holdout final."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sigard_ml.features.department_temporal import build_department_temporal_dataset
from sigard_ml.models.persistence import PersistenceBaseline
from sigard_ml.models.random_forest import build_random_forest


def metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float | None]:
    error = predicted.astype(float) - actual.astype(float)
    positive = actual.gt(0)
    return {"mae": float(error.abs().mean()), "rmse": float(math.sqrt(error.pow(2).mean())),
            "median_absolute_error": float(error.abs().median()), "bias": float(error.mean()),
            "mae_target_gt_0": float(error[positive].abs().mean()) if positive.any() else None,
            "mean_weekly_absolute_error": float(error.abs().mean())}


def _parameters(candidate: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    return {**candidate, **defaults}


def walk_forward(data: pd.DataFrame, features: list[str], parameters: dict[str, Any], start: int, stop: int, stage: str) -> pd.DataFrame:
    rows = []
    for index in range(start, stop):
        train, test = data.iloc[:index], data.iloc[[index]]
        model = build_random_forest(parameters)
        model.fit(train[features], train["target_cases_next_week"])
        prediction = float(model.predict(test[features])[0])
        if prediction < 0:
            raise ValueError("RandomForest produjo una predicción negativa; no se truncó silenciosamente")
        actual = float(test.iloc[0]["target_cases_next_week"])
        baseline = float(PersistenceBaseline("cases_current_week").predict(test)[test.index[0]])
        row = test.iloc[0][["cutoff_date", "target_week_start", "target_week_end"]].to_dict()
        row.update({"evaluation_stage": stage, "official_cases": actual, "predicted_cases": prediction,
                    "predicted_cases_rounded": int(round(prediction)), "absolute_error": abs(prediction - actual),
                    "percentage_error": None if actual == 0 else abs(prediction - actual) / actual * 100,
                    "baseline_predicted_cases": baseline, "baseline_absolute_error": abs(baseline - actual)})
        rows.append(row)
    return pd.DataFrame(rows)


def run(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], Any]:
    source = pd.read_parquet(root / config["input"])
    features = config["features"]
    dataset, quality = build_department_temporal_dataset(source, features)
    minimum = int(config["evaluation"]["minimum_training_weeks"])
    holdout = int(config["evaluation"]["final_holdout_weeks"])
    holdout_start = len(dataset) - holdout
    if holdout_start <= minimum:
        raise ValueError("No hay tamaño suficiente para development y holdout")
    trials = []
    for candidate in config["search"]:
        params = _parameters(candidate, config["model_defaults"])
        predictions = walk_forward(dataset, features, params, minimum, holdout_start, "development")
        score = metrics(dataset.iloc[minimum:holdout_start].target_cases_next_week.reset_index(drop=True), predictions.predicted_cases)
        trials.append((score["mae"], score["rmse"], -candidate["min_samples_leaf"], json.dumps(candidate, sort_keys=True), candidate, score))
    selected = min(trials)
    selected_candidate, development_metrics = selected[4], selected[5]
    final_parameters = _parameters(selected_candidate, config["model_defaults"])
    development = walk_forward(dataset, features, final_parameters, minimum, holdout_start, "development")
    final = walk_forward(dataset, features, final_parameters, holdout_start, len(dataset), "final_holdout")
    actual = final.official_cases
    rf_metrics = metrics(actual, final.predicted_cases)
    baseline_metrics = metrics(actual, final.baseline_predicted_cases)
    final_model = build_random_forest(final_parameters).fit(dataset[features], dataset.target_cases_next_week)
    importance = sorted(({"feature": feature, "importance": float(value)} for feature, value in zip(features, final_model.feature_importances_)), key=lambda x: (-x["importance"], x["feature"]))
    rf_low = final.loc[final.official_cases <= final.official_cases.median(), "predicted_cases"] - final.loc[final.official_cases <= final.official_cases.median(), "official_cases"]
    summary = {
        "pipeline": config["pipeline"], "model": "RandomForestRegressor", "model_variant": selected_candidate,
        "random_state": config["model_defaults"]["random_state"], "features": features,
        "observations": {"official_supported_weeks": quality["official_supported_weeks"], "modeling_rows": len(dataset), "development_predictions": len(development), "final_holdout_predictions": len(final), "real_observations_used_for_final_fit": len(dataset)},
        "train_backtest_strategy": {"type": "expanding_window_walk_forward", "minimum_training_weeks": minimum, "selection_scope": "development only", "final_holdout_weeks": holdout, "assessment": "exploratory MVP due to limited sample and discontinuous official series"},
        "metrics": rf_metrics, "baseline_metrics": baseline_metrics,
        "comparison": {"rf_lower_mae": rf_metrics["mae"] < baseline_metrics["mae"], "rf_lower_rmse": rf_metrics["rmse"] < baseline_metrics["rmse"], "rf_lower_mean_weekly_error": rf_metrics["mean_weekly_absolute_error"] < baseline_metrics["mean_weekly_absolute_error"], "rf_bias": rf_metrics["bias"], "systematic_bias_direction": "overestimation" if rf_metrics["bias"] > 0 else "underestimation" if rf_metrics["bias"] < 0 else "none", "low_incidence_mean_bias": float(rf_low.mean())},
        "development_selection_metrics": development_metrics,
        "search_results": [{"variant": item[4], "metrics": item[5]} for item in sorted(trials)],
        "feature_importances": importance,
        "feature_importance_warning": "Las importancias del Random Forest no implican causalidad epidemiológica.",
        "prediction_policy": "Se valida prediction >= 0; no se aplica truncamiento silencioso.",
        "limitations": ["Número limitado de semanas oficiales disponibles.", "La serie oficial presenta discontinuidades.", "Los registros ausentes no pueden interpretarse como cero.", "La evaluación es exploratoria por el tamaño muestral.", "El modelo temporal no valida distribución territorial."],
    }
    backtest = {"model": "RandomForestRegressor", "baseline_role": "Referencia exclusiva para evaluar persistencia; no es modelo candidato.", "percentage_error_rule": "Es null cuando official_cases = 0 y no es métrica principal.", "development": _records(development), "final_holdout": _records(final)}
    return dataset, quality, backtest, summary, final_model


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    formatted = frame.copy()
    for column in ["cutoff_date", "target_week_start", "target_week_end"]:
        formatted[column] = pd.to_datetime(formatted[column]).dt.strftime("%Y-%m-%d")
    return formatted.replace({np.nan: None}).to_dict("records")


def write_outputs(result: tuple, config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    dataset, quality, backtest, summary, model = result
    paths = {key: root / value for key, value in config["outputs"].items()}
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben artefactos: {existing}")
    for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(paths["dataset"], index=False, engine="pyarrow", compression="snappy")
    for key, value in [("quality_report", quality), ("backtest", backtest), ("summary", summary)]:
        paths[key].write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    joblib.dump({"model": model, "features": config["features"], "parameters": {**summary["model_variant"], **config["model_defaults"]}, "data_version": config["data_version"]}, paths["artifact"], compress=3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = json.loads(args.config.read_text(encoding="utf-8")); root = args.repo_root.resolve()
    result = run(config, root)
    print(f"Observaciones temporales válidas después de lags: {len(result[0])}")
    write_outputs(result, config, root, args.overwrite)


if __name__ == "__main__": main()
