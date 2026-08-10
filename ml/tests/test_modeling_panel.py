from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sigard_ml.features.pipeline import run_pipeline, write_outputs
from sigard_ml.features.radio_week import add_neighbor_features, add_temporal_features
from sigard_ml.validation.modeling_panel import ModelingPanelValidationError, validate_inputs


def base_panel() -> pd.DataFrame:
    rows = []
    for radio, cases in (("1", [1, 2, 3, 4, 5]), ("2", [10, 20, 30, 40, 50])):
        for index, value in enumerate(cases):
            start = pd.Timestamp("2024-01-07") + pd.Timedelta(weeks=index)
            rows.append({"radio_id": radio, "week_start_date": start, "synthetic_cases_assigned": value})
    return pd.DataFrame(rows)


def test_temporal_features_use_exact_consecutive_dates() -> None:
    panel = base_panel()
    result = add_temporal_features(panel, [1, 2, 3], [2, 3], 1)
    row = result.loc[(result.radio_id == "1") & (result.week_start_date == pd.Timestamp("2024-01-28"))].iloc[0]
    assert (row.cases_lag_1, row.cases_lag_2, row.cases_lag_3) == (3, 2, 1)
    assert row.cases_rolling_mean_3 == 2
    assert row.target_cases_next_week == 5
    gapped = panel.loc[panel.week_start_date.ne(pd.Timestamp("2024-01-21"))]
    result = add_temporal_features(gapped, [1, 2, 3], [2, 3], 1)
    row = result.loc[(result.radio_id == "1") & (result.week_start_date == pd.Timestamp("2024-01-28"))].iloc[0]
    assert pd.isna(row.cases_lag_1)


def test_neighbor_features_only_use_declared_neighbors_and_past() -> None:
    edges = pd.DataFrame({"radio_id": ["1", "2"], "neighbor_id": ["2", "1"]})
    result = add_neighbor_features(base_panel(), edges, [1, 2], "mean")
    row = result.loc[(result.radio_id == "1") & (result.week_start_date == pd.Timestamp("2024-01-28"))].iloc[0]
    assert row.neighbor_cases_lag_1 == 30
    assert row.neighbor_cases_lag_2 == 20


def config() -> dict:
    return {
        "pipeline": {"name": "test", "version": "1"},
        "inputs": {"territorial": "in/territorial.parquet", "weekly": "in/weekly.parquet", "synthetic": "in/synthetic.parquet"},
        "columns": {"radio_id": "rid", "population": "pop", "households": "hh", "dwellings": "dw", "area_km2": "area", "population_density": "density", "neighbors": "neighbors", "year": "year", "week": "week", "week_start": "start", "week_end": "end", "cases": "cases"},
        "climate_columns": ["tmin", "tmax", "tmean", "humidity", "rain"],
        "features": {"case_lags": [1, 2, 3], "rolling_windows": [2, 3], "neighbor_lags": [1, 2], "neighbor_aggregation": "mean", "target_horizon_weeks": 1},
        "training_requirements": {"required_columns": ["cases_lag_1", "cases_lag_2", "cases_lag_3", "cases_rolling_mean_2", "cases_rolling_mean_3", "neighbor_cases_lag_1", "neighbor_cases_lag_2", "target_cases_next_week"]},
        "universe": {"expected_radio_count": 2},
        "outputs": {"full_panel": "out/full.parquet", "modeling_panel": "out/model.parquet", "quality_report": "out/report.json"},
    }


def test_pipeline_integration_filters_history_and_is_deterministic(tmp_path: Path) -> None:
    cfg = config()
    input_dir = tmp_path / "in"; input_dir.mkdir()
    territorial = pd.DataFrame({"rid": ["1", "2"], "pop": [100, 200], "hh": [40, 80], "dw": [50, 90], "area": [1.0, 2.0], "density": [100.0, 100.0], "neighbors": [["2"], ["1"]]})
    starts = pd.date_range("2024-01-07", periods=5, freq="7D")
    weekly = pd.DataFrame({"year": [2024] * 5, "week": range(1, 6), "start": starts, "end": starts + pd.Timedelta(days=6), "tmin": [1.] * 5, "tmax": [2.] * 5, "tmean": [1.5] * 5, "humidity": [60.] * 5, "rain": [0.] * 5})
    synthetic = pd.DataFrame([{"year": 2024, "week": week, "start": start, "end": start + pd.Timedelta(days=6), "rid": radio, "cases": week * int(radio)} for week, start in zip(range(1, 6), starts) for radio in ("1", "2")])
    territorial.to_parquet(input_dir / "territorial.parquet", index=False); weekly.to_parquet(input_dir / "weekly.parquet", index=False); synthetic.to_parquet(input_dir / "synthetic.parquet", index=False)
    first = run_pipeline(cfg, tmp_path)
    second = run_pipeline(cfg, tmp_path)
    pd.testing.assert_frame_equal(first[0], second[0])
    assert len(first[0]) == 10
    assert len(first[1]) == 2
    assert first[2]["quality"]["leakage_checks_passed"] is True
    write_outputs(*first, cfg, tmp_path)
    assert json.loads((tmp_path / "out/report.json").read_text(encoding="utf-8"))["rows"]["modeling_panel"] == 2
    with pytest.raises(FileExistsError):
        write_outputs(*first, cfg, tmp_path)


def test_input_validation_rejects_duplicate_keys() -> None:
    cfg = config()
    territorial = pd.DataFrame({"rid": ["1", "2"], "pop": [1, 1], "hh": [1, 1], "dw": [1, 1], "area": [1., 1.], "density": [1., 1.], "neighbors": [["2"], ["1"]]})
    weekly = pd.DataFrame({"year": [2024], "week": [1], "start": pd.to_datetime(["2024-01-07"]), "end": pd.to_datetime(["2024-01-13"]), "tmin": [1.], "tmax": [2.], "tmean": [1.5], "humidity": [60.], "rain": [0.]})
    synthetic = pd.DataFrame({"rid": ["1", "1"], "year": [2024, 2024], "week": [1, 1], "start": pd.to_datetime(["2024-01-07"] * 2), "end": pd.to_datetime(["2024-01-13"] * 2), "cases": [0, 0]})
    with pytest.raises(ModelingPanelValidationError, match="duplicadas"):
        validate_inputs(territorial, weekly, synthetic, cfg)
