from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sigard_ml.evaluation.random_forest_pipeline import RandomForestValidationError, run_random_forest


FEATURES = [
    "population", "households", "dwellings", "area_km2", "population_density",
    "temperature_min_mean", "temperature_max_mean", "temperature_mean",
    "relative_humidity_mean", "precipitation_sum", "synthetic_cases_assigned",
    "cases_lag_1", "cases_lag_2", "cases_lag_3", "cases_rolling_mean_2",
    "cases_rolling_mean_3", "neighbor_cases_lag_1", "neighbor_cases_lag_2",
]


def inputs(tmp_path: Path) -> dict:
    dates = pd.date_range("2024-01-07", periods=6, freq="7D")
    rows = []
    for week, date in enumerate(dates, 1):
        for radio, population in (("a", 100), ("b", 200)):
            cases = (week + (radio == "b")) % 3
            row = {
                "radio_id": radio, "epidemiological_year": 2024,
                "epidemiological_week": week, "week_start_date": date,
                "target_cases_next_week": (cases + 1) % 3,
            }
            row.update({feature: float(index + cases + population / 100) for index, feature in enumerate(FEATURES)})
            row["synthetic_cases_assigned"] = cases
            rows.append(row)
    panel = pd.DataFrame(rows)
    split = pd.DataFrame({"week_start_date": dates, "split": ["train"] * 4 + ["test"] * 2})
    test = panel.loc[panel.week_start_date.isin(dates[-2:])]
    baseline = test[["radio_id", "week_start_date", "target_cases_next_week"]].rename(columns={"week_start_date": "origin_week_start_date"})
    baseline["predicted_cases"] = 0
    base_metrics = {"metrics": {"mae": 1.0, "rmse": 1.0, "mae_target_gt_0": 1.0}, "weekly_metrics": [{"absolute_total_error": 1.0}, {"absolute_total_error": 1.0}]}
    for name, frame in (("panel", panel), ("split", split), ("baseline", baseline)):
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    (tmp_path / "baseline.json").write_text(json.dumps(base_metrics), encoding="utf-8")
    return {
        "pipeline": {"name": "test", "version": "1"},
        "inputs": {"panel": "panel.parquet", "split": "split.parquet", "baseline_predictions": "baseline.parquet", "baseline_metrics": "baseline.json"},
        "data_version": "test", "columns": {"radio_id": "radio_id", "year": "epidemiological_year", "week": "epidemiological_week", "week_start": "week_start_date", "target": "target_cases_next_week"},
        "features": FEATURES, "model": {"n_estimators": 20, "max_depth": 4, "min_samples_split": 2, "min_samples_leaf": 1, "max_features": "sqrt", "random_state": 7, "n_jobs": 1},
        "evaluation": {"near_zero_threshold": 0.5, "expected_test_rows": 4}, "outputs": {},
    }


def test_random_forest_is_reproducible_nonnegative_and_uses_exact_test(tmp_path: Path) -> None:
    config = inputs(tmp_path)
    first, second = run_random_forest(config, tmp_path), run_random_forest(config, tmp_path)
    pd.testing.assert_frame_equal(first[1], second[1])
    pd.testing.assert_frame_equal(first[2], second[2])
    assert first[3] == second[3]
    assert len(first[1]) == 4
    assert first[1]["predicted_cases"].ge(0).all()
    assert set(first[2]["feature"]) == set(FEATURES)


@pytest.mark.parametrize("mutation", ["null", "infinite", "target_feature", "test_overlap"])
def test_invalid_training_contract_is_rejected(tmp_path: Path, mutation: str) -> None:
    config = inputs(tmp_path)
    if mutation in {"null", "infinite"}:
        panel = pd.read_parquet(tmp_path / "panel.parquet")
        panel.loc[0, FEATURES[0]] = np.nan if mutation == "null" else np.inf
        panel.to_parquet(tmp_path / "panel.parquet", index=False)
    elif mutation == "target_feature":
        config = copy.deepcopy(config)
        config["features"].append("target_cases_next_week")
    else:
        split = pd.read_parquet(tmp_path / "split.parquet")
        split.loc[0, "split"] = "test"
        split.to_parquet(tmp_path / "split.parquet", index=False)
    with pytest.raises(RandomForestValidationError):
        run_random_forest(config, tmp_path)
