"""Iteración 9: dos capas territoriales explícitamente independientes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

LEVELS = ["very_low", "low", "medium", "high"]


def deterministic_percentiles(frame: pd.DataFrame, score: str) -> pd.DataFrame:
    """Orden total por score y radio_id; evita categorías ausentes por empates."""
    result = frame.sort_values([score, "radio_id"], kind="mergesort").copy()
    result["deterministic_rank"] = np.arange(1, len(result) + 1)
    result["percentile"] = result["deterministic_rank"] / len(result) * 100.0
    result["relative_level"] = pd.cut(result["percentile"], bins=[0, 25, 50, 75, 100], labels=LEVELS, include_lowest=True).astype("string")
    return result.sort_values("radio_id", kind="mergesort").reset_index(drop=True)


def _feature_rank(frame: pd.DataFrame, column: str) -> pd.Series:
    ordered = frame[["radio_id", column]].sort_values([column, "radio_id"], kind="mergesort")
    ranks = pd.Series(np.arange(1, len(ordered) + 1) / len(ordered), index=ordered.index)
    return ranks.reindex(frame.index)


def _ranking_comparison(previous: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    merged = previous[["radio_id", "deterministic_rank", "relative_level"]].merge(current[["radio_id", "deterministic_rank", "relative_level"]], on="radio_id", suffixes=("_previous", "_current"), validate="one_to_one")
    change = (merged.deterministic_rank_current - merged.deterministic_rank_previous).abs()
    movers = merged.assign(absolute_change=change).sort_values(["absolute_change", "radio_id"], ascending=[False, True]).head(10)
    return {"spearman_ranking_correlation": float(merged.deterministic_rank_previous.corr(merged.deterministic_rank_current, method="spearman")), "mean_absolute_position_change": float(change.mean()), "max_absolute_position_change": int(change.max()), "radios_changing_relative_level": int(merged.relative_level_previous.ne(merged.relative_level_current).sum()), "largest_movements": [{"radio_id": row.radio_id, "previous_rank": int(row.deterministic_rank_previous), "current_rank": int(row.deterministic_rank_current), "absolute_change": int(row.absolute_change), "previous_level": row.relative_level_previous, "current_level": row.relative_level_current} for row in movers.itertuples()]}


def build_structural(territorial: gpd.GeoDataFrame, config: dict[str, Any]) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    mapping = config["structural_features"]
    required = {"radio_id", "geometry", *mapping.values()}
    if missing := sorted(required.difference(territorial.columns)): raise ValueError(f"Faltan columnas territoriales: {missing}")
    if len(territorial) != config["expected_radios"] or territorial.radio_id.nunique() != config["expected_radios"]: raise ValueError("El universo territorial no contiene exactamente 263 radios únicos")
    result = territorial[["radio_id", *mapping.values(), "geometry"]].rename(columns={value: key for key, value in mapping.items()}).copy()
    distributions, transformations, rank_columns = {}, {}, []
    threshold = float(config["skewness_log1p_threshold"])
    for feature in mapping:
        values = result[feature].astype(float)
        skewness = float(values.skew())
        transformed = np.log1p(values) if skewness > threshold else values
        transformations[feature] = "log1p" if skewness > threshold else "identity"
        rank_column = f"{feature}_rank"
        result[rank_column] = _feature_rank(result.assign(**{feature: transformed}), feature)
        rank_columns.append(rank_column)
        distributions[feature] = {"min": float(values.min()), "max": float(values.max()), "mean": float(values.mean()), "median": float(values.median()), "skewness": skewness}
    previous = result[["radio_id", *rank_columns]].copy()
    previous["previous_score"] = previous[rank_columns].mean(axis=1)
    previous = deterministic_percentiles(previous, "previous_score")
    result["demographic_residential_component"] = result[["population_rank", "households_rank", "dwellings_rank"]].mean(axis=1)
    result["density_component"] = result["population_density_rank"]
    result["territorial_context_score"] = 0.5 * result["demographic_residential_component"] + 0.5 * result["density_component"]
    result = gpd.GeoDataFrame(deterministic_percentiles(result, "territorial_context_score"), geometry="geometry", crs=territorial.crs)
    comparison = _ranking_comparison(previous, result)
    output_columns = ["radio_id", *mapping.keys(), "demographic_residential_component", "density_component", "territorial_context_score", "percentile", "relative_level", "geometry"]
    result = result[output_columns]
    report_transformations = {**transformations, "area_km2": "not applied to current score; log1p rank used only to reconstruct legacy comparison"}
    report = {"pipeline": config["pipeline"], "number_of_radios": len(result), "source_columns": mapping,
              "features_used": ["population", "population_density", "households", "dwellings"], "descriptive_features": ["area_km2"], "distributions": distributions, "transformations": report_transformations, "normalization_method": "deterministic ordinal rank / 263 in [1/263, 1], tie-break radio_id",
              "weighting_method": "50% demographic-residential magnitude and 50% population density; conceptual MVP weights not optimized against dengue", "exact_formula": "0.5 * mean(population_rank, households_rank, dwellings_rank) + 0.5 * population_density_rank",
              "score_min": float(result.territorial_context_score.min()), "score_max": float(result.territorial_context_score.max()),
              "percentile_counts": {level: int((result.relative_level == level).sum()) for level in LEVELS},
              "null_counts": {column: int(value) for column, value in result.drop(columns="geometry").isna().sum().items()}, "duplicate_counts": {"radio_id": int(result.radio_id.duplicated().sum())},
              "geometry_validation": {"crs": str(result.crs), "epsg": result.crs.to_epsg(), "valid": bool(result.geometry.is_valid.all()), "empty": int(result.geometry.is_empty.sum()), "null": int(result.geometry.isna().sum())},
              "comparison_with_previous_index": comparison, "interpretation": "El índice resume contexto territorial relativo y no constituye una estimación epidemiológica de riesgo.",
              "limitations": ["No es probabilidad de dengue, incidencia esperada ni riesgo sanitario oficial.", "No está validado epidemiológicamente.", "Los pesos 50/50 son una decisión conceptual del MVP y no expresan causalidad.", "area_km2 se conserva sólo como atributo descriptivo y no participa del score."]}
    return result, report


def build_experimental(territorial: gpd.GeoDataFrame, predictions: pd.DataFrame, config: dict[str, Any]) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    selected = predictions.loc[predictions.variant.eq(config["experimental_variant"])].copy()
    selected["target_week_start"] = pd.to_datetime(selected["target_week_start_date"])
    selected["target_week_end"] = selected["target_week_start"] + pd.Timedelta(days=6)
    selected["cutoff_date"] = pd.to_datetime(selected["origin_week_start_date"]) + pd.Timedelta(days=6)
    selected["experimental_spatial_score"] = selected["predicted_cases"].astype(float)
    if selected.duplicated(["radio_id", "target_week_start"]).any(): raise ValueError("Hay claves radio-semana duplicadas")
    ranked = []
    for _, group in selected.groupby("target_week_start", sort=True):
        if len(group) != config["expected_radios"] or group.radio_id.nunique() != config["expected_radios"]: raise ValueError("Una semana no contiene 263 radios")
        ranked.append(deterministic_percentiles(group, "experimental_spatial_score"))
    result = pd.concat(ranked, ignore_index=True)
    result["synthetic_scenario"] = "spatial_clusters"
    result = result.merge(territorial[["radio_id", "geometry"]], on="radio_id", validate="many_to_one")
    columns = ["radio_id", "cutoff_date", "target_week_start", "target_week_end", "experimental_spatial_score", "percentile", "relative_level", "synthetic_scenario", "geometry"]
    result = gpd.GeoDataFrame(result[columns].sort_values(["target_week_start", "radio_id"]).reset_index(drop=True), geometry="geometry", crs=territorial.crs)
    weeks = sorted(result.target_week_start.unique())
    expected = pd.date_range(min(weeks), max(weeks), freq="7D")
    counts = {pd.Timestamp(week).date().isoformat(): {level: int(((result.target_week_start == week) & (result.relative_level == level)).sum()) for level in LEVELS} for week in weeks}
    report = {"pipeline": config["pipeline"], "number_of_radios": int(result.radio_id.nunique()), "number_of_weeks": len(weeks), "rows": len(result), "scenario": "spatial_clusters",
              "score_source": {"artifact": config["inputs"]["experimental_predictions"], "variant": config["experimental_variant"], "column": "predicted_cases", "retrained": False, "condition": "synthetic spatial prediction reused as experimental score"},
              "classification_method": "independent deterministic rank per target week; percentile=rank/263*100; tie-break radio_id",
              "counts_by_level_per_week": counts, "missing_weeks": [date.date().isoformat() for date in expected.difference(pd.DatetimeIndex(weeks))],
              "conservation_status": "not_applicable: scores are continuous experimental predictions and are not forced to sum to the official departmental total",
              "null_counts": {column: int(value) for column, value in result.drop(columns="geometry").isna().sum().items()}, "duplicate_radio_week_keys": int(result.duplicated(["radio_id", "target_week_start"]).sum()),
              "geometry_validation": {"crs": str(result.crs), "epsg": result.crs.to_epsg(), "valid": bool(result.geometry.is_valid.all()), "empty": int(result.geometry.is_empty.sum()), "null": int(result.geometry.isna().sum())},
              "limitations": ["Utiliza una distribución espacial sintética y no observaciones georreferenciadas.", "No constituye validación epidemiológica espacial ni casos reales predichos por radio.", "Demuestra cómo podría variar territorialmente SIGARD cuando exista información espacial observada."]}
    return result, report


def run(config: dict[str, Any], root: Path) -> tuple[gpd.GeoDataFrame, dict[str, Any], gpd.GeoDataFrame, dict[str, Any]]:
    territorial = gpd.read_parquet(root / config["inputs"]["territorial"])
    predictions = pd.read_parquet(root / config["inputs"]["experimental_predictions"])
    structural, structural_report = build_structural(territorial, config)
    experimental, experimental_report = build_experimental(territorial, predictions, config)
    return structural, structural_report, experimental, experimental_report


def _write_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    serializable = frame.copy()
    for column in serializable.select_dtypes(include=["datetime", "datetimetz"]).columns:
        serializable[column] = serializable[column].dt.strftime("%Y-%m-%d")
    path.write_text(serializable.to_json(drop_id=True, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")


def write_outputs(result: tuple, config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    structural, structural_report, experimental, experimental_report = result
    paths = {key: root / value for key, value in config["outputs"].items()}
    if existing := [str(path) for path in paths.values() if path.exists()]:
        if not overwrite: raise FileExistsError(f"No se sobrescriben artefactos: {existing}")
    for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
    structural.to_parquet(paths["context_parquet"], index=False, compression="snappy")
    _write_geojson(structural, paths["context_geojson"])
    paths["context_report"].write_text(json.dumps(structural_report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = json.loads(args.config.read_text(encoding="utf-8")); root = args.repo_root.resolve(); write_outputs(run(config, root), config, root, args.overwrite)


if __name__ == "__main__": main()
