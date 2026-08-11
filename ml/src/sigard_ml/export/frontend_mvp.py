"""Contrato final de artefactos estáticos del frontend; no entrena modelos."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


class FrontendExportError(ValueError):
    """Los artefactos aprobados no satisfacen el contrato frontend."""


def _read(path: Path) -> dict[str, Any]:
    if not path.exists(): raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _model() -> dict[str, str]:
    return {"name": "RandomForestRegressor", "variant": "rf_minimal_climate_log_delta", "evaluation_status": "exploratory"}


def build_artifacts(config: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {key: root / value for key, value in config["inputs"].items()}
    delta, temporal_backtest, summary = _read(paths["temporal_delta_report"]), _read(paths["temporal_backtest"]), _read(paths["temporal_summary"])
    context_report, experimental_report = _read(paths["territorial_context_report"]), _read(paths["experimental_report"])
    context, experimental = gpd.read_file(paths["territorial_context"]), gpd.read_file(paths["experimental_history"])
    expected = config["expected"]
    if delta["best_rf_by_development"] != expected["temporal_variant"]: raise FrontendExportError("La variante temporal aprobada no coincide")
    if len(delta["weekly_predictions"]) != expected["holdout_predictions"]: raise FrontendExportError("El holdout temporal no contiene seis predicciones")
    if context.crs is None or context.crs.to_epsg() != 4326 or len(context) != expected["radios"] or context.radio_id.nunique() != expected["radios"]: raise FrontendExportError("Contexto territorial incompatible")
    if context.geometry.isna().any() or context.geometry.is_empty.any() or not context.geometry.is_valid.all(): raise FrontendExportError("Geometrías contextuales inválidas")
    forbidden = ("synthetic", "cases", "prediction", "target", "probability")
    if any(any(token in column.lower() for token in forbidden) for column in context.columns): raise FrontendExportError("El contexto contiene columnas prohibidas")
    experimental["cutoff_date"] = pd.to_datetime(experimental.cutoff_date)
    experimental["target_week_start"] = pd.to_datetime(experimental.target_week_start)
    experimental["target_week_end"] = pd.to_datetime(experimental.target_week_end)
    if experimental.crs is None or experimental.crs.to_epsg() != 4326 or not experimental.geometry.is_valid.all() or experimental.geometry.isna().any() or experimental.geometry.is_empty.any(): raise FrontendExportError("Geometrías experimentales inválidas")
    if not experimental.synthetic_scenario.eq(expected["scenario"]).all(): raise FrontendExportError("Escenario experimental incorrecto")
    counts = experimental.groupby("target_week_start").agg(rows=("radio_id", "size"), radios=("radio_id", "nunique"))
    if len(counts) != expected["experimental_weeks"] or not counts.eq(expected["radios"]).all().all(): raise FrontendExportError("Cada semana experimental debe contener 263 radios")
    if experimental.duplicated(["radio_id", "target_week_start"]).any(): raise FrontendExportError("Hay claves radio-semana duplicadas")
    if set(context.radio_id) != set(experimental.radio_id): raise FrontendExportError("Los universos territoriales no coinciden")
    temporal_by_target = {row["target_week_start"]: row for row in delta["weekly_predictions"]}
    experimental_dates = {date.date().isoformat() for date in experimental.target_week_start.unique()}
    aligned_targets = sorted(set(temporal_by_target).intersection(experimental_dates))
    if not aligned_targets: raise FrontendExportError("No hay semanas alineadas")
    temporal_predictions, weeks = [], []
    for target in aligned_targets:
        temporal = temporal_by_target[target]
        spatial = experimental.loc[experimental.target_week_start.eq(pd.Timestamp(target))]
        if len(spatial) != expected["radios"]: raise FrontendExportError(f"{target} no tiene 263 radios")
        cutoff, end = spatial.cutoff_date.dt.date.astype(str).unique(), spatial.target_week_end.dt.date.astype(str).unique()
        if len(cutoff) != 1 or len(end) != 1 or cutoff[0] != temporal["cutoff_date"] or end[0] != temporal["target_week_end"]: raise FrontendExportError(f"Fechas desalineadas para {target}")
        predicted = float(temporal["rf_minimal_climate_log_delta_prediction"])
        if not np.isfinite(predicted) or predicted < 0: raise FrontendExportError("Predicción temporal inválida")
        temporal_predictions.append({"cutoff_date": temporal["cutoff_date"], "target_week_start": target, "target_week_end": temporal["target_week_end"], "predicted_cases": predicted, "predicted_cases_rounded": max(0, int(np.rint(predicted))), "official_cases": float(temporal["official_cases"]) if temporal["official_cases"] is not None else None, "absolute_error": float(temporal["rf_minimal_climate_log_delta_absolute_error"]), "persistence_prediction": float(temporal["persistence_baseline_prediction"]), "persistence_absolute_error": float(temporal["persistence_baseline_absolute_error"])})
        weeks.append({"cutoff_date": temporal["cutoff_date"], "cutoff_label": temporal["cutoff_date"], "target_week_start": target, "target_week_end": temporal["target_week_end"], "target_week_label": f"{target} a {temporal['target_week_end']}", "has_temporal_prediction": True, "has_experimental_spatial": True})
    temporal_artifact = {"model": _model(), "predictions": temporal_predictions}
    available = {"default_cutoff_date": weeks[-1]["cutoff_date"], "weeks": weeks}
    rf = delta["holdout_metrics"][expected["temporal_variant"]]; baseline = delta["holdout_metrics"]["persistence_baseline"]
    direction = delta["direction_analysis"]
    reduction = (baseline["mae"] - rf["mae"]) / baseline["mae"] * 100.0
    metric = lambda values, name: {"mae": float(values["mae"]), "rmse": float(values["rmse"]), "medae": float(values["median_absolute_error"]), "bias": float(values["bias"]), "direction_accuracy": float(direction[name]["direction_accuracy"])}
    evaluation = {"model": _model(), "dataset": {"official_weeks": int(delta["dataset"]["official_supported_weeks"]), "modelable_rows": int(delta["dataset"]["modeling_rows"]), "development_predictions": int(delta["splits"]["development_rows"]), "holdout_predictions": int(delta["splits"]["holdout_rows"])}, "metrics": {"random_forest": metric(rf, expected["temporal_variant"]), "persistence_baseline": metric(baseline, "persistence_baseline"), "mae_reduction_vs_baseline_pct": float(reduction)}, "backtest": delta["weekly_predictions"]}
    metadata = {"project": "SIGARD", "territory": "Departamento Capital, La Rioja", "prototype_status": "academic_mvp", "temporal_model": {"name": "RandomForestRegressor", "variant": expected["temporal_variant"], "validation": "exploratory"}, "territorial_context": {"label": "Contexto territorial relativo", "data_type": "real", "dynamic": False}, "experimental_spatial": {"label": "Simulación espacial experimental", "data_type": "synthetic", "dynamic": True, "scenario": expected["scenario"]}, "disclaimers": {"territorial_context": "Resume contexto territorial relativo y no constituye una estimación epidemiológica de riesgo.", "experimental_spatial": "Representa una distribución territorial sintética utilizada para demostrar el comportamiento espacial del prototipo.", "spatial_validation": "La validación espacial real permanece pendiente hasta disponer de casos epidemiológicos territorialmente referenciados."}}
    artifacts = {"temporal_predictions": temporal_artifact, "available_weeks": available, "model_evaluation": evaluation, "metadata": metadata}
    legacy = []
    for relative in config["legacy_frontend_files"]:
        path = root / relative
        if not path.exists(): raise FrontendExportError(f"Falta legacy requerido: {path}")
        legacy.append(relative)
    report = {"pipeline": config["pipeline"], "available_cutoff_weeks": [row["cutoff_date"] for row in weeks], "default_cutoff_date": available["default_cutoff_date"], "temporal_prediction_count": len(temporal_predictions), "temporal_holdout_count": len(delta["weekly_predictions"]), "experimental_week_count": int(experimental_report["number_of_weeks"]), "structural_radios": len(context), "experimental_rows": len(experimental), "files_exported": [*config["frontend_outputs"].values(), config["quality_report"]], "schema_validations": {"temporal_variant": True, "aligned_intersection_only": True, "context_schema": True, "experimental_schema": True, "same_radio_universe": True}, "geometry_validations": {"context_epsg_4326_valid": True, "experimental_epsg_4326_valid": True}, "legacy_files_preserved": legacy, "warnings": ["Los archivos mvp_prediction.*, mvp_prediction_summary y mvp_backtest son legacy hasta Iteración 11.", "Sólo cuatro de seis semanas del holdout tienen simulación espacial experimental alineada."], "limitations": [*delta["limitations"], *context_report["limitations"], *experimental_report["limitations"]]}
    return artifacts, report


def write_artifacts(artifacts: dict[str, Any], report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    outputs = {key: root / value for key, value in config["frontend_outputs"].items()}
    quality = root / config["quality_report"]
    all_paths = [*outputs.values(), quality]
    if existing := [str(path) for path in all_paths if path.exists()]:
        if not overwrite: raise FileExistsError(f"No se sobrescriben exports: {existing}")
    for path in all_paths: path.parent.mkdir(parents=True, exist_ok=True)
    for key in ["temporal_predictions", "available_weeks", "model_evaluation", "metadata"]:
        outputs[key].write_text(_dump(artifacts[key]), encoding="utf-8", newline="\n")
    shutil.copyfile(root / config["inputs"]["territorial_context"], outputs["territorial_context"])
    shutil.copyfile(root / config["inputs"]["experimental_history"], outputs["experimental_history"])
    quality.write_text(_dump(report), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = _read(args.config.resolve()); root = args.repo_root.resolve(); artifacts, report = build_artifacts(config, root); write_artifacts(artifacts, report, config, root, args.overwrite)


if __name__ == "__main__": main()
