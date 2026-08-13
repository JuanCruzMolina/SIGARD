from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from sigard_ml.territorial.analysis import LEVELS, deterministic_percentiles, run, tie_aware_percentiles, write_outputs

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "ml/configs/territorial_analysis.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result():
    return run(CONFIG, ROOT)


def test_structural_contract_balanced_levels_and_geometry(result):
    structural, report, _, _ = result
    assert len(structural) == structural.radio_id.nunique() == 263
    assert structural.radio_id.is_unique
    assert structural.territorial_context_score.notna().all()
    assert np.isfinite(structural.territorial_context_score).all()
    assert structural.percentile.between(0, 100).all()
    assert set(structural.relative_level) == set(LEVELS)
    counts = structural.relative_level.value_counts()
    assert counts.sum() == 263 and (counts.max() - counts.min()) <= 1
    assert structural.crs.to_epsg() == 4326 and structural.geometry.is_valid.all()
    assert not structural.geometry.is_empty.any() and not structural.geometry.isna().any()
    assert report["number_of_radios"] == 263


def test_context_formula_components_area_exclusion_and_clean_schema(result):
    structural, report, _, _ = result
    territorial = pd.read_parquet(ROOT / CONFIG["inputs"]["territorial"])
    expected = {}
    for output, source in [("population", "poblacion"), ("population_density", "densidad_poblacional"), ("households", "hogares"), ("dwellings", "viviendas")]:
        ordered = territorial[["radio_id", source]].sort_values([source, "radio_id"], kind="mergesort")
        expected[output] = pd.Series(np.arange(1, 264) / 263, index=ordered.radio_id).reindex(structural.radio_id).to_numpy()
    demographic = np.mean([expected["population"], expected["households"], expected["dwellings"]], axis=0)
    np.testing.assert_allclose(structural.demographic_residential_component, demographic)
    np.testing.assert_allclose(structural.density_component, expected["population_density"])
    np.testing.assert_allclose(structural.territorial_context_score, 0.5 * demographic + 0.5 * expected["population_density"])
    assert report["features_used"] == ["population", "population_density", "households", "dwellings"]
    assert report["descriptive_features"] == ["area_km2"]
    assert not any(token in column for column in structural.columns for token in ["synthetic", "cases", "target", "prediction"])


def test_deterministic_tie_break_by_radio_id():
    frame = pd.DataFrame({"radio_id": ["c", "a", "b", "d"], "score": [1.0] * 4})
    first = deterministic_percentiles(frame, "score").set_index("radio_id")
    second = deterministic_percentiles(frame.sample(frac=1, random_state=4), "score").set_index("radio_id")
    pd.testing.assert_frame_equal(first, second)
    assert first.loc["a", "percentile"] == 25.0
    assert first.loc["d", "percentile"] == 100.0


def test_experimental_tie_aware_percentiles_are_monotonic_and_radio_independent():
    frame = pd.DataFrame(
        {
            "radio_id": ["f", "e", "d", "c", "b", "a"],
            "score": [0.01, 0.02, 0.08, 0.08, 0.08, 0.09],
        }
    )
    first = tie_aware_percentiles(frame, "score").set_index("radio_id")
    renamed = frame.assign(radio_id=["a", "b", "c", "d", "e", "f"])
    second = tie_aware_percentiles(renamed, "score")
    tied = first.loc[["d", "c", "b"]]
    assert tied.percentile.nunique() == 1
    assert tied.relative_level.nunique() == 1
    ordered = first.sort_values("score")
    assert ordered.percentile.is_monotonic_increasing
    level_order = ordered.relative_level.map({level: index for index, level in enumerate(LEVELS)})
    assert level_order.is_monotonic_increasing
    pd.testing.assert_series_equal(
        first.reset_index().sort_values("score").percentile.reset_index(drop=True),
        second.sort_values("score").percentile.reset_index(drop=True),
    )


def test_experimental_contract_every_week_and_no_future(result):
    _, _, experimental, report = result
    assert len(experimental) == 4 * 263 and report["number_of_weeks"] == 4
    assert not experimental.duplicated(["radio_id", "target_week_start"]).any()
    assert experimental.experimental_spatial_score.notna().all() and np.isfinite(experimental.experimental_spatial_score).all()
    assert experimental.percentile.between(0, 100).all()
    assert experimental.synthetic_scenario.eq("spatial_clusters").all()
    assert (experimental.cutoff_date < experimental.target_week_start).all()
    for _, group in experimental.groupby("target_week_start"):
        assert len(group) == group.radio_id.nunique() == 263
        by_score = group.groupby("experimental_spatial_score")
        assert by_score.percentile.nunique().eq(1).all()
        assert by_score.relative_level.nunique().eq(1).all()
        ordered = group.sort_values("experimental_spatial_score")
        assert ordered.percentile.is_monotonic_increasing
        level_order = ordered.relative_level.map({level: index for index, level in enumerate(LEVELS)})
        assert level_order.is_monotonic_increasing
    assert experimental.crs.to_epsg() == 4326 and experimental.geometry.is_valid.all()
    assert report["missing_weeks"] == []


def test_pipeline_and_serialized_outputs_are_reproducible(tmp_path: Path, result):
    config = json.loads(json.dumps(CONFIG))
    context_keys = ["context_parquet", "context_geojson", "context_report"]
    config["outputs"] = {key: str(Path("out") / Path(config["outputs"][key]).name) for key in context_keys}
    write_outputs(result, config, tmp_path)
    first = {key: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for key, value in config["outputs"].items()}
    second_result = run(CONFIG, ROOT)
    write_outputs(second_result, config, tmp_path, overwrite=True)
    second = {key: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for key, value in config["outputs"].items()}
    assert first == second
    assert result[0].equals(second_result[0]) and result[2].equals(second_result[2])


def test_existing_experimental_artifacts_remain_frozen():
    expected = {
        "experimental_spatial_history.parquet": "5BED7C27DDBBE273FBABEA53B783BA31E6856BE6C77FEC2C1E4D4C957FDDB116",
        "experimental_spatial_history.geojson": "CBA113AD054C6817C87DD8A8D69A8A4D28686AB53F7F2091CDC261CB61192470",
        "experimental_spatial_report.json": "EA7838F78B6751C9CE321F3C459314255D8E496DB6D7CDAA07FC5C4F805705DB",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "data/processed" / name).read_bytes()).hexdigest() == digest.lower()


def test_experimental_scores_and_geometries_match_unchanged_sources(result):
    territorial = gpd.read_parquet(ROOT / CONFIG["inputs"]["territorial"])[["radio_id", "geometry"]]
    predictions = pd.read_parquet(ROOT / CONFIG["inputs"]["experimental_predictions"])
    expected = predictions.loc[predictions.variant.eq(CONFIG["experimental_variant"]), ["radio_id", "target_week_start_date", "predicted_cases"]].copy()
    expected["target_week_start"] = pd.to_datetime(expected.pop("target_week_start_date"))
    expected = expected.rename(columns={"predicted_cases": "experimental_spatial_score"}).sort_values(["target_week_start", "radio_id"]).reset_index(drop=True)
    expected = expected[["radio_id", "target_week_start", "experimental_spatial_score"]]
    experimental = result[2].sort_values(["target_week_start", "radio_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(experimental[["radio_id", "target_week_start", "experimental_spatial_score"]], expected, check_dtype=False)
    expected_geometry = experimental[["radio_id"]].merge(territorial, on="radio_id", validate="many_to_one").geometry
    assert experimental.geometry.geom_equals_exact(expected_geometry, tolerance=0).all()


def test_temporal_frontend_artifacts_remain_frozen():
    expected = {
        "temporal_predictions.json": "963f0d63356b5e7f1f7a744a0d8806153536da6ac77cd6e81bcd5f4b3ed484bc",
        "model_evaluation.json": "fb1887a525177a3ebbcd96528882cab10ce0cce1142c8932e5c8225dc1dc592c",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "frontend/public/data" / name).read_bytes()).hexdigest() == digest
