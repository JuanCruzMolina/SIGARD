"""Features temporales departamentales, sin componentes espaciales."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

VALID_STATUSES = {"observed", "explicit_zero"}


def build_department_temporal_dataset(source: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Crea filas cutoff->t+1 mediante joins exactos de siete días."""
    frame = source.copy()
    frame["week_start_date"] = pd.to_datetime(frame["week_start_date"])
    frame["week_end_date"] = pd.to_datetime(frame["week_end_date"])
    eligible = frame["epidemiological_status"].isin(VALID_STATUSES) & frame["climate_week_complete"].eq(True)
    observed = frame.loc[eligible].sort_values("week_start_date").copy()
    if observed["dengue_cases_observed"].isna().any():
        raise ValueError("Una semana observada no puede tener casos nulos")
    by_date = observed.set_index("week_start_date", drop=False)

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for _, current in observed.iterrows():
        cutoff = current["week_start_date"]
        history_dates = [cutoff - pd.Timedelta(days=7 * lag) for lag in range(1, 4)]
        rolling4_dates = [cutoff - pd.Timedelta(days=7 * lag) for lag in range(4)]
        target_date = cutoff + pd.Timedelta(days=7)
        reasons = []
        if any(date not in by_date.index for date in rolling4_dates):
            reasons.append("insufficient_consecutive_history")
        if target_date not in by_date.index:
            reasons.append("missing_consecutive_target")
        if reasons:
            excluded.append({"cutoff_week": cutoff.date().isoformat(), "reasons": reasons})
            continue
        history = [by_date.loc[date] for date in rolling4_dates]
        cases = [float(item["dengue_cases_observed"]) for item in history]
        target = by_date.loc[target_date]
        week = int(current["epidemiological_week"])
        row = {
            "cutoff_week": cutoff, "cutoff_date": current["week_end_date"],
            "target_week": target_date, "target_week_start": target_date,
            "target_week_end": target["week_end_date"],
            "target_epidemiological_year": int(target["epidemiological_year"]),
            "target_epidemiological_week": int(target["epidemiological_week"]),
            "cases_current_week": cases[0], "cases_lag_1": cases[1],
            "cases_lag_2": cases[2], "cases_lag_3": cases[3],
            "cases_rolling_mean_2": float(np.mean(cases[:2])),
            "cases_rolling_mean_3": float(np.mean(cases[:3])),
            "cases_rolling_mean_4": float(np.mean(cases[:4])),
            "cases_trend_1": cases[0] - cases[1],
            "cases_trend_2": cases[0] - cases[2],
            "temperature_min_mean": float(current["temperature_min_mean"]),
            "temperature_max_mean": float(current["temperature_max_mean"]),
            "temperature_mean": float(current["temperature_mean"]),
            "relative_humidity_mean": float(current["relative_humidity_mean"]),
            "precipitation_sum": float(current["precipitation_sum"]),
            "temperature_mean_lag_1": float(history[1]["temperature_mean"]),
            "relative_humidity_lag_1": float(history[1]["relative_humidity_mean"]),
            "precipitation_lag_1": float(history[1]["precipitation_sum"]),
            "precipitation_rolling_sum_2": float(sum(item["precipitation_sum"] for item in history[:2])),
            "precipitation_rolling_sum_3": float(sum(item["precipitation_sum"] for item in history[:3])),
            "epidemiological_week": week,
            "week_sin": math.sin(2 * math.pi * week / 52),
            "week_cos": math.cos(2 * math.pi * week / 52),
            "target_cases_next_week": float(target["dengue_cases_observed"]),
            "target_condition": "official_observed_department_total",
        }
        rows.append(row)
    result = pd.DataFrame(rows).sort_values("cutoff_week").reset_index(drop=True)
    if list(result.columns.intersection(["radio_id", "synthetic_cases_assigned", "geometry", "spatial_clusters"])):
        raise ValueError("El dataset departamental contiene variables espaciales o sintéticas")
    if result[features + ["target_cases_next_week"]].isna().any().any():
        raise ValueError("El dataset temporal contiene nulos en features o target")
    gaps = observed.assign(delta_days=observed["week_start_date"].diff().dt.days)
    gap_records = gaps.loc[gaps["delta_days"].gt(7), ["week_start_date", "delta_days"]]
    status_counts = frame["epidemiological_status"].value_counts().to_dict()
    report = {
        "pipeline": {"name": "department_temporal_modeling", "version": "0.2.0"},
        "unit": "departamento Capital - semana epidemiológica",
        "source_rows": int(len(frame)), "official_supported_weeks": int(len(observed)),
        "total_rows": int(len(result)), "usable_weeks": int(len(result)),
        "excluded_source_status_counts": {k: int(v) for k, v in status_counts.items() if k not in VALID_STATUSES},
        "explicit_zero_weeks": int((frame["epidemiological_status"] == "explicit_zero").sum()),
        "excluded_eligible_weeks": excluded,
        "exclusion_reason_counts": {
            "insufficient_consecutive_history": sum("insufficient_consecutive_history" in x["reasons"] for x in excluded),
            "missing_consecutive_target": sum("missing_consecutive_target" in x["reasons"] for x in excluded),
        },
        "gaps": [{"next_observed_week": r.week_start_date.date().isoformat(), "gap_days": int(r.delta_days)} for r in gap_records.itertuples()],
        "nulls": {column: int(value) for column, value in result.isna().sum().items()},
        "temporal_range": {"cutoff_min": result.cutoff_week.min().date().isoformat(), "cutoff_max": result.cutoff_week.max().date().isoformat(), "target_min": result.target_week.min().date().isoformat(), "target_max": result.target_week.max().date().isoformat()},
        "target_statistics": {k: float(v) for k, v in result.target_cases_next_week.describe()[["min", "max", "mean", "50%", "std"]].items()},
        "features": features,
        "rules": ["missing_record y outside_source_coverage se excluyen, nunca se convierten a cero", "lags, rolling y target se resuelven por fechas separadas exactamente siete días", "el clima contemporáneo corresponde al cutoff; no se usa clima de la semana objetivo"],
    }
    return result, report
