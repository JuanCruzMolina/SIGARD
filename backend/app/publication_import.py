import argparse
import hashlib
import json
import math
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


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave JSON duplicada")
        result[key] = value
    return result


def _json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Número JSON no finito")
    return number


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
            documents[filename] = json.loads(
                content, object_pairs_hook=_json_object,
                parse_float=_json_float, parse_constant=_json_float,
            )
        except (ValueError, UnicodeError) as error:
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


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} debe ser un objeto")
    return value


def _required_text(value: Any, label: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"Campo requerido inválido: {label} (máximo {max_length} caracteres)")


def _number(value: Any, label: str, minimum: float | None = None,
            maximum: float | None = None, integer: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} debe ser un número finito")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} fuera de rango") from error
    if (not math.isfinite(number) or (minimum is not None and number < minimum)
            or (maximum is not None and number > maximum)
            or (integer and not number.is_integer())):
        raise ValueError(f"{label} fuera de rango o tipo numérico inválido")
    return number


def _assert_crs(value: dict[str, Any], label: str) -> None:
    # GeoJSON without a legacy `crs` member uses WGS84 longitude/latitude.
    # Do not silently relabel projected coordinates via ST_SetSRID.
    if "crs" not in value:
        return
    crs = value["crs"]
    if (not isinstance(crs, dict) or crs.get("type") != "name"
            or not isinstance(crs.get("properties"), dict)
            or not isinstance(crs["properties"].get("name"), str)
            or crs["properties"].get("name") not in {
                "EPSG:4326", "urn:ogc:def:crs:EPSG::4326",
                "urn:ogc:def:crs:OGC:1.3:CRS84",
            }):
        raise ValueError(f"CRS incompatible en {label}: se requiere EPSG:4326/CRS84")


def _assert_feature_collection(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise ValueError(f"{label} no es una FeatureCollection")
    features = value.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{label}.features debe ser una lista")
    _assert_crs(value, label)
    return features


def _radio_properties(feature: dict[str, Any], label: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError(f"Feature inválida en {label}")
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise ValueError(f"Feature inválida en {label}")
    radio_id = properties.get("radio_id")
    if not isinstance(radio_id, str) or not radio_id.strip() or len(radio_id) > 32:
        raise ValueError(f"radio_id inválido en {label}")
    if not isinstance(geometry.get("type"), str) or geometry["type"] not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Geometría no poligonal para el radio {radio_id}")
    _assert_crs(feature, label)
    _assert_crs(geometry, label)
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError(f"Coordenadas inválidas para el radio {radio_id}")
    polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError(f"Coordenadas inválidas para el radio {radio_id}")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(f"Coordenadas de anillo inválidas para el radio {radio_id}")
            for position in ring:
                if not isinstance(position, list) or len(position) < 2:
                    raise ValueError(f"Coordenadas inválidas para el radio {radio_id}")
                _number(position[0], f"{radio_id}.longitud EPSG:4326", -180, 180)
                _number(position[1], f"{radio_id}.latitud EPSG:4326", -90, 90)
                for ordinate in position[2:]:
                    _number(ordinate, f"{radio_id}.coordenada")
    # Topology (self intersections, holes, etc.) is checked by ST_IsValid below.
    return radio_id, properties, geometry


def load_and_validate(source_dir: Path) -> PublicationPayload:
    documents, input_hash = _read_contracts(source_dir)
    for filename, document in documents.items():
        _assert_no_private_keys(document, filename)
    _object(documents["model_evaluation.json"], "model_evaluation")
    _object(documents["mvp_metadata.json"], "mvp_metadata")

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
        if not isinstance(properties.get("relative_level"), str) or properties["relative_level"] not in LEVELS:
            raise ValueError(f"Nivel territorial inválido para {radio_id}")
        for key in ("population", "households", "dwellings"):
            _number(properties.get(key), f"{radio_id}.{key}", 0, 2147483647, integer=True)
        for key in ("population_density", "demographic_residential_component", "density_component", "territorial_context_score"):
            _number(properties.get(key), f"{radio_id}.{key}")
        if _number(properties.get("area_km2"), f"{radio_id}.area_km2", 0) == 0:
            raise ValueError(f"{radio_id}.area_km2 debe ser positiva")
        _number(properties.get("percentile"), f"{radio_id}.percentile", 0, 100)
        territorial_by_radio[radio_id] = properties
        territorial_geometry[radio_id] = geometry

    weeks_by_cutoff: dict[date, dict[str, Any]] = {}
    for week in weeks:
        _object(week, "weeks")
        _required_text(week.get("cutoff_label"), "weeks.cutoff_label", 40)
        _required_text(week.get("target_week_label"), "weeks.target_week_label", 80)
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
        _object(prediction, "predictions")
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
        if _number(prediction.get("predicted_cases"), "predictions.predicted_cases") < 0:
            raise ValueError(f"Predicción negativa para el corte {cutoff}")
        _number(prediction.get("predicted_cases_rounded"), "predictions.predicted_cases_rounded", 0, 2147483647, integer=True)
        for key in ("official_cases", "absolute_error", "persistence_prediction", "persistence_absolute_error"):
            if prediction.get(key) is not None:
                _number(prediction[key], f"predictions.{key}")
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
        if not isinstance(properties.get("relative_level"), str) or properties["relative_level"] not in LEVELS:
            raise ValueError(f"Nivel experimental inválido: {cutoff}/{radio_id}")
        if _number(properties.get("experimental_spatial_score"), "experimental.experimental_spatial_score") < 0:
            raise ValueError(f"Score experimental negativo: {cutoff}/{radio_id}")
        _number(properties.get("percentile"), "experimental.percentile", 0, 100)
        _required_text(properties.get("synthetic_scenario"), "experimental.synthetic_scenario", 80)
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
    _required_text(publication_version, "version", 80)
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
