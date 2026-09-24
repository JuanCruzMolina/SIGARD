import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from .config import get_settings
from .database import build_engine
from .models import (
    ExperimentalSpatialResult,
    PublicationBatch,
    PublicationWeek,
    TemporalPrediction,
    TerritorialRadio,
)


CONTRACT_FILES = (
    "available_weeks.json",
    "temporal_predictions.json",
    "territorial_context.geojson",
    "experimental_spatial_history.geojson",
    "model_evaluation.json",
    "mvp_metadata.json",
)
LEVELS = {"very_low", "low", "medium", "high"}
PRIVATE_KEYS = {
    "actor_user_id",
    "address_reference",
    "description",
    "email",
    "internal_notes",
    "password",
    "password_hash",
    "privacy_notice_version",
    "retention_until",
    "submission_key_hash",
    "tracking_code",
}


@dataclass(frozen=True)
class PublicationPayload:
    input_hash: str
    default_cutoff_date: date
    weeks: list[dict[str, Any]]
    model: dict[str, Any]
    predictions: list[dict[str, Any]]
    territorial_features: list[dict[str, Any]]
    experimental_features: list[dict[str, Any]]
    model_evaluation: dict[str, Any]
    metadata: dict[str, Any]


def _read_contracts(source_dir: Path) -> tuple[dict[str, Any], str]:
    documents: dict[str, Any] = {}
    digest = hashlib.sha256()
    for filename in CONTRACT_FILES:
        path = source_dir / filename
        if not path.is_file():
            raise ValueError(f"Falta el contrato requerido: {filename}")
        content = path.read_bytes()
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        try:
            documents[filename] = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON inválido en {filename}") from error
    return documents, digest.hexdigest()


def _assert_no_private_keys(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in PRIVATE_KEYS:
                raise ValueError(f"Campo privado no permitido en contrato público: {path}.{key}")
            _assert_no_private_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_private_keys(nested, f"{path}[{index}]")


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} debe ser una fecha ISO")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Fecha inválida en {label}: {value}") from error


def _assert_feature_collection(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise ValueError(f"{label} no es una FeatureCollection")
    features = value.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{label}.features debe ser una lista")
    return features


def _radio_properties(feature: dict[str, Any], label: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise ValueError(f"Feature inválida en {label}")
    radio_id = properties.get("radio_id")
    if not isinstance(radio_id, str) or not radio_id:
        raise ValueError(f"radio_id inválido en {label}")
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Geometría no poligonal para el radio {radio_id}")
    if not isinstance(geometry.get("coordinates"), list):
        raise ValueError(f"Coordenadas inválidas para el radio {radio_id}")
    return radio_id, properties, geometry


def load_and_validate(source_dir: Path) -> PublicationPayload:
    documents, input_hash = _read_contracts(source_dir)
    for filename, document in documents.items():
        _assert_no_private_keys(document, filename)

    available = documents["available_weeks.json"]
    predictions_document = documents["temporal_predictions.json"]
    weeks = available.get("weeks") if isinstance(available, dict) else None
    predictions = predictions_document.get("predictions") if isinstance(predictions_document, dict) else None
    model = predictions_document.get("model") if isinstance(predictions_document, dict) else None
    if not isinstance(weeks, list) or not weeks:
        raise ValueError("No hay semanas publicables")
    if not isinstance(predictions, list) or not isinstance(model, dict):
        raise ValueError("El contrato de predicciones es inválido")

    territorial_features = _assert_feature_collection(
        documents["territorial_context.geojson"], "territorial_context"
    )
    experimental_features = _assert_feature_collection(
        documents["experimental_spatial_history.geojson"], "experimental_spatial_history"
    )
    if len(territorial_features) != 263:
        raise ValueError("El contexto territorial debe contener exactamente 263 radios")

    territorial_by_radio: dict[str, dict[str, Any]] = {}
    territorial_geometry: dict[str, dict[str, Any]] = {}
    for feature in territorial_features:
        radio_id, properties, geometry = _radio_properties(feature, "territorial_context")
        if radio_id in territorial_by_radio:
            raise ValueError(f"Radio territorial duplicado: {radio_id}")
        if properties.get("relative_level") not in LEVELS:
            raise ValueError(f"Nivel territorial inválido para {radio_id}")
        territorial_by_radio[radio_id] = properties
        territorial_geometry[radio_id] = geometry

    weeks_by_cutoff: dict[date, dict[str, Any]] = {}
    for week in weeks:
        cutoff = _parse_date(week.get("cutoff_date"), "weeks.cutoff_date")
        start = _parse_date(week.get("target_week_start"), "weeks.target_week_start")
        end = _parse_date(week.get("target_week_end"), "weeks.target_week_end")
        if cutoff in weeks_by_cutoff:
            raise ValueError(f"Semana duplicada para el corte {cutoff}")
        if start != cutoff + timedelta(days=1) or end != cutoff + timedelta(days=7):
            raise ValueError(f"Intervalo objetivo no consecutivo para el corte {cutoff}")
        if week.get("has_temporal_prediction") is not True or week.get("has_experimental_spatial") is not True:
            raise ValueError(f"El corte {cutoff} no tiene ambos productos publicables")
        weeks_by_cutoff[cutoff] = week

    predictions_by_cutoff: dict[date, dict[str, Any]] = {}
    for prediction in predictions:
        cutoff = _parse_date(prediction.get("cutoff_date"), "predictions.cutoff_date")
        if cutoff in predictions_by_cutoff:
            raise ValueError(f"Predicción duplicada para el corte {cutoff}")
        week = weeks_by_cutoff.get(cutoff)
        if week is None:
            raise ValueError(f"Predicción sin semana publicada: {cutoff}")
        if prediction.get("target_week_start") != week.get("target_week_start") or prediction.get(
            "target_week_end"
        ) != week.get("target_week_end"):
            raise ValueError(f"Predicción desalineada para el corte {cutoff}")
        if float(prediction.get("predicted_cases", -1)) < 0:
            raise ValueError(f"Predicción negativa para el corte {cutoff}")
        predictions_by_cutoff[cutoff] = prediction
    if set(predictions_by_cutoff) != set(weeks_by_cutoff):
        raise ValueError("Las predicciones no cubren exactamente las semanas publicadas")

    experimental_counts = {cutoff: 0 for cutoff in weeks_by_cutoff}
    experimental_keys: set[tuple[date, str]] = set()
    for feature in experimental_features:
        radio_id, properties, geometry = _radio_properties(feature, "experimental_spatial_history")
        cutoff = _parse_date(properties.get("cutoff_date"), "experimental.cutoff_date")
        week = weeks_by_cutoff.get(cutoff)
        if week is None:
            raise ValueError(f"Resultado experimental sin semana publicada: {cutoff}")
        key = (cutoff, radio_id)
        if key in experimental_keys:
            raise ValueError(f"Resultado experimental duplicado: {cutoff}/{radio_id}")
        if radio_id not in territorial_by_radio:
            raise ValueError(f"Radio experimental desconocido: {radio_id}")
        if geometry != territorial_geometry[radio_id]:
            raise ValueError(f"Geometría experimental distinta para el radio {radio_id}")
        if properties.get("target_week_start") != week.get("target_week_start") or properties.get(
            "target_week_end"
        ) != week.get("target_week_end"):
            raise ValueError(f"Resultado experimental desalineado: {cutoff}/{radio_id}")
        if properties.get("relative_level") not in LEVELS:
            raise ValueError(f"Nivel experimental inválido: {cutoff}/{radio_id}")
        if float(properties.get("experimental_spatial_score", -1)) < 0:
            raise ValueError(f"Score experimental negativo: {cutoff}/{radio_id}")
        experimental_keys.add(key)
        experimental_counts[cutoff] += 1
    if any(count != 263 for count in experimental_counts.values()):
        raise ValueError("Cada semana experimental debe contener exactamente 263 radios")
    if len(experimental_features) != 263 * len(weeks_by_cutoff):
        raise ValueError("La historia experimental contiene filas fuera del contrato")

    default_cutoff = _parse_date(available.get("default_cutoff_date"), "default_cutoff_date")
    if default_cutoff not in weeks_by_cutoff:
        raise ValueError("El corte predeterminado no está disponible")

    return PublicationPayload(
        input_hash=input_hash,
        default_cutoff_date=default_cutoff,
        weeks=weeks,
        model=model,
        predictions=predictions,
        territorial_features=territorial_features,
        experimental_features=experimental_features,
        model_evaluation=documents["model_evaluation.json"],
        metadata=documents["mvp_metadata.json"],
    )


def import_publication(database_url: str, source_dir: Path, version: str | None = None) -> tuple[str, bool]:
    payload = load_and_validate(source_dir)
    publication_version = version or f"mvp-{payload.input_hash[:12]}"
    engine = build_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            existing = session.scalar(
                select(PublicationBatch).where(PublicationBatch.input_hash == payload.input_hash)
            )
            if existing is not None:
                if existing.status != "published":
                    raise RuntimeError("El mismo conjunto de entrada existe, pero no está publicado")
                return existing.id, False

            session.execute(
                update(PublicationBatch)
                .where(PublicationBatch.status == "published")
                .values(status="retired")
            )
            batch = PublicationBatch(
                version=publication_version,
                input_hash=payload.input_hash,
                status="staged",
                default_cutoff_date=payload.default_cutoff_date,
                metadata_json={"mvp": payload.metadata, "temporal_model": payload.model},
                model_evaluation_json=payload.model_evaluation,
            )
            session.add(batch)
            session.flush()

            for week in payload.weeks:
                session.add(PublicationWeek(
                    batch_id=batch.id,
                    cutoff_date=_parse_date(week["cutoff_date"], "cutoff_date"),
                    target_week_start=_parse_date(week["target_week_start"], "target_week_start"),
                    target_week_end=_parse_date(week["target_week_end"], "target_week_end"),
                    cutoff_label=week["cutoff_label"],
                    target_week_label=week["target_week_label"],
                    has_temporal_prediction=week["has_temporal_prediction"],
                    has_experimental_spatial=week["has_experimental_spatial"],
                ))
            session.flush()

            for prediction in payload.predictions:
                session.add(TemporalPrediction(
                    batch_id=batch.id,
                    cutoff_date=_parse_date(prediction["cutoff_date"], "cutoff_date"),
                    target_week_start=_parse_date(prediction["target_week_start"], "target_week_start"),
                    target_week_end=_parse_date(prediction["target_week_end"], "target_week_end"),
                    predicted_cases=float(prediction["predicted_cases"]),
                    predicted_cases_rounded=int(prediction["predicted_cases_rounded"]),
                    official_cases=prediction.get("official_cases"),
                    absolute_error=prediction.get("absolute_error"),
                    persistence_prediction=prediction.get("persistence_prediction"),
                    persistence_absolute_error=prediction.get("persistence_absolute_error"),
                ))

            radio_rows = []
            for feature in payload.territorial_features:
                radio_id, properties, geometry = _radio_properties(feature, "territorial_context")
                radio_rows.append({
                    "batch_id": batch.id,
                    "radio_id": radio_id,
                    "population": int(properties["population"]),
                    "population_density": float(properties["population_density"]),
                    "households": int(properties["households"]),
                    "dwellings": int(properties["dwellings"]),
                    "area_km2": float(properties["area_km2"]),
                    "demographic_residential_component": float(properties["demographic_residential_component"]),
                    "density_component": float(properties["density_component"]),
                    "territorial_context_score": float(properties["territorial_context_score"]),
                    "percentile": float(properties["percentile"]),
                    "relative_level": properties["relative_level"],
                    "geometry": json.dumps(geometry, separators=(",", ":")),
                })
            session.execute(text("""
                INSERT INTO territorial_radios (
                    batch_id, radio_id, population, population_density, households, dwellings,
                    area_km2, demographic_residential_component, density_component,
                    territorial_context_score, percentile, relative_level, geom
                ) VALUES (
                    :batch_id, :radio_id, :population, :population_density, :households, :dwellings,
                    :area_km2, :demographic_residential_component, :density_component,
                    :territorial_context_score, :percentile, :relative_level,
                    ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326)
                )
            """), radio_rows)

            for feature in payload.experimental_features:
                radio_id, properties, _geometry = _radio_properties(feature, "experimental_spatial_history")
                session.add(ExperimentalSpatialResult(
                    batch_id=batch.id,
                    cutoff_date=_parse_date(properties["cutoff_date"], "cutoff_date"),
                    radio_id=radio_id,
                    target_week_start=_parse_date(properties["target_week_start"], "target_week_start"),
                    target_week_end=_parse_date(properties["target_week_end"], "target_week_end"),
                    experimental_spatial_score=float(properties["experimental_spatial_score"]),
                    percentile=float(properties["percentile"]),
                    relative_level=properties["relative_level"],
                    synthetic_scenario=properties["synthetic_scenario"],
                ))
            session.flush()

            invalid_geometry_count = session.scalar(
                select(func.count())
                .select_from(TerritorialRadio)
                .where(TerritorialRadio.batch_id == batch.id)
                .where(text("NOT ST_IsValid(geom) OR ST_SRID(geom) <> 4326"))
            )
            if invalid_geometry_count:
                raise ValueError("PostGIS rechazó una o más geometrías territoriales")

            batch.status = "published"
            batch.published_at = datetime.now(timezone.utc)
            session.flush()
            return batch.id, True
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa y publica contratos epidemiológicos aprobados")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args()
    batch_id, created = import_publication(
        get_settings().database_url,
        args.source_dir,
        version=args.version,
    )
    action = "publicado" if created else "ya estaba publicado"
    print(f"Lote {batch_id}: {action}")


if __name__ == "__main__":
    main()
