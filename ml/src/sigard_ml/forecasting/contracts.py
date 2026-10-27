"""Contrato en memoria para probar el futuro adaptador de conteos acreditados."""

from dataclasses import dataclass
from datetime import date, timedelta
from numbers import Real

import numpy as np
import pandas as pd

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR

PROVISIONAL_EXPERIMENT = "provisional_aggregate_experiment"


class ForecastError(ValueError):
    """Entrada, disponibilidad o protocolo incompatible con el pronóstico."""


def require(condition, message):
    if not condition:
        raise ForecastError(message)


def day(value):
    """Fechas sin hora; los cortes representan el cierre del día declarado."""
    require(type(value) is date, "Se requiere fecha sin hora")
    return value


def week(value):
    day(value)
    year, number = DEFAULT_CALENDAR.date_week(value)
    require(DEFAULT_CALENDAR.week_bounds(year, number)[0] == value, "La semana debe comenzar en domingo")
    return year, number


def nonnegative(values, *, integer=False):
    require(not any(isinstance(value, (bool, np.bool_)) for value in values.dropna()), "Un booleano no es un conteo")
    require(all(isinstance(value, Real) for value in values.dropna()), "Se requieren números, no textos")
    try:
        numeric = pd.to_numeric(values, errors="raise").dropna().astype(float)
    except (TypeError, ValueError) as error:
        raise ForecastError("Variable numérica inválida") from error
    require(np.isfinite(numeric).all() and numeric.ge(0).all(), "Valores no finitos o negativos")
    if integer:
        require(numeric.eq(np.floor(numeric)).all(), "Los conteos deben ser enteros")


@dataclass
class Inputs:
    """Snapshots ficticios: nunca un permiso de uso epidemiológico.

    counts: radio_id, week_start, available_on, count, state, coverage_complete,
      pending, mature, source_ref. state: complete/provisional/unknown.
    climate: week_start, available_on, temperature, humidity, precipitation,
      complete, source_ref. Misma serie agregada para toda Capital.
    territory: radio_id, available_on, population, area_km2, source_ref.
    Cada snapshot reemplaza al anterior completo de esa clave.
    """

    radios: tuple[str, ...]
    counts: pd.DataFrame
    climate: pd.DataFrame
    territory: pd.DataFrame
    edges: tuple[tuple[str, str], ...]
    graph_available_on: date
    graph_ref: str
    dataset_version: str
    data_kind: str = "fictional"
    count_unit: str = "fictional_eligible_episode_count"

    def validate(self):
        # Antes de inspeccionar tablas: no hay un flag que habilite entradas reales.
        require(self.data_kind == "fictional", "Uso real bloqueado: faltan adaptador acreditado, P1–P6 y permisos")
        require(self.count_unit == "fictional_eligible_episode_count", "No confundir registros/notificaciones/presencia con conteos de episodios")
        require(type(self.radios) is tuple and bool(self.radios) and len(set(self.radios)) == len(self.radios), "Universo territorial vacío o duplicado")
        require(all(isinstance(radio, str) and radio.startswith("fictional_") for radio in self.radios), "Sólo identificadores enteramente ficticios")
        require(isinstance(self.dataset_version, str) and self.dataset_version.startswith("fictional_"), "Falta versión ficticia")
        day(self.graph_available_on)
        require(isinstance(self.graph_ref, str) and self.graph_ref.startswith("fictional_"), "Falta procedencia ficticia del grafo")
        self._validate_snapshots(lambda ref: isinstance(ref, str) and ref.startswith("fictional_"))

    def _validate_snapshots(self, valid_reference, *, retrospective=False):
        """Reglas comunes; el adaptador acreditado comprueba identidad y permisos antes."""
        specifications = (
            (self.counts, {"radio_id", "week_start", "available_on", "count", "state", "coverage_complete", "pending", "mature", "source_ref"}, ["radio_id", "week_start", "available_on"]),
            (self.climate, {"week_start", "available_on", "temperature", "humidity", "precipitation", "complete", "source_ref"}, ["week_start", "available_on"]),
            (self.territory, {"radio_id", "available_on", "population", "area_km2", "source_ref"}, ["radio_id", "available_on"]),
        )
        for frame, columns, keys in specifications:
            require(isinstance(frame, pd.DataFrame) and set(frame.columns) == columns, "Esquema de snapshots inválido; no admite campos personales ni coordenadas")
            require(not frame.duplicated(keys).any(), "Snapshot duplicado o ambiguo")
            required_keys = [key for key in keys if not retrospective or key != "available_on"]
            require(frame[required_keys + ["source_ref"]].notna().all().all(), "Clave o procedencia ausente")
            if retrospective:
                require(not frame.duplicated(required_keys).any(), "Exportación retrospectiva con revisiones ambiguas")
            require(frame.source_ref.map(valid_reference).all(), "Procedencia inválida para el contrato")
            for value in frame.available_on:
                if not retrospective or value is not None:
                    day(value)
            if "week_start" in frame:
                for value in frame.week_start:
                    week(value)
            if "radio_id" in frame:
                require(set(frame.radio_id) <= set(self.radios), "Radio ajeno al universo")
        require(set(self.counts.state) <= {"complete", "provisional", "unknown"}, "Estado de conteo inválido")
        for frame, columns in ((self.counts, ("coverage_complete", "pending", "mature")), (self.climate, ("complete",))):
            for column in columns:
                require(frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).all(), "Indicador debe ser booleano explícito")
        nonnegative(self.counts["count"], integer=True)
        complete = self.counts.state.eq("complete")
        require(self.counts.loc[complete, "count"].notna().all(), "Conteo completo nulo")
        for frame in (self.counts, self.climate):
            require(all((retrospective and row.available_on is None) or row.available_on >= row.week_start
                        for row in frame.itertuples()), "Snapshot anterior al inicio de su semana")
        require(all(row.available_on >= row.week_start + timedelta(days=6)
                    for row in self.counts.itertuples() if known_count(row)), "Conteo maduro antes del cierre semanal")
        require(all((retrospective and row.available_on is None) or row.available_on >= row.week_start + timedelta(days=6)
                    for row in self.climate.itertuples() if row.complete), "Clima completo antes del cierre semanal")
        for column in ("population", "area_km2"):
            nonnegative(self.territory[column])
        require(self.territory.area_km2.dropna().gt(0).all(), "Superficie debe ser positiva")
        nonnegative(self.climate.precipitation)
        for column in ("temperature", "humidity"):
            require(all(isinstance(value, Real) and not isinstance(value, (bool, np.bool_))
                        for value in self.climate[column].dropna()), "Clima debe ser numérico")
            values = pd.to_numeric(self.climate[column], errors="raise").dropna()
            require(np.isfinite(values).all(), "Clima no finito")
        require(self.climate.humidity.dropna().between(0, 100).all(), "Humedad fuera de rango")
        require(type(self.edges) is tuple and len(set(self.edges)) == len(self.edges), "Aristas duplicadas")
        for left, right in self.edges:
            require(left in self.radios and right in self.radios and left != right and (right, left) in self.edges, "Vecindad debe ser simétrica, sin lazos y del mismo universo")


def known_count(row):
    """Un positivo parcial no acredita el conteo completo de la celda."""
    return (row is not None and row.state == "complete" and row.coverage_complete
            and not row.pending and row.mature and pd.notna(row.count))


def experimental(inputs):
    return getattr(inputs, "experiment_mode", None) == PROVISIONAL_EXPERIMENT


def snapshot_scenario(inputs):
    return experimental(inputs) and inputs.count_unit == "snapshot_record_count"


def usable_count(inputs, row):
    """Registros observados sólo en la modalidad explícita; nunca los acredita."""
    if experimental(inputs):
        if snapshot_scenario(inputs):
            return (row is not None and row.state == "provisional" and not row.pending
                    and pd.notna(row.count) and row.count >= 0)
        return row is not None and row.state == "provisional" and pd.notna(row.count) and row.count > 0
    return known_count(row)
