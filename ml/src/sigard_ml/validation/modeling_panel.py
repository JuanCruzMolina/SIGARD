"""Validaciones del panel de modelado radio-semana."""

from __future__ import annotations

from typing import Any

import pandas as pd


class ModelingPanelValidationError(ValueError):
    """Indica una violación del contrato del panel."""


def validate_inputs(territorial: pd.DataFrame, weekly: pd.DataFrame, synthetic: pd.DataFrame, config: dict[str, Any]) -> None:
    c = config["columns"]
    requirements = {
        "territorial": [c[k] for k in ("radio_id", "population", "households", "dwellings", "area_km2", "population_density", "neighbors")],
        "weekly": [c[k] for k in ("year", "week", "week_start", "week_end")] + config["climate_columns"],
        "synthetic": [c[k] for k in ("radio_id", "year", "week", "week_start", "week_end", "cases")],
    }
    for name, frame in (("territorial", territorial), ("weekly", weekly), ("synthetic", synthetic)):
        missing = sorted(set(requirements[name]) - set(frame.columns))
        if missing:
            raise ModelingPanelValidationError(f"Columnas faltantes en {name}: {missing}")
    expected = int(config["universe"]["expected_radio_count"])
    if len(territorial) != expected or territorial[c["radio_id"]].nunique() != expected:
        raise ModelingPanelValidationError(f"El maestro no contiene {expected} radios únicos")
    if weekly.duplicated([c["year"], c["week"]]).any():
        raise ModelingPanelValidationError("Semanas duplicadas en modeling_weekly")
    if synthetic.duplicated([c["radio_id"], c["year"], c["week"]]).any():
        raise ModelingPanelValidationError("Claves duplicadas en asignaciones sintéticas")
    counts = synthetic.groupby([c["year"], c["week"]])[c["radio_id"]].agg(["size", "nunique"])
    if not counts.eq(expected).all().all():
        raise ModelingPanelValidationError(f"No todas las semanas contienen exactamente {expected} radios")
    territorial_ids = set(territorial[c["radio_id"]].astype(str))
    synthetic_ids = set(synthetic[c["radio_id"]].astype(str))
    if synthetic_ids != territorial_ids:
        raise ModelingPanelValidationError("Los radios sintéticos no coinciden exactamente con el maestro territorial")
    declared_neighbors = {str(value) for values in territorial[c["neighbors"]] for value in values}
    if not declared_neighbors.issubset(territorial_ids):
        raise ModelingPanelValidationError("neighbor_ids contiene radios ajenos al maestro territorial")
    date_keys = [c["year"], c["week"], c["week_start"], c["week_end"]]
    synthetic_weeks = synthetic[date_keys].drop_duplicates().sort_values(date_keys).reset_index(drop=True)
    weekly_weeks = weekly[date_keys].sort_values(date_keys).reset_index(drop=True)
    if not synthetic_weeks.equals(weekly_weeks):
        raise ModelingPanelValidationError("Las semanas o fechas sintéticas no coinciden con modeling_weekly")
    cases = pd.to_numeric(synthetic[c["cases"]], errors="coerce")
    if cases.isna().any() or cases.lt(0).any() or cases.mod(1).ne(0).any():
        raise ModelingPanelValidationError("Los casos sintéticos deben ser enteros no negativos y no nulos")


def _gap_records(panel: pd.DataFrame) -> list[dict[str, Any]]:
    weeks = panel[["epidemiological_year", "epidemiological_week", "week_start_date"]].drop_duplicates().sort_values("week_start_date")
    weeks["days_since_previous"] = weeks["week_start_date"].diff().dt.days
    return weeks.loc[weeks["days_since_previous"].gt(7)].assign(week_start_date=lambda x: x.week_start_date.dt.strftime("%Y-%m-%d")).to_dict(orient="records")


def validate_and_report(panel: pd.DataFrame, modeling: pd.DataFrame, territorial: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    keys = ["radio_id", "epidemiological_year", "epidemiological_week"]
    duplicate_count = int(panel.duplicated(keys).sum())
    sorted_ok = panel.index.equals(panel.sort_values(["radio_id", "week_start_date"]).index)
    date_span_bad = int((panel["week_end_date"] - panel["week_start_date"]).dt.days.ne(6).sum())
    if duplicate_count or not sorted_ok or date_span_bad:
        raise ModelingPanelValidationError("El panel viola claves, orden o calendario semanal")
    lookup = panel.set_index(["radio_id", "week_start_date"])["synthetic_cases_assigned"]
    leakage_failures = 0
    for lag in config["features"]["case_lags"]:
        expected = pd.Series([lookup.get((r, d - pd.Timedelta(weeks=lag)), pd.NA) for r, d in zip(panel.radio_id, panel.week_start_date)], dtype="Float64")
        actual = panel[f"cases_lag_{lag}"].astype("Float64")
        leakage_failures += int(~(actual.eq(expected) | (actual.isna() & expected.isna())).all())
    target_expected = pd.Series([lookup.get((r, d + pd.Timedelta(weeks=1)), pd.NA) for r, d in zip(panel.radio_id, panel.week_start_date)], dtype="Float64")
    target_actual = panel["target_cases_next_week"].astype("Float64")
    target_failures = int(~(target_actual.eq(target_expected) | (target_actual.isna() & target_expected.isna())).all())
    edges = set()
    c = config["columns"]
    for radio, neighbors in territorial[[c["radio_id"], c["neighbors"]]].itertuples(index=False):
        edges.update((str(radio), str(neighbor)) for neighbor in neighbors)
    neighbor_failures = 0
    for lag in config["features"]["neighbor_lags"]:
        expected_values = []
        for radio, date in zip(panel.radio_id, panel.week_start_date):
            values = [lookup.get((neighbor, date - pd.Timedelta(weeks=lag)), pd.NA) for owner, neighbor in edges if owner == str(radio)]
            available = [float(value) for value in values if not pd.isna(value)]
            expected_values.append(sum(available) / len(available) if available else pd.NA)
        expected = pd.Series(expected_values, dtype="Float64")
        actual = panel[f"neighbor_cases_lag_{lag}"].astype("Float64")
        neighbor_failures += int(~(actual.eq(expected) | (actual.isna() & expected.isna())).all())
    required = config["training_requirements"]["required_columns"]
    exclusion_counts = {column: int(panel[column].isna().sum()) for column in required}
    excluded = panel.loc[~panel[required].notna().all(axis=1), required]
    reason_counts = excluded.isna().apply(lambda row: ",".join(row.index[row]), axis=1).value_counts().sort_index()
    target = modeling["target_cases_next_week"]
    gaps = _gap_records(panel)
    report = {
        "pipeline": config["pipeline"], "inputs": config["inputs"],
        "unit": "radio censal - semana epidemiológica",
        "data_nature": {"synthetic_cases_assigned": "asignación sintética, no evidencia epidemiológica espacial", "target_cases_next_week": "asignación sintética t+1 del mismo radio"},
        "coverage": {"first_week_start": panel.week_start_date.min().strftime("%Y-%m-%d"), "last_week_start": panel.week_start_date.max().strftime("%Y-%m-%d"), "weeks": int(panel.week_start_date.nunique())},
        "rows": {"radio_week_panel": len(panel), "modeling_panel": len(modeling), "excluded": len(panel) - len(modeling)},
        "exclusions": {"missing_by_requirement": exclusion_counts, "reason_combinations": {str(k): int(v) for k, v in reason_counts.items()}},
        "target_distribution": {"count": int(target.count()), "min": float(target.min()), "mean": float(target.mean()), "std": float(target.std()), "q25": float(target.quantile(0.25)), "median": float(target.median()), "q75": float(target.quantile(0.75)), "max": float(target.max()), "zero_count": int(target.eq(0).sum()), "zero_percentage": float(target.eq(0).mean() * 100)},
        "quality": {"expected_radios_per_week": int(config["universe"]["expected_radio_count"]), "weeks_with_invalid_radio_count": 0, "duplicate_key_rows": duplicate_count, "temporal_gaps": gaps, "temporal_gap_count": len(gaps), "non_consecutive_target_failures": target_failures, "lag_reconstruction_failures": leakage_failures, "neighbor_reconstruction_failures": neighbor_failures, "neighbor_edges_declared": len(edges), "leakage_checks_passed": target_failures + leakage_failures + neighbor_failures == 0},
    }
    if not report["quality"]["leakage_checks_passed"]:
        raise ModelingPanelValidationError(f"Fallaron controles de leakage: {report['quality']}")
    return report
