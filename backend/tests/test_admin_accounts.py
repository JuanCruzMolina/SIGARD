import importlib.util
import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.main import create_app
from app.models import AdminAccountAudit, User
from app.security import create_access_token, hash_password, verify_password


PASSWORD = "fictitious-initial-password"
NEXT_PASSWORD = "fictitious-replacement-password"
BASE = "/api/v1/admin/users"


def add_user(client, email="admin@example.test", role="admin", active=True):
    with client.app.state.SessionLocal() as db:
        user = User(email=email, password_hash=hash_password(PASSWORD), rol=role, active=active)
        db.add(user)
        db.commit()
        return user


def headers(user):
    return {"Authorization": "Bearer " + create_access_token(user, get_settings())}


def login(client, email="admin@example.test", password=PASSWORD):
    return client.post("/api/v1/admin/session", json={"email": email, "password": password})


def test_authorized_create_list_login_and_credential_free_audit(client):
    admin = add_user(client)
    response = client.post(BASE, headers=headers(admin), json={
        "email": "  Second@Example.Test  ", "password": NEXT_PASSWORD, "current_password": PASSWORD,
    })
    assert response.status_code == 201
    created = response.json()
    assert created["email"] == "second@example.test" and created["active"] is True
    assert set(created) == {"id", "email", "active", "created_at"}
    assert NEXT_PASSWORD not in response.text and "password_hash" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert login(client, " SECOND@EXAMPLE.TEST ", NEXT_PASSWORD).status_code == 200
    page = client.get(BASE + "?page_size=1&page=2", headers=headers(admin)).json()
    assert page["total"] == 2 and page["active_admin_count"] == 2
    assert page["current_user_id"] == admin.id and len(page["items"]) == 1
    with client.app.state.SessionLocal() as db:
        saved = db.get(User, created["id"])
        assert saved.password_hash != NEXT_PASSWORD and verify_password(NEXT_PASSWORD, saved.password_hash)
        audit = db.scalar(select(AdminAccountAudit))
        assert (audit.actor_user_id, audit.target_user_id, audit.action) == (admin.id, saved.id, "created")
        assert not any("password" in column.name or "token" in column.name for column in AdminAccountAudit.__table__.columns)


@pytest.mark.parametrize("method,suffix,payload", [
    ("GET", "", None),
    ("POST", "", {"email": "new@example.test", "password": NEXT_PASSWORD, "current_password": PASSWORD}),
    ("POST", "/1/deactivate", {"current_password": PASSWORD}),
    ("POST", "/1/password", {"current_password": PASSWORD, "new_password": NEXT_PASSWORD}),
])
def test_all_account_routes_reject_anonymous_and_non_admin(client, method, suffix, payload):
    user = add_user(client, role="user")
    assert client.request(method, BASE + suffix, json=payload).status_code == 401
    assert client.request(method, BASE + suffix, headers=headers(user), json=payload).status_code == 403


@pytest.mark.parametrize("email", ["admin@example.test", "ADMIN@example.test", " admin@example.test "])
def test_duplicate_addresses_are_rejected_without_changes(client, email):
    admin = add_user(client)
    response = client.post(BASE, headers=headers(admin), json={"email": email, "password": NEXT_PASSWORD, "current_password": PASSWORD})
    assert response.status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(AdminAccountAudit.id))) == 0


@pytest.mark.parametrize("changes", [
    {"email": "invalid"}, {"password": "short"}, {"password": "x" * 201},
    {"rol": "admin"}, {"active": True}, {"token_version": 8}, {"current_password": ""},
])
def test_validation_never_echoes_credentials_or_accepts_privilege_fields(client, changes):
    admin = add_user(client)
    response = client.post(BASE, headers=headers(admin), json={
        "email": "new@example.test", "password": NEXT_PASSWORD, "current_password": PASSWORD, **changes,
    })
    assert response.status_code == 422
    assert PASSWORD not in response.text and NEXT_PASSWORD not in response.text
    assert "input" not in response.text and "password_hash" not in response.text


@pytest.mark.parametrize("suffix,extra", [("", {"email": "new@example.test", "password": NEXT_PASSWORD}), ("/1/deactivate", {}), ("/1/password", {"new_password": NEXT_PASSWORD})])
def test_changes_require_the_acting_admin_password(client, suffix, extra):
    admin = add_user(client)
    response = client.post(BASE + suffix, headers=headers(admin), json={"current_password": "fictitious-wrong-password", **extra})
    assert response.status_code == 403
    assert "fictitious-wrong-password" not in response.text
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count(AdminAccountAudit.id))) == 0


def test_deactivation_revokes_tokens_and_login_but_keeps_other_admin(client):
    admin, target = add_user(client), add_user(client, "other@example.test")
    old_headers = headers(target)
    response = client.post(f"{BASE}/{target.id}/deactivate", headers=headers(admin), json={"current_password": PASSWORD})
    assert response.status_code == 200 and response.json()["active"] is False
    assert login(client, target.email).status_code == 401
    assert client.get(BASE, headers=old_headers).status_code == 401
    assert client.get("/api/v1/admin/citizen-reports", headers=old_headers).status_code == 401
    assert client.get(BASE, headers=headers(admin)).status_code == 200
    # Repeating the command is idempotent and does not create another audit.
    assert client.post(f"{BASE}/{target.id}/deactivate", headers=headers(admin), json={"current_password": PASSWORD}).status_code == 200
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count(AdminAccountAudit.id))) == 1


def test_last_active_admin_is_protected_even_with_inactive_admin_and_active_non_admin(client):
    admin = add_user(client)
    add_user(client, "inactive@example.test", active=False)
    add_user(client, "reader@example.test", role="user")
    response = client.post(f"{BASE}/{admin.id}/deactivate", headers=headers(admin), json={"current_password": PASSWORD})
    assert response.status_code == 409
    assert client.get(BASE, headers=headers(admin)).status_code == 200


@pytest.mark.parametrize("self_rotation", [False, True])
def test_rotation_revokes_every_old_token_and_password(client, self_rotation):
    admin = add_user(client)
    target = admin if self_rotation else add_user(client, "other@example.test")
    old_tokens = [headers(target), {"Authorization": "Bearer " + login(client, target.email).json()["access_token"]}]
    response = client.post(f"{BASE}/{target.id}/password", headers=headers(admin), json={"current_password": PASSWORD, "new_password": NEXT_PASSWORD})
    assert response.status_code == 200
    assert PASSWORD not in response.text and NEXT_PASSWORD not in response.text
    assert login(client, target.email).status_code == 401
    new_session = login(client, target.email, NEXT_PASSWORD)
    assert new_session.status_code == 200
    for old in old_tokens:
        assert client.get(BASE, headers=old).status_code == 401
        assert client.get("/api/v1/admin/citizen-reports", headers=old).status_code == 401
    assert client.get(BASE, headers={"Authorization": "Bearer " + new_session.json()["access_token"]}).status_code == 200
    if not self_rotation:
        assert client.get(BASE, headers=headers(admin)).status_code == 200


def test_rotation_rejects_same_password_inactive_and_missing_targets(client):
    admin = add_user(client)
    inactive = add_user(client, "inactive@example.test", active=False)
    for target, password, status in [(admin.id, PASSWORD, 422), (inactive.id, NEXT_PASSWORD, 409), (999, NEXT_PASSWORD, 404)]:
        assert client.post(f"{BASE}/{target}/password", headers=headers(admin), json={"current_password": PASSWORD, "new_password": password}).status_code == status


def test_old_tokens_without_version_fail_closed_and_public_api_remains_anonymous(client):
    admin = add_user(client)
    settings = get_settings()
    payload = jwt.decode(create_access_token(admin, settings), settings.secret_key, algorithms=[settings.algorithm])
    del payload["ver"]
    legacy = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    assert client.get(BASE, headers={"Authorization": "Bearer " + legacy}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/public/weeks").status_code == 503  # no publication fixture, not 401
    assert client.get("/api/v1/research/spatial/models").status_code == 404


def test_password_confirmation_uses_existing_rate_limiter(client, monkeypatch):
    from app.security import rate_limiter
    monkeypatch.setattr(rate_limiter, "_buckets", {})
    settings = get_settings().model_copy(update={"admin_login_rate_limit": 1})
    client.app.dependency_overrides[get_settings] = lambda: settings
    admin = add_user(client)
    payload = {"current_password": "fictitious-wrong-password"}
    assert client.post(f"{BASE}/{admin.id}/deactivate", headers=headers(admin), json=payload).status_code == 403
    assert client.post(f"{BASE}/{admin.id}/deactivate", headers=headers(admin), json=payload).status_code == 429


def test_revocation_while_waiting_for_lock_is_rechecked(client):
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.admin_accounts import authorize_change
    admin = add_user(client)
    with client.app.state.SessionLocal() as waiting:
        stale_actor = waiting.get(User, admin.id)
        with client.app.state.SessionLocal() as other:
            other.get(User, admin.id).token_version += 1
            other.commit()
        request = Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []})
        with pytest.raises(HTTPException) as rejected:
            authorize_change(waiting, stale_actor, PASSWORD, request, get_settings())
        assert rejected.value.status_code == 401


def test_simultaneous_self_deactivations_cannot_remove_both_admins(client):
    admins = [add_user(client), add_user(client, "other@example.test")]
    barrier = Barrier(2)
    def deactivate(admin):
        barrier.wait(timeout=5)
        return client.post(f"{BASE}/{admin.id}/deactivate", headers=headers(admin), json={"current_password": PASSWORD}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(deactivate, admins))
    assert sorted(statuses) == [200, 409]
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count(User.id)).where(User.active.is_(True), User.rol == "admin")) == 1


def test_bootstrap_only_creates_the_first_account_and_never_restores_privileges(tmp_path, monkeypatch):
    import app.main as main
    settings = Settings(_env_file=None, secret_key="fictitious-secret-key-with-enough-entropy", admin_bootstrap_email="first@example.test", admin_bootstrap_password=PASSWORD)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    url = f"sqlite:///{tmp_path / 'bootstrap.db'}"
    app = create_app(database_url=url, auto_create_schema=True)
    with TestClient(app):
        with app.state.SessionLocal() as db:
            first = db.scalar(select(User))
            assert first.email == "first@example.test"
            first.active = False
            db.commit()
    settings.admin_bootstrap_email = "replacement@example.test"
    app = create_app(database_url=url, auto_create_schema=True)
    with TestClient(app):
        with app.state.SessionLocal() as db:
            users = db.scalars(select(User)).all()
            assert len(users) == 1 and users[0].active is False


def test_migration_up_down_on_isolated_sqlite_and_postgresql_sql(tmp_path):
    path = Path(__file__).parents[1] / "migrations/versions/20261020_04_admin_accounts.py"
    spec = importlib.util.spec_from_file_location("admin_accounts_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, email VARCHAR(150) NOT NULL)"))
        connection.execute(text("INSERT INTO usuarios VALUES (1,'Legacy@Example.Test')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "token_version" in {c["name"] for c in inspect(connection).get_columns("usuarios")}
            assert "admin_account_audit" in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT token_version FROM usuarios WHERE id=1")) == 0
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("INSERT INTO usuarios (id,email) VALUES (2,' legacy@example.test ')"))
            migration.downgrade()
            assert "token_version" not in {c["name"] for c in inspect(connection).get_columns("usuarios")}
            assert "admin_account_audit" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT email FROM usuarios WHERE id=1")) == "Legacy@Example.Test"
            migration.upgrade()
            assert connection.scalar(text("SELECT token_version FROM usuarios WHERE id=1")) == 0
            migration.downgrade()
    engine.dispose()
    output = io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})):
        migration.upgrade()
        migration.downgrade()
    sql = output.getvalue()
    assert "lower(trim(email))" in sql and "DROP COLUMN token_version" in sql


def test_readiness_rejects_the_previous_account_schema(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'old-schema.db'}", auto_create_schema=False)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)"))
    with TestClient(app) as test_client:
        response = test_client.get("/health/ready")
        assert response.status_code == 503
        assert "token_version" not in response.text


@pytest.mark.skipif(not os.environ.get("SIGARD_TEST_POSTGRES_URL"), reason="Requiere un PostgreSQL descartable autorizado; no usa la instancia persistente")
def test_postgresql_isolated_migration_integrity_revocation_and_concurrency(monkeypatch):
    """Real PostgreSQL only; strict endpoint/database guard prevents use of the installation."""
    from app import admin_accounts
    url = make_url(os.environ["SIGARD_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and url.port not in (None, 5432, 5433)
    assert url.database == "sigard_stage15_test" and url.username == "sigard_stage15_test"
    assert url.password is None and not url.query
    url = url.update_query_dict({"options": "-c statement_timeout=15000 -c lock_timeout=10000"})
    engine = create_engine(url)
    path = Path(__file__).parents[1] / "migrations/versions/20261020_04_admin_accounts.py"
    spec = importlib.util.spec_from_file_location("stage15_pg_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    app = None
    try:
        with engine.begin() as connection:
            assert connection.execute(text("SELECT current_database(), current_user")).one() == ("sigard_stage15_test", "sigard_stage15_test")
            assert not inspect(connection).get_table_names(), "La base de prueba debe estar vacía"
            connection.execute(text("""CREATE TABLE usuarios (
                id SERIAL PRIMARY KEY, email VARCHAR(150) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL DEFAULT 'user',
                activo BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT usuarios_rol_check CHECK (rol IN ('admin', 'user'))
            )"""))
            connection.execute(text("INSERT INTO usuarios (email,password_hash,rol) VALUES (:email,:password,'admin')"), {"email": " ADMIN@example.test ", "password": hash_password(PASSWORD)})
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.scalar(text("SELECT token_version FROM usuarios")) == 0
                migration.downgrade()
                assert "token_version" not in {c["name"] for c in inspect(connection).get_columns("usuarios")}
                migration.upgrade()
            for sql, values, code in [
                ("INSERT INTO usuarios (email,password_hash) VALUES (:email,'fictitious-hash')", {"email": "admin@EXAMPLE.test"}, "23505"),
                ("UPDATE usuarios SET token_version=NULL", {}, "23502"),
                ("INSERT INTO admin_account_audit (actor_user_id,target_user_id,action) VALUES (999,1,'created')", {}, "23503"),
            ]:
                with pytest.raises(IntegrityError) as rejected:
                    with connection.begin_nested():
                        connection.execute(text(sql), values)
                assert rejected.value.orig.pgcode == code

        app = create_app(database_url=url.render_as_string(hide_password=False), auto_create_schema=False)
        with TestClient(app) as client:
            first = login(client)
            assert first.status_code == 200
            first_headers = {"Authorization": "Bearer " + first.json()["access_token"]}
            first_id = client.get(BASE, headers=first_headers).json()["current_user_id"]
            created = client.post(BASE, headers=first_headers, json={"email": "other@example.test", "password": PASSWORD, "current_password": PASSWORD})
            assert created.status_code == 201
            second_id = created.json()["id"]
            old_other = {"Authorization": "Bearer " + login(client, "other@example.test").json()["access_token"]}
            assert client.post(f"{BASE}/{second_id}/password", headers=first_headers, json={"current_password": PASSWORD, "new_password": NEXT_PASSWORD}).status_code == 200
            assert login(client, "other@example.test").status_code == 401
            assert client.get(BASE, headers=old_other).status_code == 401
            assert client.post(f"{BASE}/{first_id}/password", headers=first_headers, json={"current_password": PASSWORD, "new_password": NEXT_PASSWORD}).status_code == 200
            assert client.get(BASE, headers=first_headers).status_code == 401
            assert login(client).status_code == 401

            original_lock = admin_accounts.lock_account_changes
            for cross in (False, True):
                with app.state.SessionLocal() as db:
                    for user in db.scalars(select(User)):
                        user.active = True
                        user.token_version += 1
                    db.commit()
                sessions = [{"Authorization": "Bearer " + login(client, email, NEXT_PASSWORD).json()["access_token"]} for email in ("admin@example.test", "other@example.test")]
                barrier = Barrier(2)
                def coordinated_lock(db):
                    barrier.wait(timeout=5)  # Both requests are already authenticated.
                    original_lock(db)
                monkeypatch.setattr(admin_accounts, "lock_account_changes", coordinated_lock)
                def deactivate(index):
                    target = (first_id, second_id)[1 - index if cross else index]
                    return client.post(f"{BASE}/{target}/deactivate", headers=sessions[index], json={"current_password": NEXT_PASSWORD}).status_code
                with ThreadPoolExecutor(max_workers=2) as pool:
                    statuses = list(pool.map(deactivate, (0, 1)))
                assert sorted(statuses) == ([200, 401] if cross else [200, 409])
                monkeypatch.setattr(admin_accounts, "lock_account_changes", original_lock)
                with app.state.SessionLocal() as db:
                    assert db.scalar(select(func.count(User.id)).where(User.active.is_(True), User.rol == "admin")) == 1
    finally:
        if app:
            app.state.engine.dispose()
        engine.dispose()
