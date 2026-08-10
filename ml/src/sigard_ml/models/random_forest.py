"""Random Forest reproducible para conteos sintéticos radio-semana."""

from __future__ import annotations

from typing import Any

from sklearn.ensemble import RandomForestRegressor


def build_random_forest(parameters: dict[str, Any]) -> RandomForestRegressor:
    """Construye el estimador sólo con los hiperparámetros declarados."""
    required = {
        "n_estimators", "max_depth", "min_samples_split", "min_samples_leaf",
        "max_features", "random_state", "n_jobs",
    }
    missing = sorted(required.difference(parameters))
    if missing:
        raise ValueError(f"Faltan parámetros de Random Forest: {missing}")
    return RandomForestRegressor(**parameters)
