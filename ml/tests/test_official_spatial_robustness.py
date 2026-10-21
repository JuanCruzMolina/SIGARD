"""Fictitious paired experiments; no estimator fitting or serialized models."""

import ast
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sigard_ml.official.spatial_ml import robustness as rob
from sigard_ml.official.spatial_ml.robustness_report import write_report


def fixture():
    rows = []
    for j, part in enumerate(rob.PARTS):
        for w in range(2):
            target = date(2024, 1, 7) + timedelta(weeks=j * 3 + w)
            for radio, y in enumerate([0, 1, 0, 1, None]):
                pa, pb = [.2, .6, .8, .4, .1][radio], [.1, .7, .3, .8, .5][radio]
                rows.append({"radio_censal": str(radio), "fecha_inicio_semana": target - timedelta(days=7),
                    rob.TARGET: target, "partition": part, rob.LABEL: y,
                    "random_forest_A_probability": pa, "random_forest_A_predicted": int(pa >= .5),
                    "random_forest_B_probability": pb, "random_forest_B_predicted": int(pb >= .5),
                    "training_prevalence_probability": .5, "training_prevalence_predicted": 1})
    frame = pd.DataFrame(rows)
    summary, weekly, bins = [], [], []
    for part in rob.PARTS:
        grid = frame[frame.partition.eq(part)]
        for model in rob.MODELS:
            summary.append({"model": model, "partition": part, **rob.evaluate_group(grid, model)})
            known = grid[grid[rob.LABEL].notna()]
            bins.extend({"model": model, "partition": part, **r} for r in rob.reliability(known[rob.LABEL], known[model + "_probability"]))
            for week, group in grid.groupby(rob.TARGET):
                weekly.append({"model": model, "partition": part, "target_week": str(week), **rob.evaluate_group(group, model)})
    return frame, pd.DataFrame(summary), pd.DataFrame(weekly), pd.DataFrame(bins)


def test_paired_metrics_unknowns_temporal_sensitivity_and_no_mutation():
    args = fixture()
    before = args[0].copy(deep=True)
    data = rob.analyze(*args)
    pd.testing.assert_frame_equal(args[0], before)
    assert len(data["partition_metrics"]) == 9
    assert len(data["weekly_metrics"]) == 18
    assert all(r["matches"] for r in data["frozen_consistency"])
    assert all(r["n"] == 8 and r["unknown_excluded"] == 2 for r in data["partition_metrics"])
    assert all(r["n"] == 4 for r in data["leave_one_week_out"])
    assert all(r["exactly_unchanged"] == 5 for r in data["successive_weeks"])
    assert all(r["only_B_correct"] == 4 and r["only_A_correct"] == 0 for r in data["paired_errors"])
    assert all(r["brier_skill"] > 0 for r in data["baseline_comparison"] if r["model"] == rob.MODELS[1])
    assert data["auc_temporal_decomposition"][1]["pooled_auc_reconstructed"] == 1
    known = next(r for r in data["score_distributions"] if r["population"] == "known_labels")
    all_grid = next(r for r in data["score_distributions"] if r["population"] == "all_radios")
    assert known["n"] == 4 and all_grid["n"] == 5 and known["mean"] != all_grid["mean"]


@pytest.mark.parametrize("kind", ["metric", "weekly", "bin", "baseline", "class", "duplicate", "future", "score", "label", "missing_grid"])
def test_incompatible_or_changed_results_rejected(kind):
    frame, summary, weekly, bins = fixture()
    if kind == "metric":
        summary.loc[0, "brier"] += .01
    elif kind == "weekly":
        weekly.loc[0, "n"] += 1
    elif kind == "bin":
        bins.loc[0, "n"] += 1
    elif kind == "baseline":
        frame.training_prevalence_probability = .49
    elif kind == "class":
        frame.loc[0, "random_forest_A_predicted"] = 1
    elif kind == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif kind == "future":
        frame.loc[0, rob.TARGET] += timedelta(days=7)
    elif kind == "score":
        frame.loc[0, "random_forest_B_probability"] = np.inf
    elif kind == "label":
        frame.loc[0, rob.LABEL] = .5
    else:
        frame = frame.drop(index=0)
    with pytest.raises((ValueError, KeyError)):
        rob.analyze(frame, summary, weekly, bins)


def test_no_labels_and_no_alerts_preserve_undefined_values():
    frame, *_ = fixture()
    frame[rob.LABEL] = np.nan
    result = rob.evaluate_group(frame, rob.MODELS[0])
    assert result["n"] == 0 and result["brier"] is result["precision"] is None
    assert result["unknown_excluded"] == len(frame)
    frame.loc[0, rob.LABEL] = 0
    frame.loc[1, rob.LABEL] = 1
    frame["random_forest_A_probability"] = .1
    result = rob.evaluate_group(frame, rob.MODELS[0])
    assert result["precision"] is None and result["recall"] == 0


def test_artifact_snapshot_detects_change_without_following_sources(tmp_path):
    folder = tmp_path / "authorized"
    folder.mkdir()
    p = folder / "metrics.txt"
    p.write_text("frozen")
    before = rob.snapshot([folder])
    p.write_text("modified")
    assert rob.snapshot([folder]) != before


def test_private_report_reconciles_results_and_has_no_network_assets(tmp_path):
    data = rob.analyze(*fixture())
    write_report(tmp_path, data, False)
    html = (tmp_path / "report.private.html").read_text(encoding="utf-8")
    assert "pendiente de revisión humana" in html
    assert "Sólo B correcto" in html and "0.0000" in html
    assert "<script" not in html and '<img src="http' not in html
    assert "positivos son provisionales" in html and "prueba ya consultada" in html


def test_report_narrative_uses_fixture_metrics_instead_of_fixed_conclusions(tmp_path):
    data = rob.analyze(*fixture())
    write_report(tmp_path, data, False)
    summary = (tmp_path / "summary.private.md").read_text(encoding="utf-8")
    assert "Precision 0.5000→1.0000 y F1 0.5000→1.0000" in summary
    assert "pero reduce Precision" not in summary
    assert "ninguno mejora su error probabilístico" not in summary
    assert "sobreestimación media, mayor en B" not in summary


def test_report_preserves_undefined_metrics_without_crashing(tmp_path):
    data = rob.analyze(*fixture())
    for row in data["partition_metrics"]:
        for key in ("precision", "recall", "f1", "average_precision_pr_auc", "roc_auc", "brier", "mean_probability", "prevalence", "fp", "fn", "tp", "predicted_positive", "positive"):
            row[key] = None
    write_report(tmp_path, data, False)
    assert "AP ND→ND" in (tmp_path / "summary.private.md").read_text(encoding="utf-8")


def test_new_modules_never_train_or_run_model_inference():
    for name in ("robustness.py", "robustness_report.py", "robustness_plots.py"):
        tree = ast.parse(Path(rob.__file__).with_name(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"fit", "fit_transform", "partial_fit", "predict", "predict_proba"}
                assert not (node.func.attr == "load" and isinstance(node.func.value, ast.Name) and node.func.value.id == "joblib")
