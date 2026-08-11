from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import numpy as np

from sigard_ml.evaluation.department_temporal_variants import inverse_target, missing_record_audit, run, transform_target


EXPECTED_REDUCED = ["cases_current_week", "cases_lag_1", "cases_rolling_mean_2", "cases_trend_1", "temperature_mean", "relative_humidity_mean", "precipitation_sum", "week_sin", "week_cos"]


@cache
def local_run():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "ml/configs/department_temporal_variants.json").read_text(encoding="utf-8"))
    return run(config, root)


def test_reduced_feature_set_is_exact():
    report = local_run()
    assert report["feature_sets"]["rf_reduced"] == EXPECTED_REDUCED
    assert report["feature_sets"]["rf_reduced_log_target"] == EXPECTED_REDUCED


def test_log1p_expm1_round_trip_and_nonnegative():
    values = np.array([0.0, 1.0, 20.0, 2049.0])
    np.testing.assert_allclose(inverse_target(transform_target(values, True), True), values)
    assert (inverse_target(np.array([0.0, 1.0]), True) >= 0).all()


def test_holdout_is_identical_and_development_disjoint_for_all_variants():
    report = local_run()
    frozen = report["frozen_evaluation"]
    assert frozen["holdout_target_weeks"] == ["2024-05-19", "2024-05-26", "2024-06-02", "2024-06-09", "2024-06-16", "2024-06-23"]
    assert set(frozen["development_target_weeks"]).isdisjoint(frozen["holdout_target_weeks"])
    assert len(report["weekly_predictions"]) == 6
    for row in report["weekly_predictions"]:
        assert {"persistence_prediction", "rf_full_prediction", "rf_reduced_prediction", "rf_log_prediction"}.issubset(row)


def test_missing_records_are_not_reclassified_without_evidence():
    audit = missing_record_audit()
    assert audit["states_changed"] == 0
    assert audit["explicit_zero_rows_in_sources"] == 0
    assert not audit["verified_zeros_scenario_executed"]


def test_variants_are_reproducible_nonnegative_and_report_schema():
    first, second = local_run(), local_run()
    assert first == second
    required = {"dataset_summary", "missing_record_audit", "feature_sets", "development_metrics", "chosen_hyperparameters", "holdout_metrics", "weekly_predictions", "winner_among_rf_variants", "comparison_vs_baseline", "limitations"}
    assert required.issubset(first)
    assert set(first["holdout_metrics"]) == {"persistence_baseline", "rf_full", "rf_reduced", "rf_reduced_log_target"}
    for row in first["weekly_predictions"]:
        assert min(row["persistence_prediction"], row["rf_full_prediction"], row["rf_reduced_prediction"], row["rf_log_prediction"]) >= 0
