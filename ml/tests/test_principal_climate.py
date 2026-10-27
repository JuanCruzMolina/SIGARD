"""Clima enteramente ficticio: sin fuentes, servicios, ajuste ni inferencia."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.adapter import climate_snapshots, TABLE_COLUMNS
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR, CALENDAR_VERSION, CalendarError
from sigard_ml.transformation.temporal import aggregate_climate
from test_forecasting_adapter import adapt, bundle_fixture, panel, ORIGIN, REVIEW


def daily(start="2023-12-31", end="2024-03-09"):
    dates = pd.date_range(start, end)
    temperature = np.arange(len(dates)) // 7
    return pd.DataFrame(dict(date=dates, temperature_min=temperature - 5.,
        temperature_max=temperature + 5., temperature_mean=temperature.astype(float),
        relative_humidity=50., precipitation=2.))


def weekly():
    return aggregate_climate(daily(), calendar=DEFAULT_CALENDAR)


def mapped(frame=None, delayed=False):
    frame = weekly() if frame is None else frame
    availability = {row.week_start_date.date(): REVIEW if delayed else row.week_end_date.date()
                    for row in frame.itertuples()}
    return climate_snapshots(frame, availability=availability, source_ref="fictional_climate")


@pytest.mark.parametrize("start,year,number", [
    ("2020-12-27", 2020, 53), ("2021-01-03", 2021, 1),
    ("2021-12-26", 2021, 52), ("2022-01-02", 2022, 1),
    ("2022-12-25", 2022, 52), ("2023-01-01", 2023, 1),
    ("2023-12-24", 2023, 52), ("2023-12-31", 2024, 1),
    ("2024-12-22", 2024, 52), ("2024-12-29", 2025, 1),
    ("2025-12-28", 2025, 53), ("2026-01-04", 2026, 1),
    ("2026-12-27", 2026, 52),
])
def test_official_climate_boundaries_and_all_seven_dates(start, year, number):
    end = pd.Timestamp(start) + pd.Timedelta(days=6)
    result = aggregate_climate(daily(start, end), calendar=DEFAULT_CALENDAR)
    assert len(result) == 1
    row = result.iloc[0]
    assert (row.epidemiological_year, row.epidemiological_week) == (year, number)
    assert row.week_start_date == pd.Timestamp(start)
    assert row.week_end_date == end
    assert row.week_start_date.dayofweek == 6 and row.week_end_date.dayofweek == 5
    assert row.calendar_version == CALENDAR_VERSION and row.climate_week_complete


def test_legacy_replay_stays_explicit_and_unchanged():
    source = daily("2025-12-28", "2026-01-03")
    legacy = aggregate_climate(source)
    official = aggregate_climate(source, calendar=DEFAULT_CALENDAR)
    assert legacy.epidemiological_year.tolist() == [2026]
    assert legacy.epidemiological_week.tolist() == [1]
    assert official.epidemiological_year.tolist() == [2025]
    assert official.epidemiological_week.tolist() == [53]
    pd.testing.assert_frame_equal(legacy.drop(columns=["epidemiological_year", "epidemiological_week"]),
        official[legacy.columns].drop(columns=["epidemiological_year", "epidemiological_week"]))


@pytest.mark.parametrize("field", ["temperature_min", "temperature_max", "temperature_mean",
                                    "relative_humidity", "precipitation"])
def test_missing_daily_value_never_becomes_complete(field):
    source = daily()
    source.loc[0, field] = np.nan
    frame = aggregate_climate(source, calendar=DEFAULT_CALENDAR)
    assert frame.iloc[0].climate_days_observed == 7
    assert not frame.iloc[0].climate_values_complete
    assert not frame.iloc[0].climate_week_complete
    with pytest.raises(ForecastError, match="incompleto"):
        mapped(frame)


@pytest.mark.parametrize("failure", ["missing_day", "duplicate", "infinite", "hour", "humidity", "rain", "outside"])
def test_bad_daily_data(failure):
    source = daily()
    if failure == "missing_day":
        frame = aggregate_climate(source.iloc[1:], calendar=DEFAULT_CALENDAR)
        assert frame.iloc[0].climate_days_observed == 6
        assert not frame.iloc[0].climate_week_complete
        return
    if failure == "duplicate": source = pd.concat([source, source.iloc[:1]])
    elif failure == "infinite": source.loc[0, "temperature_mean"] = np.inf
    elif failure == "hour": source.loc[0, "date"] += pd.Timedelta(hours=1)
    elif failure == "humidity": source.loc[0, "relative_humidity"] = 101.
    elif failure == "rain": source.loc[0, "precipitation"] = -1.
    elif failure == "outside": source = daily("2019-12-28", "2019-12-28")
    with pytest.raises((ValueError, CalendarError)):
        aggregate_climate(source, calendar=DEFAULT_CALENDAR)


def test_mapping_requires_explicit_effective_availability_and_official_calendar():
    frame = weekly()
    with pytest.raises(ForecastError, match="Disponibilidad"):
        climate_snapshots(frame, availability={}, source_ref="fictional_climate")
    with pytest.raises(ForecastError, match="antes del cierre"):
        climate_snapshots(frame, availability={v.date(): v.date() for v in frame.week_start_date},
                          source_ref="fictional_climate")
    frame.loc[0, "epidemiological_week"] = 2
    with pytest.raises(ForecastError, match="desalineadas"):
        mapped(frame)
    with pytest.raises(ForecastError, match="oficial"):
        mapped(aggregate_climate(daily()))


def test_existing_adapter_and_features_consume_mapping_without_training():
    bundle = bundle_fixture()
    result = mapped()
    assert set(result.columns) == TABLE_COLUMNS["climate"]
    for field in ("week_start", "available_on"):
        result[field] = result[field].map(date.isoformat)
    bundle["climate"] = result.to_dict("records")
    row = panel(adapt(bundle)).iloc[0]
    assert row.temperature_lag_1 == 3.
    assert row.temperature_mean_4 == 1.5
    assert row.humidity_lag_1 == row.humidity_mean_4 == 50.
    assert row.precipitation_lag_1 == 14. and row.precipitation_sum_4 == 56.
    assert all(item["week"] < ORIGIN.isoformat() for item in row.provenance["climate"])


def test_late_availability_and_future_observations_cannot_leak():
    bundle = bundle_fixture()
    for delayed in (False, True):
        result = mapped(delayed=delayed)
        future = result.week_start.ge(ORIGIN)
        result.loc[future, "temperature"] = 999.
        for field in ("week_start", "available_on"):
            result[field] = result[field].map(date.isoformat)
        bundle["climate"] = result.to_dict("records")
        row = panel(adapt(bundle)).iloc[0]
        if delayed:
            assert pd.isna(row.temperature_lag_1) and pd.isna(row.precipitation_sum_4)
            assert row.provenance["climate"] == []
        else:
            assert row.temperature_lag_1 == 3. and row.temperature_mean_4 == 1.5


def test_gap_in_history_does_not_shift_or_fill_rolling_window():
    bundle = bundle_fixture()
    result = mapped()
    result = result.loc[result.week_start.ne(ORIGIN - timedelta(weeks=2))]
    # El contrato derivado exige grilla completa: no fabrica una semana.
    for field in ("week_start", "available_on"):
        result[field] = result[field].map(date.isoformat)
    bundle["climate"] = result.to_dict("records")
    with pytest.raises(ForecastError, match="Contexto incompleto"):
        adapt(bundle)
