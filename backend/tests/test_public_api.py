import json
from datetime import date, datetime, timezone

from app.models import (
    ExperimentalSpatialResult,
    PublicationBatch,
    PublicationWeek,
    TemporalPrediction,
    TerritorialRadio,
)


GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-66.86, -29.42], [-66.85, -29.42], [-66.85, -29.41], [-66.86, -29.42]]],
}


def seed_publication(client):
    batch = PublicationBatch(
        version="test-publication-v1",
        input_hash="a" * 64,
        status="published",
        default_cutoff_date=date(2024, 6, 22),
        metadata_json={
            "mvp": {
                "project": "SIGARD",
                "disclaimers": {"experimental_spatial": "Producto sintético de prueba."},
            },
            "temporal_model": {"name": "RandomForestRegressor"},
        },
        model_evaluation_json={"metrics": {"mae": 1.0}, "backtest": []},
        published_at=datetime.now(timezone.utc),
    )
    with client.app.state.SessionLocal() as db:
        db.add(batch)
        db.flush()
        db.add(PublicationWeek(
            batch_id=batch.id,
            cutoff_date=date(2024, 6, 22),
            target_week_start=date(2024, 6, 23),
            target_week_end=date(2024, 6, 29),
            cutoff_label="2024-06-22",
            target_week_label="2024-06-23 a 2024-06-29",
            has_temporal_prediction=True,
            has_experimental_spatial=True,
        ))
        db.flush()
        db.add(TemporalPrediction(
            batch_id=batch.id,
            cutoff_date=date(2024, 6, 22),
            target_week_start=date(2024, 6, 23),
            target_week_end=date(2024, 6, 29),
            predicted_cases=2.5,
            predicted_cases_rounded=2,
            official_cases=3.0,
            absolute_error=0.5,
            persistence_prediction=4.0,
            persistence_absolute_error=1.0,
        ))
        db.add(TerritorialRadio(
            batch_id=batch.id,
            radio_id="460140101",
            population=100,
            population_density=10.0,
            households=40,
            dwellings=45,
            area_km2=10.0,
            demographic_residential_component=0.5,
            density_component=0.5,
            territorial_context_score=0.5,
            percentile=50.0,
            relative_level="medium",
            geom=json.dumps(GEOMETRY),
        ))
        db.flush()
        db.add(ExperimentalSpatialResult(
            batch_id=batch.id,
            cutoff_date=date(2024, 6, 22),
            radio_id="460140101",
            target_week_start=date(2024, 6, 23),
            target_week_end=date(2024, 6, 29),
            experimental_spatial_score=0.25,
            percentile=50.0,
            relative_level="medium",
            synthetic_scenario="spatial_clusters",
        ))
        db.commit()


def test_public_api_returns_503_without_a_published_batch(client):
    response = client.get("/api/v1/public/weeks")
    assert response.status_code == 503


def test_public_api_exposes_only_the_published_contract(client):
    seed_publication(client)
    paths = [
        "/api/v1/public/weeks",
        "/api/v1/public/predictions/2024-06-22",
        "/api/v1/public/territorial-context",
        "/api/v1/public/experimental-spatial-history/2024-06-22",
        "/api/v1/public/metadata",
        "/api/v1/public/model-evaluation",
    ]
    forbidden = {"description", "address_reference", "internal_notes", "tracking_code", "email"}
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=300"
        assert response.headers["x-sigard-publication-version"] == "test-publication-v1"
        assert not any(key in response.text.lower() for key in forbidden)

    assert client.get("/api/v1/public/predictions/2024-06-21").status_code == 404
    assert client.get("/api/v1/public/predictions/not-a-date").status_code == 422
    territorial = client.get("/api/v1/public/territorial-context").json()
    assert territorial["features"][0]["geometry"] == GEOMETRY
    experimental = client.get("/api/v1/public/experimental-spatial-history/2024-06-22").json()
    assert experimental["features"][0]["properties"]["synthetic_scenario"] == "spatial_clusters"
