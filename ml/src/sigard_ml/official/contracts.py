"""Contratos internos validados; ningún constructor lee o escribe archivos."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from sigard_ml.official import SCHEMA_VERSION
from sigard_ml.official.calendar_rules import Calendar, CalendarError, DEFAULT_CALENDAR


class ContractError(ValueError):
    """Error estructural sin valores de registros en el mensaje."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_text(value: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), "Falta una referencia requerida")


def require_date(value: date) -> None:
    require(type(value) is date, "Se requiere una fecha sin hora")


def require_count(value: int) -> None:
    require(type(value) is int and value >= 0, "Se requiere un conteo entero no negativo")


def require_number(value: float) -> None:
    require(type(value) in (float, int) and math.isfinite(value), "Se requiere un número finito")


def require_radio(value: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{9}", value) is not None,
            "Se requiere un código de radio de nueve dígitos")


class DataKind(str, Enum):
    OFFICIAL_OBSERVED = "official_observed"
    FICTIONAL_FIXTURE = "fictional_fixture"


class RecordUnit(str, Enum):
    UNKNOWN = "unknown"
    PATIENT = "patient"
    EPISODE = "episode"
    NOTIFICATION = "notification"
    SAMPLE = "sample"
    UPDATE = "update"


class Eligibility(str, Enum):
    UNRESOLVED = "unresolved"
    ELIGIBLE_EPISODE = "eligible_episode"
    EXCLUDED = "excluded"


class LocationRole(str, Enum):
    UNKNOWN = "unknown"
    RESIDENCE = "residence"
    NOTIFICATION = "notification"


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    MISSING_COORDINATES = "missing_coordinates"
    INVALID_COORDINATES = "invalid_coordinates"
    UNKNOWN_CRS = "unknown_crs"
    OUTSIDE_CAPITAL = "outside_capital"
    BOUNDARY = "boundary"
    AMBIGUOUS = "ambiguous"


class ObservationStatus(str, Enum):
    OBSERVED = "observed"
    EXPLICIT_ZERO = "explicit_zero"
    MISSING = "missing_record"
    OUTSIDE_COVERAGE = "outside_source_coverage"


class Target(str, Enum):
    COUNT = "next_week_cases"
    OCCURRENCE = "next_week_occurrence"
    INCIDENCE = "next_week_incidence"


class EvaluationMode(str, Enum):
    RETROSPECTIVE = "retrospective"
    AS_OF_RECONSTRUCTED = "as_of_reconstructed"


@dataclass(frozen=True)
class EpidemiologicalWeek:
    """Intervalo domingo-sábado; la correspondencia año-SE la aporta calendar."""

    year: int
    number: int
    start: date
    end: date
    convention: str = "ARGENTINA_SNVS_SUNDAY_SATURDAY"
    calendar: Calendar = field(default=DEFAULT_CALENDAR, repr=False, kw_only=True)

    @property
    def calendar_version(self) -> str:
        return self.calendar.version

    def __post_init__(self) -> None:
        require(type(self.year) is int and 1 <= self.year < 9999, "Año epidemiológico inválido")
        require(type(self.number) is int and 1 <= self.number <= 53, "Semana epidemiológica inválida")
        require_date(self.start)
        require_date(self.end)
        require(self.start.weekday() == 6 and self.end == self.start + timedelta(days=6),
                "El intervalo debe ser domingo-sábado")
        require(isinstance(self.calendar, Calendar), "Configuración de calendario inválida")
        try:
            expected = self.calendar.week_bounds(self.year, self.number)
        except CalendarError as error:
            raise ContractError(str(error)) from error
        require(expected == (self.start, self.end),
                "El año y la SE no corresponden al intervalo en la versión de calendario")
        require(self.convention == "ARGENTINA_SNVS_SUNDAY_SATURDAY", "Convención no admitida")


@dataclass(frozen=True)
class DatasetMetadata:
    dataset_id: str
    data_kind: DataKind
    source_versions: tuple[str, ...]
    transformation_version: str
    period_start: date
    period_end: date
    territorial_version: str
    unit: str = "radio_censal_epidemiological_week"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value in (self.dataset_id, self.transformation_version, self.territorial_version):
            require_text(value)
        require(isinstance(self.data_kind, DataKind), "Clasificación de datos no admitida")
        require(type(self.source_versions) is tuple and bool(self.source_versions), "Falta procedencia")
        for value in self.source_versions:
            require_text(value)
        require_date(self.period_start)
        require_date(self.period_end)
        require(self.period_start <= self.period_end, "Período invertido")
        require(self.unit == "radio_censal_epidemiological_week", "Unidad no admitida")
        require(self.schema_version == SCHEMA_VERSION, "Versión de contrato no admitida")


@dataclass(frozen=True, repr=False)
class Coordinates:
    """Objeto privado. x=longitud e y=latitud únicamente si CRS es EPSG:4326."""

    x: float
    y: float
    crs: str
    role: LocationRole

    def __post_init__(self) -> None:
        require_number(self.x)
        require_number(self.y)
        require_text(self.crs)
        require(isinstance(self.role, LocationRole), "Rol de ubicación inválido")
        if self.crs == "EPSG:4326":
            require(-180 <= self.x <= 180 and -90 <= self.y <= 90, "Coordenadas fuera de rango")


@dataclass(frozen=True, repr=False)
class EpidemiologicalRecord:
    """Registro normalizado privado; no presume que una fila sea un caso.

    Las referencias deben ser opacas, sin nombres, documentos ni domicilios.
    La clasificación se referencia por una regla versionada, sin texto clínico.
    """

    record_ref: str
    source_id: str
    source_version: str
    record_unit: RecordUnit
    eligibility: Eligibility
    classification_rule_version: str
    epidemiological_date: date | None
    available_on: date | None
    coordinates: Coordinates | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for value in (self.record_ref, self.source_id, self.source_version, self.classification_rule_version):
            require_text(value)
        require(isinstance(self.record_unit, RecordUnit), "Unidad de registro inválida")
        require(isinstance(self.eligibility, Eligibility), "Elegibilidad inválida")
        require(self.eligibility != Eligibility.ELIGIBLE_EPISODE or self.record_unit == RecordUnit.EPISODE,
                "Sólo episodios resueltos pueden ser elegibles")
        for value in (self.epidemiological_date, self.available_on):
            if value is not None:
                require_date(value)
        require(self.coordinates is None or isinstance(self.coordinates, Coordinates), "Ubicación inválida")


@dataclass(frozen=True)
class TerritorialAssignment:
    episode_ref: str = field(repr=False)
    status: AssignmentStatus
    cartography_version: str
    radio_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.episode_ref)
        require_text(self.cartography_version)
        require(isinstance(self.status, AssignmentStatus), "Estado de asignación inválido")
        if self.status == AssignmentStatus.ASSIGNED:
            require_radio(self.radio_id)
        else:
            require(self.radio_id is None, "Una asignación no válida no puede tener radio")


class QualityCode(str, Enum):
    MISSING_DATE = "missing_date"
    INVALID_DATE = "invalid_date"
    UNRESOLVED_RECORD_UNIT = "unresolved_record_unit"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    UNASSIGNABLE = "unassignable"
    MISSING_WEEK = "missing_week"


@dataclass(frozen=True)
class QualityReport:
    """Conteos agregados internos; sin muestras, textos libres ni identificadores."""

    inspected_rows: int
    accepted_rows: int
    issue_counts: tuple[tuple[QualityCode, int], ...] = ()

    def __post_init__(self) -> None:
        require_count(self.inspected_rows)
        require_count(self.accepted_rows)
        require(self.accepted_rows <= self.inspected_rows, "Conteos de calidad incompatibles")
        require(type(self.issue_counts) is tuple, "Se requiere una secuencia inmutable de incidencias")
        codes = []
        for code, count in self.issue_counts:
            require(isinstance(code, QualityCode), "Código de calidad no admitido")
            require_count(count)
            require(count <= self.inspected_rows, "Conteo de incidencia excede registros inspeccionados")
            codes.append(code)
        require(len(codes) == len(set(codes)), "Código de calidad duplicado")

    def summary(self) -> dict:
        return {"inspected_rows": self.inspected_rows, "accepted_rows": self.accepted_rows,
                "issue_counts": {code.value: count for code, count in sorted(self.issue_counts)}}


@dataclass(frozen=True)
class ObservedRadioWeek:
    radio_id: str
    week: EpidemiologicalWeek
    observed_cases: int | None
    status: ObservationStatus
    geographic_coverage: float | None

    def __post_init__(self) -> None:
        require_radio(self.radio_id)
        require(isinstance(self.week, EpidemiologicalWeek), "Semana inválida")
        require(isinstance(self.status, ObservationStatus), "Estado de observación inválido")
        if self.status in (ObservationStatus.MISSING, ObservationStatus.OUTSIDE_COVERAGE):
            require(self.observed_cases is None, "Una ausencia no puede convertirse en cero")
        else:
            require_count(self.observed_cases)
            require((self.observed_cases == 0) == (self.status == ObservationStatus.EXPLICIT_ZERO),
                    "El cero debe declararse explícitamente")
        if self.geographic_coverage is not None:
            require_number(self.geographic_coverage)
            require(0 <= self.geographic_coverage <= 1, "Cobertura fuera de rango")


@dataclass(frozen=True)
class ObservedPanel:
    metadata: DatasetMetadata
    rows: tuple[ObservedRadioWeek, ...]

    def __post_init__(self) -> None:
        require(isinstance(self.metadata, DatasetMetadata), "Metadatos inválidos")
        require(type(self.rows) is tuple, "Se requieren filas inmutables")
        keys = set()
        for row in self.rows:
            require(isinstance(row, ObservedRadioWeek), "Fila observada inválida")
            key = (row.radio_id, row.week.start)
            require(key not in keys, "Clave radio-semana duplicada")
            keys.add(key)
            require(self.metadata.period_start <= row.week.start <= row.week.end <= self.metadata.period_end,
                    "Semana fuera del período declarado")


@dataclass(frozen=True)
class FeatureValue:
    """Valor agregado y fecha de disponibilidad, a verificar contra el corte.

    No admite coordenadas ni identificadores individuales; las futuras
    implementaciones deberán usar una lista explícita de variables agregadas.
    """

    name: str
    value: float
    observed_through: date
    available_on: date

    def __post_init__(self) -> None:
        require_text(self.name)
        require(re.fullmatch(
            r"cases_current|cases_lag_[1-9][0-9]*|cases_rolling_mean_[1-9][0-9]*|"
            r"cases_trend|season_sin|season_cos|population|households|dwellings|density|"
            r"neighbor_cases_lag_[1-9][0-9]*|temperature_min_mean|temperature_max_mean|"
            r"temperature_mean|relative_humidity_mean|precipitation_sum", self.name) is not None,
            "Variable fuera de las familias agregadas admitidas")
        require_number(self.value)
        require_date(self.observed_through)
        require_date(self.available_on)
        require(self.observed_through <= self.available_on, "Observación posterior a su disponibilidad")


@dataclass(frozen=True)
class TrainingExample:
    radio_id: str
    cutoff_date: date
    target_week: EpidemiologicalWeek
    target_value: float
    features: tuple[FeatureValue, ...]

    def __post_init__(self) -> None:
        require_radio(self.radio_id)
        require_date(self.cutoff_date)
        require(isinstance(self.target_week, EpidemiologicalWeek), "Semana objetivo inválida")
        require(self.target_week.start == self.cutoff_date + timedelta(days=1), "El objetivo debe ser la semana siguiente al corte")
        require_number(self.target_value)
        require(self.target_value >= 0, "Objetivo negativo")
        require(type(self.features) is tuple and bool(self.features), "Faltan variables predictoras")
        names = []
        for feature in self.features:
            require(isinstance(feature, FeatureValue), "Variable predictora inválida")
            require(feature.available_on <= self.cutoff_date, "Variable no disponible al corte")
            names.append(feature.name)
        require(len(names) == len(set(names)), "Variable predictora duplicada")


@dataclass(frozen=True)
class TrainingDataset:
    metadata: DatasetMetadata
    target: Target
    feature_names: tuple[str, ...]
    examples: tuple[TrainingExample, ...]
    evaluation_mode: EvaluationMode

    def __post_init__(self) -> None:
        require(isinstance(self.metadata, DatasetMetadata), "Metadatos inválidos")
        require(isinstance(self.target, Target), "Objetivo no admitido")
        require(isinstance(self.evaluation_mode, EvaluationMode), "Modo de evaluación inválido")
        require(type(self.feature_names) is tuple and bool(self.feature_names), "Falta lista de variables")
        for name in self.feature_names:
            require_text(name)
        require(len(self.feature_names) == len(set(self.feature_names)), "Lista de variables duplicada")
        require(type(self.examples) is tuple and bool(self.examples), "Faltan ejemplos de entrenamiento")
        keys = set()
        for example in self.examples:
            require(isinstance(example, TrainingExample), "Ejemplo de entrenamiento inválido")
            require(tuple(f.name for f in example.features) == self.feature_names, "Variables incompatibles con el contrato")
            key = (example.radio_id, example.target_week.start)
            require(key not in keys, "Ejemplo radio-semana duplicado")
            keys.add(key)
            require(self.metadata.period_start <= example.target_week.start <= example.target_week.end <= self.metadata.period_end,
                    "Objetivo fuera del período declarado")
            if self.target == Target.COUNT:
                require(example.target_value % 1 == 0, "El objetivo de casos debe ser entero")
            elif self.target == Target.OCCURRENCE:
                require(example.target_value in (0, 1), "El objetivo de aparición debe ser binario")


@dataclass(frozen=True)
class TerritorialPrediction:
    """Predicción interna experimental; no constituye un contrato público."""

    radio_id: str
    cutoff_date: date
    target_week: EpidemiologicalWeek
    target: Target
    value: float
    model_version: str
    dataset_id: str
    data_kind: DataKind

    def __post_init__(self) -> None:
        require_radio(self.radio_id)
        require_date(self.cutoff_date)
        require(isinstance(self.target_week, EpidemiologicalWeek), "Semana objetivo inválida")
        require(self.target_week.start == self.cutoff_date + timedelta(days=1), "Predicción fuera del horizonte semanal")
        require(isinstance(self.target, Target), "Objetivo no admitido")
        require(isinstance(self.data_kind, DataKind), "Clasificación de datos no admitida")
        require_number(self.value)
        require(self.value >= 0, "Predicción negativa")
        if self.target == Target.OCCURRENCE:
            require(self.value <= 1, "Probabilidad fuera de rango")
        for value in (self.model_version, self.dataset_id):
            require_text(value)

    @property
    def unit(self) -> str:
        return {Target.COUNT: "expected_cases", Target.OCCURRENCE: "probability",
                Target.INCIDENCE: "cases_per_100000_population"}[self.target]
