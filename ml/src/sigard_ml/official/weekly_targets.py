"""Objetivos de la semana exacta siguiente, separados de cualquier predictor."""

from datetime import timedelta

import pandas as pd

FEATURE_COLUMNS = ("radio_censal", "anio_epidemiologico", "semana_epidemiologica", "casos_observados")


def attach_next_week_target(panel):
    required = {"radio_censal", "fecha_inicio_semana", "fecha_fin_semana", "casos_observados",
                "estado_observacion", "cero_provisional", "registros_fecha_aproximada"}
    if not required <= set(panel):
        raise ValueError("Faltan campos para construir el objetivo semanal")
    keys = ["radio_censal", "fecha_inicio_semana"]
    if panel.duplicated(keys).any():
        raise ValueError("Celdas radio-semana repetidas")
    # No usa shift sobre filas disponibles: un hueco no salta a una semana futura.
    following = {(row.radio_censal, row.fecha_inicio_semana):
                 (row.casos_observados, row.estado_observacion, row.registros_fecha_aproximada)
                 for row in panel.itertuples()}
    targets, valid, provisional, approximate = [], [], [], []
    for row in panel.itertuples():
        target_key = row.radio_censal, row.fecha_inicio_semana + timedelta(days=7)
        if target_key not in following:
            value, is_provisional, has_approximate = None, False, False
        else:
            count, observation, approximate_count = following[target_key]
            if pd.isna(count):
                value = None
            elif count > 0:
                value = 1
            elif count == 0 and observation in {"cero_comprobado_bajo_reglas", "cero_declarado_provisional"}:
                value = 0
            else:
                raise ValueError("Cero sin respaldo explícito en la semana objetivo")
            is_provisional = value is not None  # También los positivos son conteos provisionales.
            has_approximate = bool(value == 1 and approximate_count > 0)
        targets.append(value)
        valid.append(value is not None)
        provisional.append(is_provisional)
        approximate.append(has_approximate)
    result = panel.copy()
    result["fecha_inicio_semana_objetivo"] = result.fecha_inicio_semana.map(lambda day: day + timedelta(days=7))
    result["objetivo_semana_siguiente"] = pd.array(targets, dtype="Int8")
    result["objetivo_valido"] = valid
    result["objetivo_provisional"] = provisional
    result["objetivo_con_fecha_aproximada"] = approximate
    result["candidato_retrospectivo_con_conteo_origen"] = result.casos_observados.notna() & result.objetivo_valido
    result["apto_entrenamiento"] = False
    validate_targets(result)
    return result


def validate_targets(panel):
    target = panel.objetivo_semana_siguiente
    if not target.dropna().isin([0, 1]).all() or not panel.objetivo_valido.eq(target.notna()).all():
        raise ValueError("Objetivos inválidos o desconocidos marcados como válidos")
    if (panel.fecha_inicio_semana_objetivo != panel.fecha_inicio_semana.map(lambda day: day + timedelta(days=7))).any():
        raise ValueError("El objetivo no corresponde a la semana inmediata siguiente")
    if panel.apto_entrenamiento.any():
        raise ValueError("Fase 4.2 sólo prepara un panel retrospectivo para revisión")


def origin_count_predictors(panel):
    """Proyección limitada al origen. No reconstruye disponibilidad histórica."""
    missing = set(FEATURE_COLUMNS) - set(panel)
    if missing:
        raise ValueError("Faltan columnas del origen temporal")
    return panel[list(FEATURE_COLUMNS)].copy()
