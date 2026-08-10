from pathlib import Path

import pandas as pd

from sigard_ml.ingestion.temporal import build_temporal_weekly
import pytest

from sigard_ml.transformation.temporal import aggregate_climate, aggregate_dengue, integrate_weekly, select_modeling_weeks
from sigard_ml.validation.temporal import TemporalValidationError, epidemiological_week_start, require_unique_weeks


def test_dengue_aggregation_preserves_totals_and_absent_weeks() -> None:
    source = pd.DataFrame({"epidemiological_year": [2024, 2024, 2024], "epidemiological_week": [1, 1, 3], "dengue_cases_observed": [2, 3, 0]})
    result = aggregate_dengue(source)
    assert result["dengue_cases_observed"].sum() == 5
    assert result["epidemiological_week"].tolist() == [1, 3]
    assert result["dengue_zero_cases_observed"].tolist() == [False, True]


def test_climate_uses_argentine_epidemiological_week_and_marks_partial_week() -> None:
    source = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02"]), "temperature_min": [10.0, 12.0], "temperature_max": [20.0, 24.0], "temperature_mean": [15.0, 18.0], "relative_humidity": [40.0, 60.0], "precipitation": [1.0, 2.5]})
    result = aggregate_climate(source)
    row = result.iloc[0]
    assert (row["epidemiological_year"], row["epidemiological_week"]) == (2024, 1)
    assert row["temperature_min_mean"] == 11.0
    assert row["precipitation_sum"] == 3.5
    assert row["climate_days_observed"] == 2
    assert not row["climate_week_complete"]
    assert row["week_start_date"] == pd.Timestamp("2023-12-31")
    assert row["week_end_date"] == pd.Timestamp("2024-01-06")
    assert row["week_convention"] == "ARGENTINA_SNVS_SUNDAY_SATURDAY"


def test_epidemiological_week_is_not_assumed_to_be_iso() -> None:
    start = epidemiological_week_start(pd.Series([2024]), pd.Series([1])).iloc[0]
    assert start == pd.Timestamp("2023-12-31")


def test_integration_distinguishes_absent_record_from_zero() -> None:
    dengue = aggregate_dengue(pd.DataFrame({"epidemiological_year": [2024], "epidemiological_week": [1], "dengue_cases_observed": [0]}))
    dates = pd.to_datetime(["2024-01-01", "2024-01-08"])
    climate = aggregate_climate(pd.DataFrame({"date": dates, "temperature_min": [1.0, 2.0], "temperature_max": [3.0, 4.0], "temperature_mean": [2.0, 3.0], "relative_humidity": [50.0, 60.0], "precipitation": [0.0, 0.0]}))
    coverage = pd.DataFrame({"epidemiological_year": [2024, 2024], "epidemiological_week": [1, 2]})
    result = integrate_weekly(dengue, climate, coverage)
    assert result["dengue_record_available"].tolist() == [True, False]
    assert result["dengue_zero_cases_observed"].tolist() == [True, False]
    assert result["dengue_cases_observed"].isna().tolist() == [False, True]
    assert result["epidemiological_status"].tolist() == ["explicit_zero", "missing_record"]


def test_modeling_excludes_missing_and_outside_coverage_without_filling_cases() -> None:
    integrated = pd.DataFrame({
        "epidemiological_year": [2024, 2024, 2022],
        "epidemiological_week": [1, 2, 1],
        "epidemiological_status": ["observed", "missing_record", "outside_source_coverage"],
        "climate_week_complete": [True, True, True],
        "dengue_cases_observed": [4.0, float("nan"), float("nan")],
    })
    result = select_modeling_weeks(integrated)
    assert result["dengue_cases_observed"].tolist() == [4.0]
    assert result["epidemiological_status"].tolist() == ["observed"]


def test_duplicate_year_week_is_rejected() -> None:
    duplicated = pd.DataFrame({"epidemiological_year": [2024, 2024], "epidemiological_week": [1, 1]})
    with pytest.raises(TemporalValidationError, match="duplicadas"):
        require_unique_weeks(duplicated, "test")


def test_local_pipeline_expected_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    import json
    config = json.loads((root / "ml/configs/temporal_weekly.json").read_text(encoding="utf-8"))
    dengue, climate, integrated, modeling, report = build_temporal_weekly(config, root)
    assert dengue.groupby("epidemiological_year")["dengue_cases_observed"].sum().to_dict() == {2023: 352, 2024: 10656}
    assert climate["week_start_date"].min() == pd.Timestamp("2014-12-28")
    assert climate["week_start_date"].max() == pd.Timestamp("2024-12-29")
    assert len(integrated) == len(climate)
    assert report["dengue"]["missing_records_within_source_coverage"] == 63
    assert report["dengue"]["weeks_outside_source_coverage"] == 419
    assert len(modeling) == 41
    assert modeling["dengue_cases_observed"].notna().all()
