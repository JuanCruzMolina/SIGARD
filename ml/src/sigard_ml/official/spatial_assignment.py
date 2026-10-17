"""Coincidencia geométrica y confianza geográfica separadas de la epidemiología."""

import math
from collections import Counter

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import Point

from sigard_ml.official.cartography import validate_metric_extent, validate_radios
from sigard_ml.official.normalization import parse_coordinate
from sigard_ml.official.settings import PRECISION_LABEL_WORDS, normalize_header
from sigard_ml.official.spatial_settings import EXCHANGE_CRS, EXPECTED_RADIOS, METRIC_CRS


def precision_category(label):
    """Vocabulario cerrado: una etiqueta no valida exactitud ni radio de error."""
    if label is None or pd.isna(label) or not str(label).strip():
        return "missing"
    words = set(normalize_header(label).split())
    matches = [name for name, vocabulary in PRECISION_LABEL_WORDS.items() if words & vocabulary]
    return matches[0] if len(matches) == 1 else "other_or_mixed"


def validate_assignment_options(coordinate_crs, crs_confirmed, boundary_review_m,
                                documented_uncertainty_m, uncertainty_evidence_ref, location_role):
    if type(crs_confirmed) is not bool:
        raise ValueError("Confirmación de CRS inválida")
    crs = CRS(coordinate_crs) if coordinate_crs else None
    if crs is not None and crs.to_epsg() not in {4326, 32719}:
        raise ValueError("CRS de puntos no admitido; documentar transformación antes de ampliar")
    if crs is not None and crs.to_epsg() != 4326 and not crs_confirmed:
        raise ValueError("No se transforman coordenadas proyectadas bajo un CRS supuesto")
    for value in (boundary_review_m, documented_uncertainty_m):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("Distancia de revisión inválida")
    if documented_uncertainty_m is not None and not uncertainty_evidence_ref:
        raise ValueError("El margen documentado requiere referencia de evidencia")
    if location_role not in {"unknown", "residence", "notification"}:
        raise ValueError("Significado geográfico no admitido")
    return crs


def prepare_points(frame, coordinate_crs):
    """Reutiliza el parser; nunca invierte ejes, corrige ni completa posiciones."""
    parsed, coordinate_states = [], []
    for x, y in zip(frame.longitude_candidate, frame.latitude_candidate, strict=True):
        x, x_status, _ = parse_coordinate(x)
        y, y_status, _ = parse_coordinate(y)
        if "missing" in (x_status, y_status):
            state = "missing_coordinates"
        elif x_status != "parsed" or y_status != "parsed":
            state = "invalid_coordinates"
        elif coordinate_crs is None:
            state = "unknown_crs"
        elif coordinate_crs.to_epsg() == 4326 and not (-180 <= x <= 180 and -90 <= y <= 90):
            state = "invalid_coordinates"
        else:
            state = "usable"
        coordinate_states.append(state)
        parsed.append(Point(x, y) if state == "usable" else None)
    if coordinate_crs is None:
        return None, coordinate_states
    points = gpd.GeoSeries(parsed, crs=coordinate_crs).to_crs(EXCHANGE_CRS)
    for index, point in enumerate(points):
        if point is not None and (point.is_empty or not math.isfinite(point.x) or not math.isfinite(point.y)):
            coordinate_states[index] = "invalid_coordinates"
            points.iloc[index] = None
    return points, coordinate_states


def spatial_matches(points, radios):
    """Intersects conserva bordes y múltiples radios; within sólo interiores."""
    points_frame = gpd.GeoDataFrame(geometry=points)
    covered, interiors = {}, {}
    for predicate, target in (("intersects", covered), ("within", interiors)):
        joined = gpd.sjoin(points_frame, radios[["radio_id", "geometry"]], how="inner", predicate=predicate)
        for index, group in joined.groupby(level=0, sort=True):
            target[index] = sorted(group.radio_id.tolist())
    return covered, interiors


def possible_radios(point, metric_radios, radius_m):
    """Candidatos por distancia al polígono; el radio es documentado o un sondeo."""
    return sorted(metric_radios.loc[metric_radios.geometry.distance(point).le(radius_m), "radio_id"].tolist())


def assign_coordinates(frame, radios, *, coordinate_crs=EXCHANGE_CRS, crs_confirmed=False,
                       boundary_review_m=None, documented_uncertainty_m=None,
                       uncertainty_evidence_ref=None, location_role="unknown",
                       geocoding_provenance_ref=None, expected_count=EXPECTED_RADIOS):
    validate_radios(radios, expected_count=expected_count)
    validate_metric_extent(radios)
    crs = validate_assignment_options(coordinate_crs, crs_confirmed, boundary_review_m,
                                     documented_uncertainty_m, uncertainty_evidence_ref, location_role)
    frame = frame.reset_index(drop=True)
    required = {"record_ref", "source_id", "sheet_ref", "longitude_candidate", "latitude_candidate"}
    if not required <= set(frame) or frame[list(required - {"longitude_candidate", "latitude_candidate"})].isna().any().any():
        raise ValueError("Derivado normalizado incompleto")
    if frame.duplicated(["source_id", "sheet_ref", "record_ref"]).any():
        raise ValueError("Referencia técnica repetida dentro de una hoja")
    if "eligibility" in frame and not frame.eligibility.isin(["unresolved", "eligible_episode", "excluded"]).all():
        raise ValueError("Elegibilidad fuera del contrato oficial")
    points, coordinate_states = prepare_points(frame, crs)
    geographic = radios.to_crs(EXCHANGE_CRS).reset_index(drop=True)
    metric = radios.to_crs(METRIC_CRS).reset_index(drop=True)
    covered, interiors = spatial_matches(points, geographic) if points is not None else ({}, {})
    metric_points = points.to_crs(METRIC_CRS) if points is not None else None
    keys = [(p.x, p.y) if p is not None else None for p in points] if points is not None else [None] * len(frame)
    counts = Counter(key for key in keys if key is not None)
    group_ids = {key: f"coordinate_{index:06d}" for index, key in enumerate(sorted(counts), 1)}
    rows = []
    for index, record in frame.iterrows():
        matches, inside = covered.get(index, []), interiors.get(index, [])
        coordinate_state = coordinate_states[index]
        geometry_state = coordinate_state
        candidate, distance, alternatives = None, None, []
        alternative_basis, reasons = None, []
        if coordinate_state == "usable":
            if len(matches) > 1:
                geometry_state = "multiple_matches"
            elif len(matches) == 1 and len(inside) == 0:
                geometry_state = "boundary"
            elif len(matches) == 1:
                geometry_state, candidate = "unique_interior", matches[0]
            else:
                geometry_state = "outside_territory"
            # Distancia al límite de TODOS los radios, incluidos límites interiores.
            if matches:
                distance = float(metric.geometry.boundary.distance(metric_points.iloc[index]).min())
                if boundary_review_m is not None and distance <= boundary_review_m:
                    reasons.append("near_boundary_review_scenario")
                radius = documented_uncertainty_m if documented_uncertainty_m is not None else boundary_review_m
                if radius is not None:
                    alternatives = possible_radios(metric_points.iloc[index], metric, radius)
                    alternative_basis = "documented_radius" if documented_uncertainty_m is not None else "review_scenario"
                    if documented_uncertainty_m is not None and distance <= documented_uncertainty_m:
                        reasons.append("documented_radius_reaches_boundary")
        if not crs_confirmed:
            reasons.append("crs_unconfirmed")
        category = precision_category(record.get("coordinate_precision_label"))
        if documented_uncertainty_m is None:
            reasons.append("positional_accuracy_undocumented")
        if category not in {"address_word"}:
            reasons.append("approximate_or_unknown_geocoding_label")
        if not geocoding_provenance_ref:
            reasons.append("geocoding_provenance_undocumented")
        if location_role == "unknown":
            reasons.append("location_meaning_unknown")
        if keys[index] is not None and counts[keys[index]] > 1:
            reasons.append("shared_coordinate_review")
        if geometry_state in {"boundary", "multiple_matches"}:
            state = "ambiguous"
        elif geometry_state == "unique_interior":
            state = "uncertain" if reasons else "unique_geometry"
        else:
            state = "unassigned"
        rows.append({"record_ref": record.record_ref, "source_id": record.source_id,
                     "sheet_ref": record.sheet_ref, "geocoding_category": category,
                     "coordinate_status": coordinate_state, "geometry_status": geometry_state,
                     "radio_candidate": candidate, "assignment_state": state,
                     "matching_radios": matches, "alternative_radios": alternatives,
                     "alternative_basis": alternative_basis, "distance_to_boundary_m": distance,
                     "uncertainty_reasons": sorted(reasons), "coordinate_group_ref": group_ids.get(keys[index]),
                     "coordinate_group_size": counts.get(keys[index], 0),
                     "eligibility": record.get("eligibility", "unresolved"),
                     "location_role": location_role, "epidemiological_precision_validated": False,
                     "crs_confirmed": crs_confirmed})
    return pd.DataFrame(rows)
