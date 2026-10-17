"""Fechas públicas verificadas; los registros de integración son ficticios."""

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from sigard_ml.official.calendar import make_week, week_from_date, weeks_between
from sigard_ml.official.calendar_audit import audit_artifacts, calendar_changes, compare_panel
from sigard_ml.official.calendar_rules import (
    CALENDAR_VERSION, LEGACY_VERSION, Calendar, CalendarError, CalendarYear,
    DEFAULT_CALENDAR, LEGACY_CALENDAR, VERIFIED_YEARS, calendar_from_config,
)
from sigard_ml.official.contracts import ContractError, EpidemiologicalWeek
from sigard_ml.official.observed_dates import assign_hierarchy_weeks
from sigard_ml.official.weekly_targets import attach_next_week_target
from sigard_ml.validation.temporal import epidemiological_week_start


# Calendarios MSAL (página 1 de cada PDF), enlaces y resolución: official-calendar.md.
YEAR_LIMITS = [
    (2020, "2019-12-29", 53, "2021-01-02"),
    (2021, "2021-01-03", 52, "2022-01-01"),
    (2022, "2022-01-02", 52, "2022-12-31"),
    (2023, "2023-01-01", 52, "2023-12-30"),
    (2024, "2023-12-31", 52, "2024-12-28"),
    (2025, "2024-12-29", 53, "2026-01-03"),
    (2026, "2026-01-04", 52, "2027-01-02"),
]


@pytest.mark.parametrize("year,first,last_number,last", YEAR_LIMITS)
def test_official_first_and_last_weeks_and_every_day_roundtrip(year, first, last_number, last):
    first, last = date.fromisoformat(first), date.fromisoformat(last)
    assert make_week(year, 1).start == first
    assert make_week(year, last_number).end == last
    weeks = weeks_between(first, last)
    assert len(weeks) == last_number
    assert [week.number for week in weeks] == list(range(1, last_number + 1))
    for week in weeks:
        assert week.calendar_version == CALENDAR_VERSION
        for offset in range(7):
            assert week_from_date(week.start + timedelta(days=offset)) == week
    if year > 2020:
        assert week_from_date(first - timedelta(days=1)).year == year - 1
    if year < 2026:
        assert week_from_date(last + timedelta(days=1)).year == year + 1


@pytest.mark.parametrize("value,year,number,start,end", [
    ("2020-01-01", 2020, 1, "2019-12-29", "2020-01-04"),
    ("2020-02-29", 2020, 9, "2020-02-23", "2020-02-29"),
    ("2020-12-31", 2020, 53, "2020-12-27", "2021-01-02"),
    ("2021-01-01", 2020, 53, "2020-12-27", "2021-01-02"),
    ("2021-12-31", 2021, 52, "2021-12-26", "2022-01-01"),
    ("2022-01-01", 2021, 52, "2021-12-26", "2022-01-01"),
    ("2022-12-31", 2022, 52, "2022-12-25", "2022-12-31"),
    ("2023-01-01", 2023, 1, "2023-01-01", "2023-01-07"),
    ("2023-12-31", 2024, 1, "2023-12-31", "2024-01-06"),
    ("2024-01-01", 2024, 1, "2023-12-31", "2024-01-06"),
    ("2024-02-29", 2024, 9, "2024-02-25", "2024-03-02"),
    ("2024-12-31", 2025, 1, "2024-12-29", "2025-01-04"),
    ("2025-01-01", 2025, 1, "2024-12-29", "2025-01-04"),
    ("2025-12-27", 2025, 52, "2025-12-21", "2025-12-27"),
    ("2025-12-28", 2025, 53, "2025-12-28", "2026-01-03"),
    ("2025-12-31", 2025, 53, "2025-12-28", "2026-01-03"),
    ("2026-01-01", 2025, 53, "2025-12-28", "2026-01-03"),
    ("2026-01-03", 2025, 53, "2025-12-28", "2026-01-03"),
    ("2026-01-04", 2026, 1, "2026-01-04", "2026-01-10"),
    ("2026-01-10", 2026, 1, "2026-01-04", "2026-01-10"),
    ("2026-01-11", 2026, 2, "2026-01-11", "2026-01-17"),
    ("2026-12-31", 2026, 52, "2026-12-27", "2027-01-02"),
])
def test_verified_dates(value, year, number, start, end):
    week = week_from_date(date.fromisoformat(value))
    assert (week.year, week.number, week.start.isoformat(), week.end.isoformat()) == (year, number, start, end)


@pytest.mark.parametrize("year", [2021, 2022, 2023, 2024, 2026])
def test_nonexistent_week_53_is_rejected_including_direct_contract(year):
    with pytest.raises(ContractError):
        make_week(year, 53)
    with pytest.raises(ContractError):
        EpidemiologicalWeek(year, 53, make_week(year, 52).start + timedelta(days=7),
                            make_week(year, 52).end + timedelta(days=7))


def test_legacy_replay_is_explicit_and_versions_cannot_be_mixed():
    value = date(2026, 1, 4)
    official, legacy = week_from_date(value), week_from_date(value, calendar=LEGACY_CALENDAR)
    assert (official.year, official.number) == (2026, 1)
    assert (legacy.year, legacy.number) == (2026, 2)
    assert legacy.calendar_version == LEGACY_VERSION
    with pytest.raises(ContractError):
        replace(legacy, calendar=DEFAULT_CALENDAR)
    assert make_week(2026, 53, calendar=LEGACY_CALENDAR).start == date(2026, 12, 27)
    assert week_from_date(date(2025, 12, 28), calendar=LEGACY_CALENDAR).number == 1


@pytest.mark.parametrize("value", [date(2019, 12, 28), date(2027, 1, 3), datetime(2026, 1, 4), "2026-01-04"])
def test_no_silent_extrapolation_or_datetime_coercion(value):
    with pytest.raises(ContractError):
        week_from_date(value)


def test_configuration_is_versioned_immutable_and_independent_of_coverage():
    config = json.loads((Path(__file__).parents[1] / "configs/official.calendar.example.json").read_text(encoding="utf-8"))
    assert calendar_from_config(config["calendar"]) == DEFAULT_CALENDAR
    assert calendar_from_config(config["historical_replay_calendar"]) == LEGACY_CALENDAR
    assert config["analysis_period"]["end"] == "2024-12-31"
    assert not config["coverage_extension"]["enabled"]
    rows = [{**asdict(entry), "start": entry.start.isoformat()} for entry in VERIFIED_YEARS]
    assert calendar_from_config({"version": CALENDAR_VERSION, "years": rows}) == DEFAULT_CALENDAR
    rows.append({"year": 2027, "start": "2027-01-03", "weeks": 52, "evidence": "fixture ficticio, no fuente oficial"})
    extended = calendar_from_config({"version": "fictional-calendar-extension-v1", "years": rows})
    assert make_week(2027, 1, calendar=extended).start == date(2027, 1, 3)
    with pytest.raises(CalendarError):
        calendar_from_config({"version": CALENDAR_VERSION, "years": rows})
    assert len(DEFAULT_CALENDAR.years) == 7


@pytest.mark.parametrize("config", [
    {}, {"version": "unknown"}, {"version": LEGACY_VERSION, "years": []},
    {"version": "fixture", "years": []}, {"version": CALENDAR_VERSION, "typo": 1},
    {"version": "fixture", "years": [{"year": 2026, "start": "2026-01-05", "weeks": 52, "evidence": "fixture"}]},
])
def test_invalid_configuration_is_rejected(config):
    with pytest.raises(CalendarError):
        calendar_from_config(config)


def test_discontinuous_calendar_is_rejected():
    with pytest.raises(CalendarError):
        Calendar("fixture", (VERIFIED_YEARS[0], VERIFIED_YEARS[2]))
    with pytest.raises(CalendarError):
        CalendarYear(2026, date(2026, 1, 4), True, "fixture")


def test_vector_adapter_respects_version_invalid_53_and_index():
    years = pd.Series([2025, 2026, 2026, None], index=[4, 8, 12, 16])
    numbers = pd.Series([53, 1, 53, 1], index=years.index)
    result = epidemiological_week_start(years, numbers, calendar=DEFAULT_CALENDAR)
    assert result.index.equals(years.index)
    assert result.iloc[:2].tolist() == [pd.Timestamp("2025-12-28"), pd.Timestamp("2026-01-04")]
    assert result.iloc[2:].isna().all()
    legacy = epidemiological_week_start(years, numbers)
    assert pd.isna(legacy.iloc[0])
    assert legacy.iloc[1] == pd.Timestamp("2025-12-28")


def test_2026_reference_dates_and_next_week_target_remain_coherent():
    dates = [date(2025, 12, 28), date(2026, 1, 4), date(2026, 1, 11)]
    frame = pd.DataFrame({"symptom_onset": dates, "symptom_onset_status": ["valid"] * 3})
    assigned = assign_hierarchy_weeks(frame, hierarchy=["symptom_onset"], period_start=dates[0],
                                    period_end=date(2026, 1, 17), as_of=date(2026, 1, 18), version="fictional")
    assert assigned.epidemiological_year.tolist() == [2025, 2026, 2026]
    assert assigned.epidemiological_week.tolist() == [53, 1, 2]
    panel = pd.DataFrame({"radio_censal": ["fictional"] * 3, "fecha_inicio_semana": assigned.week_start,
        "fecha_fin_semana": assigned.week_end, "casos_observados": pd.array([2, 0, None], dtype="Int64"),
        "estado_observacion": ["registros_observados", "cero_comprobado_bajo_reglas", "sin_datos"],
        "cero_provisional": [False] * 3, "registros_fecha_aproximada": [0] * 3})
    result = attach_next_week_target(panel)
    assert result.objetivo_semana_siguiente.iloc[0] == 0
    assert result.objetivo_semana_siguiente.iloc[1:].isna().all()
    assert result.fecha_inicio_semana_objetivo.iloc[0] == date(2026, 1, 4)


def test_potential_impact_is_only_after_current_coverage_and_preserves_date_intervals():
    current = calendar_changes(date(2020, 1, 1), date(2024, 12, 31))
    assert current["days_with_changed_labels"] == 0
    future = calendar_changes(date(2025, 12, 27), date(2026, 1, 11))
    assert future["first_changed_date"] == "2025-12-28"
    assert future["days_with_changed_labels"] == 15
    panel = pd.DataFrame({"anio_epidemiologico": [2026, 2026], "semana_epidemiologica": [1, 2],
        "fecha_inicio_semana": [date(2025, 12, 28), date(2026, 1, 4)],
        "fecha_fin_semana": [date(2026, 1, 3), date(2026, 1, 10)]})
    original = panel.copy(deep=True)
    report = compare_panel(panel)
    assert report["rows_with_changed_labels"] == 2
    assert report["rows_with_changed_intervals"] == 0
    assert report["year_week_keys_change"]
    assert not report["count_migration_between_date_intervals_required"]
    pd.testing.assert_frame_equal(panel, original)


def test_private_audit_reads_originals_without_overwriting_and_requires_fresh_output(tmp_path):
    source = tmp_path / "data/raw/fictional.xlsx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fictional source used only for preservation hashes")
    observed = tmp_path / "data/interim/official/observed/fixture"
    observed.mkdir(parents=True)
    panel = pd.DataFrame({"anio_epidemiologico": [2024], "semana_epidemiologica": [1],
        "fecha_inicio_semana": [date(2023, 12, 31)], "fecha_fin_semana": [date(2024, 1, 6)]})
    panel.to_parquet(observed / "panel.parquet")
    pd.DataFrame({"reference_date": [date(2024, 1, 1)], "week_start": [date(2023, 12, 31)],
        "epidemiological_year": [2024], "epidemiological_week": [1]}).to_parquet(observed / "records_audit.parquet")
    originals = {path: path.read_bytes() for path in (source, observed / "panel.parquet", observed / "records_audit.parquet")}
    output = tmp_path / "data/interim/calendar-fixture"
    report = audit_artifacts(tmp_path, output)
    assert report["sha256_unchanged"] and report["preserved_file_count"] == 3
    assert not report["coverage_extended"] and not report["panels_regenerated"]
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert "fictional source" not in (output / "impact.private.json").read_text()
    with pytest.raises(ValueError, match="nuevo"):
        audit_artifacts(tmp_path, output)
    with pytest.raises(ValueError, match="data/interim"):
        audit_artifacts(tmp_path, tmp_path / "data/processed/forbidden")
