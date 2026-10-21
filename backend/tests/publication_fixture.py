"""Deterministic public-contract fixtures; no source data, models or cartography.

Only pytest's temporary directory receives generated JSON/GeoJSON. The existing
contract requires 263 radios; one week is the smallest complete temporal batch.
"""

from copy import deepcopy
import json


CUTOFF = "2030-01-05"
START = "2030-01-06"
END = "2030-01-12"
CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}


def publication_documents():
    territorial = []
    experimental = []
    for index in range(263):
        # Disjoint squares in an arbitrary test grid, unrelated to La Rioja.
        x = round(10 + (index % 20) * 0.002, 6)
        y = round(10 + (index // 20) * 0.002, 6)
        ring = [[x, y], [round(x + 0.001, 6), y],
                [round(x + 0.001, 6), round(y + 0.001, 6)],
                [x, round(y + 0.001, 6)], [x, y]]
        geometry = {"type": "Polygon", "coordinates": [ring]}
        # Exercise both geometry types admitted by the existing contract.
        if index == 262:
            geometry = {"type": "MultiPolygon", "coordinates": [[ring]]}
        radio_id = f"TEST-{index:04d}"
        territorial.append({"type": "Feature", "geometry": geometry, "properties": {
            "radio_id": radio_id, "population": 100 + index,
            "population_density": 10.5, "households": 40, "dwellings": 45,
            "area_km2": 10.0, "demographic_residential_component": 0.5,
            "density_component": 0.5, "territorial_context_score": 0.5,
            "percentile": 50.0, "relative_level": "medium",
        }})
        experimental.append({"type": "Feature", "geometry": deepcopy(geometry), "properties": {
            "radio_id": radio_id, "cutoff_date": CUTOFF, "target_week_start": START,
            "target_week_end": END, "experimental_spatial_score": 0.25,
            "percentile": 50.0, "relative_level": "medium",
            "synthetic_scenario": "fictitious-import-only-v1",
        }})
    return {
        "available_weeks.json": {"default_cutoff_date": CUTOFF, "weeks": [{
            "cutoff_date": CUTOFF, "target_week_start": START, "target_week_end": END,
            "cutoff_label": CUTOFF, "target_week_label": f"{START} a {END}",
            "has_temporal_prediction": True, "has_experimental_spatial": True,
        }]},
        "temporal_predictions.json": {"model": {"name": "fictitious-no-model", "version": "test-v1"},
            "predictions": [{"cutoff_date": CUTOFF, "target_week_start": START,
                "target_week_end": END, "predicted_cases": 2.5, "predicted_cases_rounded": 2,
                "official_cases": None, "absolute_error": None,
                "persistence_prediction": None, "persistence_absolute_error": None}]},
        "territorial_context.geojson": {"type": "FeatureCollection", "crs": deepcopy(CRS), "features": territorial},
        "experimental_spatial_history.geojson": {"type": "FeatureCollection", "crs": deepcopy(CRS), "features": experimental},
        "model_evaluation.json": {"model": {"name": "fictitious-no-model"}, "metrics": {}, "backtest": []},
        "mvp_metadata.json": {
            "project": "SIGARD-test-only", "territory": "Fictitious grid",
            "prototype_status": "test-only", "data_type": "synthetic",
            "fixture_version": "territorial-import-v1", "transformation_version": "deterministic-grid-v1",
            "provenance": "Generated from constants; no source files or trained models",
            "period": {"start": START, "end": END}, "unit": "fictitious-radio-week",
            "crs": "EPSG:4326", "territorial_context": {"data_type": "synthetic"},
            "experimental_spatial": {"data_type": "synthetic", "scenario": "fictitious-import-only-v1"},
            "disclaimers": {"test_only": "Entirely fictitious; no epidemiological evidence."},
        },
    }


def write_publication(folder, documents):
    folder.mkdir(parents=True, exist_ok=True)
    for filename, document in documents.items():
        (folder / filename).write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return folder
