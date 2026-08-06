"""Construye el dataset territorial maestro de SIGARD v0.1."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from sigard_ml.validation.territorial import (
    CODE_WIDTHS,
    TerritorialValidationError,
    normalize_code,
    validate_one_to_one_sources,
)


LOGGER = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    """Carga la configuración JSON del pipeline."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def resolve_path(repo_root: Path, configured_path: str) -> Path:
    """Resuelve una ruta configurada con respecto a la raíz del repositorio."""
    return (repo_root / configured_path).resolve()


def require_columns(frame: pd.DataFrame, columns: list[str], source: str) -> None:
    """Falla con un mensaje legible si una fuente no contiene sus columnas."""
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise TerritorialValidationError(
            f"Columnas faltantes en {source}: {missing}"
        )


def build_radio_id(
    province: pd.Series,
    department: pd.Series,
    fraction: pd.Series,
    radio: pd.Series,
) -> pd.Series:
    """Compone el código censal estable de nueve caracteres."""
    return province + department + fraction + radio


def load_cartography(config: dict[str, Any], repo_root: Path) -> gpd.GeoDataFrame:
    """Lee, filtra y normaliza la cartografía oficial de Capital."""
    source = config["sources"]["cartography"]
    columns = source["columns"]
    path = resolve_path(repo_root, source["path"])
    LOGGER.info("Leyendo cartografía: %s", path)
    frame = gpd.read_file(path, encoding=source["encoding"])
    require_columns(frame, [*columns.values(), "geometry"], str(path))
    if frame.crs is None:
        raise TerritorialValidationError("La cartografía no declara CRS")
    expected_source_crs = config["crs"]["source"]
    if frame.crs.to_string().upper() != expected_source_crs.upper():
        raise TerritorialValidationError(
            f"CRS cartográfico inesperado: {frame.crs}; esperado {expected_source_crs}"
        )

    renamed = frame.rename(
        columns={
            columns["province_name"]: "provincia",
            columns["province_code"]: "province_code",
            columns["department_name"]: "departamento",
            columns["department_code"]: "department_code",
            columns["fraction"]: "fraccion",
            columns["radio"]: "radio",
            columns["radio_id"]: "radio_id",
        }
    )
    for field in ("province_code", "department_code", "fraccion", "radio"):
        renamed[field] = normalize_code(renamed[field], CODE_WIDTHS[field], field)
    renamed["radio_id"] = normalize_code(
        renamed["radio_id"], CODE_WIDTHS["radio_id"], "radio_id"
    )

    area = config["area"]
    filtered = renamed.loc[
        renamed["province_code"].eq(area["province_code"])
        & renamed["department_code"].eq(area["department_code"])
    ].copy()
    if filtered.empty:
        raise TerritorialValidationError("La cartografía filtrada de Capital está vacía")

    province_names = sorted(filtered["provincia"].astype(str).str.strip().unique())
    department_names = sorted(filtered["departamento"].astype(str).str.strip().unique())
    if [name.casefold() for name in province_names] != [area["province_name"].casefold()]:
        raise TerritorialValidationError(
            f"Nombre de provincia inesperado: {province_names}"
        )
    if [name.casefold() for name in department_names] != [
        area["department_name"].casefold()
    ]:
        raise TerritorialValidationError(
            f"Nombre de departamento inesperado: {department_names}"
        )

    constructed = build_radio_id(
        filtered["province_code"],
        filtered["department_code"],
        filtered["fraccion"],
        filtered["radio"],
    )
    mismatches = filtered.loc[~filtered["radio_id"].eq(constructed), "radio_id"]
    if not mismatches.empty:
        raise TerritorialValidationError(
            f"LINK no coincide con los componentes del código: {mismatches.tolist()[:10]}"
        )

    selected = filtered[
        ["radio_id", "provincia", "departamento", "fraccion", "radio", "geometry"]
    ].copy()
    selected["provincia"] = selected["provincia"].astype(str).str.strip()
    selected["departamento"] = selected["departamento"].astype(str).str.strip()
    return selected.sort_values("radio_id").reset_index(drop=True)


def load_census_count(
    name: str,
    config: dict[str, Any],
    repo_root: Path,
    quality: dict[str, Any],
) -> pd.DataFrame:
    """Agrega una variable censal exhaustiva a una fila por radio."""
    source = config["sources"][name]
    columns = config["census_columns"]
    path = resolve_path(repo_root, source["path"])
    required = list(columns.values())
    LOGGER.info("Leyendo %s: %s", name, path)
    frame = pd.read_csv(
        path,
        encoding=source["encoding"],
        dtype="string",
        usecols=required,
    )
    require_columns(frame, required, str(path))

    normalized_names = {
        columns["radio_id"]: "radio_id",
        columns["province_code"]: "province_code",
        columns["province_name"]: "province_name",
        columns["department_code"]: "department_code",
        columns["department_value"]: "department_value",
        columns["fraction"]: "fraccion",
        columns["radio"]: "radio",
        columns["variable"]: "variable",
        columns["category_code"]: "category_code",
        columns["category"]: "category",
        columns["count"]: "count",
    }
    frame = frame.rename(columns=normalized_names)
    for field in ("province_code", "department_code", "fraccion", "radio"):
        frame[field] = normalize_code(frame[field], CODE_WIDTHS[field], field)
    frame["radio_id"] = normalize_code(
        frame["radio_id"], CODE_WIDTHS["radio_id"], "radio_id"
    )

    area = config["area"]
    filtered = frame.loc[
        frame["province_code"].eq(area["province_code"])
        & frame["department_code"].eq(area["department_code"])
        & frame["variable"].eq(source["variable"])
    ].copy()
    if filtered.empty:
        raise TerritorialValidationError(
            f"{name}: no hay filas para Capital y variable {source['variable']}"
        )

    constructed = build_radio_id(
        filtered["province_code"],
        filtered["department_code"],
        filtered["fraccion"],
        filtered["radio"],
    )
    code_mismatches = sorted(
        filtered.loc[~filtered["radio_id"].eq(constructed), "radio_id"].unique()
    )
    category_duplicates = filtered.duplicated(
        ["radio_id", "variable", "category_code"], keep=False
    )
    duplicate_keys = sorted(
        filtered.loc[category_duplicates, "radio_id"].unique().tolist()
    )
    counts = pd.to_numeric(filtered["count"], errors="coerce")
    invalid_counts = counts.isna() | counts.lt(0) | counts.mod(1).ne(0)

    quality["input_checks"][name] = {
        "path": source["path"],
        "encoding": source["encoding"],
        "variable": source["variable"],
        "filtered_rows": int(len(filtered)),
        "radio_ids": int(filtered["radio_id"].nunique()),
        "duplicate_category_radio_ids": duplicate_keys,
        "component_code_mismatch_ids": code_mismatches,
        "invalid_count_rows": int(invalid_counts.sum()),
    }
    if duplicate_keys or code_mismatches or invalid_counts.any():
        raise TerritorialValidationError(f"{name}: fallaron validaciones de entrada")

    filtered["count"] = counts.astype("int64")
    result = (
        filtered.groupby("radio_id", as_index=False, sort=True)["count"]
        .sum()
        .rename(columns={"count": source["output_column"]})
    )
    return result


def add_spatial_metrics(
    frame: gpd.GeoDataFrame, metric_crs: str, output_crs: str
) -> gpd.GeoDataFrame:
    """Calcula área, centroides y vecinos en un CRS métrico."""
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise TerritorialValidationError("Hay geometrías nulas o vacías")
    if (~frame.geometry.is_valid).any():
        invalid = frame.loc[~frame.geometry.is_valid, "radio_id"].tolist()
        raise TerritorialValidationError(f"Geometrías inválidas: {invalid[:20]}")

    metric = frame.to_crs(metric_crs)
    areas = metric.geometry.area / 1_000_000
    if areas.le(0).any():
        raise TerritorialValidationError("Hay superficies no positivas")
    centroids = gpd.GeoSeries(metric.geometry.centroid, crs=metric_crs).to_crs(output_crs)

    neighbors: dict[str, list[str]] = {
        radio_id: [] for radio_id in metric["radio_id"].tolist()
    }
    rows = list(metric[["radio_id", "geometry"]].itertuples(index=False, name=None))
    for index, (left_id, left_geometry) in enumerate(rows):
        for right_id, right_geometry in rows[index + 1 :]:
            if left_geometry.touches(right_geometry):
                neighbors[left_id].append(right_id)
                neighbors[right_id].append(left_id)

    result = frame.to_crs(output_crs).copy()
    result["superficie_km2"] = areas.astype(float).values
    result["centroid_lat"] = centroids.y.astype(float).values
    result["centroid_lon"] = centroids.x.astype(float).values
    result["neighbor_ids"] = result["radio_id"].map(
        lambda radio_id: sorted(neighbors[radio_id])
    )
    return result


def write_outputs(
    frame: gpd.GeoDataFrame,
    quality: dict[str, Any],
    config: dict[str, Any],
    repo_root: Path,
) -> None:
    """Escribe las tres salidas deterministas del pipeline."""
    outputs = config["outputs"]
    parquet_path = resolve_path(repo_root, outputs["parquet"])
    geojson_path = resolve_path(repo_root, outputs["geojson"])
    report_path = resolve_path(repo_root, outputs["quality_report"])
    for path in (parquet_path, geojson_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    frame.to_parquet(parquet_path, index=False)
    geojson = json.loads(frame.to_json(drop_id=True, to_wgs84=True))
    with geojson_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(geojson, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    with report_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(quality, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def build_territorial_master(
    config: dict[str, Any], repo_root: Path
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Ejecuta la construcción completa del maestro territorial."""
    quality: dict[str, Any] = {
        "pipeline": "territorial_master",
        "version": "0.1.0",
        "area": config["area"],
        "crs": config["crs"],
        "input_checks": {},
    }
    cartography = load_cartography(config, repo_root)
    quality["input_checks"]["cartography"] = {
        "path": config["sources"]["cartography"]["path"],
        "encoding": config["sources"]["cartography"]["encoding"],
        "rows": int(len(cartography)),
        "duplicate_ids": sorted(
            cartography.loc[
                cartography.duplicated("radio_id", keep=False), "radio_id"
            ].unique().tolist()
        ),
        "invalid_geometry_ids": sorted(
            cartography.loc[~cartography.geometry.is_valid, "radio_id"].tolist()
        ),
    }

    counts = {
        name: load_census_count(name, config, repo_root, quality)
        for name in ("population", "households", "dwellings")
    }
    join_report = validate_one_to_one_sources(cartography, counts)
    quality["joins"] = join_report

    merged = cartography.copy()
    for name in ("population", "households", "dwellings"):
        merged = merged.merge(counts[name], on="radio_id", how="left", validate="one_to_one")
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=cartography.crs)
    merged = add_spatial_metrics(
        merged, config["crs"]["metric"], config["crs"]["output"]
    )
    merged["densidad_poblacional"] = merged["poblacion"] / merged["superficie_km2"]
    output_columns = [
        "radio_id",
        "provincia",
        "departamento",
        "fraccion",
        "radio",
        "poblacion",
        "hogares",
        "viviendas",
        "superficie_km2",
        "densidad_poblacional",
        "centroid_lat",
        "centroid_lon",
        "geometry",
        "neighbor_ids",
    ]
    merged = merged[output_columns].sort_values("radio_id").reset_index(drop=True)
    quality["output"] = {
        "rows": int(len(merged)),
        "unique_radio_ids": int(merged["radio_id"].nunique()),
        "null_counts": {
            column: int(value) for column, value in merged.isna().sum().items()
        },
        "radios_without_neighbors": sorted(
            merged.loc[merged["neighbor_ids"].str.len().eq(0), "radio_id"].tolist()
        ),
        "population_total": int(merged["poblacion"].sum()),
        "households_total": int(merged["hogares"].sum()),
        "dwellings_total": int(merged["viviendas"].sum()),
    }
    return merged, quality


def parse_args() -> argparse.Namespace:
    """Define los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    """Punto de entrada del pipeline territorial."""
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    repo_root = args.repo_root.resolve()
    config = load_config(args.config.resolve())
    frame, quality = build_territorial_master(config, repo_root)
    write_outputs(frame, quality, config, repo_root)
    LOGGER.info("Maestro territorial generado: %d radios", len(frame))


if __name__ == "__main__":
    main()
