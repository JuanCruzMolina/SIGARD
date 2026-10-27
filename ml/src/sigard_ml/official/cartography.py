"""Audita una copia de la cartografía vigente, sin reparar ni editar polígonos."""

import re
import math
from pathlib import Path

import geopandas as gpd
from pyproj import CRS, Proj

from sigard_ml.official.spatial_settings import (
    CAPITAL_PREFIX, EXPECTED_RADIOS, MAX_METRIC_SCALE_DEVIATION, METRIC_CRS,
)


def validate_radios(radios, *, expected_count=EXPECTED_RADIOS):
    if radios.crs is None or "radio_id" not in radios:
        raise ValueError("Cartografía sin CRS o identificadores")
    if len(radios) != expected_count or radios.radio_id.isna().any() or not radios.radio_id.is_unique:
        raise ValueError("Cantidad o identificadores censales inválidos")
    if not radios.radio_id.map(lambda value: isinstance(value, str) and
                               re.fullmatch(CAPITAL_PREFIX + r"[0-9]{4}", value) is not None).all():
        raise ValueError("Identificadores ajenos a Capital")
    geometry = radios.geometry
    if (geometry.isna().any() or geometry.is_empty.any() or not geometry.is_valid.all()
            or not geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all()):
        raise ValueError("Geometría censal nula, vacía o inválida")
    for column, expected in (("departamento", "capital"), ("provincia", "la rioja")):
        if column in radios and not radios[column].astype(str).str.strip().str.casefold().eq(expected).all():
            raise ValueError("Cartografía ajena al departamento estudiado")


def validate_metric_extent(radios):
    """Verifica metros y cuantifica escala: Capital se extiende hacia la zona 20S.

    Se permite la pequeña extrapolación de UTM 19S para diagnóstico sólo si
    sus factores de escala cumplen la tolerancia numérica centralizada.
    Esto no mide exactitud de pacientes ni errores del geocodificador.
    """
    crs = CRS(METRIC_CRS)
    west, south, east, north = radios.to_crs(4326).total_bounds
    area = crs.area_of_use
    if not crs.is_projected or any(axis.unit_name != "metre" for axis in crs.axis_info):
        raise ValueError("CRS métrico incompatible")
    if not area.south <= south <= north <= area.north:
        raise ValueError("Territorio fuera del área de uso latitudinal de UTM 19S")
    nominal = area.west <= west <= east <= area.east and area.south <= south <= north <= area.north
    # Extremos de la envolvente local de Transversa Mercator: separación del
    # meridiano central y latitud absoluta. Se incluye el mínimo de escala.
    longitudes = [west, east, min(east, max(west, -69.0))]
    latitudes = [south, north, min(north, max(south, 0.0))]
    scales = [Proj(crs).get_factors(x, y).meridional_scale for x in longitudes for y in latitudes]
    deviation = max(abs(value - 1) for value in scales)
    if not all(math.isfinite(value) for value in scales) or deviation > MAX_METRIC_SCALE_DEVIATION:
        raise ValueError("Territorio fuera del área de uso compatible con la tolerancia métrica local")
    return {"nominal_metric_area_contains_entire_territory": bool(nominal),
            "bounding_box_scale_min": min(scales), "bounding_box_scale_max": max(scales),
            "bounding_box_max_scale_deviation_pct": deviation * 100,
            "diagnostic_scale_tolerance_pct": MAX_METRIC_SCALE_DEVIATION * 100,
            "metric_scale_tolerance_verified": True}


def inspect_polygon_pairs(radios):
    """Intersección con área positiva = superposición; tocarse no es solaparse."""
    metric = radios.to_crs(METRIC_CRS).reset_index(drop=True)
    overlaps, duplicates, overlap_area = 0, 0, 0.0
    for index, geometry in enumerate(metric.geometry):
        for other in metric.sindex.query(geometry, predicate="intersects"):
            if other <= index:
                continue
            right = metric.geometry.iloc[other]
            duplicates += int(geometry.equals(right))
            area = geometry.intersection(right).area
            if area > 0:
                overlaps += 1
                overlap_area += area
    union = metric.geometry.union_all()
    polygons = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
    return {"duplicate_polygon_pairs": duplicates, "positive_area_overlap_pairs": overlaps,
            "pairwise_overlap_area_m2": overlap_area, "territory_area_km2": union.area / 1e6,
            "union_components": len(polygons), "union_holes": sum(len(p.interiors) for p in polygons)}


def compare_reference(radios, reference):
    """Comprueba IDs y igualdad topológica contra la fuente censal ya utilizada."""
    left = radios.to_crs(reference.crs).set_index("radio_id").sort_index()
    right = reference.set_index("radio_id").sort_index()
    if not left.index.equals(right.index) or not left.geometry.geom_equals(right.geometry).all():
        raise ValueError("El maestro no coincide con la cartografía censal de origen")


def audit_cartography(radios, *, reference=None, expected_count=EXPECTED_RADIOS):
    validate_radios(radios, expected_count=expected_count)
    metric_check = validate_metric_extent(radios)
    if reference is not None:
        validate_radios(reference, expected_count=expected_count)
        compare_reference(radios, reference)
    pairs = inspect_polygon_pairs(radios)
    if pairs["duplicate_polygon_pairs"]:
        raise ValueError("Polígonos censales duplicados")
    # Las superposiciones se informan y todas las coincidencias se conservan.
    return {"radio_count": len(radios), "unique_ids": int(radios.radio_id.nunique()),
            "valid_geometries": True, "source_crs": radios.crs.to_string(),
            "metric_crs": METRIC_CRS, **metric_check,
            "capital_code_prefix_verified": True, "original_geometry_match": reference is not None,
            "independent_department_boundary_available": False,
            "boundary_definition": "union_of_existing_capital_census_radios",
            **pairs}


def read_radios(path: Path):
    return gpd.read_parquet(path) if path.suffix.lower() == ".parquet" else gpd.read_file(path)


def compare_locality_boundary(radios, locality, *, expected_count=EXPECTED_RADIOS):
    """Diagnóstico de radios completos contra UNA localidad previamente identificada.

    No selecciona por nombre, repara, recorta el maestro, distribuye población o
    acredita ubicaciones. Interiores = covered_by; parciales = área positiva sin
    cobertura completa; exteriores = área cero, aun si hay contacto de borde.
    Las superficies usan el CRS métrico existente, con su control de escala.
    """
    validate_radios(radios, expected_count=expected_count)
    if (not isinstance(locality, gpd.GeoDataFrame) or not hasattr(locality, "geometry")
            or locality.crs is None or len(locality) != 1
            or locality.geometry.isna().any() or locality.geometry.is_empty.any()
            or not locality.geometry.is_valid.all()
            or not locality.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all()):
        raise ValueError("Se requiere una localidad poligonal única, válida y con CRS")
    radio_scale = validate_metric_extent(radios)
    locality_scale = validate_metric_extent(locality)
    metric = radios.to_crs(METRIC_CRS)
    boundary = locality.to_crs(METRIC_CRS).geometry.iloc[0]
    intersection = metric.geometry.intersection(boundary)
    outside = metric.geometry.difference(boundary)
    covered = metric.geometry.covered_by(boundary)
    result = metric[["radio_id"]].copy()
    result["radio_area_m2"] = metric.geometry.area
    result["intersection_area_m2"] = intersection.area
    result["outside_area_m2"] = outside.area
    result["intersection_fraction_raw"] = result.intersection_area_m2 / result.radio_area_m2
    # Sólo acota ruido de cocientes (p.ej. 1+1e-15), sin umbral de selección.
    result["intersection_fraction"] = result.intersection_fraction_raw.clip(0, 1)
    result["relation"] = "outside"
    result.loc[result.intersection_area_m2.gt(0), "relation"] = "partial"
    result.loc[covered, "relation"] = "inside"
    result["boundary_only_contact"] = metric.geometry.touches(boundary)
    counts = result.relation.value_counts()
    report = {"transformation_version": "locality-radio-comparison-1", "metric_crs": METRIC_CRS,
              "radio_scale_check": radio_scale, "locality_scale_check": locality_scale,
              "classification": "covered_by / positive intersection area / zero intersection area; no tolerance",
              "counts": {key: int(counts.get(key, 0)) for key in ("inside", "partial", "outside")},
              "boundary_only_contacts": int(result.boundary_only_contact.sum()),
              "locality_area_m2": boundary.area,
              "locality_outside_radio_union_m2": boundary.difference(metric.geometry.union_all()).area,
              "geometry_modified": False, "population_or_cases_allocated": False}
    return result.sort_values("radio_id").reset_index(drop=True), report
