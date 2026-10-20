"""Disposable loopback HTTP fixture for the account browser check, never deployment.

Reads no .env and uses no existing database. Stdin EOF shuts down and removes
the temporary SQLite store. Only fictitious credentials exist in this process.
"""

import asyncio
from datetime import date, datetime, timezone
import json
from pathlib import Path
import secrets
import socket
import sys
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402


def seed_public_contract(app):
    """Only already approved public artifacts, copied to a disposable SQLite store.

    Geometry remains JSON text here: this is not a PostGIS integration test.
    """
    from app.models import PublicationBatch, PublicationWeek, TemporalPrediction, TerritorialRadio, ExperimentalSpatialResult
    from app.publication_import import load_and_validate

    source = Path(__file__).resolve().parents[2] / "frontend/public/data"
    payload = load_and_validate(source)
    with app.state.SessionLocal() as db:
        batch = PublicationBatch(
            version="stage15-test-publication", input_hash=payload.input_hash, status="published",
            default_cutoff_date=payload.default_cutoff_date,
            metadata_json={"mvp": payload.metadata, "temporal_model": payload.model},
            model_evaluation_json=payload.model_evaluation, published_at=datetime.now(timezone.utc),
        )
        db.add(batch)
        db.flush()
        for week in payload.weeks:
            values = dict(week)
            for field in ("cutoff_date", "target_week_start", "target_week_end"):
                values[field] = date.fromisoformat(values[field])
            db.add(PublicationWeek(batch_id=batch.id, **values))
        db.flush()
        for prediction in payload.predictions:
            fields = ("predicted_cases", "predicted_cases_rounded", "official_cases", "absolute_error", "persistence_prediction", "persistence_absolute_error")
            values = {field: prediction.get(field) for field in fields}
            values.update({field: date.fromisoformat(prediction[field]) for field in ("cutoff_date", "target_week_start", "target_week_end")})
            db.add(TemporalPrediction(batch_id=batch.id, **values))
        for feature in payload.territorial_features:
            fields = ("radio_id", "population", "population_density", "households", "dwellings", "area_km2", "demographic_residential_component", "density_component", "territorial_context_score", "percentile", "relative_level")
            db.add(TerritorialRadio(batch_id=batch.id, geom=json.dumps(feature["geometry"]), **{field: feature["properties"][field] for field in fields}))
        db.flush()
        for feature in payload.experimental_features:
            props = feature["properties"]
            values = {field: props[field] for field in ("radio_id", "experimental_spatial_score", "percentile", "relative_level", "synthetic_scenario")}
            values.update({field: date.fromisoformat(props[field]) for field in ("cutoff_date", "target_week_start", "target_week_end")})
            db.add(ExperimentalSpatialResult(batch_id=batch.id, **values))
        db.commit()


def main():
    temporary_root = Path(__file__).resolve().parents[1] / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="stage14-browser-", dir=temporary_root) as directory:
        settings = config.Settings(
            _env_file=None, secret_key=secrets.token_urlsafe(48),
            database_url=f"sqlite:///{Path(directory) / 'fixture.db'}",
            auto_create_schema=True, admin_bootstrap_email=None, admin_bootstrap_password=None,
            cors_origins="http://127.0.0.1:5173", admin_login_rate_limit=100,
        )
        config.get_settings = lambda: settings
        from app.main import create_app
        from app.models import User
        from app.security import hash_password
        from app.database import Base

        app = create_app()
        Base.metadata.create_all(app.state.engine)
        if "--integral" in sys.argv:
            seed_public_contract(app)
        with app.state.SessionLocal() as db:
            db.add(User(email="stage14-admin@example.test", password_hash=hash_password("fictitious-initial-password"), rol="admin"))
            db.commit()
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))

        async def run():
            async def stop_on_input():
                await asyncio.to_thread(sys.stdin.readline)
                server.should_exit = True
            print(json.dumps({"port": listener.getsockname()[1], "fixture": "sigard-disposable-admin"}), flush=True)
            await asyncio.gather(server.serve(sockets=[listener]), stop_on_input())
        try:
            asyncio.run(run())
        finally:
            listener.close()
            app.state.engine.dispose()


if __name__ == "__main__":
    main()
