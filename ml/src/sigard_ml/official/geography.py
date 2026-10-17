"""Calidad preliminar de puntos; no asigna radios ni corrige coordenadas."""

from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from sigard_ml.official.normalization import parse_coordinate
from sigard_ml.official.settings import LOW_PRECISION_DECIMALS


def load_capital_boundary(path: Path):
    """Disuelve cartografía censal real, sin consumir epidemiología."""
    territory = gpd.read_parquet(path) if path.suffix == ".parquet" else gpd.read_file(path)
    if territory.crs is None or len(territory) != 263 or "radio_id" not in territory:
        raise ValueError("Cartografía de Capital no satisface el contrato")
    if territory.radio_id.nunique() != 263 or territory.geometry.is_empty.any() or not territory.geometry.is_valid.all():
        raise ValueError("Cartografía duplicada, vacía o inválida")
    return territory.to_crs(4326).geometry.union_all()


def inspect_coordinates(latitude_values, longitude_values, *, boundary=None,
                        crs_confirmed=False, low_precision_decimals=LOW_PRECISION_DECIMALS):
    rows = []
    for latitude_value, longitude_value in zip(latitude_values, longitude_values, strict=True):
        latitude, latitude_status, latitude_decimals = parse_coordinate(latitude_value)
        longitude, longitude_status, longitude_decimals = parse_coordinate(longitude_value)
        missing = "missing" in (latitude_status, longitude_status)
        invalid_format = "invalid_format" in (latitude_status, longitude_status)
        valid_range = (latitude is not None and longitude is not None
                       and -90 <= latitude <= 90 and -180 <= longitude <= 180)
        outside = inverted = on_boundary = None
        if boundary is not None and valid_range:
            point = Point(longitude, latitude)
            outside = not boundary.covers(point)
            on_boundary = boundary.boundary.covers(point)
        if boundary is not None and latitude is not None and longitude is not None:
            swapped_valid = -90 <= longitude <= 90 and -180 <= latitude <= 180
            inverted = swapped_valid and boundary.covers(Point(latitude, longitude)) and not (
                valid_range and boundary.covers(Point(longitude, latitude)))
        low_precision = (valid_range and min(latitude_decimals, longitude_decimals) <= low_precision_decimals)
        rows.append({"latitude_candidate": latitude, "longitude_candidate": longitude,
                     "coordinate_missing": missing, "coordinate_invalid_format": invalid_format,
                     "coordinate_global_range_valid": valid_range,
                     "outside_capital_provisional": outside, "possible_axis_inversion": inverted,
                     "on_capital_boundary_provisional": on_boundary, "low_decimal_precision": low_precision})
    counts = Counter((row["latitude_candidate"], row["longitude_candidate"])
                     for row in rows if row["coordinate_global_range_valid"])
    for row in rows:
        row["repeated_coordinate"] = row["coordinate_global_range_valid"] and counts[
            (row["latitude_candidate"], row["longitude_candidate"])] > 1
    summary = {
        "rows": len(rows), "missing": sum(row["coordinate_missing"] for row in rows),
        "invalid_format": sum(row["coordinate_invalid_format"] for row in rows),
        "valid_global_range": sum(row["coordinate_global_range_valid"] for row in rows),
        "out_of_global_range": sum(not row["coordinate_missing"] and not row["coordinate_invalid_format"]
                                   and not row["coordinate_global_range_valid"] for row in rows),
        "repeated_coordinate_rows": sum(row["repeated_coordinate"] for row in rows),
        "low_decimal_precision_rows": sum(row["low_decimal_precision"] for row in rows),
        "outside_capital_provisional": sum(row["outside_capital_provisional"] is True for row in rows) if boundary is not None else None,
        "possible_axis_inversion": sum(row["possible_axis_inversion"] is True for row in rows) if boundary is not None else None,
        "on_capital_boundary_provisional": sum(row["on_capital_boundary_provisional"] is True for row in rows) if boundary is not None else None,
        "crs_confirmed": crs_confirmed,
        "territorial_assignment_performed": False,
    }
    return rows, summary
