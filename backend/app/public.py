import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    ExperimentalSpatialResult,
    PublicationBatch,
    PublicationWeek,
    TemporalPrediction,
    TerritorialRadio,
)


router = APIRouter(prefix="/api/v1/public", tags=["información pública"])
CACHE_CONTROL = "public, max-age=300"


def _published_batch(db: Session) -> PublicationBatch:
    batch = db.scalar(select(PublicationBatch).where(PublicationBatch.status == "published"))
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay una publicación epidemiológica disponible",
        )
    return batch


def _publication_metadata(batch: PublicationBatch) -> dict[str, Any]:
    return {
        "version": batch.version,
        "input_hash": batch.input_hash,
        "published_at": batch.published_at.isoformat() if batch.published_at else None,
    }


def _cache(response: Response, batch: PublicationBatch) -> None:
    response.headers["Cache-Control"] = CACHE_CONTROL
    response.headers["X-SIGARD-Publication-Version"] = batch.version


def _geometry_column(db: Session):
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        return TerritorialRadio.geom
    return func.ST_AsGeoJSON(TerritorialRadio.geom)


def _geometry_value(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="La geometría publicada no pudo serializarse",
    )


@router.get("/weeks")
def get_weeks(response: Response, db: Session = Depends(get_db)):
    batch = _published_batch(db)
    rows = db.scalars(
        select(PublicationWeek)
        .where(PublicationWeek.batch_id == batch.id)
        .order_by(PublicationWeek.cutoff_date)
    ).all()
    _cache(response, batch)
    return {
        "default_cutoff_date": batch.default_cutoff_date,
        "weeks": [
            {
                "cutoff_date": row.cutoff_date,
                "cutoff_label": row.cutoff_label,
                "has_experimental_spatial": row.has_experimental_spatial,
                "has_temporal_prediction": row.has_temporal_prediction,
                "target_week_end": row.target_week_end,
                "target_week_label": row.target_week_label,
                "target_week_start": row.target_week_start,
            }
            for row in rows
        ],
        "publication": _publication_metadata(batch),
    }


@router.get("/predictions/{cutoff_date}")
def get_prediction(cutoff_date: date, response: Response, db: Session = Depends(get_db)):
    batch = _published_batch(db)
    row = db.scalar(
        select(TemporalPrediction).where(
            TemporalPrediction.batch_id == batch.id,
            TemporalPrediction.cutoff_date == cutoff_date,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No existe una predicción para el corte solicitado")
    _cache(response, batch)
    return {
        "absolute_error": row.absolute_error,
        "cutoff_date": row.cutoff_date,
        "official_cases": row.official_cases,
        "persistence_absolute_error": row.persistence_absolute_error,
        "persistence_prediction": row.persistence_prediction,
        "predicted_cases": row.predicted_cases,
        "predicted_cases_rounded": row.predicted_cases_rounded,
        "target_week_end": row.target_week_end,
        "target_week_start": row.target_week_start,
        "publication": _publication_metadata(batch),
    }


@router.get("/territorial-context")
def get_territorial_context(response: Response, db: Session = Depends(get_db)):
    batch = _published_batch(db)
    geometry = _geometry_column(db).label("geometry")
    rows = db.execute(
        select(TerritorialRadio, geometry)
        .where(TerritorialRadio.batch_id == batch.id)
        .order_by(TerritorialRadio.radio_id)
    ).all()
    _cache(response, batch)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "radio_id": radio.radio_id,
                    "population": radio.population,
                    "population_density": radio.population_density,
                    "households": radio.households,
                    "dwellings": radio.dwellings,
                    "area_km2": radio.area_km2,
                    "demographic_residential_component": radio.demographic_residential_component,
                    "density_component": radio.density_component,
                    "territorial_context_score": radio.territorial_context_score,
                    "percentile": radio.percentile,
                    "relative_level": radio.relative_level,
                },
                "geometry": _geometry_value(geometry_value),
            }
            for radio, geometry_value in rows
        ],
        "publication": _publication_metadata(batch),
    }


@router.get("/experimental-spatial-history/{cutoff_date}")
def get_experimental_spatial_history(
    cutoff_date: date,
    response: Response,
    db: Session = Depends(get_db),
):
    batch = _published_batch(db)
    geometry = _geometry_column(db).label("geometry")
    rows = db.execute(
        select(ExperimentalSpatialResult, geometry)
        .join(
            TerritorialRadio,
            (TerritorialRadio.batch_id == ExperimentalSpatialResult.batch_id)
            & (TerritorialRadio.radio_id == ExperimentalSpatialResult.radio_id),
        )
        .where(
            ExperimentalSpatialResult.batch_id == batch.id,
            ExperimentalSpatialResult.cutoff_date == cutoff_date,
        )
        .order_by(ExperimentalSpatialResult.radio_id)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No existe una simulación para el corte solicitado")
    _cache(response, batch)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "radio_id": result.radio_id,
                    "cutoff_date": result.cutoff_date,
                    "target_week_start": result.target_week_start,
                    "target_week_end": result.target_week_end,
                    "experimental_spatial_score": result.experimental_spatial_score,
                    "percentile": result.percentile,
                    "relative_level": result.relative_level,
                    "synthetic_scenario": result.synthetic_scenario,
                },
                "geometry": _geometry_value(geometry_value),
            }
            for result, geometry_value in rows
        ],
        "publication": _publication_metadata(batch),
    }


@router.get("/metadata")
def get_metadata(response: Response, db: Session = Depends(get_db)):
    batch = _published_batch(db)
    _cache(response, batch)
    metadata = dict(batch.metadata_json.get("mvp", {}))
    metadata["publication"] = _publication_metadata(batch)
    return metadata


@router.get("/model-evaluation")
def get_model_evaluation(response: Response, db: Session = Depends(get_db)):
    batch = _published_batch(db)
    _cache(response, batch)
    evaluation = dict(batch.model_evaluation_json)
    evaluation["publication"] = _publication_metadata(batch)
    return evaluation
