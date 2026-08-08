from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from sigard_ml.evaluation.pipeline import run_evaluation, write_outputs
from sigard_ml.evaluation.temporal import build_temporal_split
from sigard_ml.models.persistence import PersistenceBaseline


def panel() -> pd.DataFrame:
    dates = list(pd.date_range("2024-01-07", periods=3, freq="7D")) + list(pd.date_range("2024-03-03", periods=5, freq="7D"))
    rows = []
    for week_index, date in enumerate(dates, start=1):
        for radio_index, radio in enumerate(("a", "b"), start=1):
            rows.append({"radio_id": radio, "epidemiological_year": 2024, "epidemiological_week": week_index, "week_start_date": date, "synthetic_cases_assigned": week_index * radio_index, "target_cases_next_week": (week_index + 1) * radio_index})
    return pd.DataFrame(rows)


def config() -> dict:
    return {"pipeline": {"name": "test", "version": "1"}, "input": "in/panel.parquet", "data_version": "test", "seed": 7, "expected_radio_count": 2, "columns": {"radio_id": "radio_id", "year": "epidemiological_year", "week": "epidemiological_week", "week_start": "week_start_date", "current_cases": "synthetic_cases_assigned", "target": "target_cases_next_week"}, "split": {"test_weeks": 2}, "outputs": {"split": "out/split.parquet", "predictions": "out/predictions.parquet", "metrics": "out/metrics.json"}}


def test_complete_week_split_is_strictly_temporal() -> None:
    frame = panel()
    split = build_temporal_split(frame, test_weeks=2)
    train = set(split.loc[split.split.eq("train"), "week_start_date"])
    test = set(split.loc[split.split.eq("test"), "week_start_date"])
    assert train.isdisjoint(test)
    assert max(train) < min(test)
    assert frame.groupby("week_start_date").size().index.isin(test).sum() == 2


def test_gaps_start_new_blocks_and_are_not_test_continuity() -> None:
    split = build_temporal_split(panel(), test_weeks=2)
    assert split["continuous_block"].nunique() == 2
    assert split.loc[split["gap_days_from_previous"].gt(7), "continuous_block"].iloc[0] == 1
    assert set(split.loc[split.split.eq("test"), "week_start_date"]) == set(pd.to_datetime(["2024-03-24", "2024-03-31"]))


def test_baseline_does_not_access_future_target() -> None:
    model = PersistenceBaseline()
    features = pd.DataFrame({"synthetic_cases_assigned": [0, 3, 2]})
    first = model.predict(features)
    second = model.predict(features.assign(target_cases_next_week=[999, 999, 999]))
    pd.testing.assert_series_equal(first, second)
    assert first.tolist() == [0, 3, 2]


def test_evaluation_and_written_outputs_are_reproducible(tmp_path: Path) -> None:
    cfg = config()
    (tmp_path / "in").mkdir()
    panel().to_parquet(tmp_path / "in/panel.parquet", index=False)
    first, second = run_evaluation(cfg, tmp_path), run_evaluation(cfg, tmp_path)
    pd.testing.assert_frame_equal(first[0], second[0]); pd.testing.assert_frame_equal(first[1], second[1]); assert first[2] == second[2]
    write_outputs(*first, cfg, tmp_path)
    hashes_1 = {name: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() for name, path in cfg["outputs"].items()}
    write_outputs(*second, cfg, tmp_path, overwrite=True)
    hashes_2 = {name: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() for name, path in cfg["outputs"].items()}
    assert hashes_1 == hashes_2
