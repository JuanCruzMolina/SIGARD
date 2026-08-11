from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from sigard_ml.evaluation.department_temporal_delta import add_change_features, reconstruct_cases, run


@cache
def report():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "ml/configs/department_temporal_delta.json").read_text(encoding="utf-8"))
    return run(config, root)


def sample():
    return pd.DataFrame({"cases_current_week": [9.0, 3.0], "cases_lag_1": [4.0, 7.0], "target_cases_next_week": [19.0, 1.0]})


def test_growth_log_growth_and_relative_trend():
    data = add_change_features(sample())
    assert data.growth_ratio.tolist() == [2.0, 0.5]
    np.testing.assert_allclose(data.log_growth, np.log([2.0, 0.5]))
    np.testing.assert_allclose(data.relative_trend_1, [1.0, -0.5])
    np.testing.assert_allclose(data.log_cases_current, np.log([10.0, 4.0]))


def test_target_log_delta_and_reconstruction():
    data = add_change_features(sample())
    expected = np.log([20.0, 2.0]) - np.log([10.0, 4.0])
    np.testing.assert_allclose(data.target_log_delta, expected)
    np.testing.assert_allclose(reconstruct_cases(data.cases_current_week.to_numpy(), expected), data.target_cases_next_week)
    assert reconstruct_cases(np.array([1.0]), np.array([-10.0]))[0] == 0.0


def test_derived_features_do_not_depend_on_future_target():
    first = add_change_features(sample())
    changed = sample(); changed["target_cases_next_week"] = [9999.0, 8888.0]
    second = add_change_features(changed)
    columns = ["log_cases_current", "growth_ratio", "log_growth", "relative_trend_1"]
    pd.testing.assert_frame_equal(first[columns], second[columns])


def test_same_holdout_nonnegative_reproducible_and_schema():
    first, second = report(), report()
    assert first == second
    assert first["splits"]["development_weeks_sha256"] == "0288f16b6a7a948370eb2c5a2dc9cd3414500c0571c089da4caed48d99c0cd00"
    assert first["splits"]["holdout_weeks_sha256"] == "6faaa71b6cb338ba30a773d6162c5c98ed2ac6c2c074857944168fda1d4c315f"
    assert first["splits"]["holdout_target_weeks"] == ["2024-05-19", "2024-05-26", "2024-06-02", "2024-06-09", "2024-06-16", "2024-06-23"]
    required = {"dataset", "splits", "feature_sets", "target_definitions", "development_metrics", "selected_hyperparameters", "holdout_metrics", "weekly_predictions", "direction_analysis", "comparison_vs_baseline", "limitations"}
    assert required.issubset(first)
    for row in first["weekly_predictions"]:
        predictions = [value for key, value in row.items() if key.endswith("_prediction")]
        assert predictions and min(predictions) >= 0 and np.isfinite(predictions).all()
