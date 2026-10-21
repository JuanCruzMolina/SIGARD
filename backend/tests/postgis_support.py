"""Fail-closed helpers for the owned, disposable integration cluster only."""

from contextlib import contextmanager
import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SCHEMA_DB = "sigard_stage16_schema"
ADMIN_DB = "sigard_stage15_test"
USER = "sigard_stage15_test"
PORT = 5435


def validate_url(value):
    url = make_url(value)
    if not (url.drivername == "postgresql+psycopg2" and url.host == "127.0.0.1"
            and url.port == PORT and url.username == USER and url.database in (SCHEMA_DB, ADMIN_DB)
            and url.password is None and not url.query):
        raise ValueError("Only the explicit disposable loopback endpoint is authorized")
    return url


def run_id():
    value = os.environ.get("SIGARD_POSTGIS_RUN_ID", "")
    if not re.fullmatch(r"sigard-disposable-[a-f0-9]{16}", value):
        raise ValueError("Owned disposable run identity required")
    return value


def checked_engine(value):
    url = validate_url(value)
    expected = run_id()
    engine = create_engine(url, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=15000 -c lock_timeout=10000"})
    try:
        with engine.connect() as db:
            identity = db.execute(text("SELECT current_database(), current_user, current_setting('cluster_name')")).one()
            if tuple(identity) != (url.database, USER, expected):
                raise ValueError("Disposable cluster identity mismatch")
    except Exception:
        engine.dispose()
        raise
    return engine


def reset_schema(engine):
    validate_url(str(engine.url))
    with engine.begin() as db:
        if db.scalar(text("SELECT current_setting('cluster_name')")) != run_id():
            raise ValueError("Disposable cluster identity mismatch; reset forbidden")
        db.execute(text("TRUNCATE admin_account_audit, citizen_report_audit, citizen_reports, usuarios, "
                        "experimental_spatial_results, territorial_radios, temporal_predictions, "
                        "publication_weeks, publication_batches RESTART IDENTITY CASCADE"))


@contextmanager
def postgres_client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    url = os.environ["SIGARD_POSTGIS_URL"]
    engine = checked_engine(url)
    try:
        reset_schema(engine)
        app = create_app(database_url=url, auto_create_schema=False)
        with TestClient(app) as client:
            yield client
    finally:
        engine.dispose()
