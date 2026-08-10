"""Corte temporal mínimo y métricas para conteos radio-semana."""

from __future__ import annotations

import math

import pandas as pd


class EvaluationValidationError(ValueError):
    """El panel o el corte no satisface el contrato temporal."""


def _unique_weeks(panel: pd.DataFrame, week_column: str) -> pd.DataFrame:
    weeks = panel[[week_column]].drop_duplicates().sort_values(week_column).reset_index(drop=True)
    weeks[week_column] = pd.to_datetime(weeks[week_column])
    weeks["gap_days_from_previous"] = weeks[week_column].diff().dt.days.astype("Int64")
    weeks["continuous_block"] = weeks["gap_days_from_previous"].fillna(7).ne(7).cumsum().astype("int64")
    return weeks


def build_temporal_split(panel: pd.DataFrame, *, week_column: str = "week_start_date", test_weeks: int = 4) -> pd.DataFrame:
    """Reserva las últimas semanas consecutivas del bloque final como test."""
    if test_weeks < 1:
        raise EvaluationValidationError("test_weeks debe ser positivo")
    if week_column not in panel.columns:
        raise EvaluationValidationError(f"Falta {week_column!r}")
    weeks = _unique_weeks(panel, week_column)
    if len(weeks) <= test_weeks:
        raise EvaluationValidationError("No hay semanas suficientes para train y test")
    final_block = weeks.loc[weeks["continuous_block"].eq(weeks["continuous_block"].max())]
    if len(final_block) < test_weeks:
        raise EvaluationValidationError("El bloque temporal final es menor que el test solicitado")
    test_dates = set(final_block.tail(test_weeks)[week_column])
    weeks["split"] = weeks[week_column].map(lambda value: "test" if value in test_dates else "train")
    if weeks.loc[weeks.split.eq("train"), week_column].max() >= weeks.loc[weeks.split.eq("test"), week_column].min():
        raise EvaluationValidationError("Train debe preceder estrictamente a test")
    return weeks[[week_column, "gap_days_from_previous", "continuous_block", "split"]]


def validate_panel(panel: pd.DataFrame, columns: dict[str, str], expected_radios: int | None = None) -> None:
    required = set(columns.values())
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise EvaluationValidationError(f"Faltan columnas: {missing}")
    key = [columns["radio_id"], columns["week_start"]]
    if panel.duplicated(key).any():
        raise EvaluationValidationError("Hay claves radio-semana duplicadas")
    if panel[list(required)].isna().any().any():
        raise EvaluationValidationError("Las columnas requeridas contienen nulos")
    for name in ("current_cases", "target"):
        values = pd.to_numeric(panel[columns[name]], errors="raise")
        if (values < 0).any():
            raise EvaluationValidationError(f"{columns[name]} contiene valores negativos")
    if expected_radios is not None:
        counts = panel.groupby(columns["week_start"], sort=False)[columns["radio_id"]].nunique()
        if not counts.eq(expected_radios).all():
            raise EvaluationValidationError("Alguna semana no contiene el universo completo de radios")


def evaluate_predictions(predictions: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    """Calcula métricas por fila y errores de totales semanales."""
    actual = predictions["target_cases_next_week"].astype("float64")
    predicted = predictions["predicted_cases"].astype("float64")
    error = predicted - actual
    positive = actual.gt(0)
    metrics = {
        "mae": float(error.abs().mean()),
        "rmse": float(math.sqrt(error.pow(2).mean())),
        "median_absolute_error": float(error.abs().median()),
        "mae_target_gt_0": float(error.loc[positive].abs().mean()) if positive.any() else 0.0,
        "mean_bias": float(error.mean()),
        "target_zero_percentage": float(actual.eq(0).mean() * 100),
        "prediction_zero_percentage": float(predicted.eq(0).mean() * 100),
    }
    weekly = predictions.groupby(["target_week_start_date", "target_epidemiological_year", "target_epidemiological_week"], sort=True).agg(actual_total_cases=("target_cases_next_week", "sum"), predicted_total_cases=("predicted_cases", "sum")).reset_index()
    weekly["absolute_total_error"] = (weekly["predicted_total_cases"] - weekly["actual_total_cases"]).abs()
    return metrics, weekly
