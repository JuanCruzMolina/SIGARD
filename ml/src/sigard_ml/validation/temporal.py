"""Validaciones para las series temporales semanales."""

from __future__ import annotations

import pandas as pd


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


def epidemiological_week_start(year: pd.Series, week: pd.Series) -> pd.Series:
    """Obtiene el domingo de una semana epidemiológica argentina."""
    text = year.astype("Int64").astype("string") + "-W" + week.astype("Int64").astype("string").str.zfill(2) + "-1"
    return pd.to_datetime(text, format="%G-W%V-%u", errors="coerce") - pd.Timedelta(days=1)


def require_unique_weeks(frame: pd.DataFrame, source: str) -> None:
    """Rechaza más de una fila por año y semana epidemiológica."""
    keys = ["epidemiological_year", "epidemiological_week"]
    if frame.duplicated(keys, keep=False).any():
        raise TemporalValidationError(f"Semanas año-semana duplicadas en {source}")
