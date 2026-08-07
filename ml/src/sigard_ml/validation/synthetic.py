"""Contrato y métricas para asignaciones sintéticas radio-semana."""

from __future__ import annotations

from typing import Any

import pandas as pd


class SyntheticValidationError(ValueError):
    """Indica una violación del contrato de asignación sintética."""


REQUIRED_COLUMNS = [
    "epidemiological_year", "epidemiological_week", "week_start_date", "week_end_date",
    "radio_id", "department_cases_observed", "synthetic_cases_assigned",
    "synthetic_allocation_weight", "simulation_scenario", "simulation_version", "simulation_seed",
]


def validate_allocation(frame: pd.DataFrame, expected_radios: int) -> dict[str, Any]:
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise SyntheticValidationError(f"Columnas faltantes: {missing}")
    keys = ["epidemiological_year", "epidemiological_week", "radio_id"]
    duplicate_count = int(frame.duplicated(keys).sum())
    null_count = int(frame[REQUIRED_COLUMNS].isna().sum().sum())
    assigned = frame["synthetic_cases_assigned"]
    negative_count = int(assigned.lt(0).sum())
    non_integer_count = int((assigned % 1 != 0).sum())
    weekly = frame.groupby(keys[:2], sort=True).agg(
        radio_count=("radio_id", "nunique"),
        row_count=("radio_id", "size"),
        observed_total=("department_cases_observed", "first"),
        observed_values=("department_cases_observed", "nunique"),
        assigned_total=("synthetic_cases_assigned", "sum"),
    )
    bad_radio_weeks = int(((weekly["radio_count"] != expected_radios) | (weekly["row_count"] != expected_radios)).sum())
    inconsistent_observed = int((weekly["observed_values"] != 1).sum())
    conservation_failures = int((weekly["assigned_total"] != weekly["observed_total"]).sum())
    failures = duplicate_count + null_count + negative_count + non_integer_count + bad_radio_weeks + inconsistent_observed + conservation_failures
    summary = {
        "weeks": int(len(weekly)), "rows": int(len(frame)), "expected_radios_per_week": expected_radios,
        "duplicate_key_rows": duplicate_count, "null_values": null_count, "negative_assignments": negative_count,
        "non_integer_assignments": non_integer_count, "weeks_with_invalid_radio_count": bad_radio_weeks,
        "weeks_with_inconsistent_department_total": inconsistent_observed, "weekly_conservation_failures": conservation_failures,
    }
    if failures:
        raise SyntheticValidationError(f"Asignación inválida: {summary}")
    return summary


def quality_metrics(frame: pd.DataFrame, top_n: int) -> dict[str, Any]:
    cases = frame["synthetic_cases_assigned"]
    weekly_total = frame.groupby(["epidemiological_year", "epidemiological_week"])["synthetic_cases_assigned"].transform("sum")
    shares = cases.div(weekly_total.where(weekly_total.ne(0))).fillna(0.0)
    concentration = shares.pow(2).groupby([frame["epidemiological_year"], frame["epidemiological_week"]]).sum()
    by_radio = frame.groupby("radio_id", as_index=False)["synthetic_cases_assigned"].sum().sort_values(["synthetic_cases_assigned", "radio_id"], ascending=[False, True])
    zero_count = int(cases.eq(0).sum())
    return {
        "zero_assignments": zero_count,
        "zero_assignment_proportion": zero_count / len(frame),
        "weekly_concentration_hhi": {f"{year}-W{week:02d}": float(value) for (year, week), value in concentration.items()},
        "concentration_hhi_summary": {"min": float(concentration.min()), "mean": float(concentration.mean()), "max": float(concentration.max())},
        "top_radios_by_total_assignment": by_radio.head(top_n).to_dict(orient="records"),
    }
