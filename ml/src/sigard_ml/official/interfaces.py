"""Puertos para etapas futuras. No hay lectores, entrenamiento ni publicación.

Las implementaciones deberán exigir Control A antes de IO, Control B antes de
entrenamiento oficial y Control C antes de exportar cualquier payload público.
"""

from collections.abc import Sequence
from typing import Protocol

from sigard_ml.official.access import SourceRegistry
from sigard_ml.official.contracts import (
    DatasetMetadata, EpidemiologicalRecord, ObservedPanel, QualityReport,
    TerritorialAssignment, TerritorialPrediction, TrainingDataset,
)


class OfficialIngestor(Protocol):
    def ingest(self, registry: SourceRegistry, *, source_id: str, sheet: str,
               subset_ref: str) -> tuple[Sequence[EpidemiologicalRecord], QualityReport]:
        """Autoriza el alcance antes de abrir una fuente; no loguea sus valores."""
        ...


class RecordValidator(Protocol):
    def validate(self, records: Sequence[EpidemiologicalRecord]) -> QualityReport:
        """Valida sin asumir casos únicos ni eliminar posibles duplicados."""
        ...


class GeographicAssigner(Protocol):
    def assign(self, episodes: Sequence[EpidemiologicalRecord], *,
               cartography_version: str) -> Sequence[TerritorialAssignment]:
        """Una salida por episodio elegible; límites ambiguos quedan sin radio."""
        ...


class ObservedPanelBuilder(Protocol):
    def build(self, episodes: Sequence[EpidemiologicalRecord],
              assignments: Sequence[TerritorialAssignment], *,
              metadata: DatasetMetadata) -> tuple[ObservedPanel, QualityReport]:
        """Concilia asignables/no asignables y distingue ausencias de ceros."""
        ...


class FeatureBuilder(Protocol):
    def build(self, panel: ObservedPanel) -> TrainingDataset:
        """Usa historia y disponibilidad al corte, sin coordenadas individuales."""
        ...


class SpatialTrainer(Protocol):
    def fit(self, dataset: TrainingDataset, *, seed: int,
            training_approval_ref: str) -> object:
        """Exige protocolo aprobado (Control B); no publica al finalizar."""
        ...


class SpatialEvaluator(Protocol):
    def evaluate(self, dataset: TrainingDataset,
                 predictions: Sequence[TerritorialPrediction]) -> object:
        """Semanas futuras completas, baselines y errores territoriales."""
        ...


class PublicationPreparer(Protocol):
    def prepare(self, predictions: Sequence[TerritorialPrediction], *,
                publication_approval_ref: str) -> object:
        """Control C, privacidad y contrato nuevo antes de reutilizar la API."""
        ...
