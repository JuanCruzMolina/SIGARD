"""Predictores explícitos del origen, sin campos de la semana objetivo."""

from datetime import timedelta
import math

import numpy as np
import pandas as pd

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR

KEYS = ["radio_censal", "fecha_inicio_semana"]
LAGS = (1, 2, 3, 4)
WINDOWS = (4, 8, 12)
STATIC = ("superficie_km2", "poblacion", "densidad_poblacional")
CALENDAR_FEATURES = ["radio_censal", "anio_epidemiologico", "semana_epidemiologica",
                     "estacionalidad_seno", "estacionalidad_coseno"]


def calendar_predictors(panel):
    """Calendario conocido de antemano y código territorial de la grilla."""
    result = panel[KEYS + ["anio_epidemiologico", "semana_epidemiologica"]].copy()
    lengths = result.anio_epidemiologico.map({entry.year: entry.weeks for entry in DEFAULT_CALENDAR.years})
    phase = 2 * math.pi * (result.semana_epidemiologica - 1) / lengths
    result["estacionalidad_seno"] = np.sin(phase)
    result["estacionalidad_coseno"] = np.cos(phase)
    return result


def exact_lag(values, index, lag):
    """Fecha exacta; nunca salta huecos ni usa el orden de las filas."""
    keys = pd.MultiIndex.from_arrays([
        index.get_level_values(0),
        index.get_level_values(1).map(lambda day: day - timedelta(weeks=lag)),
    ], names=KEYS)
    return pd.Series(pd.array(values.reindex(keys), dtype="Int64"), index=index)


def history_features(values, index, prefix, *, include_origin=False):
    result = pd.DataFrame(index=index)
    if include_origin:
        result[prefix + "_origen"] = values.reindex(index)
    lagged = {lag: exact_lag(values, index, lag) for lag in range(1, max(WINDOWS) + 1)}
    for lag in LAGS:
        result[f"{prefix}_rezago_{lag}"] = lagged[lag]
    for window in WINDOWS:
        block = pd.concat([lagged[lag] for lag in range(1, window + 1)], axis=1)
        result[f"{prefix}_acumulado_{window}"] = block.sum(axis=1, min_count=window).astype("Int64")
        result[f"{prefix}_semanas_conocidas_{window}"] = block.notna().sum(axis=1).astype("Int64")
    # Disponibilidad del valor NO acredita disponibilidad histórica/completitud.
    for name in list(result):
        if "semanas_conocidas" not in name:
            result[name + "_valor_disponible"] = result[name].notna()
    return result


def build_features(panel, static, neighbors):
    panel = panel.sort_values(KEYS).reset_index(drop=True)
    result = calendar_predictors(panel)
    index = pd.MultiIndex.from_frame(panel[KEYS])
    counts = pd.Series(pd.array(panel.casos_observados, dtype="Int64"), index=index)
    local = history_features(counts, index, "registros_retro", include_origin=True)
    # Suma vecinal sólo si TODOS los vecinos son conocidos. Sin vecinos => null.
    weekly_sum, weekly_known = {}, {}
    weeks = sorted(panel.fecha_inicio_semana.unique())
    for radio in sorted(neighbors):
        adjacent = neighbors[radio]
        if adjacent:
            block = pd.concat([counts.xs(other, level=0).reindex(weeks).rename(other)
                               for other in adjacent], axis=1)
            total = block.sum(axis=1, min_count=len(adjacent)).astype("Int64")
            known = block.notna().sum(axis=1)
            for day in weeks:
                weekly_sum[radio, day], weekly_known[radio, day] = total.loc[day], known.loc[day]
        else:
            for day in weeks:
                weekly_sum[radio, day], weekly_known[radio, day] = pd.NA, 0
    adjacent_counts = pd.Series(pd.array([weekly_sum[key] for key in index], dtype="Int64"), index=index)
    adjacent_known = pd.Series(pd.array([weekly_known[key] for key in index], dtype="Int64"), index=index)
    spatial = history_features(adjacent_counts, index, "vecinos_retro")
    for lag in LAGS:
        spatial[f"vecinos_retro_conocidos_rezago_{lag}"] = exact_lag(adjacent_known, index, lag)
    result = pd.concat([result, local.reset_index(drop=True), spatial.reset_index(drop=True)], axis=1)
    attributes = static[["radio_censal", *STATIC]].copy()
    attributes["cantidad_vecinos"] = attributes.radio_censal.map(lambda radio: len(neighbors[radio]))
    result = result.merge(attributes, on="radio_censal", how="left", validate="many_to_one")
    for name in STATIC:
        result[name + "_valor_disponible"] = result[name].notna()
    result["historia_disponible_en_origen_validada"] = False
    result["contexto_censal_disponible_en_origen_validado"] = False
    return result


def feature_definitions(columns):
    definitions = {"radio_censal": {
        "kind": "categorical_territorial_identifier", "role": "key_and_candidate_predictor",
        "historical_availability_verified": False,
        "definition": "Current 2022 census radio universe; historical boundary/availability not verified",
        "unit": "census_code_not_numeric_magnitude", "max_source_week_offset": None,
    }}
    for name in columns:
        if name in KEYS:
            continue
        calendar = name in CALENDAR_FEATURES
        history = name.startswith(("registros_retro", "vecinos_retro"))
        base_name = name.removesuffix("_valor_disponible")
        offsets = None
        if history:
            if "_origen" in base_name:
                offsets = [0]
            elif "_acumulado_" in base_name or "_semanas_conocidas_" in base_name:
                offsets = list(range(-int(base_name.rsplit("_", 1)[1]), 0))
            else:
                offsets = [-int(base_name.rsplit("_", 1)[1])]
        definitions[name] = {
            "kind": "calendar" if calendar else "retrospective_history" if history else "territorial_context",
            "historical_availability_verified": calendar,
            "max_source_week_offset": 0 if name.startswith("registros_retro_origen") else -1 if history else None,
            "missing_policy": "preserve_null; full window/all neighbors required for sums",
            "window": "[t-W,t-1]" if "acumulado" in name or "semanas_conocidas" in name else None,
            "source_week_offsets": offsets,
            "spatial_aggregation": "all queen neighbors; no partial sums" if name.startswith("vecinos_retro") else None,
            "value_availability_indicator": name.endswith("_valor_disponible"),
            "unit": "provisional_eligible_records" if history else "km2" if name == "superficie_km2"
                else "persons" if name == "poblacion" else "persons_per_km2" if name == "densidad_poblacional"
                else "indicator_or_calendar_or_count",
        }
    return definitions
