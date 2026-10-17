"""Validaciones para las series temporales semanales."""

from __future__ import annotations

import pandas as pd

from sigard_ml.official.calendar_rules import Calendar, CalendarError, LEGACY_CALENDAR


class TemporalValidationError(ValueError):
    """Indica que una fuente temporal viola su contrato declarado."""


def require_columns(frame: pd.DataFrame, columns: list[str], source: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise TemporalValidationError(f"Columnas faltantes en {source}: {missing}")


def integer_values(values: pd.Series, field: str, minimum: int) -> tuple[pd.Series, pd.Series]:
    """Convierte enteros y devuelve también la máscara de valores inválidos."""
    numeric = pd.to_numeric(values, errors="coerce")
    invalid = numeric.isna() | numeric.lt(minimum) | numeric.mod(1).ne(0)
    converted = numeric.where(~invalid).astype("Int64")
    return converted, invalid


def epidemiological_week_start(year: pd.Series, week: pd.Series, *, calendar: Calendar = LEGACY_CALENDAR) -> pd.Series:
    """Domingo por versión; el pipeline histórico conserva explícitamente v0.

    El circuito oficial usa DEFAULT_CALENDAR. Este adaptador devuelve NaT ante
    valores inválidos, incluidos años no verificados en la versión solicitada.
    """
    if not year.index.equals(week.index):
        raise TemporalValidationError("Índices de año y semana incompatibles")
    years, invalid_year = integer_values(year, "year", 1)
    weeks, invalid_week = integer_values(week, "week", 1)
    starts = []
    for y, w, invalid in zip(years, weeks, invalid_year | invalid_week):
        try:
            starts.append(pd.NaT if invalid else calendar.week_bounds(int(y), int(w))[0])
        except CalendarError:
            starts.append(pd.NaT)
    return pd.Series(pd.to_datetime(starts), index=year.index)


def require_unique_weeks(frame: pd.DataFrame, source: str) -> None:
    """Rechaza más de una fila por año y semana epidemiológica."""
    keys = ["epidemiological_year", "epidemiological_week"]
    if frame.duplicated(keys, keep=False).any():
        raise TemporalValidationError(f"Semanas año-semana duplicadas en {source}")
