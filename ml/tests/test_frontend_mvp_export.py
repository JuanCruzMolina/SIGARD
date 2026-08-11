from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest

from sigard_ml.export.frontend_mvp import build_artifacts, write_artifacts

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "ml/configs/frontend_mvp_export.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built():
    return build_artifacts(CONFIG, ROOT)


def test_available_weeks_is_exact_intersection_and_default(built):
    artifacts, report = built
    weeks = artifacts["available_weeks"]["weeks"]
    assert [row["cutoff_date"] for row in weeks] == ["2024-06-01", "2024-06-08", "2024-06-15", "2024-06-22"]
    assert [row["target_week_start"] for row in weeks] == ["2024-06-02", "2024-06-09", "2024-06-16", "2024-06-23"]
    assert artifacts["available_weeks"]["default_cutoff_date"] == "2024-06-22"
    assert all(row["has_temporal_prediction"] and row["has_experimental_spatial"] for row in weeks)
    assert report["available_cutoff_weeks"] == [row["cutoff_date"] for row in weeks]


def test_temporal_schema_and_dates_align_with_spatial(built):
    artifacts, _ = built
    required = {"cutoff_date", "target_week_start", "target_week_end", "predicted_cases", "predicted_cases_rounded", "official_cases", "absolute_error", "persistence_prediction", "persistence_absolute_error"}
    assert len(artifacts["temporal_predictions"]["predictions"]) == 4
    assert all(set(row) == required for row in artifacts["temporal_predictions"]["predictions"])
    spatial = gpd.read_file(ROOT / CONFIG["inputs"]["experimental_history"])
    for row in artifacts["temporal_predictions"]["predictions"]:
        selected = spatial.loc[spatial.target_week_start.eq(row["target_week_start"])]
        assert len(selected) == selected.radio_id.nunique() == 263
        assert selected.target_week_end.nunique() == 1 and selected.target_week_end.iloc[0].date().isoformat() == row["target_week_end"]
        assert selected.cutoff_date.nunique() == 1 and selected.cutoff_date.iloc[0].date().isoformat() == row["cutoff_date"]


def test_context_and_experimental_universe_geometry_levels():
    context = gpd.read_file(ROOT / CONFIG["inputs"]["territorial_context"])
    experimental = gpd.read_file(ROOT / CONFIG["inputs"]["experimental_history"])
    assert len(context) == context.radio_id.nunique() == 263
    assert set(context.radio_id) == set(experimental.radio_id)
    assert context.geometry.is_valid.all() and experimental.geometry.is_valid.all()
    for _, group in experimental.groupby("target_week_start"):
        assert len(group) == group.radio_id.nunique() == 263
        assert set(group.relative_level) == {"very_low", "low", "medium", "high"}


def test_model_evaluation_exactly_reflects_delta_report(built):
    artifacts, _ = built
    source = json.loads((ROOT / CONFIG["inputs"]["temporal_delta_report"]).read_text(encoding="utf-8"))
    evaluation = artifacts["model_evaluation"]
    rf = source["holdout_metrics"]["rf_minimal_climate_log_delta"]
    baseline = source["holdout_metrics"]["persistence_baseline"]
    assert evaluation["metrics"]["random_forest"]["mae"] == rf["mae"]
    assert evaluation["metrics"]["persistence_baseline"]["mae"] == baseline["mae"]
    assert evaluation["metrics"]["random_forest"]["mae"] < evaluation["metrics"]["persistence_baseline"]["mae"]
    assert evaluation["metrics"]["mae_reduction_vs_baseline_pct"] == pytest.approx((baseline["mae"] - rf["mae"]) / baseline["mae"] * 100)
    assert evaluation["backtest"] == source["weekly_predictions"] and len(evaluation["backtest"]) == 6


def test_metadata_legacy_preservation_no_model_write_and_reproducibility(tmp_path: Path, built):
    artifacts, report = built
    assert artifacts["metadata"]["territorial_context"]["data_type"] == "real"
    assert artifacts["metadata"]["experimental_spatial"]["data_type"] == "synthetic"
    legacy_before = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in CONFIG["legacy_frontend_files"]}
    models_before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "ml/artifacts").glob("*") if path.is_file()}
    config = json.loads(json.dumps(CONFIG))
    config["inputs"]["territorial_context"] = str((ROOT / CONFIG["inputs"]["territorial_context"]).resolve())
    config["inputs"]["experimental_history"] = str((ROOT / CONFIG["inputs"]["experimental_history"]).resolve())
    config["frontend_outputs"] = {key: str(Path("out") / Path(value).name) for key, value in config["frontend_outputs"].items()}
    config["quality_report"] = "out/frontend_mvp_export_report.json"
    write_artifacts(artifacts, report, config, tmp_path)
    first = {value: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for value in [*config["frontend_outputs"].values(), config["quality_report"]]}
    write_artifacts(*build_artifacts(CONFIG, ROOT), config, tmp_path, overwrite=True)
    second = {value: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for value in [*config["frontend_outputs"].values(), config["quality_report"]]}
    assert first == second
    assert legacy_before == {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in CONFIG["legacy_frontend_files"]}
    assert models_before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "ml/artifacts").glob("*") if path.is_file()}
