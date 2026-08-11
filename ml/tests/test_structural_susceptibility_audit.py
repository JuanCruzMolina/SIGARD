from __future__ import annotations

import json
from pathlib import Path

import pytest

from sigard_ml.territorial.audit import run

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "ml/configs/structural_susceptibility_audit.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return run(CONFIG, ROOT)


def test_audit_uses_only_real_territorial_features(report):
    assert report["dataset"]["radios"] == 263
    assert report["dataset"]["epidemiological_variables_used"] is False
    assert report["dataset"]["features"] == ["population", "population_density", "households", "dwellings", "area_km2"]


def test_correlation_and_redundancy_contract(report):
    assert set(report["pearson_correlation"]) == set(report["dataset"]["features"])
    assert set(report["spearman_correlation"]) == set(report["dataset"]["features"])
    high_pairs = {(row["method"], row["feature_a"], row["feature_b"]) for row in report["absolute_correlations_over_0_80"]}
    assert ("pearson", "population", "households") in high_pairs
    assert ("spearman", "households", "dwellings") in high_pairs


def test_leave_one_out_and_formula_comparisons_have_valid_sensitivity(report):
    assert set(report["leave_one_feature_out"]) == set(report["dataset"]["features"])
    assert set(report["formula_comparisons"]) == {"A_vs_B_without_area", "A_vs_C_compact", "A_vs_D_demographic_context", "B_vs_C", "B_vs_D", "C_vs_D"}
    for comparison in [*report["leave_one_feature_out"].values(), *report["formula_comparisons"].values()]:
        assert -1 <= comparison["spearman_ranking_correlation"] <= 1
        assert comparison["mean_absolute_position_change"] >= 0
        assert comparison["max_absolute_position_change"] >= comparison["mean_absolute_position_change"]


def test_audit_is_reproducible_and_does_not_rename_index(report):
    assert report == run(CONFIG, ROOT)
    assert report["name_assessment"]["current_name_justified"] is False
    assert report["name_assessment"]["recommended"] == "territorial_context_score"
    assert report["area_assessment"]["directional_assumption_supported"] is False
