"""Etapa 7: exporta predicciones existentes del MVP como artefactos estáticos."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping


class ExportValidationError(ValueError):
    """Una entrada o artefacto no satisface el contrato de presentación."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _date(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _risk_levels(values: pd.Series, quantiles: list[float], labels: list[str]) -> tuple[pd.Series, list[float]]:
    thresholds = [float(values.quantile(q)) for q in quantiles]
    levels = pd.Series(labels[-1], index=values.index, dtype="string")
    for threshold, label in reversed(list(zip(thresholds, labels[:-1]))):
        levels.loc[values.le(threshold)] = label
    return levels, thresholds


def _validate_inputs(territorial: gpd.GeoDataFrame, panel: pd.DataFrame, predictions: pd.DataFrame,
                     comparison: dict[str, Any], model_config: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    expected = int(config["expected_radio_count"])
    if territorial.crs is None or territorial.crs.to_epsg() != 4326:
        raise ExportValidationError("Las geometrías deben estar en EPSG:4326")
    if len(territorial) != expected or territorial.radio_id.nunique() != expected or territorial.radio_id.duplicated().any():
        raise ExportValidationError("El maestro territorial no contiene exactamente 263 radios únicos")
    if territorial.geometry.isna().any() or territorial.geometry.is_empty.any() or not territorial.geometry.is_valid.all():
        raise ExportValidationError("El maestro territorial contiene geometrías ausentes, vacías o inválidas")
    selected = comparison["selection"]["selected_variant"]
    if selected != model_config["selected_variant"]:
        raise ExportValidationError("La variante MVP difiere entre comparación y configuración")
    chosen = predictions.loc[predictions.variant.eq(selected)].copy()
    if len(chosen) != int(model_config["expected_test_rows"]):
        raise ExportValidationError("La cantidad de predicciones MVP no coincide con el contrato")
    weeks = sorted(pd.to_datetime(chosen.target_week_start_date).unique())
    if len(weeks) != int(config["expected_test_week_count"]):
        raise ExportValidationError("El backtest no contiene exactamente las cuatro semanas de test")
    counts = chosen.groupby("target_week_start_date").agg(rows=("radio_id", "size"), radios=("radio_id", "nunique"))
    if not counts.eq(expected).all().all():
        raise ExportValidationError("Cada semana debe contener exactamente 263 radios únicos")
    if chosen.predicted_cases.isna().any() or not np.isfinite(chosen.predicted_cases).all() or chosen.predicted_cases.lt(0).any():
        raise ExportValidationError("predicted_cases debe ser finito y no negativo")
    if not chosen.target_is_synthetic.all() or not chosen.is_prediction.all():
        raise ExportValidationError("Las filas deben conservar su condición sintética/predicha")
    panel_key = panel[["radio_id", "week_start_date", "target_cases_next_week"]].copy()
    checked = chosen.merge(panel_key, left_on=["radio_id", "origin_week_start_date"], right_on=["radio_id", "week_start_date"], validate="one_to_one", suffixes=("", "_panel"))
    if not checked.target_cases_next_week.astype("int64").equals(checked.target_cases_next_week_panel.astype("int64")):
        raise ExportValidationError("El total oficial/target no coincide con modeling_panel")
    return chosen.sort_values(["target_week_start_date", "radio_id"]).reset_index(drop=True)


def _feature_collection(rows: pd.DataFrame, territorial: gpd.GeoDataFrame, config: dict[str, Any]) -> dict[str, Any]:
    joined = territorial[["radio_id", "poblacion", "densidad_poblacional", "geometry"]].merge(rows, on="radio_id", validate="one_to_one")
    levels, _ = _risk_levels(joined.predicted_cases, config["risk"]["quantiles"], config["risk"]["labels"])
    joined["risk_level"] = levels
    features = []
    for row in joined.sort_values("radio_id").itertuples(index=False):
        properties = {
            "radio_id": str(row.radio_id), "population": int(row.poblacion),
            "population_density": float(row.densidad_poblacional),
            "prediction_week_start": _date(row.target_week_start_date),
            "prediction_week_end": _date(pd.Timestamp(row.target_week_start_date) + pd.Timedelta(days=6)),
            "predicted_cases": float(row.predicted_cases),
            "predicted_cases_rounded": int(np.rint(row.predicted_cases)),
            "risk_level": str(row.risk_level), "simulation_scenario": config["simulation_scenario"],
            "model_name": str(row.model_name), "model_version": str(row.model_version),
            "data_scope": config["data_scope"],
        }
        features.append({"type": "Feature", "geometry": mapping(row.geometry), "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def build_artifacts(config: dict[str, Any], root: Path) -> dict[str, Any]:
    paths = {key: root / value for key, value in config["inputs"].items()}
    territorial = gpd.read_parquet(paths["territorial"])
    panel, predictions = pd.read_parquet(paths["panel"]), pd.read_parquet(paths["predictions"])
    comparison, model_config = _read_json(paths["comparison"]), _read_json(paths["model_config"])
    chosen = _validate_inputs(territorial, panel, predictions, comparison, model_config, config)
    target = pd.Timestamp(config["target_week_start"]) if config["target_week_start"] != "latest" else chosen.target_week_start_date.max()
    current = chosen.loc[chosen.target_week_start_date.eq(target)].copy()
    if len(current) != config["expected_radio_count"]:
        raise ExportValidationError("La semana objetivo configurada no pertenece al test")
    _, thresholds = _risk_levels(current.predicted_cases, config["risk"]["quantiles"], config["risk"]["labels"])
    selected_metrics = next(row["metrics"] for row in comparison["variants"] if row["variant"] == model_config["selected_variant"])
    top = current.sort_values(["predicted_cases", "radio_id"], ascending=[False, True]).head(config["summary_top_radio_count"])
    summary = {
        "prediction_week": {"start": _date(target), "end": _date(target + pd.Timedelta(days=6))},
        "cutoff_date": _date(target - pd.Timedelta(days=1)),
        "model": {"name": "RandomForestRegressor", "version": model_config["pipeline"]["version"]},
        "variant": model_config["selected_variant"], "predicted_cases_radio_sum": float(current.predicted_cases.sum()),
        "number_of_radios": int(len(current)),
        "top_predicted_radios": [{"radio_id": str(r.radio_id), "predicted_cases": float(r.predicted_cases)} for r in top.itertuples()],
        "model_metrics": selected_metrics,
        "methodological_warning": config["methodological_warning"],
        "configuration": {"data_version": model_config["data_version"], "features": model_config["features"],
            "parameters": model_config["parameters"], "simulation_scenario": config["simulation_scenario"],
            "risk": {**config["risk"], "thresholds_for_selected_week": thresholds,
                     "warning": "Categoría visual relativa dentro de la semana; no es un umbral sanitario oficial."}},
        "data_scope": config["data_scope"],
    }
    backtest = []
    for week, rows in chosen.groupby("target_week_start_date", sort=True):
        official = int(rows.target_cases_next_week.sum())
        predicted = float(rows.predicted_cases.sum())
        backtest.append({"cutoff_date": _date(week - pd.Timedelta(days=1)), "prediction_week_start": _date(week),
            "prediction_week_end": _date(week + pd.Timedelta(days=6)), "department_cases_official": official,
            "department_cases_predicted_from_radio_sum": predicted, "absolute_error": abs(predicted - official),
            "percentage_error": abs(predicted - official) / official * 100 if official else None,
            "number_of_radios": int(len(rows)), "model_name": "RandomForestRegressor",
            "simulation_scenario": config["simulation_scenario"]})
    return {"prediction": _feature_collection(current, territorial, config), "summary": summary,
            "backtest": {"weeks": backtest, "methodological_warning": config["methodological_warning"], "data_scope": config["data_scope"]},
            "backtest_predictions": {"type": "FeatureCollection", "features": sum((_feature_collection(rows, territorial, config)["features"] for _, rows in chosen.groupby("target_week_start_date", sort=True)), [])}}


def write_artifacts(artifacts: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    outputs = {key: root / value for key, value in config["outputs"].items()}
    existing = [str(path) for path in outputs.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas de etapa 7 sin --overwrite: {existing}")
    mapping_keys = {"prediction": "prediction", "summary": "summary", "backtest": "backtest", "backtest_predictions": "backtest_predictions"}
    for key, path in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump(artifacts[mapping_keys[key]]), encoding="utf-8", newline="\n")
    for key, relative in config["frontend_copies"].items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(outputs[key], destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    config = _read_json(args.config.resolve())
    write_artifacts(build_artifacts(config, args.repo_root.resolve()), config, args.repo_root.resolve(), args.overwrite)


if __name__ == "__main__":
    main()
