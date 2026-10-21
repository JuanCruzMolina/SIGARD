"""Descriptive A/B robustness from frozen authorized experiments; never fit/load models."""

import argparse
from contextlib import ExitStack
from io import BytesIO
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.spatial_pipeline import digest_path
from sigard_ml.official.spatial_ml.research_diagnostics import (
    NO_FIT_TARGETS, PARTS, assert_close, audit_sklearn, checked_paths,
    numeric_metrics, read_json, reliability, roc_week_pair_diagnostics, verify_manifest,
)

VERSION = "official-spatial-robustness-1.0"
A = "data/processed/official/spatial_rf_05c_v1"
B = "data/processed/official/spatial_rf_B_05f_v1"
REGISTRY = "data/interim/official/spatial_app_session_v1/registry.private.json"
OUTPUT = "data/processed/official/spatial_robustness_v1"
MODELS = ("random_forest_A", "random_forest_B", "training_prevalence")
KEYS = ["radio_censal", "fecha_inicio_semana"]
TARGET = "fecha_inicio_semana_objetivo"
LABEL = "objetivo_semana_siguiente"
SIX = ("precision", "recall", "f1", "average_precision_pr_auc", "roc_auc", "brier")
CORE = ["n", "positive", "negative", "prevalence", "threshold", *SIX,
        "tn", "fp", "fn", "tp", "predicted_positive", "mean_probability",
        "calibration_gap_mean_probability_minus_prevalence", "ece_10_uniform_bins_descriptive",
        "brier_negative_contribution", "brier_positive_contribution"]


def evaluate_group(group, model):
    known = group[group[LABEL].notna()]
    # No denominator is fabricated for a week without labels.
    if known.empty:
        result = {key: None for key in CORE}
        result.update(n=0, positive=0, negative=0, threshold=.5)
    else:
        result = numeric_metrics(known[LABEL], known[model + "_probability"])
    return {**result, "grid_rows": len(group), "unknown_excluded": len(group) - len(known),
            "mean_probability_all_radios": float(group[model + "_probability"].mean())}


def analyze(frame, frozen, frozen_weekly, frozen_bins):
    """Pure analysis; no paths, fitting, threshold search, label construction or imputation."""
    frame = frame.copy(deep=True)
    if (frame.duplicated(KEYS).any() or frame[KEYS + [TARGET, "partition"]].isna().any().any()
            or set(frame.partition) != set(PARTS)
            or not frame[LABEL].dropna().isin([0, 1]).all()):
        raise ValueError("Invalid experimental keys, partitions or labels")
    origins = pd.to_datetime(frame[KEYS[1]])
    targets = pd.to_datetime(frame[TARGET])
    if not ((targets - origins).dt.days.eq(7).all() and targets.dt.dayofweek.eq(6).all()
            and frame.groupby(TARGET).partition.nunique().eq(1).all()):
        raise ValueError("Invalid frozen temporal alignment")
    for model in MODELS:
        p = frame[model + "_probability"].to_numpy(float)
        if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
            raise ValueError("Invalid frozen scores")
        if not np.array_equal(frame[model + "_predicted"], (p >= .5).astype(int)):
            raise ValueError("Frozen class differs from fixed threshold")
    prior = frame.loc[frame.partition.eq("train"), LABEL].mean()
    if not np.isfinite(prior) or not np.allclose(frame.training_prevalence_probability, prior, rtol=0, atol=1e-15):
        raise ValueError("Baseline is not the frozen training prior")
    summary, weekly, bins, audit, distributions, transitions, stability, omitted, paired = ([] for _ in range(9))
    for part in PARTS:
        grid = frame[frame.partition.eq(part)]
        weeks = sorted(grid[TARGET].unique())
        for model in MODELS:
            result = evaluate_group(grid, model)
            summary.append({"model": model, "partition": part, **result})
            known = grid[grid[LABEL].notna()]
            if len(known):
                if known[LABEL].nunique() == 2:
                    audit_sklearn(known[LABEL], known[model + "_probability"], result, audit, model + ":" + part)
                bins.extend({"model": model, "partition": part, **r}
                            for r in reliability(known[LABEL], known[model + "_probability"]))
            for week, group in grid.groupby(TARGET, sort=True):
                row = evaluate_group(group, model)
                weekly.append({"model": model, "partition": part, "target_week": str(week), **row})
                for population, data in (("all_radios", group), ("known_labels", group[group[LABEL].notna()])):
                    if data.empty:
                        continue
                    p = data[model + "_probability"]
                    distributions.append({"model": model, "partition": part, "target_week": str(week),
                        "population": population, "n": len(data), "mean": float(p.mean()),
                        "sd_population": float(p.std(ddof=0)), "min": float(p.min()), "max": float(p.max()),
                        "q10": float(p.quantile(.1)), "median": float(p.median()), "q90": float(p.quantile(.9)),
                        "fraction_ge_0_5": float(p.ge(.5).mean()), "fraction_ge_0_75": float(p.ge(.75).mean())})
            pivot = grid.pivot(index=KEYS[0], columns=TARGET, values=model + "_probability")
            if pivot.isna().any().any():
                raise ValueError("Incomplete common inference grid")
            for before, after in zip(pivot.columns[:-1], pivot.columns[1:]):
                delta = pivot[after] - pivot[before]
                transitions.append({"model": model, "partition": part, "before": str(before), "after": str(after),
                    "n_radios": len(pivot), "exactly_unchanged": int(delta.eq(0).sum()),
                    "mean_absolute_change": float(delta.abs().mean()), "max_absolute_change": float(delta.abs().max())})
            for week in weeks:
                remaining = grid[grid[TARGET].ne(week)]
                if remaining.empty:
                    continue
                omitted.append({"model": model, "partition": part, "omitted_week": str(week),
                                **evaluate_group(remaining, model)})
            rows = [r for r in weekly if r["model"] == model and r["partition"] == part]
            for metric in SIX:
                values = [r[metric] for r in rows if r[metric] is not None]
                stability.append({"model": model, "partition": part, "metric": metric, "n_weeks": len(rows),
                    "defined_weeks": len(values), "pooled": result[metric],
                    "weekly_min": min(values) if values else None, "weekly_max": max(values) if values else None,
                    "weekly_macro_mean": float(np.mean(values)) if values else None})
            for key in ("n", "positive", "negative", "tp", "fp", "tn", "fn", "grid_rows", "unknown_excluded"):
                if all(r[key] is not None for r in rows):
                    assert_close(key, sum(r[key] for r in rows), result[key], audit, "weekly_sum:" + model + part)
            if result["n"]:
                assert_close("brier", sum(r["n"] * r["brier"] for r in rows if r["n"]) / result["n"],
                             result["brier"], audit, "weekly_weighted:" + model + part)
        known = grid[grid[LABEL].notna()]
        a, b, y = known.random_forest_A_predicted, known.random_forest_B_predicted, known[LABEL]
        paired.append({"partition": part, "n": len(known), "both_correct": int((a.eq(y) & b.eq(y)).sum()),
            "only_A_correct": int((a.eq(y) & b.ne(y)).sum()), "only_B_correct": int((a.ne(y) & b.eq(y)).sum()),
            "both_wrong": int((a.ne(y) & b.ne(y)).sum())})
    # Compare every saved scalar used here, including undefined values and denominators.
    for computed, stored, keys, fields in (
        (summary, frozen, ["model", "partition"], CORE + ["grid_rows", "unknown_excluded", "mean_probability_all_radios"]),
        (weekly, frozen_weekly, ["model", "partition", "target_week"], CORE + ["grid_rows", "unknown_excluded", "mean_probability_all_radios"]),
        (bins, frozen_bins, ["model", "partition", "bin"], ["n", "positive", "mean_probability", "fraction_positive"]),
    ):
        saved = stored.copy()
        if "target_week" in keys:
            saved["target_week"] = pd.to_datetime(saved.target_week).dt.strftime("%Y-%m-%d")
            for row in computed:
                row["target_week"] = str(row["target_week"])[:10]
        if saved.duplicated(keys).any() or len(saved) != len(computed):
            raise ValueError("Frozen summary keys differ")
        lookup = {tuple(row[k] for k in keys): row for row in saved.to_dict("records")}
        for row in computed:
            old = lookup[tuple(row[k] for k in keys)]
            for key in fields:
                assert_close(key, row[key], old[key], audit, "frozen:" + str(tuple(row[k] for k in keys)))
    comparison = []
    for part in PARTS:
        base = next(r for r in summary if r["model"] == MODELS[2] and r["partition"] == part)
        for model in MODELS[:2]:
            row = next(r for r in summary if r["model"] == model and r["partition"] == part)
            comparison.append({"model": model, "partition": part, "n": row["n"],
                **{"delta_" + key: row[key] - base[key] if row[key] is not None and base[key] is not None else None for key in SIX},
                "brier_skill": 1 - row["brier"] / base["brier"] if base["brier"] else None})
    # Reuse audited temporal AUC decomposition, substituting B only in memory.
    auc = []
    if frame.loc[frame.partition.eq("test"), LABEL].dropna().nunique() == 2:
        for model in MODELS[:2]:
            projection = frame.copy()
            projection["random_forest_A_probability"] = frame[model + "_probability"]
            _, decomposition = roc_week_pair_diagnostics(projection)
            auc.append({**decomposition[0], "model": model})
    return {"partition_metrics": summary, "weekly_metrics": weekly, "calibration_bins": bins,
            "frozen_consistency": audit, "baseline_comparison": comparison, "score_distributions": distributions,
            "successive_weeks": transitions, "weekly_stability": stability, "leave_one_week_out": omitted,
            "paired_errors": paired, "auc_temporal_decomposition": auc}


def snapshot(folders):
    # Only the two authorized experiment directories, never inherited source paths.
    return {str(p): digest_path(p) for folder in folders for p in folder.iterdir() if p.is_file()}


def run(root, output_dir=OUTPUT, plot_python=None):
    root = Path(root).resolve()
    require_branch(root)
    source, output = checked_paths(root, B, output_dir)
    _, _ = checked_paths(root, A, output_dir)
    folders = [root / A, source]
    before = snapshot(folders)
    registry_path = root / REGISTRY
    registry_hash = digest_path(registry_path)
    registry = read_json(registry_path)
    if registry.get("local_read_authorized") is not True:
        raise ValueError("Existing local read authorization missing")
    manifests = {}
    for model, folder in zip(("A", "B"), folders):
        if digest_path(folder / "integrity_manifest.private.json") != registry["models"][model]["manifest_sha256"]:
            raise ValueError("Experiment differs from authorized registry")
        manifests[model] = verify_manifest(folder)
    # Read and decode the same hash-checked bytes; explicit file allowlist, no inherited sources.
    def read(model, name, parquet=False):
        folder = folders[0 if model == "A" else 1]
        data = (folder / name).read_bytes()
        import hashlib
        if hashlib.sha256(data).hexdigest() != manifests[model]["outputs_sha256"][name]:
            raise ValueError("Frozen artifact changed during read")
        return pd.read_parquet(BytesIO(data)) if parquet else json.loads(data)
    review_a, review_b = read("A", "review.private.json"), read("B", "review.private.json")
    if not (review_a["training_authorized"] is False and review_a["coverage_verified"] is False
            and review_b["training_authorized"] is False and review_b["test_previously_examined"] is True
            and review_b["operational_model_enabled"] is False and review_b["threshold"] == .5):
        raise ValueError("Frozen methodological contract differs")
    a = read("A", "predictions_radio_week.private.parquet", True).sort_values(KEYS).reset_index(drop=True)
    b = read("B", "predictions_radio_week.private.parquet", True).sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b[a.columns], check_exact=True)
    # Exact approved split dates, weeks and grid from the pre-existing contracts.
    expected = {"train": pd.date_range("2024-01-07", periods=8, freq="7D"),
                "validation": pd.date_range("2024-03-10", periods=8, freq="7D"),
                "test": pd.date_range("2024-05-12", periods=4, freq="7D")}
    for part, dates in expected.items():
        group = b[b.partition.eq(part)]
        if set(pd.to_datetime(group[TARGET])) != set(dates) or not group.groupby(TARGET).size().eq(263).all():
            raise ValueError("Frozen approved population or dates differ")
    tables = analyze(b, read("B", "metrics.private.parquet", True),
                     read("B", "weekly_metrics.private.parquet", True), read("B", "calibration.private.parquet", True))
    # Cross-check against original A/baseline metrics, not just their B copies.
    original = read("A", "metrics.private.json")
    for row in tables["partition_metrics"]:
        if row["model"] in original:
            for key in SIX:
                assert_close(key, row[key], original[row["model"]][row["partition"]][key],
                             tables["frozen_consistency"], "original_A")
    if snapshot(folders) != before or digest_path(registry_path) != registry_hash:
        raise ValueError("Existing artifacts changed")
    output.mkdir()
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(output / (name + ".private.csv"), index=False)
    # JSON conversion preserves undefined values as null, never NaN.
    payload = {name: json.loads(pd.DataFrame(rows).to_json(orient="records", double_precision=15)) for name, rows in tables.items()}
    (output / "analysis.private.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    metadata = {"version": VERSION, "analysis_kind": "descriptive_exploratory_not_independent_validation",
        "training_performed": False, "models_loaded": False, "threshold": .5, "calibration_fitted": False,
        "labels_modified": False, "frontend_modified": False, "human_review": "pending", "publication_authorized": False,
        "registry_sha256": registry_hash, "input_files_sha256": before,
        "packages": {name: importlib.metadata.version(name) for name in ("pandas", "numpy", "scipy", "scikit-learn", "pyarrow")},
        "source_code_sha256": {p.name: digest_path(p) for p in Path(__file__).parent.glob("robustness*.py")}}
    from sigard_ml.official.spatial_ml.robustness_report import write_report
    if plot_python:
        subprocess.run([str((root / plot_python).resolve()), "-B", str(Path(__file__).with_name("robustness_plots.py")),
                        str(output / "analysis.private.json")], cwd=root, check=True)
    write_report(output, payload, bool(plot_python))
    if snapshot(folders) != before or digest_path(registry_path) != registry_hash:
        raise ValueError("Existing artifacts changed")
    metadata["protected_experiment_files_unchanged"] = len(before)
    metadata["output_sha256"] = {p.name: digest_path(p) for p in output.iterdir() if p.is_file()}
    (output / "manifest.private.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_dir": str(output.relative_to(root)), "frozen_checks": len(tables["frozen_consistency"]),
            "protected_experiment_files_unchanged": len(before)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=OUTPUT)
    parser.add_argument("--plot-python")
    args = parser.parse_args()
    with ExitStack() as stack:
        for target in NO_FIT_TARGETS:
            stack.enter_context(patch(target, side_effect=RuntimeError("Training/model loading forbidden")))
        print(json.dumps(run(Path.cwd(), args.output_dir, args.plot_python)))


if __name__ == "__main__":
    main()
