from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sigard_ml.territorial.analysis import LEVELS, deterministic_percentiles, run, write_outputs

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
        assert set(group.relative_level) == set(LEVELS)
        counts = group.relative_level.value_counts()
        assert counts.max() - counts.min() <= 1
    assert experimental.crs.to_epsg() == 4326 and experimental.geometry.is_valid.all()
    assert report["missing_weeks"] == []


def test_pipeline_and_serialized_outputs_are_reproducible(tmp_path: Path, result):
    config = json.loads(json.dumps(CONFIG))
    config["outputs"] = {key: str(Path("out") / Path(value).name) for key, value in config["outputs"].items()}
    write_outputs(result, config, tmp_path)
    first = {key: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for key, value in config["outputs"].items()}
    second_result = run(CONFIG, ROOT)
    write_outputs(second_result, config, tmp_path, overwrite=True)
    second = {key: hashlib.sha256((tmp_path / value).read_bytes()).hexdigest() for key, value in config["outputs"].items()}
    assert first == second
    assert result[0].equals(second_result[0]) and result[2].equals(second_result[2])


def test_existing_experimental_artifacts_remain_frozen():
    expected = {
        "experimental_spatial_history.parquet": "3A9D34C3E6E5101030633E66A23C8D49B7AEBD363CB25D0C3CD8C1AFAFC97315",
        "experimental_spatial_history.geojson": "375D56B4782C47CA36B40C2614C98F06D91DAAB384BDC9B91119414C19905BC3",
        "experimental_spatial_report.json": "86966908261D395C99032B37B50DA6A8A017B04787D4252A0FED0B69DA8EFEAB",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "data/processed" / name).read_bytes()).hexdigest() == digest.lower()
