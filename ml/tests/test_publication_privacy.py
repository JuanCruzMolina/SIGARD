"""Generated in-memory fixtures; never opens private datasets or fits models."""
from datetime import date
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from sigard_ml.forecasting.v3_run import snapshot_provenance


def test_snapshot_provenance_uses_authorized_scope_and_preserves_unknowns():
    bundle = dict(radios=["fictional_a", "fictional_b"],
                  snapshot_scenario=dict(covered_weeks=["2025-01-05"]))
    frame = pd.DataFrame(dict(radio_id=bundle["radios"], week_start=[date(2025, 1, 5)] * 2,
        snapshot_count=[2., float("nan")], label_usable=[True, False], recorded_positive_count=[2, 1]))
    assert snapshot_provenance(frame, bundle) == dict(source_grid_cells=2, usable_labels=1,
        unknown_labels=1, source_positive_records=3)
    for invalid in (frame.iloc[:1], pd.concat([frame, frame.iloc[:1]]),
                    frame.assign(label_usable=True), frame.assign(radio_id="fictional_other")):
        with pytest.raises(AssertionError):
            snapshot_provenance(invalid, bundle)


def test_renderer_rejects_public_outputs_and_existing_reports(tmp_path):
    source = Path(__file__).resolve().parents[2] / "tools/render_thesis_validation.py"
    spec = importlib.util.spec_from_file_location("private_renderer", source)
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    private = tmp_path / "data/interim/official"
    private.mkdir(parents=True)
    assert renderer.private_output(private / "new", tmp_path) == private / "new"
    for target in (tmp_path / "docs/figures", private, private / "../outside"):
        with pytest.raises(ValueError):
            renderer.private_output(target, tmp_path)
