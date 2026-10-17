"""Fase 5D: auditorías ficticias sin ajustar ni cargar modelos."""

import ast
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn import metrics as skm

from sigard_ml.official.spatial_ml import research_diagnostics as diag


@pytest.mark.parametrize("y,p", [
    ([0, 0, 0, 1], [.25] * 4), ([1, 0, 1, 0], [.8, .2, .8, .1]),
    ([0, 1, 1, 0, 1], [.9, .9, .2, .2, .2]), ([0, 1], [0, 1]),
    ([0, 1, 0, 1], [.5, .5, .5, .5]),
])
def test_independent_rank_ap_confusion_brier_match_sklearn(y, p):
    result = diag.numeric_metrics(y, p)
    assert result["average_precision_pr_auc"] == pytest.approx(skm.average_precision_score(y, p))
    assert result["roc_auc"] == pytest.approx(skm.roc_auc_score(y, p))
    assert result["brier"] == pytest.approx(skm.brier_score_loss(y, p))
    assert result["brier"] == pytest.approx(result["brier_negative_contribution"] + result["brier_positive_contribution"])
    assert result["confusion_matrix_true_rows_predicted_columns_0_1"] == skm.confusion_matrix(y, np.asarray(p) >= .5, labels=[0, 1]).tolist()
    assert result["log_loss"] == pytest.approx(skm.log_loss(y, np.column_stack([1 - np.asarray(p), p]), labels=[0, 1]))


def test_no_positive_predictions_are_distinguished_from_zero_precision():
    result = diag.numeric_metrics([0, 0, 0, 1], [.25] * 4)
    assert result["precision"] is None and result["precision_undefined"]
    assert result["recall"] == result["f1"] == 0
    assert result["average_precision_pr_auc"] == .25
    audit = []
    diag.assert_close("precision", None, 0, audit, "fictional")
    assert audit[0]["matches"]


def test_degenerate_classes_keep_undefined_metrics_explicit():
    negative = diag.numeric_metrics([0, 0], [.1, .2])
    assert negative["roc_auc"] is negative["average_precision_pr_auc"] is negative["recall"] is None
    positive = diag.numeric_metrics([1, 1], [.1, .2])
    assert positive["roc_auc"] is None and positive["average_precision_pr_auc"] == 1


@pytest.mark.parametrize("y,p", [([], []), ([0], [np.nan]), ([0], [1.1]), ([0], [-.1]),
    ([.5, 1], [.2, .6]), ([0, 1], [.2]), ([2], [.5])])
def test_invalid_evaluation_is_rejected(y, p):
    with pytest.raises(ValueError):
        diag.numeric_metrics(y, p)


def test_bin_boundaries_sizes_and_ece_are_deterministic():
    y, p = [0, 1, 0, 1], [0, .1, .9, 1]
    bins = diag.reliability(y, p)
    assert [r["bin"] for r in bins] == [0, 1, 9]
    assert sum(r["n"] for r in bins) == 4
    result = diag.numeric_metrics(y, p)
    assert result["ece_10_uniform_bins_descriptive"] == pytest.approx(sum(
        r["n"] * abs(r["mean_probability"] - r["fraction_positive"]) for r in bins) / 4)


def audit_fixture():
    rows = []
    index = 0
    for part, count in zip(diag.PARTS, (2, 2, 4)):
        for week in range(count):
            target = date(2024, 1, 7) + timedelta(weeks=index)
            index += 1
            for radio in range(6):
                unknown = radio == 5
                y = None if unknown else int((radio + week) % 3 == 0)
                p = [.8, .4, .2, .7, .1, .5][radio]
                rows.append({"partition": part, "fecha_inicio_semana_objetivo": target,
                    "radio_censal": str(radio), "fecha_inicio_semana": target - timedelta(days=7),
                    "objetivo_semana_siguiente": y, "random_forest_A_probability": p,
                    "random_forest_A_predicted": int(p >= .5)})
    frame = pd.DataFrame(rows)
    prior = frame.loc[frame.partition.eq("train"), "objetivo_semana_siguiente"].mean()
    frame["training_prevalence_probability"] = prior
    frame["training_prevalence_predicted"] = int(prior >= .5)
    stored, weekly, calibration = {}, [], []
    for model in diag.MODELS:
        stored[model] = {}
        for part in diag.PARTS:
            group = frame[frame.partition.eq(part)]
            known = group[group.objetivo_semana_siguiente.notna()]
            result = diag.numeric_metrics(known.objetivo_semana_siguiente, known[model + "_probability"])
            stored[model][part] = {k: (0 if k == "precision" and v is None else v) for k, v in result.items()}
            calibration.extend({"model": model, "partition": part, **row} for row in diag.reliability(
                known.objetivo_semana_siguiente, known[model + "_probability"]))
            for week, data in group.groupby("fecha_inicio_semana_objetivo"):
                known = data[data.objetivo_semana_siguiente.notna()]
                result = diag.numeric_metrics(known.objetivo_semana_siguiente, known[model + "_probability"])
                weekly.append({"model": model, "partition": part, "target_week": week, **result})
    return frame, stored, pd.DataFrame(weekly), pd.DataFrame(calibration)


def test_weekly_pooling_and_unknown_exclusion_without_estimators():
    frame, stored, weekly, calibration = audit_fixture()
    result = diag.diagnose_predictions(frame, stored, weekly, calibration)
    summary, weeks, bins, audit, curves, comparison = result
    assert len(summary) == 6 and len(weeks) == 16 and len(curves) == 6 and len(comparison) == 3
    assert all(r["matches"] for r in audit)
    assert next(r for r in summary if r["model"] == diag.MODELS[0] and r["partition"] == "test")["n"] == 20
    assert sum(r["n"] for r in bins if r["model"] == diag.MODELS[0] and r["partition"] == "test") == 20
    assert all(r["unknown_excluded"] == 1 for r in weeks)


@pytest.mark.parametrize("corruption", ["metric", "weekly", "bin", "future_prior"])
def test_inconsistent_saved_results_stop_diagnosis(corruption):
    frame, stored, weekly, calibration = audit_fixture()
    if corruption == "metric":
        stored[diag.MODELS[0]]["test"]["brier"] += .01
    elif corruption == "weekly":
        weekly.loc[0, "tp"] += 1
    elif corruption == "bin":
        calibration.loc[0, "n"] += 1
    else:
        frame["training_prevalence_probability"] = .8
    with pytest.raises(ValueError):
        diag.diagnose_predictions(frame, stored, weekly, calibration)


def test_fixed_cohort_keeps_only_radios_known_in_every_test_week():
    frame, *_ = audit_fixture()
    frame.loc[frame.partition.eq("test") & frame.radio_censal.eq("4") & frame.fecha_inicio_semana_objetivo.eq(
        frame.loc[frame.partition.eq("test"), "fecha_inicio_semana_objetivo"].min()), "objetivo_semana_siguiente"] = np.nan
    rows, stability = diag.matched_test_diagnostics(frame)
    assert stability["matched_known_radios"] == 4
    assert stability["all_test_radios"] == 6
    assert all(r["n"] == 4 for r in rows)
    assert stability["successive_week_correlations"][0]["radios_with_exactly_unchanged_probability"] == 6


def test_roc_pair_decomposition_reconstructs_pooled_auc():
    frame, *_ = audit_fixture()
    rows, summary = diag.roc_week_pair_diagnostics(frame)
    assert len(rows) == 32
    known = frame[frame.partition.eq("test") & frame.objetivo_semana_siguiente.notna()]
    for row in summary:
        assert row["within_week_pair_fraction"] + row["between_weeks_pair_fraction"] == pytest.approx(1)
        actual = skm.roc_auc_score(known.objetivo_semana_siguiente, known[row["model"] + "_probability"])
        assert row["pooled_auc_reconstructed"] == pytest.approx(actual)
        assert row["within_week_pair_fraction"] * row["within_week_auc_weighted_by_pairs"] + row["between_weeks_pair_fraction"] * row["between_weeks_auc_weighted_by_pairs"] == pytest.approx(actual)


def test_exact_density_redundancy_uses_one_row_per_radio():
    frame, *_ = audit_fixture()
    for feature in diag.BASE:
        frame[feature] = frame.radio_censal.astype(int) + 1.0
    frame["superficie_km2"] = frame.radio_censal.astype(int) + 2.0
    frame["densidad_poblacional"] = frame.poblacion / frame.superficie_km2
    importance = pd.DataFrame({"feature": diag.BASE, "importance_mdi": [1 / 7] * 7})
    distributions, correlation, redundancy = diag.feature_diagnostics(frame, importance)
    assert redundancy["unique_radios"] == 6
    assert redundancy["density_identity_max_relative_error"] == 0
    assert redundancy["all_grid_static_distributions_identical_across_partitions"]
    assert all(r["unique_radios"] == 6 for r in correlation)
    assert len(distributions) == 42
    bad = frame.copy(deep=True)
    bad.loc[0, "poblacion"] += 1
    with pytest.raises(ValueError):
        diag.feature_diagnostics(bad, importance)


def test_ecdf_distance_is_descriptive_and_tie_aware():
    assert diag.empirical_ks_distance([1, 1, 2], [1, 1, 2]) == 0
    assert diag.empirical_ks_distance([1, 1], [2, 2]) == 1
    assert diag.empirical_ks_distance([1, 2], [1, 1]) == .5


def test_nested_arrow_confusion_array_and_tamper_detection():
    saved = np.empty(2, dtype=object)
    saved[:] = [np.array([10, 2]), np.array([3, 4])]
    audit = []
    diag.assert_close("confusion", [[10, 2], [3, 4]], saved, audit, "fictional")
    assert audit[0]["matches"]
    with pytest.raises(ValueError):
        diag.assert_close("confusion", [[11, 2], [3, 4]], saved, audit, "fictional")


def test_hash_tamper_rejected(tmp_path):
    path = tmp_path / "fixture.txt"
    path.write_text("frozen", encoding="utf-8")
    mapping = {str(path): diag.digest_path(path)}
    diag.verify_hashes(mapping)
    path.write_text("different", encoding="utf-8")
    with pytest.raises(ValueError):
        diag.verify_hashes(mapping)


@pytest.mark.parametrize("output", ["frontend/public/report", "backend/report", "data/processed/official",
    "data/interim/official/report", diag.DEFAULT_INPUT])
def test_private_new_destination_required(tmp_path, output):
    with pytest.raises(ValueError):
        diag.checked_paths(tmp_path, diag.DEFAULT_INPUT, output)


def test_no_estimator_training_or_loading_calls_in_diagnostic_modules():
    for name in ("research_diagnostics.py", "research_diagnostic_plots.py", "research_diagnostic_report.py"):
        tree = ast.parse(Path(diag.__file__).with_name(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"fit", "fit_transform", "partial_fit", "predict", "predict_proba"}
                assert not (node.func.attr == "load" and isinstance(node.func.value, ast.Name) and node.func.value.id == "joblib")


def test_date_flags_dont_infer_onset_sample_effect_from_global_delay():
    frame, *_ = audit_fixture()
    labels = frame[diag.KEYS].copy()
    labels["objetivo_con_fecha_aproximada"] = False
    labels["pendientes_semana_objetivo"] = 0
    report = diag.date_diagnostics(frame, labels, {"delay_evidence": {"paired_symptom_sample_records": 100},
        "analysis_period": {"start": "2020-01-01", "end": "2024-12-31"}})
    assert all(row["positive_labels_with_approximate_date_flag"] == 0 for row in report["by_partition"])
    assert report["delay_imputation_or_relabeling"] is False
