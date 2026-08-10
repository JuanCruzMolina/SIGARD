from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sigard_ml.evaluation.random_forest_pipeline import RandomForestValidationError
from sigard_ml.evaluation.random_forest_variants_pipeline import inverse_target, run_variants, transform_target
from test_random_forest_evaluation import FEATURES, inputs


def variants_config(tmp_path: Path) -> dict:
    base = inputs(tmp_path)
    original = {"metrics": {"mae": 1.0, "rmse": 1.0, "mae_target_gt_0": 1.0, "mean_bias": 0.0, "prediction_near_zero_percentage": 100.0}, "weekly_metrics": [{"absolute_total_error": 1.0}]}
    (tmp_path / "original.json").write_text(json.dumps(original), encoding="utf-8")
    return {
        "pipeline": {"name": "test", "version": "1"},
        "inputs": {**base["inputs"], "original_metrics": "original.json"},
        "data_version": "test", "columns": base["columns"],
        "full_features": FEATURES, "reduced_features": FEATURES[-5:],
        "variants": {
            "rf_regularized": {"feature_set": "full", "target_transform": "identity", "parameters": base["model"]},
            "rf_log_target": {"feature_set": "full", "target_transform": "log1p", "parameters": base["model"]},
            "rf_reduced_features": {"feature_set": "reduced", "target_transform": "identity", "parameters": base["model"]},
        },
        "evaluation": {**base["evaluation"], "global_metric_max_relative_deterioration": .1, "positive_mae_max_relative_deterioration": .05},
        "outputs": {},
    }


def test_log_target_is_inverted() -> None:
    values = pd.Series([0.0, 1.0, 3.0, 10.0])
    np.testing.assert_allclose(inverse_target(transform_target(values, "log1p"), "log1p"), values)


def test_variants_keep_exact_test_and_are_reproducible(tmp_path: Path) -> None:
    config = variants_config(tmp_path)
    first, second = run_variants(config, tmp_path), run_variants(config, tmp_path)
    pd.testing.assert_frame_equal(first[1], second[1])
    assert first[2] == second[2] and first[3] == second[3] and first[4] == second[4]
    assert set(first[1].groupby("variant").size()) == {4}
    expected = pd.read_parquet(tmp_path / "baseline.parquet")[["radio_id", "origin_week_start_date"]].sort_values(["origin_week_start_date", "radio_id"]).reset_index(drop=True)
    for _, frame in first[1].groupby("variant"):
        pd.testing.assert_frame_equal(frame[["radio_id", "origin_week_start_date"]].reset_index(drop=True), expected)
    assert first[1].predicted_cases.ge(0).all()
    assert first[0]["model_name"] == first[4]["selected_variant"]


def test_future_week_in_train_is_rejected(tmp_path: Path) -> None:
    config = variants_config(tmp_path)
    split = pd.read_parquet(tmp_path / "split.parquet")
    split.loc[split.index[-1], "split"] = "train"
    split.to_parquet(tmp_path / "split.parquet", index=False)
    with pytest.raises(RandomForestValidationError):
        run_variants(config, tmp_path)


def test_target_feature_leakage_is_rejected(tmp_path: Path) -> None:
    config = copy.deepcopy(variants_config(tmp_path))
    config["full_features"].append("target_cases_next_week")
    with pytest.raises(RandomForestValidationError):
        run_variants(config, tmp_path)
