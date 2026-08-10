"""Etapa 6: entrenamiento y evaluación temporal de Random Forest."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sigard_ml.evaluation.pipeline import load_config, resolve_path
from sigard_ml.evaluation.temporal import evaluate_predictions
from sigard_ml.models.random_forest import build_random_forest

LOGGER = logging.getLogger(__name__)


class RandomForestValidationError(ValueError):
    """Una entrada no satisface el contrato de la etapa 6."""


def _validate_inputs(panel: pd.DataFrame, split: pd.DataFrame, baseline: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns, features = config["columns"], config["features"]
    required_panel = set(columns.values()) | set(features)
    missing = sorted(required_panel.difference(panel.columns))
    if missing:
        raise RandomForestValidationError(f"Faltan columnas del panel: {missing}")
    if len(features) != len(set(features)):
        raise RandomForestValidationError("La lista de features contiene duplicados")
    forbidden = set(columns.values()) | {"week_end_date"}
    overlap = sorted(forbidden.intersection(features))
    if overlap:
        raise RandomForestValidationError(f"Features prohibidas por identidad/fecha/target: {overlap}")
    if any("target" in feature.lower() for feature in features):
        raise RandomForestValidationError("Una feature parece contener información del target")
    expected_split_columns = {columns["week_start"], "split"}
    if not expected_split_columns.issubset(split.columns):
        raise RandomForestValidationError("evaluation_split no contiene semana y split")
    if split[columns["week_start"]].duplicated().any() or not set(split["split"]).issubset({"train", "test"}):
        raise RandomForestValidationError("evaluation_split tiene semanas duplicadas o etiquetas inválidas")
    panel_weeks = set(pd.to_datetime(panel[columns["week_start"]]))
    split_weeks = set(pd.to_datetime(split[columns["week_start"]]))
    if panel_weeks != split_weeks:
        raise RandomForestValidationError("Las semanas del panel y evaluation_split no coinciden exactamente")
    labeled = panel.merge(split[[columns["week_start"], "split"]], on=columns["week_start"], how="left", validate="many_to_one")
    train, test = labeled.loc[labeled["split"].eq("train")].copy(), labeled.loc[labeled["split"].eq("test")].copy()
    train_weeks, test_weeks = set(train[columns["week_start"]]), set(test[columns["week_start"]])
    if not train_weeks or not test_weeks or train_weeks.intersection(test_weeks):
        raise RandomForestValidationError("Train y test deben existir y ser disjuntos")
    if max(train_weeks) >= min(test_weeks):
        raise RandomForestValidationError("Ninguna semana de test puede entrar al entrenamiento")
    numeric = pd.concat([train[features], test[features]], ignore_index=True).apply(pd.to_numeric, errors="raise")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy(dtype="float64")).all():
        raise RandomForestValidationError("Las features de train/test contienen nulos o infinitos")
    target = pd.to_numeric(labeled[columns["target"]], errors="raise")
    if target.isna().any() or not np.isfinite(target.to_numpy(dtype="float64")).all():
        raise RandomForestValidationError("El target contiene nulos o infinitos")
    key = [columns["radio_id"], columns["week_start"]]
    baseline_key = ["radio_id", "origin_week_start_date"]
    expected = test[key].rename(columns={columns["radio_id"]: "radio_id", columns["week_start"]: "origin_week_start_date"}).sort_values(baseline_key).reset_index(drop=True)
    observed = baseline[baseline_key].sort_values(baseline_key).reset_index(drop=True)
    if not expected.equals(observed):
        raise RandomForestValidationError("El test no coincide exactamente con las filas del baseline")
    expected_rows = config["evaluation"]["expected_test_rows"]
    if len(test) != expected_rows or len(baseline) != expected_rows:
        raise RandomForestValidationError(f"La evaluación debe contener exactamente {expected_rows} filas")
    return train, test


def _prediction_frame(test: pd.DataFrame, panel: pd.DataFrame, predicted: np.ndarray, columns: dict[str, str], version: str) -> pd.DataFrame:
    result = test[[columns["radio_id"], columns["year"], columns["week"], columns["week_start"], columns["target"]]].copy()
    result.columns = ["radio_id", "origin_epidemiological_year", "origin_epidemiological_week", "origin_week_start_date", "target_cases_next_week"]
    result["target_week_start_date"] = result["origin_week_start_date"] + pd.Timedelta(days=7)
    target_year_week = panel[[columns["week_start"], columns["year"], columns["week"]]].drop_duplicates()
    target_year_week.columns = ["target_week_start_date", "target_epidemiological_year", "target_epidemiological_week"]
    result = result.merge(target_year_week, on="target_week_start_date", how="left", validate="many_to_one")
    missing = result["target_epidemiological_year"].isna()
    result.loc[missing, "target_epidemiological_year"] = result.loc[missing, "origin_epidemiological_year"]
    result.loc[missing, "target_epidemiological_week"] = result.loc[missing, "origin_epidemiological_week"] + 1
    result[["target_epidemiological_year", "target_epidemiological_week"]] = result[["target_epidemiological_year", "target_epidemiological_week"]].astype("int64")
    result["predicted_cases"] = np.maximum(predicted.astype("float64"), 0.0)
    result["predicted_cases_rounded"] = result["predicted_cases"].round().astype("int64")
    result["model_name"], result["model_version"] = "RandomForestRegressor", version
    result["target_is_synthetic"], result["is_prediction"] = True, True
    return result.sort_values(["origin_week_start_date", "radio_id"]).reset_index(drop=True)


def _weekly_percentage(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.copy()
    weekly["absolute_percentage_error"] = np.where(
        weekly["actual_total_cases"].ne(0),
        weekly["absolute_total_error"] / weekly["actual_total_cases"] * 100,
        np.nan,
    )
    return weekly


def run_random_forest(config: dict[str, Any], root: Path) -> tuple[Any, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    inputs = {name: resolve_path(root, path) for name, path in config["inputs"].items()}
    panel, split = pd.read_parquet(inputs["panel"]), pd.read_parquet(inputs["split"])
    baseline_predictions = pd.read_parquet(inputs["baseline_predictions"])
    with inputs["baseline_metrics"].open(encoding="utf-8") as stream:
        baseline_report = json.load(stream)
    train, test = _validate_inputs(panel, split, baseline_predictions, config)
    features, target = config["features"], config["columns"]["target"]
    model = build_random_forest(config["model"])
    model.fit(train[features], train[target].astype("float64"))
    predictions = _prediction_frame(test, panel, model.predict(test[features]), config["columns"], config["pipeline"]["version"])
    if (predictions["predicted_cases"] < 0).any():
        raise RandomForestValidationError("Hay predicciones negativas")
    metrics, weekly = evaluate_predictions(predictions)
    threshold = float(config["evaluation"]["near_zero_threshold"])
    metrics.pop("prediction_zero_percentage")
    metrics["prediction_near_zero_percentage"] = float(predictions["predicted_cases"].le(threshold).mean() * 100)
    weekly = _weekly_percentage(weekly)
    importance = pd.DataFrame({"feature": features, "importance": model.feature_importances_}).sort_values(["importance", "feature"], ascending=[False, True]).reset_index(drop=True)
    importance["rank"] = np.arange(1, len(importance) + 1)
    importance["target_is_synthetic"] = True
    weekly_records = weekly.assign(target_week_start_date=weekly.target_week_start_date.dt.strftime("%Y-%m-%d")).replace({np.nan: None}).to_dict(orient="records")
    report = {
        "pipeline": config["pipeline"],
        "model": {"name": "RandomForestRegressor", "parameters": config["model"], "prediction_clipped_at_zero": True, "predictions_rounded_for_metrics": False},
        "provenance": {"inputs": config["inputs"], "input_version": config["data_version"], "unit": "radio_censal - semana_epidemiologica", "target_condition": "synthetic", "prediction_condition": "predicted"},
        "features": features,
        "rows": {"input": len(panel), "train": len(train), "test_predictions": len(predictions)},
        "split": {"source": config["inputs"]["split"], "train_week_count": train[config["columns"]["week_start"]].nunique(), "test_week_count": test[config["columns"]["week_start"]].nunique(), "test_start": test[config["columns"]["week_start"]].min().date().isoformat(), "test_end": test[config["columns"]["week_start"]].max().date().isoformat()},
        "metrics": metrics,
        "weekly_metrics": weekly_records,
        "limitations": ["El target por radio es una asignación sintética, no evidencia epidemiológica espacial.", "Las importancias reflejan un dataset espacial sintético y no evidencia causal epidemiológica.", "No se utilizó SHAP ni tuning exhaustivo."],
    }
    baseline_metrics = baseline_report["metrics"]
    baseline_weekly_error = float(np.mean([row["absolute_total_error"] for row in baseline_report["weekly_metrics"]]))
    rf_weekly_error = float(weekly["absolute_total_error"].mean())
    comparison = {
        "role_of_baseline": "PersistenceBaseline es sólo referencia de control, no modelo candidato.",
        "evaluation_rows": len(predictions),
        "test_weeks": report["split"],
        "metrics": [
            {"model": "PersistenceBaseline", "mae": baseline_metrics["mae"], "rmse": baseline_metrics["rmse"], "mae_target_gt_0": baseline_metrics["mae_target_gt_0"], "mean_weekly_absolute_total_error": baseline_weekly_error},
            {"model": "RandomForestRegressor", "mae": metrics["mae"], "rmse": metrics["rmse"], "mae_target_gt_0": metrics["mae_target_gt_0"], "mean_weekly_absolute_total_error": rf_weekly_error},
        ],
        "target_condition": "synthetic",
    }
    return model, predictions, importance, report, comparison


def write_outputs(model: Any, predictions: pd.DataFrame, importance: pd.DataFrame, report: dict[str, Any], comparison: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    paths = {name: resolve_path(root, value) for name, value in config["outputs"].items()}
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas existentes: {existing}")
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(paths["predictions"], index=False, engine="pyarrow", compression="snappy")
    importance.to_parquet(paths["feature_importance"], index=False, engine="pyarrow", compression="snappy")
    for name, value in (("metrics", report), ("comparison", comparison)):
        with paths[name].open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    joblib.dump({"model": model, "features": config["features"], "config": config["model"], "data_version": config["data_version"]}, paths["artifact"], compress=3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true", help="Reemplaza sólo las cinco salidas configuradas de etapa 6")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config, root = load_config(args.config.resolve()), args.repo_root.resolve()
    result = run_random_forest(config, root)
    write_outputs(*result, config, root, args.overwrite)
    LOGGER.info("Random Forest evaluado sobre %d predicciones", len(result[1]))


if __name__ == "__main__":
    main()
