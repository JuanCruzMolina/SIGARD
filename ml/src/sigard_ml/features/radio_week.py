"""Features temporales y espaciales sin anticipación para radio-semana."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _dated_values(panel: pd.DataFrame, weeks: int, output: str) -> pd.DataFrame:
    """Devuelve casos de t-weeks asociados a la fila fechada en t."""
    values = panel[["radio_id", "week_start_date", "synthetic_cases_assigned"]].copy()
    values["week_start_date"] += pd.Timedelta(weeks=weeks)
    return values.rename(columns={"synthetic_cases_assigned": output})


def add_temporal_features(panel: pd.DataFrame, case_lags: list[int], rolling_windows: list[int], target_horizon: int) -> pd.DataFrame:
    result = panel.copy()
    for lag in case_lags:
        result = result.merge(_dated_values(panel, lag, f"cases_lag_{lag}"), on=["radio_id", "week_start_date"], how="left", validate="one_to_one")
        result[f"cases_lag_{lag}"] = result[f"cases_lag_{lag}"].astype("Int64")
    for window in rolling_windows:
        columns = [f"cases_lag_{lag}" for lag in range(1, window + 1)]
        result[f"cases_rolling_mean_{window}"] = result[columns].mean(axis=1, skipna=False)
    future = panel[["radio_id", "week_start_date", "synthetic_cases_assigned"]].copy()
    future["week_start_date"] -= pd.Timedelta(weeks=target_horizon)
    future = future.rename(columns={"synthetic_cases_assigned": "target_cases_next_week"})
    result = result.merge(future, on=["radio_id", "week_start_date"], how="left", validate="one_to_one")
    result["target_cases_next_week"] = result["target_cases_next_week"].astype("Int64")
    return result


def neighbor_edges(territorial: pd.DataFrame, radio_column: str, neighbor_column: str) -> pd.DataFrame:
    edges = territorial[[radio_column, neighbor_column]].rename(columns={radio_column: "radio_id", neighbor_column: "neighbor_id"}).explode("neighbor_id")
    edges["radio_id"] = edges["radio_id"].astype("string")
    edges["neighbor_id"] = edges["neighbor_id"].astype("string")
    return edges.dropna().drop_duplicates().sort_values(["radio_id", "neighbor_id"]).reset_index(drop=True)


def add_neighbor_features(panel: pd.DataFrame, edges: pd.DataFrame, lags: list[int], aggregation: str) -> pd.DataFrame:
    if aggregation != "mean":
        raise ValueError(f"Agregación vecinal no soportada: {aggregation}")
    result = panel.copy()
    cases = panel[["radio_id", "week_start_date", "synthetic_cases_assigned"]].rename(columns={"radio_id": "neighbor_id"})
    for lag in lags:
        prior = cases.copy()
        prior["week_start_date"] += pd.Timedelta(weeks=lag)
        joined = edges.merge(prior, on="neighbor_id", how="left", validate="many_to_many")
        spatial = joined.groupby(["radio_id", "week_start_date"], as_index=False, sort=True)["synthetic_cases_assigned"].mean()
        spatial = spatial.rename(columns={"synthetic_cases_assigned": f"neighbor_cases_lag_{lag}"})
        result = result.merge(spatial, on=["radio_id", "week_start_date"], how="left", validate="one_to_one")
    return result


def build_panel(territorial: pd.DataFrame, weekly: pd.DataFrame, synthetic: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = config["columns"]
    territorial_columns = [c[k] for k in ("radio_id", "population", "households", "dwellings", "area_km2", "population_density")]
    names = {c[k]: k for k in ("radio_id", "population", "households", "dwellings", "area_km2", "population_density")}
    territory = territorial[territorial_columns].rename(columns=names)
    time_columns = [c["year"], c["week"], c["week_start"], c["week_end"], *config["climate_columns"]]
    canonical = {c["year"]: "epidemiological_year", c["week"]: "epidemiological_week", c["week_start"]: "week_start_date", c["week_end"]: "week_end_date"}
    time = weekly[time_columns].rename(columns=canonical).copy()
    source_keys = [c["year"], c["week"], c["week_start"], c["week_end"]]
    assignments = synthetic[[*source_keys, c["radio_id"], c["cases"]]].rename(columns={**canonical, c["radio_id"]: "radio_id", c["cases"]: "synthetic_cases_assigned"}).copy()
    keys = ["epidemiological_year", "epidemiological_week", "week_start_date", "week_end_date"]
    panel = assignments.merge(time, on=keys, how="left", validate="many_to_one").merge(territory, on="radio_id", how="left", validate="many_to_one")
    f = config["features"]
    panel = add_temporal_features(panel, f["case_lags"], f["rolling_windows"], f["target_horizon_weeks"])
    edges = neighbor_edges(territorial, c["radio_id"], c["neighbors"])
    panel = add_neighbor_features(panel, edges, f["neighbor_lags"], f["neighbor_aggregation"])
    order = ["radio_id", "week_start_date"]
    panel = panel.sort_values(order).reset_index(drop=True)
    required = config["training_requirements"]["required_columns"]
    modeling = panel.loc[panel[required].notna().all(axis=1)].copy().reset_index(drop=True)
    return panel, modeling
