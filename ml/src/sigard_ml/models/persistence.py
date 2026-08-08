"""Baseline temporal de persistencia."""

from __future__ import annotations

import pandas as pd


class PersistenceBaseline:
    """Predice t+1 copiando los casos disponibles en t."""

    def __init__(self, current_cases_column: str = "synthetic_cases_assigned") -> None:
        self.current_cases_column = current_cases_column

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """Devuelve predicciones no negativas sin requerir ni leer el target."""
        if self.current_cases_column not in features.columns:
            raise ValueError(f"Falta la columna contemporánea {self.current_cases_column!r}")
        current = pd.to_numeric(features[self.current_cases_column], errors="raise")
        if current.isna().any():
            raise ValueError("Los casos actuales no pueden contener nulos")
        if (current < 0).any():
            raise ValueError("Los casos actuales no pueden ser negativos")
        return current.clip(lower=0).rename("predicted_cases")
