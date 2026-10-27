"""Transformaciones del MVP histórico; calendario sigard-iso-shift-v0 explícito."""

from __future__ import annotations

import pandas as pd

from sigard_ml.official.calendar_rules import Calendar, LEGACY_CALENDAR

from sigard_ml.validation.temporal import epidemiological_week_start, require_unique_weeks

WEEK_CONVENTION = "ARGENTINA_SNVS_SUNDAY_SATURDAY"


def add_week_contract(frame: pd.DataFrame, *, calendar: Calendar = LEGACY_CALENDAR) -> pd.DataFrame:
    result = frame.copy()
    result["week_start_date"] = epidemiological_week_start(result["epidemiological_year"], result["epidemiological_week"], calendar=calendar)
    result["week_end_date"] = result["week_start_date"] + pd.Timedelta(days=6)
    result["week_convention"] = WEEK_CONVENTION
    return result


def aggregate_dengue(frame: pd.DataFrame) -> pd.DataFrame:
    """Suma conteos publicados por estrato sin crear semanas ausentes."""
    result = frame.groupby(["epidemiological_year", "epidemiological_week"], as_index=False, sort=True)["dengue_cases_observed"].sum()
    result = add_week_contract(result)
    result["dengue_record_available"] = True
    result["dengue_zero_cases_observed"] = result["dengue_cases_observed"].eq(0)
    result["epidemiological_status"] = result["dengue_zero_cases_observed"].map({True: "explicit_zero", False: "observed"})
    columns = ["epidemiological_year", "epidemiological_week", "week_start_date", "week_end_date", "week_convention", "dengue_cases_observed", "dengue_record_available", "dengue_zero_cases_observed", "epidemiological_status"]
    require_unique_weeks(result, "dengue_weekly")
    return result[columns]


def aggregate_climate(frame: pd.DataFrame, *, calendar: Calendar = LEGACY_CALENDAR) -> pd.DataFrame:
    """Agrega días con calendario explícito; el default conserva el MVP histórico.

    Para el principal usar DEFAULT_CALENDAR y sólo fechas de sus años verificados.
    La completitud oficial exige siete días distintos y cinco variables completas.
    No estima fechas de disponibilidad ni imputa observaciones ausentes.
    """
    official = calendar != LEGACY_CALENDAR
    fields = ["temperature_min", "temperature_max", "temperature_mean", "relative_humidity", "precipitation"]
    if official:
        frame = frame.copy()
        if frame["date"].isna().any() or frame["date"].duplicated().any():
            raise ValueError("Clima con fechas nulas o duplicadas")
        if not frame["date"].eq(frame["date"].dt.normalize()).all():
            raise ValueError("Clima requiere fechas diarias sin hora")
        for field in fields:
            if frame[field].dropna().map(lambda value: isinstance(value, bool)).any():
                raise ValueError("Clima requiere números, no booleanos")
            values = pd.to_numeric(frame[field], errors="raise")
            if not values.dropna().map(lambda value: float('-inf') < value < float('inf')).all():
                raise ValueError("Clima con valores no finitos")
            frame[field] = values
        if (frame["precipitation"].dropna().lt(0).any()
                or not frame["relative_humidity"].dropna().between(0, 100).all()):
            raise ValueError("Clima fuera de rango")
    labels = frame["date"].map(lambda value: calendar.date_week(value.date()))
    daily = frame.assign(epidemiological_year=labels.map(lambda value: value[0]).astype("int64"),
                         epidemiological_week=labels.map(lambda value: value[1]).astype("int64"))
    grouped = daily.groupby(["epidemiological_year", "epidemiological_week"], as_index=False, sort=True).agg(
        temperature_min_mean=("temperature_min", "mean"),
        temperature_max_mean=("temperature_max", "mean"),
        temperature_mean=("temperature_mean", "mean"),
        relative_humidity_mean=("relative_humidity", "mean"),
        precipitation_sum=("precipitation", lambda x: x.sum(min_count=1)),
        climate_days_observed=("date", "nunique"),
    )
    grouped = add_week_contract(grouped, calendar=calendar)
    grouped["climate_data_available"] = grouped["climate_days_observed"].gt(0)
    grouped["climate_week_complete"] = grouped["climate_days_observed"].eq(7)
    if official:
        valid_days = daily.groupby(["epidemiological_year", "epidemiological_week"], sort=True)[fields].count()
        grouped["climate_values_complete"] = valid_days.eq(7).all(axis=1).to_numpy()
        grouped["climate_week_complete"] &= grouped["climate_values_complete"]
        grouped["calendar_version"] = calendar.version
    columns = ["epidemiological_year", "epidemiological_week", "week_start_date", "week_end_date", "week_convention", "temperature_min_mean", "temperature_max_mean", "temperature_mean", "relative_humidity_mean", "precipitation_sum", "climate_days_observed", "climate_data_available", "climate_week_complete"]
    require_unique_weeks(grouped, "climate_weekly")
    if official:
        columns += ["climate_values_complete", "calendar_version"]
    return grouped[columns]


def integrate_weekly(dengue: pd.DataFrame, climate: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """Une ambas series sin imputar ausencias ni confundirlas con ceros."""
    keys = ["epidemiological_year", "epidemiological_week", "week_start_date", "week_end_date", "week_convention"]
    result = climate.merge(dengue, on=keys, how="outer", validate="one_to_one", sort=True)
    coverage_keys = set(map(tuple, coverage[["epidemiological_year", "epidemiological_week"]].to_numpy()))
    in_coverage = pd.Series(list(map(tuple, result[["epidemiological_year", "epidemiological_week"]].to_numpy())), index=result.index).isin(coverage_keys)
    result["dengue_record_available"] = result["dengue_record_available"].fillna(False).astype(bool)
    result["dengue_zero_cases_observed"] = result["dengue_zero_cases_observed"].fillna(False).astype(bool)
    result["climate_data_available"] = result["climate_data_available"].fillna(False).astype(bool)
    result["climate_week_complete"] = result["climate_week_complete"].fillna(False).astype(bool)
    result["epidemiological_status"] = result["epidemiological_status"].astype("string")
    result.loc[result["epidemiological_status"].isna() & in_coverage, "epidemiological_status"] = "missing_record"
    result.loc[result["epidemiological_status"].isna() & ~in_coverage, "epidemiological_status"] = "outside_source_coverage"
    require_unique_weeks(result, "department_weekly")
    return result.sort_values(keys).reset_index(drop=True)


def select_modeling_weeks(integrated: pd.DataFrame) -> pd.DataFrame:
    """Conserva sólo resultados observados con una semana climática completa."""
    eligible = integrated["epidemiological_status"].isin(["observed", "explicit_zero"]) & integrated["climate_week_complete"]
    result = integrated.loc[eligible].copy().reset_index(drop=True)
    if result["dengue_cases_observed"].isna().any():
        raise ValueError("modeling_weekly contiene casos nulos")
    require_unique_weeks(result, "modeling_weekly")
    return result
