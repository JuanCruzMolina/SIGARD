"""Validación del calendario, ceros y objetivos temporales heredados."""

from datetime import date, timedelta

import pandas as pd

from sigard_ml.official.calendar import make_week, weeks_between
from sigard_ml.official.coverage_panel import validate_coverage_panel
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.weekly_targets import attach_next_week_target


def validate_panel(panel, radios, period):
    if panel.empty or panel.duplicated(KEYS).any() or panel.radio_censal.isna().any():
        raise ValueError("Grilla vacía o claves repetidas/inválidas")
    weeks = weeks_between(date.fromisoformat(period["start"]), date.fromisoformat(period["end"]))
    expected = {(radio, week.start) for radio in radios for week in weeks}
    if set(panel[KEYS].itertuples(index=False, name=None)) != expected:
        raise ValueError("No se conserva la grilla completa radio-semana")
    for row in panel[["anio_epidemiologico", "semana_epidemiologica", "fecha_inicio_semana", "fecha_fin_semana"]].drop_duplicates().itertuples(index=False):
        week = make_week(int(row.anio_epidemiologico), int(row.semana_epidemiologica))
        if row.fecha_inicio_semana != week.start or row.fecha_fin_semana != week.end:
            raise ValueError("Panel incompatible con el calendario corregido")
    if not panel.casos_observados.dropna().mod(1).eq(0).all():
        raise ValueError("Los registros deben ser conteos enteros")
    validate_coverage_panel(panel)
    recalculated = attach_next_week_target(panel)
    for name in ("objetivo_semana_siguiente", "objetivo_valido", "objetivo_provisional", "objetivo_con_fecha_aproximada", "fecha_inicio_semana_objetivo"):
        pd.testing.assert_series_equal(panel[name].reset_index(drop=True), recalculated[name], check_names=False)
    if panel.validado.any() or panel.apto_entrenamiento.any():
        raise ValueError("La preparación no admite paneles habilitados para entrenamiento")


def require_temporal_bounds(frame):
    if not (frame.fecha_inicio_semana_objetivo == frame.fecha_inicio_semana.map(lambda day: day + timedelta(days=7))).all():
        raise ValueError("Objetivo fuera de t+1")
    if (frame.fecha_fin_semana >= frame.fecha_inicio_semana_objetivo).any():
        raise ValueError("El origen intersecta la semana objetivo")
