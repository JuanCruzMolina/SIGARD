"""Etapa 6.1: ajuste controlado de RandomForestRegressor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sigard_ml.evaluation.pipeline import load_config, resolve_path
from sigard_ml.evaluation.random_forest_pipeline import _prediction_frame, _validate_inputs
from sigard_ml.evaluation.temporal import evaluate_predictions
from sigard_ml.models.random_forest import build_random_forest


def transform_target(values: pd.Series, method: str) -> np.ndarray:
    values = values.to_numpy(dtype="float64")
    if method == "identity":
        return values
    if method == "log1p":
        return np.log1p(values)
    raise ValueError(f"Transformación de target desconocida: {method}")


def inverse_target(values: np.ndarray, method: str) -> np.ndarray:
    if method == "identity":
        return np.asarray(values, dtype="float64")
    if method == "log1p":
        return np.expm1(values)
    raise ValueError(f"Transformación de target desconocida: {method}")


def _metrics(predictions: pd.DataFrame, threshold: float) -> tuple[dict[str, float], list[dict[str, Any]]]:
    metrics, weekly = evaluate_predictions(predictions)
    metrics.pop("prediction_zero_percentage")
    metrics["prediction_le_0_5_percentage"] = float(predictions.predicted_cases.le(threshold).mean() * 100)
    metrics["mean_weekly_absolute_total_error"] = float(weekly.absolute_total_error.mean())
    weekly["signed_total_error"] = weekly.predicted_total_cases - weekly.actual_total_cases
    records = weekly.assign(target_week_start_date=weekly.target_week_start_date.dt.strftime("%Y-%m-%d")).to_dict(orient="records")
    return metrics, records


def _reference_metrics(report: dict[str, Any]) -> dict[str, float]:
    result = dict(report["metrics"])
    result["mean_weekly_absolute_total_error"] = float(np.mean([row["absolute_total_error"] for row in report["weekly_metrics"]]))
    if "prediction_near_zero_percentage" in result:
        result["prediction_le_0_5_percentage"] = result["prediction_near_zero_percentage"]
    return result


def _select(rows: list[dict[str, Any]], original: dict[str, float], limits: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    global_limit = 1 + float(limits["global_metric_max_relative_deterioration"])
    positive_limit = 1 + float(limits["positive_mae_max_relative_deterioration"])
    for row in rows:
        m = row["metrics"]
        row["selection_eligible"] = bool(m["mae"] <= original["mae"] * global_limit and m["rmse"] <= original["rmse"] * global_limit and m["mae_target_gt_0"] <= original["mae_target_gt_0"] * positive_limit)
    eligible = [row for row in rows if row["selection_eligible"]] or rows
    chosen = min(eligible, key=lambda row: (row["metrics"]["mean_weekly_absolute_total_error"], abs(row["metrics"]["mean_bias"]), row["metrics"]["mae_target_gt_0"], row["metrics"]["mae"]))
    rule = {"priority": ["mean_weekly_absolute_total_error", "absolute_mean_bias", "mae_target_gt_0", "mae"], "global_max_relative_deterioration": global_limit - 1, "positive_mae_max_relative_deterioration": positive_limit - 1, "fallback_if_none_eligible": "same ordered criteria across all variants"}
    return chosen["variant"], rule


def run_variants(config: dict[str, Any], root: Path) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = {name: resolve_path(root, value) for name, value in config["inputs"].items()}
    panel, split, baseline_predictions = pd.read_parquet(paths["panel"]), pd.read_parquet(paths["split"]), pd.read_parquet(paths["baseline_predictions"])
    baseline_report = json.loads(paths["baseline_metrics"].read_text(encoding="utf-8"))
    original_report = json.loads(paths["original_metrics"].read_text(encoding="utf-8"))
    validation_config = {"columns": config["columns"], "features": config["full_features"], "evaluation": config["evaluation"]}
    train, test = _validate_inputs(panel, split, baseline_predictions, validation_config)
    variant_rows, frames, fitted = [], [], {}
    for name, spec in config["variants"].items():
        features = config[f"{spec['feature_set']}_features"]
        model = build_random_forest(spec["parameters"])
        model.fit(train[features], transform_target(train[config["columns"]["target"]], spec["target_transform"]))
        raw = inverse_target(model.predict(test[features]), spec["target_transform"])
        predictions = _prediction_frame(test, panel, np.maximum(raw, 0), config["columns"], config["pipeline"]["version"])
        predictions["variant"] = name
        predictions["target_transform"] = spec["target_transform"]
        metrics, weekly = _metrics(predictions, float(config["evaluation"]["near_zero_threshold"]))
        variant_rows.append({"variant": name, "features": features, "target_transform": spec["target_transform"], "parameters": spec["parameters"], "metrics": metrics, "weekly_metrics": weekly})
        frames.append(predictions)
        fitted[name] = model
    original, baseline = _reference_metrics(original_report), _reference_metrics(baseline_report)
    selected, rule = _select(variant_rows, original, config["evaluation"])
    selected_spec = config["variants"][selected]
    selected_features = config[f"{selected_spec['feature_set']}_features"]
    artifact = {"model": fitted[selected], "model_name": selected, "features": selected_features, "target_transform": selected_spec["target_transform"], "inverse_transform": "expm1" if selected_spec["target_transform"] == "log1p" else "identity", "clip_min": 0.0, "parameters": selected_spec["parameters"], "data_version": config["data_version"]}
    common = {"pipeline": config["pipeline"], "rows": {"input": len(panel), "train": len(train), "test_per_variant": len(test)}, "split": {"source": config["inputs"]["split"], "train_week_count": train[config["columns"]["week_start"]].nunique(), "test_week_count": test[config["columns"]["week_start"]].nunique(), "test_start": test[config["columns"]["week_start"]].min().date().isoformat(), "test_end": test[config["columns"]["week_start"]].max().date().isoformat()}, "provenance": {"inputs": config["inputs"], "input_version": config["data_version"], "unit": "radio_censal - semana_epidemiologica", "target_condition": "synthetic", "prediction_condition": "predicted"}, "limitations": ["El target por radio es una asignación sintética, no evidencia epidemiológica espacial ni una ubicación real de casos.", "Se compararon sólo tres variantes controladas del mismo RandomForestRegressor; no hubo tuning exhaustivo."]}
    report = {**common, "variants": variant_rows}
    comparison = {**common, "selection": {"selected_variant": selected, "rule": rule, "reason": "Prioriza sobreestimación semanal y bias, sujeto a guardas de desempeño global y en targets positivos."}, "references": [{"model": "PersistenceBaseline", "metrics": baseline}, {"model": "RandomForestRegressor_original", "metrics": original}], "variants": [{"variant": row["variant"], "selection_eligible": row["selection_eligible"], "metrics": row["metrics"]} for row in variant_rows]}
    mvp_config = {"pipeline": config["pipeline"], "selected_variant": selected, "algorithm": "RandomForestRegressor", "features": selected_features, "target_transform": selected_spec["target_transform"], "inverse_transform": artifact["inverse_transform"], "prediction_clip_min": 0.0, "parameters": selected_spec["parameters"], "data_version": config["data_version"], "split_source": config["inputs"]["split"], "expected_test_rows": config["evaluation"]["expected_test_rows"], "target_condition": "synthetic"}
    return artifact, pd.concat(frames, ignore_index=True), report, comparison, mvp_config


def write_outputs(result: tuple[Any, ...], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    artifact, predictions, report, comparison, mvp_config = result
    paths = {name: resolve_path(root, value) for name, value in config["outputs"].items()}
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas de etapa 6.1: {existing}")
    for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(paths["predictions"], index=False, engine="pyarrow", compression="snappy")
    for key, value in (("metrics", report), ("comparison", comparison), ("mvp_config", mvp_config)):
        paths[key].write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    joblib.dump(artifact, paths["artifact"], compress=3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = load_config(args.config.resolve()); result = run_variants(config, args.repo_root.resolve()); write_outputs(result, config, args.repo_root.resolve(), args.overwrite)


if __name__ == "__main__": main()
