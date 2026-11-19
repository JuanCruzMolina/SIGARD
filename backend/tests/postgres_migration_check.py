"""Real PostgreSQL/PostGIS check of the public Alembic chain on a NEW, disposable database.

Run from the repository root with the local research cluster already started:

    .\\backend\\.venv\\Scripts\\python.exe -B backend/tests/postgres_migration_check.py \\
        --connection data/interim/official/<cluster>/connection.private.json \\
        --output data/interim/official/public-migration-postgis/result.private.json

Guards: loopback 127.0.0.1:55439 only (never 5432), cluster name ``sigard-epi-*``, a database
named exactly ``sigard_public_migration_test`` that must not exist beforehand, and it is dropped
at the end even on failure. No other database is opened besides ``postgres`` (to create/drop).
Credentials are read from a private file and never printed. Only fictional values are inserted.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DATABASE = "sigard_public_migration_test"
PORT = 55439
ALERT_TABLES = {"internal_alert_rules", "internal_alert_evaluations", "internal_alert_candidates", "internal_alert_audit"}
PREVENTION_TABLES = {"prevention_sections", "prevention_audit"}


def guarded_url(raw, database):
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg2" or url.host != "127.0.0.1" or url.port != PORT or url.query:
        raise SystemExit("blocked: only the owned loopback research cluster on 55439 is allowed")
    return url.set(database=database)


def check_cluster(engine):
    with engine.connect() as db:
        name, port = db.execute(text("SELECT current_setting('cluster_name'), current_setting('port')")).one()
    if not name.startswith("sigard-epi-") or int(port) != PORT:
        raise SystemExit("blocked: unexpected cluster identity")


def alembic_config(url):
    from alembic.config import Config
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ.setdefault("SECRET_KEY", "migration-check-" + os.urandom(16).hex())
    from app.config import get_settings
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


def pgcode(error):
    return getattr(getattr(error, "orig", None), "pgcode", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Resolve before changing the working directory below.
    args.connection, args.output = args.connection.resolve(), args.output.resolve()
    private = ROOT / "data/interim/official"
    if not args.connection.resolve().is_relative_to(private) or not args.output.resolve().is_relative_to(private):
        raise SystemExit("blocked: private connection and output paths required")
    raw = json.loads(args.connection.read_text(encoding="utf-8-sig"))["url"]
    admin = create_engine(guarded_url(raw, "postgres"), isolation_level="AUTOCOMMIT")
    target_url = guarded_url(raw, DATABASE)
    check_cluster(admin)
    # Settings read .env relative to the working directory: use an empty private folder.
    work = Path(tempfile.mkdtemp(prefix="migration-check-", dir=BACKEND / ".tmp"))
    os.chdir(work)
    sys.path.insert(0, str(BACKEND))
    steps, created = [], False

    def step(name, ok, **detail):
        steps.append(dict(name=name, ok=bool(ok), **detail))
        if not ok:
            raise AssertionError(name)

    try:
        with admin.connect() as db:
            if db.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": DATABASE}):
                raise SystemExit("blocked: disposable database already exists; refusing to reuse it")
            db.execute(text(f'CREATE DATABASE "{DATABASE}"'))
            created = True
        engine = create_engine(target_url)
        with engine.begin() as db:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            postgis = db.scalar(text("SELECT postgis_lib_version()"))
            server = db.scalar(text("SHOW server_version"))
        step("database_created_with_postgis", True, server_version=server, postgis=postgis)

        from alembic import command
        config = alembic_config(target_url)
        command.upgrade(config, "head")
        with engine.connect() as db:
            head = db.scalar(text("SELECT version_num FROM alembic_version"))
            tables = set(inspect(db).get_table_names())
        step("upgrade_head", head == "20261114_06" and ALERT_TABLES | PREVENTION_TABLES <= tables, head=head, tables=len(tables))

        from app.database import build_session_factory
        from app.prevention_seed import seed_from_file
        session = build_session_factory(engine)
        with session() as db:
            first = seed_from_file(db)
        with session() as db:
            second = seed_from_file(db)
        with engine.connect() as db:
            published = db.scalar(text("SELECT count(*) FROM prevention_sections WHERE status='published'"))
        step("prevention_seed_idempotent", first > 0 and second == 0 and published == first, created=first, rerun=second, published=published)

        # CHECK constraints fire before foreign keys: a bad status must fail with 23514, a valid
        # status with the same fictional references must reach the FK check (23503).
        insert = text("""INSERT INTO internal_alert_candidates (rule_id, rule_revision, rule_json, evaluation_id, target_week,
            radio_id, evidence_json, status) VALUES (999999, 1, '{}', 999999, DATE '2024-01-07', 'FICT-001', '{}', :status)""")
        codes = {}
        for status in ("published", "publicada", "approved_public", "pending"):
            try:
                with engine.begin() as db:
                    db.execute(insert, {"status": status})
                codes[status] = "inserted"
            except IntegrityError as error:
                codes[status] = pgcode(error)
        step("alert_candidate_cannot_be_published", codes["published"] == codes["publicada"] == codes["approved_public"] == "23514"
             and codes["pending"] == "23503", codes=codes)
        rule = text("""INSERT INTO internal_alert_rules (name, capability, model, threshold, consecutive_weeks, created_by_user_id, updated_by_user_id)
            VALUES ('Regla ficticia', 'quantity', 'fictional', :threshold, 2, 999999, 999999)""")
        rule_codes = {}
        for threshold in (4, 5):
            try:
                with engine.begin() as db:
                    db.execute(rule, {"threshold": threshold})
                rule_codes[threshold] = "inserted"
            except IntegrityError as error:
                rule_codes[threshold] = pgcode(error)
        step("alert_rule_threshold_minimum_5", rule_codes[4] == "23514" and rule_codes[5] == "23503", codes=rule_codes)
        try:
            with engine.begin() as db:
                db.execute(text("UPDATE prevention_sections SET status='archivada' WHERE id=(SELECT min(id) FROM prevention_sections)"))
            prevention_code = "updated"
        except IntegrityError as error:
            prevention_code = pgcode(error)
        step("prevention_status_constrained", prevention_code == "23514", code=prevention_code)

        command.downgrade(config, "20261114_05")
        with engine.connect() as db:
            tables = set(inspect(db).get_table_names())
            head = db.scalar(text("SELECT version_num FROM alembic_version"))
        step("downgrade_06", head == "20261114_05" and not ALERT_TABLES & tables and PREVENTION_TABLES <= tables, head=head)
        command.downgrade(config, "20261020_04")
        with engine.connect() as db:
            tables = set(inspect(db).get_table_names())
            head = db.scalar(text("SELECT version_num FROM alembic_version"))
        step("downgrade_05", head == "20261020_04" and not (ALERT_TABLES | PREVENTION_TABLES) & tables and "usuarios" in tables, head=head)
        command.upgrade(config, "head")
        with engine.connect() as db:
            tables = set(inspect(db).get_table_names())
            head = db.scalar(text("SELECT version_num FROM alembic_version"))
        with session() as db:
            reseeded = seed_from_file(db)
        step("upgrade_again_and_reseed", head == "20261114_06" and ALERT_TABLES | PREVENTION_TABLES <= tables and reseeded == first, head=head, reseeded=reseeded)

        from fastapi.testclient import TestClient
        from app.main import create_app
        app = create_app(database_url=target_url.render_as_string(hide_password=False), auto_create_schema=False)
        with TestClient(app) as client:
            ready = client.get("/health/ready").status_code
            prevention = client.get("/api/v1/public/prevention")
            alerts = client.get("/api/v1/admin/alerts/rules").status_code
        app.state.engine.dispose()
        step("api_on_postgis", ready == 200 and prevention.status_code == 200 and alerts in (401, 403),
             ready=ready, prevention=prevention.status_code, admin_without_token=alerts)
        engine.dispose()
        status = "passed"
    except AssertionError:
        status = "failed"
    except Exception as error:  # recorded, never hides the cleanup below
        secret = make_url(raw).password or "<no-password>"
        steps.append(dict(name="unexpected_error", ok=False, error_class=type(error).__name__, message=str(error).replace(secret, "***")[:400]))
        status = "failed"
    finally:
        if created:
            with admin.connect() as db:
                db.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"), {"n": DATABASE})
                db.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE}"'))
                dropped = not db.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": DATABASE})
            steps.append(dict(name="database_dropped", ok=dropped))
        admin.dispose()
    result = dict(status=status if all(s["ok"] for s in steps) else "failed", database=DATABASE, port=PORT, steps=steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(dict(status=result["status"], steps=[(s["name"], s["ok"]) for s in steps])))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
