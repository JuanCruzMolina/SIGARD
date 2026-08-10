"""Escenarios reproducibles de asignación sintética por radio censal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ClusterParameters:
    focus_count: int
    focus_intensity: float
    neighbor_intensity: float
    persistence_probability: float
    noise_sigma: float


def normalized_population(territorial: pd.DataFrame, population_column: str) -> np.ndarray:
    population = territorial[population_column].to_numpy(dtype="float64")
    if not np.isfinite(population).all() or (population < 0).any() or population.sum() <= 0:
        raise ValueError("La población debe ser finita, no negativa y tener suma positiva")
    return population / population.sum()


def _base_rows(week: Any, territorial: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    total = int(getattr(week, columns["observed_cases"]))
    return pd.DataFrame(
        {
            "epidemiological_year": getattr(week, columns["year"]),
            "epidemiological_week": getattr(week, columns["week"]),
            "week_start_date": getattr(week, columns["week_start"]),
            "week_end_date": getattr(week, columns["week_end"]),
            "radio_id": territorial[columns["radio_id"]].astype("string").to_numpy(),
            "department_cases_observed": total,
        }
    )


def _finish(rows: pd.DataFrame, assigned: np.ndarray, weights: np.ndarray, scenario: str, version: str, seed: int) -> pd.DataFrame:
    rows["synthetic_cases_assigned"] = assigned.astype("int64")
    rows["synthetic_allocation_weight"] = weights.astype("float64")
    rows["simulation_scenario"] = scenario
    rows["simulation_version"] = version
    rows["simulation_seed"] = seed
    return rows


def population_proportional(
    territorial: pd.DataFrame,
    weeks: pd.DataFrame,
    columns: dict[str, str],
    seed: int,
    version: str,
) -> pd.DataFrame:
    """Distribuye cada total semanal mediante una multinomial poblacional."""
    ordered = territorial.sort_values(columns["radio_id"]).reset_index(drop=True)
    weights = normalized_population(ordered, columns["population"])
    rng = np.random.default_rng(seed)
    frames = []
    for week in weeks.sort_values([columns["year"], columns["week"]]).itertuples(index=False):
        rows = _base_rows(week, ordered, columns)
        assigned = rng.multinomial(int(rows["department_cases_observed"].iloc[0]), weights)
        frames.append(_finish(rows, assigned, weights, "population_proportional", version, seed))
    return pd.concat(frames, ignore_index=True)


def _neighbors(value: Any) -> set[str]:
    if value is None:
        return set()
    return {str(item) for item in value}


def _focus_sequence(rng: np.random.Generator, radio_count: int, weeks: int, params: ClusterParameters) -> Iterator[np.ndarray]:
    previous = np.array([], dtype="int64")
    for _ in range(weeks):
        retained = previous[rng.random(len(previous)) < params.persistence_probability]
        retained = np.unique(retained)[: params.focus_count]
        available = np.setdiff1d(np.arange(radio_count), retained, assume_unique=True)
        needed = params.focus_count - len(retained)
        additions = rng.choice(available, size=needed, replace=False) if needed else np.array([], dtype="int64")
        previous = np.sort(np.concatenate([retained, additions])).astype("int64")
        yield previous


def spatial_clusters(
    territorial: pd.DataFrame,
    weeks: pd.DataFrame,
    columns: dict[str, str],
    seed: int,
    version: str,
    params: ClusterParameters,
) -> pd.DataFrame:
    """Favorece focos reproducibles y sus vecinos, con persistencia semanal."""
    ordered = territorial.sort_values(columns["radio_id"]).reset_index(drop=True)
    if not 1 <= params.focus_count <= len(ordered):
        raise ValueError("focus_count debe estar entre 1 y la cantidad de radios")
    if min(params.focus_intensity, params.neighbor_intensity, params.noise_sigma) < 0:
        raise ValueError("Las intensidades y noise_sigma no pueden ser negativas")
    if not 0 <= params.persistence_probability <= 1:
        raise ValueError("persistence_probability debe estar entre 0 y 1")
    population = normalized_population(ordered, columns["population"])
    radio_ids = ordered[columns["radio_id"]].astype("string").tolist()
    neighbor_sets = [_neighbors(value) for value in ordered[columns["neighbors"]]]
    rng = np.random.default_rng(seed)
    ordered_weeks = weeks.sort_values([columns["year"], columns["week"]])
    frames = []
    for week, focus_indices in zip(ordered_weeks.itertuples(index=False), _focus_sequence(rng, len(ordered), len(ordered_weeks), params), strict=True):
        focus_ids = {radio_ids[index] for index in focus_indices}
        multiplier = np.ones(len(ordered), dtype="float64")
        multiplier[focus_indices] += params.focus_intensity
        for index, neighbors in enumerate(neighbor_sets):
            if radio_ids[index] not in focus_ids and neighbors.intersection(focus_ids):
                multiplier[index] += params.neighbor_intensity
        noise = rng.lognormal(mean=0.0, sigma=params.noise_sigma, size=len(ordered))
        weights = population * multiplier * noise
        weights /= weights.sum()
        rows = _base_rows(week, ordered, columns)
        assigned = rng.multinomial(int(rows["department_cases_observed"].iloc[0]), weights)
        frames.append(_finish(rows, assigned, weights, "spatial_clusters", version, seed))
    return pd.concat(frames, ignore_index=True)
