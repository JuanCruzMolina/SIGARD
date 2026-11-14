import importlib.util
import io
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.config import get_settings
from app.models import PreventionAudit, PreventionSection, User
from app.prevention_seed import DEFAULT_SOURCE, legacy_sections, seed_from_file, seed_prevention
from app.security import create_access_token, hash_password


ADMIN = "/api/v1/admin/prevention"
PUBLIC = "/api/v1/public/prevention"
SOURCE = {"source_label": "Guía ficticia de referencia", "source_url": "https://example.test/guia"}


def add_user(client, email="admin@example.test", role="admin"):
    with client.app.state.SessionLocal() as db:
        user = User(email=email, password_hash=hash_password("fictitious-password"), rol=role)
        db.add(user)
        db.commit()
        return user


def auth(user):
    return {"Authorization": "Bearer " + create_access_token(user, get_settings())}


def draft(client, admin, slug="seccion-ficticia", **fields):
    payload = {"slug": slug, "title": "Título ficticio", "body": "- Acción ficticia uno\n- Acción ficticia dos", "position": 70, **SOURCE, **fields}
    response = client.post(ADMIN, headers=auth(admin), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def public_slugs(client):
    return [section["slug"] for section in client.get(PUBLIC).json()["sections"]]


def test_create_edit_publish_unpublish_cycle_with_audit(client):
    admin = add_user(client)
    created = draft(client, admin)
    assert created["status"] == "draft" and created["version"] == 0 and created["has_pending_changes"]
    assert public_slugs(client) == []

    edited = client.patch(f"{ADMIN}/{created['id']}", headers=auth(admin), json={
        "revision": created["revision"], "title": "  Título   ficticio editado ", "body": "Párrafo **ficticio** con [guía](https://example.test/a).",
    })
    assert edited.status_code == 200
    edited = edited.json()
    assert edited["title"] == "Título ficticio editado" and edited["revision"] == created["revision"] + 1
    assert edited["updated_by"] == "admin@example.test"

    published = client.post(f"{ADMIN}/{created['id']}/publish", headers=auth(admin), json={"revision": edited["revision"]}).json()
    assert published["status"] == "published" and published["version"] == 1 and not published["has_pending_changes"]
    assert published["published_by"] == "admin@example.test"
    public = client.get(PUBLIC)
    assert public.headers["cache-control"] == "public, max-age=60"
    [section] = public.json()["sections"]
    assert section["title"] == "Título ficticio editado" and section["version"] == 1
    assert set(section) == {"slug", "title", "body", "position", "source_label", "source_url", "version", "published_at"}

    # Editing a published section only changes the working copy.
    pending = client.patch(f"{ADMIN}/{created['id']}", headers=auth(admin), json={"revision": published["revision"], "body": "Borrador ficticio no público"}).json()
    assert pending["status"] == "published" and pending["has_pending_changes"]
    assert "Borrador ficticio" not in client.get(PUBLIC).text

    again = client.post(f"{ADMIN}/{created['id']}/publish", headers=auth(admin), json={"revision": pending["revision"]}).json()
    assert again["version"] == 2 and "Borrador ficticio no público" in client.get(PUBLIC).text
    assert client.post(f"{ADMIN}/{created['id']}/publish", headers=auth(admin), json={"revision": again["revision"]}).status_code == 409

    hidden = client.post(f"{ADMIN}/{created['id']}/unpublish", headers=auth(admin), json={"revision": again["revision"]})
    assert hidden.status_code == 200 and hidden.json()["status"] == "draft"
    body = client.get(PUBLIC).json()
    assert body["sections"] == [] and body["initialized"] is True
    assert client.post(f"{ADMIN}/{created['id']}/unpublish", headers=auth(admin), json={"revision": hidden.json()["revision"]}).status_code == 409

    history = client.get(f"{ADMIN}/{created['id']}/history", headers=auth(admin)).json()
    assert [entry["action"] for entry in history] == ["unpublish", "publish", "update", "publish", "update", "create"]
    assert all(entry["actor"] == "admin@example.test" for entry in history)
    update = history[-2]
    assert update["before"]["title"] == "Título ficticio" and update["after"]["title"] == "Título ficticio editado"
    assert history[0]["before"]["version"] == 2 and history[0]["after"] is None


def test_stale_revision_is_rejected_without_changes(client):
    admin = add_user(client)
    created = draft(client, admin)
    first = client.patch(f"{ADMIN}/{created['id']}", headers=auth(admin), json={"revision": created["revision"], "title": "Primero"})
    assert first.status_code == 200
    stale = client.patch(f"{ADMIN}/{created['id']}", headers=auth(admin), json={"revision": created["revision"], "title": "Segundo"})
    assert stale.status_code == 409
    assert client.post(f"{ADMIN}/{created['id']}/publish", headers=auth(admin), json={"revision": created["revision"]}).status_code == 409
    with client.app.state.SessionLocal() as db:
        assert db.get(PreventionSection, created["id"]).title == "Primero"
        assert db.scalar(select(PreventionAudit).where(PreventionAudit.action == "publish")) is None


def test_publish_requires_health_reference(client):
    admin = add_user(client)
    created = draft(client, admin, source_label=None, source_url=None)
    response = client.post(f"{ADMIN}/{created['id']}/publish", headers=auth(admin), json={"revision": created["revision"]})
    assert response.status_code == 422 and "fuente" in response.json()["detail"]
    assert public_slugs(client) == []


@pytest.mark.parametrize("method,suffix,payload", [
    ("GET", "", None),
    ("POST", "", {"slug": "x", "title": "x", "body": "x"}),
    ("PATCH", "/1", {"revision": 1, "title": "x"}),
    ("POST", "/1/publish", {"revision": 1}),
    ("POST", "/1/unpublish", {"revision": 1}),
    ("GET", "/1/history", None),
])
def test_admin_routes_reject_anonymous_and_non_admin(client, method, suffix, payload):
    admin = add_user(client)
    draft(client, admin, slug="x")
    user = add_user(client, email="user@example.test", role="user")
    assert client.request(method, ADMIN + suffix, json=payload).status_code == 401
    assert client.request(method, ADMIN + suffix, headers={"Authorization": "Bearer invalid"}, json=payload).status_code == 401
    assert client.request(method, ADMIN + suffix, headers=auth(user), json=payload).status_code == 403
    with client.app.state.SessionLocal() as db:
        section = db.scalar(select(PreventionSection))
        assert (section.title, section.status) == ("Título ficticio", "draft")
        assert [entry.action for entry in db.scalars(select(PreventionAudit))] == ["create"]


@pytest.mark.parametrize("field,value", [
    ("body", "<script>alert(1)</script>"),
    ("body", "Texto <img src=x onerror=alert(1)>"),
    ("body", "Mirá [esto](javascript:alert(1))"),
    ("body", "Mirá [esto](JaVa\tScript:alert(1))"),
    ("body", "Enlace [inseguro](http://example.test)"),
    ("body", "Imagen data:text/html;base64,AAAA"),
    ("body", "Entidad &lt;b&gt;"),
    ("body", "Control \x07 oculto"),
    ("body", "x" * 4001),
    ("body", "   "),
    ("title", "y" * 121),
    ("title", "<b>Título</b>"),
    ("source_url", "javascript:alert(1)"),
    ("source_url", "http://example.test/no-https"),
    ("body", "Contacto paciente@example.test"),
    ("body", "Persona con documento 30.123.456"),
])
def test_unsafe_or_personal_content_is_rejected_without_echo(client, field, value):
    admin = add_user(client)
    response = client.post(ADMIN, headers=auth(admin), json={"slug": "inseguro", "title": "Título", "body": "Texto", **SOURCE, field: value})
    assert response.status_code == 422
    if len(value.strip()) > 3:
        assert value.strip() not in response.text
    created = draft(client, admin)
    edit = client.patch(f"{ADMIN}/{created['id']}", headers=auth(admin), json={"revision": created["revision"], field: value})
    assert edit.status_code == 422
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(PreventionSection).where(PreventionSection.slug == "inseguro")) is None
        assert db.get(PreventionSection, created["id"]).revision == created["revision"]


def test_invalid_slug_duplicate_and_unknown_fields(client):
    admin = add_user(client)
    draft(client, admin, slug="duplicada")
    assert client.post(ADMIN, headers=auth(admin), json={"slug": "duplicada", "title": "t", "body": "b"}).status_code == 409
    assert client.post(ADMIN, headers=auth(admin), json={"slug": "Con Espacios", "title": "t", "body": "b"}).status_code == 422
    section = client.get(ADMIN, headers=auth(admin)).json()[0]
    assert client.patch(f"{ADMIN}/{section['id']}", headers=auth(admin), json={"revision": section["revision"], "status": "published"}).status_code == 422
    assert client.patch(f"{ADMIN}/{section['id']}", headers=auth(admin), json={"revision": section["revision"]}).status_code == 422
    assert client.patch(f"{ADMIN}/999", headers=auth(admin), json={"revision": 1, "title": "t"}).status_code == 404


def test_initial_import_is_idempotent_and_preserves_admin_edits(client):
    with client.app.state.SessionLocal() as db:
        assert seed_from_file(db) == 5
    body = client.get(PUBLIC).json()
    assert [section["slug"] for section in body["sections"]] == [
        "prevencion", "control-vectorial", "sintomas", "consejos-medicos", "signos-alarma"]
    assert all(section["version"] == 1 and section["source_url"].startswith("https://") for section in body["sections"])
    content = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
    assert all(f"- {item}" in body["sections"][0]["body"] for item in content["prevention"])

    admin = add_user(client)
    section = client.get(ADMIN, headers=auth(admin)).json()[0]
    client.patch(f"{ADMIN}/{section['id']}", headers=auth(admin), json={"revision": section["revision"], "title": "Título editado por admin"})
    with client.app.state.SessionLocal() as db:
        assert seed_from_file(db) == 0
        assert db.scalar(select(PreventionSection).where(PreventionSection.slug == "prevencion")).title == "Título editado por admin"
        seeds = db.scalars(select(PreventionAudit).where(PreventionAudit.action == "seed_import")).all()
        assert len(seeds) == 5 and all(entry.actor_user_id is None and len(entry.after_json["source_sha256"]) == 64 for entry in seeds)
    history = client.get(f"{ADMIN}/{section['id']}/history", headers=auth(admin)).json()
    assert history[-1]["actor"] == "Carga inicial del sistema"


def test_legacy_mapping_rejects_unsafe_source_content():
    content = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
    assert len(legacy_sections(content)) == 5
    content["prevention"] = ["<script>alert(1)</script>"]
    with pytest.raises(Exception):
        legacy_sections(content)


def test_public_route_reports_uninitialized_store(client):
    body = client.get(PUBLIC).json()
    assert body == {"schema_version": "prevention-sections/1", "initialized": False,
                    "content_kind": "general_health_guidance", "sections": []}


def test_seed_rolls_back_nothing_on_partial_existing(client):
    with client.app.state.SessionLocal() as db:
        content = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
        db.add(PreventionSection(slug="sintomas", title="Existente", body="Texto existente", status="draft"))
        db.commit()
        assert seed_prevention(db, content, "0" * 64) == 4
        assert db.scalar(select(PreventionSection).where(PreventionSection.slug == "sintomas")).status == "draft"
    assert "sintomas" not in public_slugs(client)


def test_migration_up_down_on_isolated_sqlite_and_postgresql_sql(tmp_path):
    path = Path(__file__).parents[1] / "migrations/versions/20261114_05_prevention_content.py"
    spec = importlib.util.spec_from_file_location("prevention_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261020_04"
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, email VARCHAR(150) NOT NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            tables = set(inspect(connection).get_table_names())
            assert {"prevention_sections", "prevention_audit"} <= tables
            model_columns = {column.name for column in PreventionSection.__table__.columns}
            assert {c["name"] for c in inspect(connection).get_columns("prevention_sections")} == model_columns
            assert {c["name"] for c in inspect(connection).get_columns("prevention_audit")} == {c.name for c in PreventionAudit.__table__.columns}
            connection.execute(text("INSERT INTO prevention_sections (slug,title,body) VALUES ('a','t','b')"))
            assert connection.execute(text("SELECT status, revision, version FROM prevention_sections")).one() == ("draft", 1, 0)
            migration.downgrade()
            assert not {"prevention_sections", "prevention_audit"} & set(inspect(connection).get_table_names())
            migration.upgrade()
            migration.downgrade()
    engine.dispose()
    output = io.StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})):
        migration.upgrade()
        migration.downgrade()
    sql = output.getvalue()
    assert "CREATE TABLE prevention_sections" in sql and "DROP TABLE prevention_audit" in sql


def test_readiness_requires_prevention_schema(client):
    assert client.get("/health/ready").status_code == 200
    with client.app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE prevention_audit"))
    assert client.get("/health/ready").status_code == 503
