from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from sigard_ml.evaluation.department_temporal_pipeline import walk_forward
from sigard_ml.features.department_temporal import build_department_temporal_dataset


FEATURES = [
    "cases_current_week", "cases_lag_1", "cases_lag_2", "cases_lag_3",
    "cases_rolling_mean_2", "cases_rolling_mean_3", "cases_rolling_mean_4",
    "cases_trend_1", "cases_trend_2", "temperature_min_mean",
    "temperature_max_mean", "temperature_mean", "relative_humidity_mean",
    "precipitation_sum", "temperature_mean_lag_1", "relative_humidity_lag_1",
    "precipitation_lag_1", "precipitation_rolling_sum_2",
    "precipitation_rolling_sum_3", "epidemiological_week", "week_sin", "week_cos",
]


def weekly(periods=9):
    dates = pd.date_range("2024-01-07", periods=periods, freq="7D")
    return pd.DataFrame({
        "epidemiological_year": 2024, "epidemiological_week": range(2, 2 + periods),
        "week_start_date": dates, "week_end_date": dates + pd.Timedelta(days=6),
        "epidemiological_status": "observed", "climate_week_complete": True,
        "dengue_cases_observed": np.arange(periods, dtype=float),
        "temperature_min_mean": np.arange(periods) + 10.0,
        "temperature_max_mean": np.arange(periods) + 20.0,
        "temperature_mean": np.arange(periods) + 15.0,
        "relative_humidity_mean": np.arange(periods) + 50.0,
        "precipitation_sum": np.arange(periods, dtype=float),
    })


def test_exact_lags_target_and_cutoff_only_features():
    data, report = build_department_temporal_dataset(weekly(), FEATURES)
    first = data.iloc[0]
    assert len(data) == 5 and report["usable_weeks"] == 5
    assert first["cases_current_week"] == 3
    assert [first[f"cases_lag_{i}"] for i in range(1, 4)] == [2, 1, 0]
    assert first["target_cases_next_week"] == 4
    assert first["temperature_mean"] == 18
    assert first["temperature_mean_lag_1"] == 17
    assert first["target_week"] == first["cutoff_week"] + pd.Timedelta(days=7)
    assert not any("target" in feature for feature in FEATURES)


def test_gap_does_not_create_lags_or_target_across_blocks():
    source = weekly(10).drop(index=[4]).reset_index(drop=True)
    data, _ = build_department_temporal_dataset(source, FEATURES)
    assert pd.Timestamp("2024-01-28") not in set(data.cutoff_week)
    assert pd.Timestamp("2024-02-11") not in set(data.cutoff_week)
    assert all(data.target_week - data.cutoff_week == pd.Timedelta(days=7))


def test_missing_and_outside_are_excluded_not_zero_filled():
    source = weekly(14)
    source.loc[4, ["epidemiological_status", "dengue_cases_observed"]] = ["missing_record", np.nan]
    source.loc[5, ["epidemiological_status", "dengue_cases_observed"]] = ["outside_source_coverage", np.nan]
    data, report = build_department_temporal_dataset(source, FEATURES)
    assert not data["target_cases_next_week"].eq(0).any()
    assert report["excluded_source_status_counts"] == {"missing_record": 1, "outside_source_coverage": 1}


def test_walk_forward_is_reproducible_baseline_correct_and_nonnegative():
    data, _ = build_department_temporal_dataset(weekly(18), FEATURES)
    params = {"n_estimators": 20, "max_depth": 3, "min_samples_split": 2, "min_samples_leaf": 2, "max_features": "sqrt", "random_state": 7, "n_jobs": 1}
    first = walk_forward(data, FEATURES, params, 5, len(data), "test")
    second = walk_forward(data, FEATURES, params, 5, len(data), "test")
    pd.testing.assert_frame_equal(first, second)
    assert first.predicted_cases.ge(0).all()
    expected = data.iloc[5:].cases_current_week.reset_index(drop=True)
    pd.testing.assert_series_equal(first.baseline_predicted_cases, expected, check_names=False)


def test_future_target_mutation_does_not_change_features():
    source = weekly()
    first, _ = build_department_temporal_dataset(source, FEATURES)
    changed = copy.deepcopy(source)
    changed.loc[4, "dengue_cases_observed"] = 9999
    second, _ = build_department_temporal_dataset(changed, FEATURES)
    row1 = first.loc[first.cutoff_week.eq(pd.Timestamp("2024-01-28")), FEATURES]
    row2 = second.loc[second.cutoff_week.eq(pd.Timestamp("2024-01-28")), FEATURES]
    pd.testing.assert_frame_equal(row1, row2)


def test_artifact_schema_on_local_data():
    from pathlib import Path
    import json
    from sigard_ml.evaluation.department_temporal_pipeline import run
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "ml/configs/department_temporal_random_forest.json").read_text(encoding="utf-8"))
    dataset, quality, backtest, summary, _ = run(config, root)
    assert len(dataset) == 32
    assert {"cutoff_week", "target_week", "target_cases_next_week"}.issubset(dataset.columns)
    assert set(backtest) >= {"development", "final_holdout"}
    assert set(summary) >= {"model", "model_variant", "random_state", "features", "observations", "metrics", "baseline_metrics", "feature_importances", "limitations"}
    assert quality["excluded_source_status_counts"] == {"outside_source_coverage": 419, "missing_record": 63}
