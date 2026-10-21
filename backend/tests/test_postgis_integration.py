"""Only fictitious geometry and the cluster created by postgis_disposable.py."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from pathlib import Path
from threading import Event
import time

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, DBAPIError

from postgis_support import checked_engine, validate_url, reset_schema


@pytest.fixture(autouse=True)
def require_owned_cluster(request):
    if not request.node.name.startswith("test_unauthorized_destinations") and not os.environ.get("SIGARD_POSTGIS_URL"):
        pytest.skip("Requires the owned disposable PostGIS runner")


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://sigard_stage15_test@127.0.0.1:5432/sigard_stage16_schema",
    "postgresql+psycopg2://sigard_stage15_test@127.0.0.1:5433/sigard_stage16_schema",
    "postgresql+psycopg2://sigard_stage15_test@localhost:5435/sigard_stage16_schema",
    "postgresql+psycopg2://other@127.0.0.1:5435/sigard_stage16_schema",
    "postgresql+psycopg2://sigard_stage15_test@127.0.0.1:5435/other",
    "postgresql+psycopg2://sigard_stage15_test@127.0.0.1:5435/sigard_stage16_schema?host=other",
    "postgresql+psycopg2://sigard_stage15_test:secret@127.0.0.1:5435/sigard_stage16_schema",
])
def test_unauthorized_destinations_rejected_before_connection(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.fixture
def engine():
    if not os.environ.get("SIGARD_POSTGIS_URL"):
        pytest.skip("Requires the owned disposable PostGIS runner")
    engine = checked_engine(os.environ["SIGARD_POSTGIS_URL"])
    yield engine
    engine.dispose()


def test_full_migration_chain_up_down_up(engine):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    assert not (set(inspect(engine).get_table_names(schema="public")) - {"spatial_ref_sys"})
    for revision in ("20260819_01", "20260923_02", "20260924_03", "20261020_04"):
        command.upgrade(config, revision)
        with engine.connect() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == revision
    tables = set(inspect(engine).get_table_names(schema="public"))
    assert {"usuarios", "admin_account_audit", "citizen_reports", "citizen_report_audit", "publication_batches",
            "publication_weeks", "temporal_predictions", "territorial_radios", "experimental_spatial_results"} <= tables
    columns = {c["name"]: c for c in inspect(engine).get_columns("usuarios")}
    assert columns["token_version"]["nullable"] is False
    assert inspect(engine).get_foreign_keys("admin_account_audit")
    with engine.connect() as db:
        indexes = dict(db.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public'")).all())
        assert "lower" in indexes["uq_usuarios_email_normalized"]
        assert "USING gist" in indexes["ix_citizen_reports_geom"]
        assert "USING gist" in indexes["ix_territorial_radios_geom"]
        assert "WHERE" in indexes["uq_publication_batches_one_published"]
    command.downgrade(config, "base")
    assert not (set(inspect(engine).get_table_names(schema="public")) - {"spatial_ref_sys", "alembic_version"})
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names(schema="public")) == tables


def seed_geometry(client):
    from app.models import PublicationBatch, PublicationWeek, TerritorialRadio, ExperimentalSpatialResult
    with client.app.state.SessionLocal() as db:
        batch = PublicationBatch(version="fictitious-postgis", input_hash="f" * 64, status="published",
                                 default_cutoff_date=date(2024, 6, 22), metadata_json={}, model_evaluation_json={})
        db.add(batch)
        db.flush()
        db.add(PublicationWeek(batch_id=batch.id, cutoff_date=date(2024, 6, 22), target_week_start=date(2024, 6, 23),
            target_week_end=date(2024, 6, 29), cutoff_label="fixture", target_week_label="fixture",
            has_temporal_prediction=False, has_experimental_spatial=True))
        db.flush()
        db.add(TerritorialRadio(batch_id=batch.id, radio_id="fictional-radio", population=100, population_density=10,
            households=40, dwellings=45, area_km2=10, demographic_residential_component=.5, density_component=.5,
            territorial_context_score=.5, percentile=50, relative_level="medium",
            geom=func.ST_GeomFromText("POLYGON((-66.9 -29.5,-66.8 -29.5,-66.8 -29.4,-66.9 -29.4,-66.9 -29.5))",4326)))
        db.flush()
        db.add(ExperimentalSpatialResult(batch_id=batch.id, cutoff_date=date(2024, 6, 22), radio_id="fictional-radio",
            target_week_start=date(2024, 6, 23), target_week_end=date(2024, 6, 29), experimental_spatial_score=.25,
            percentile=50, relative_level="medium", synthetic_scenario="fictitious-no-training"))
        db.commit()


def test_postgis_storage_srid_relationships_indexes_and_public_projection(client):
    seed_geometry(client)
    with client.app.state.engine.begin() as db:
        assert db.execute(text("SELECT ST_SRID(geom),ST_IsValid(geom),ST_Contains(geom,ST_SetSRID(ST_MakePoint(-66.85,-29.45),4326)), "
            "ST_Covers(geom,ST_SetSRID(ST_MakePoint(-66.9,-29.45),4326)) FROM territorial_radios")).one() == (4326,True,True,True)
        assert not db.scalar(text("SELECT ST_Contains(geom,ST_SetSRID(ST_MakePoint(-66.9,-29.45),4326)) FROM territorial_radios"))
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(text("UPDATE territorial_radios SET geom=ST_Transform(geom,3857)"))
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text("UPDATE territorial_radios SET population=-1"))
        db.execute(text("SET LOCAL enable_seqscan=off"))
        plan = " ".join(db.scalars(text("EXPLAIN SELECT * FROM territorial_radios WHERE geom && ST_MakeEnvelope(-67,-30,-66,-29,4326)")))
        assert "ix_territorial_radios_geom" in plan
    for path in ("/territorial-context", "/experimental-spatial-history/2024-06-22"):
        response = client.get("/api/v1/public" + path)
        assert response.status_code == 200
        assert response.json()["features"][0]["geometry"]["type"] == "Polygon"


def test_report_generated_point_and_persistence_across_app_restart(client):
    from test_citizen_reports import VALID_REPORT
    from app.main import create_app
    from fastapi.testclient import TestClient
    created = client.post("/api/v1/citizen-reports",json=VALID_REPORT)
    assert created.status_code == 201
    with client.app.state.engine.connect() as db:
        assert db.execute(text("SELECT ST_SRID(geom),ST_X(geom),ST_Y(geom) FROM citizen_reports")).one() == (4326,VALID_REPORT["longitude"],VALID_REPORT["latitude"])
        assert db.scalar(text("SELECT count(*) FROM experimental_spatial_results")) == 0
    app = create_app(database_url=os.environ["SIGARD_POSTGIS_URL"],auto_create_schema=False)
    with TestClient(app) as restarted:
        assert restarted.get("/api/v1/citizen-reports/status/" + created.json()["tracking_code"]).status_code == 200


def test_expired_and_wrong_signature_tokens_rejected(client):
    from test_admin_accounts import add_user, BASE
    from app.config import get_settings
    from app.security import create_access_token
    user = add_user(client)
    settings = get_settings()
    expired = create_access_token(user,settings.model_copy(update={"access_token_expire_minutes":-1}))
    wrong = create_access_token(user,settings.model_copy(update={"secret_key":"wrong-signing-key-only-for-fictitious-test"}))
    for token in (expired,wrong):
        assert client.get(BASE,headers={"Authorization":"Bearer "+token}).status_code == 401


def test_advisory_lock_really_blocks_and_revalidates_revoked_actor(client,monkeypatch):
    from app import admin_accounts
    from app.models import User
    from test_admin_accounts import add_user,headers,PASSWORD,BASE
    first=add_user(client)
    second=add_user(client,email="blocked@example.test")
    entered=Event()
    pids=[]
    original=admin_accounts.lock_account_changes
    def observed(db):
        pids.append(db.scalar(text("SELECT pg_backend_pid()")))
        entered.set()
        original(db)
    monkeypatch.setattr(admin_accounts,"lock_account_changes",observed)
    with client.app.state.SessionLocal() as holder, ThreadPoolExecutor(max_workers=1) as pool:
        original(holder)
        holder_pid=holder.scalar(text("SELECT pg_backend_pid()"))
        future=pool.submit(lambda: client.post(f"{BASE}/{second.id}/deactivate",headers=headers(second),json={"current_password":PASSWORD}).status_code)
        try:
            assert entered.wait(5)
            waiting=False
            until=time.monotonic()+5
            while time.monotonic()<until:
                with client.app.state.engine.connect() as monitor:
                    waiting=holder_pid in monitor.scalar(text("SELECT pg_blocking_pids(:pid)"),{"pid":pids[0]})
                if waiting: break
                time.sleep(.02)
            assert waiting and holder_pid != pids[0], "Independent PostgreSQL transaction must actually wait"
            actor=holder.get(User,second.id)
            actor.active=False
            actor.token_version+=1
            holder.commit()
        finally:
            holder.rollback()
        assert future.result(timeout=5)==401
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count(User.id)).where(User.active.is_(True)))==1
