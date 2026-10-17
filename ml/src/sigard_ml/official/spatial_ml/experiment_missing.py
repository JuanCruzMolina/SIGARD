"""Vista numérica futura: conserva NaN y distingue disponibilidad temporal."""

import numpy as np
import pandas as pd

from sigard_ml.official.spatial_ml.experiment_selection import BASE, SHORT, LONG, NEIGHBOR


def numeric_view(features, selected, *, mode="retrospective", available_at_origin=None):
    """No ajusta parámetros ni escribe sobre las observaciones originales.

    `available_at_origin` es evidencia externa, nunca inferida desde una fecha
    de síntomas o muestra. En modo operativo se bloquea lo no acreditado.
    """
    if mode not in {"retrospective", "point_in_time"} or not selected or len(selected) != len(set(selected)):
        raise ValueError("Modo o selección de variables inválidos")
    if not set(selected) <= set(BASE + SHORT + LONG + NEIGHBOR):
        raise ValueError("Variables fuera de la lista permitida")
    original = features[selected].astype("float64").copy()
    if np.isinf(original.to_numpy()).any():
        raise ValueError("No se admiten valores infinitos")
    evidence = pd.DataFrame(False, index=original.index, columns=selected)
    if available_at_origin is not None:
        if not available_at_origin.index.equals(original.index) or list(available_at_origin.columns) != selected:
            raise ValueError("La evidencia temporal no coincide con los valores")
        if not available_at_origin.stack().isin([True, False]).all():
            raise ValueError("Evidencia temporal inválida")
        evidence = available_at_origin.fillna(False).astype(bool)
    states = pd.DataFrame("known_value", index=original.index, columns=selected)
    states[original.eq(0)] = "known_numeric_zero_not_an_epidemiological_label"
    states[original.isna()] = "unknown_value"
    states[~evidence & original.notna()] = "value_present_but_historical_availability_unverified"
    for name in selected:
        if name.startswith(("registros_retro_", "vecinos_retro_")):
            zero = original[name].eq(0)
            states.loc[zero & evidence[name], name] = "supported_observation_zero"
            states.loc[zero & ~evidence[name], name] = "supported_observation_zero_historical_availability_unverified"
    result = original if mode == "retrospective" else original.where(evidence)
    if mode == "point_in_time":
        states[~evidence] = "temporally_unavailable_or_unverified"
    indicators = result.isna().rename(columns=lambda name: name + "_missing")
    return result, indicators, states
