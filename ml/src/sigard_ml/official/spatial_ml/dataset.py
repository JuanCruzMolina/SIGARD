"""Geografía verificable; predictores, etiquetas y auditoría separados."""

import numpy as np
import pandas as pd

from sigard_ml.official.cartography import validate_radios
from sigard_ml.official.spatial_ml.features import KEYS, STATIC, build_features, calendar_predictors
from sigard_ml.official.spatial_ml.validation import require_temporal_bounds, validate_panel


def territorial_context(radios, *, expected_count=263):
    validate_radios(radios, expected_count=expected_count)
    ordered = radios.sort_values("radio_id").reset_index(drop=True)
    ids = set(ordered.radio_id)
    neighbors = {row.radio_id: sorted(list(row.neighbor_ids)) for row in ordered.itertuples()}
    for radio, adjacent in neighbors.items():
        if radio in adjacent or len(adjacent) != len(set(adjacent)) or not set(adjacent) <= ids:
            raise ValueError("Vecindad inválida")
        if any(radio not in neighbors[other] for other in adjacent):
            raise ValueError("Vecindad asimétrica")
    # Contraste completo de contigüidad queen, incluida la ausencia de aristas.
    # No se reparan polígonos ni se geocodifica.
    verified = {radio: [] for radio in ids}
    for i, row in enumerate(ordered.itertuples()):
        for j in ordered.sindex.query(row.geometry, predicate="touches"):
            if j != i:
                verified[row.radio_id].append(ordered.radio_id.iloc[j])
    if any(sorted(verified[radio]) != neighbors[radio] for radio in ids):
        raise ValueError("Vecindad no coincide con las geometrías existentes")
    static = pd.DataFrame(ordered[["radio_id", *STATIC]]).rename(columns={"radio_id": "radio_censal"})
    for column in STATIC:
        values = pd.to_numeric(static[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all() or values.lt(0).any():
            raise ValueError("Contexto censal inválido; no imputar valores")
        static[column] = values
    if static.superficie_km2.le(0).any() or not static.poblacion.mod(1).eq(0).all():
        raise ValueError("Superficie/población inválida")
    if not np.allclose(static.densidad_poblacional, static.poblacion / static.superficie_km2):
        raise ValueError("Densidad inconsistente con población y área")
    if not np.allclose(static.superficie_km2, ordered.to_crs("EPSG:32719").area / 1e6, rtol=1e-6):
        raise ValueError("Área inconsistente con las geometrías")
    return static, neighbors


def build_dataset(panel, static, neighbors, period):
    panel = panel.sort_values(KEYS).reset_index(drop=True)
    validate_panel(panel, set(static.radio_censal), period)
    require_temporal_bounds(panel)
    labels = panel[KEYS + ["fecha_inicio_semana_objetivo", "objetivo_semana_siguiente", "objetivo_valido",
                          "objetivo_provisional", "objetivo_con_fecha_aproximada", "escenario", "panel_fechas"]].copy()
    labels["apto_entrenamiento"] = False
    # Contexto completo para auditoría, no para incorporarlo automáticamente a X.
    return {"predictors_retrospective": build_features(panel, static, neighbors),
            "predictors_calendar": calendar_predictors(panel), "labels": labels, "context": panel.copy()}
