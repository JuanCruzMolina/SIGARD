import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import shape

from sigard_ml.presentation.mvp_export import _dump, _read_json, build_artifacts, write_artifacts


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "ml/configs/mvp_export.json"


@pytest.fixture(scope="module")
def result():
    return build_artifacts(_read_json(CONFIG_PATH), ROOT)


def test_selected_week_geojson_contract(result):
    collection = result["prediction"]
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 263
    ids = [feature["properties"]["radio_id"] for feature in collection["features"]]
    assert len(set(ids)) == 263
    required = {"radio_id", "population", "population_density", "prediction_week_start",
                "prediction_week_end", "predicted_cases", "predicted_cases_rounded", "risk_level",
                "simulation_scenario", "model_name", "model_version", "data_scope"}
    assert all(set(feature["properties"]) == required for feature in collection["features"])
    assert all(shape(feature["geometry"]).is_valid for feature in collection["features"])
    assert all(feature["properties"]["predicted_cases"] >= 0 for feature in collection["features"])
    assert "observed_cases_by_radio" not in _dump(collection)


def test_totals_and_four_test_weeks(result):
    summary, backtest = result["summary"], result["backtest"]["weeks"]
    assert summary["prediction_week"]["start"] == "2024-06-23"
    assert summary["number_of_radios"] == 263
    assert len(backtest) == 4
    assert [row["prediction_week_start"] for row in backtest] == ["2024-06-02", "2024-06-09", "2024-06-16", "2024-06-23"]
    assert all(row["number_of_radios"] == 263 for row in backtest)
    assert summary["predicted_cases_radio_sum"] == pytest.approx(backtest[-1]["department_cases_predicted_from_radio_sum"])


def test_risk_is_relative_and_documented(result):
    levels = {feature["properties"]["risk_level"] for feature in result["prediction"]["features"]}
    assert levels.issubset({"very_low", "low", "medium", "high"})
    assert "no es un umbral sanitario oficial" in result["summary"]["configuration"]["risk"]["warning"]


def test_serialization_and_frontend_copies_are_deterministic(tmp_path, result):
    config = _read_json(CONFIG_PATH)
    config["outputs"] = {key: str(tmp_path / Path(value).name) for key, value in config["outputs"].items()}
    config["frontend_copies"] = {key: str(tmp_path / "frontend" / Path(value).name) for key, value in config["frontend_copies"].items()}
    write_artifacts(result, config, ROOT)
    first = {key: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for key, path in config["outputs"].items()}
    write_artifacts(result, config, ROOT, overwrite=True)
    second = {key: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for key, path in config["outputs"].items()}
    assert first == second
    for key, frontend in config["frontend_copies"].items():
        assert (ROOT / frontend).read_bytes() == (ROOT / config["outputs"][key]).read_bytes()
        json.loads((ROOT / frontend).read_text(encoding="utf-8"))


def test_source_geometries_are_epsg_4326_and_valid():
    territorial = gpd.read_parquet(ROOT / "data/processed/territorial_master.parquet")
    assert territorial.crs.to_epsg() == 4326
    assert territorial.geometry.is_valid.all()
