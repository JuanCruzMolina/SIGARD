"""F6.6: read-only administrative audit trail on the local administrative API (generated fixtures only).

Covers access (missing, invalid, expired, revoked, deactivated, other role), the local guard, CORS,
read-only routes, events of every category without sensitive values, allowlisted summaries (an
unknown field never reaches the response), filters (category, action, actor, Argentina dates with
an event at 23:30 of the last day), order and pagination, the recorded query (fail closed, hidden
by default) and that neither the deployable `app.main` nor the demo API contain the route.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from jose import jwt
import pytest
from sqlalchemy import insert, select, text

from app import main
from app.admin_audit import PATH, mount, view_log
from app.config import get_settings
from app.database import Base
from app.models import CitizenReport, InternalAlertAudit, User
from app.predictive_admin import audit as viewer_audit
from predictive_admin_support import ORIGIN, add_account, bearer, client

# Windows: a child of a process without a console would open its own console window; then
# hide it. With a console (visible or hidden) children keep sharing it, as before.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) and (
    0 if __import__("ctypes").windll.kernel32.GetConsoleWindow() else subprocess.CREATE_NO_WINDOW)

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = 'fictitious-password'
LOCAL = {'Origin': ORIGIN}
# Fictitious values that must never appear in the audit response.
SECRETS = {
    'new_password': 'contraseña-ficticia-nueva-123',
    'description': 'Descripción privada ficticia con detalle sensible de la prueba de auditoría.',
    'internal_note': 'Nota interna ficticia que no debe salir de la ficha.',
    'public_message': 'Mensaje público ficticio con texto libre.',
    'body': 'Texto ficticio del cuerpo de la sección preventiva para la auditoría.',
    'comment': 'Comentario ficticio de la decisión sobre la candidata.',
    'evidence': 'valor-esperado-ficticio-7.25',
    'new_field': 'valor-de-un-campo-nuevo-no-permitido',
}
LATITUDE, LONGITUDE = -29.412345, -66.856789


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    """The local administrative app (create_app + audit mount) with the single local origin."""
    settings = get_settings().model_copy(update={'cors_origins': ORIGIN})
    monkeypatch.setattr(main, 'get_settings', lambda: settings)
    app = main.create_app(database_url=f"sqlite:///{(tmp_path / 'audit.db').as_posix()}", auto_create_schema=True)
    Base.metadata.create_all(app.state.engine)
    mount(app)
    admin = add_account(app)
    return app, {**LOCAL, **bearer(admin)}, admin


def rows(app, table):
    with app.state.engine.connect() as connection:
        return [dict(r) for r in connection.execute(select(table).order_by(table.c.id)).mappings()]


def keys(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


async def generate_events(app, headers):
    """One event of each category through the real routes where they exist, with known secrets."""
    async with client(app) as c:
        created = await c.post('/api/v1/admin/users', headers=headers, json={
            'email': 'auditada@example.test', 'password': SECRETS['new_password'], 'current_password': PASSWORD})
        assert created.status_code == 201, created.text
        report = await c.post('/api/v1/citizen-reports', json={
            'category': 'agua_acumulada', 'description': SECRETS['description'], 'neighborhood': 'Zona Ficticia',
            'latitude': LATITUDE, 'longitude': LONGITUDE, 'privacy_accepted': True, 'privacy_notice_version': '2026-08-19'})
        assert report.status_code == 201, report.text
        with app.state.SessionLocal() as db:
            stored = db.scalar(select(CitizenReport))
        assert (await c.get(f'/api/v1/admin/citizen-reports/{stored.id}', headers=headers)).status_code == 200
        updated = await c.patch(f'/api/v1/admin/citizen-reports/{stored.id}', headers=headers, json={
            'status': 'en_revision', 'internal_notes': SECRETS['internal_note'], 'public_status_message': SECRETS['public_message']})
        assert updated.status_code == 200, updated.text
        assert (await c.get('/api/v1/admin/citizen-reports/export.csv', headers=headers)).status_code == 200
        section = await c.post('/api/v1/admin/prevention', headers=headers, json={
            'slug': 'auditoria-ficticia', 'title': 'Sección ficticia de auditoría', 'body': SECRETS['body'], 'position': 90,
            'source_label': 'Fuente ficticia', 'source_url': 'https://example.org/fuente'})
        assert section.status_code == 201, section.text
        draft = section.json()
        edited = await c.patch(f"/api/v1/admin/prevention/{draft['id']}", headers=headers, json={
            'title': 'Sección ficticia de auditoría editada', 'body': SECRETS['body'], 'position': 90,
            'source_label': 'Fuente ficticia', 'source_url': 'https://example.org/fuente', 'revision': draft['revision']})
        assert edited.status_code == 200, edited.text
        published = await c.post(f"/api/v1/admin/prevention/{draft['id']}/publish", headers=headers, json={'revision': edited.json()['revision']})
        assert published.status_code == 200, published.text
    admin_id = (await_admin_id(app))
    with app.state.engine.begin() as connection:
        # Internal alerts (same shapes as internal_alerts.audit) and a private viewer query.
        connection.execute(insert(InternalAlertAudit.__table__), [
            dict(actor_user_id=admin_id, action='rule_created', entity='rule', entity_id=1, before_json=None,
                 after_json={'id': 1, 'name': 'Regla ficticia', 'threshold': 5, 'radio_ids': ['FX0000001'], 'nuevo_campo': SECRETS['new_field']},
                 created_at=datetime.now(timezone.utc)),
            dict(actor_user_id=admin_id, action='candidate_discarded', entity='candidate', entity_id=7,
                 before_json={'status': 'pending'},
                 after_json={'status': 'discarded', 'comment': SECRETS['comment'], 'reason': 'false_alarm', 'target_week': '2024-04-07',
                             'radio_id': 'FX0000001', 'rule_id': 1, 'evidence': [{'expected': SECRETS['evidence']}]},
                 created_at=datetime.now(timezone.utc)),
        ])
        connection.execute(insert(viewer_audit).values(actor_user_id=admin_id, route='comparison', period='2024-SE15',
                                                       radio='460140105', created_at=datetime.now(timezone.utc)))
    return stored


def await_admin_id(app):
    with app.state.SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == 'admin@example.test'))


@pytest.mark.anyio
async def test_access_requires_a_valid_current_administrator(local_app):
    app, headers, admin = local_app
    settings = get_settings()
    async with client(app) as c:
        assert (await c.get(PATH, headers=headers)).status_code == 200
        missing = await c.get(PATH, headers=LOCAL)
        assert missing.status_code == 401 and missing.headers['www-authenticate'] == 'Bearer'
        assert (await c.get(PATH, headers={**LOCAL, 'Authorization': 'Bearer no-es-un-token'})).status_code == 401
        expired = jwt.encode({'sub': str(admin.id), 'role': 'admin', 'ver': admin.token_version,
                              'exp': datetime.now(timezone.utc) - timedelta(minutes=1)}, settings.secret_key, algorithm=settings.algorithm)
        assert (await c.get(PATH, headers={**LOCAL, 'Authorization': f'Bearer {expired}'})).status_code == 401
        # Revoked session (password rotation / deactivation bump token_version).
        with app.state.SessionLocal() as db:
            db.get(User, admin.id).token_version += 1
            db.commit()
        assert (await c.get(PATH, headers=headers)).status_code == 401
        other = add_account(app, 'usuario@example.test', role='user')
        assert (await c.get(PATH, headers={**LOCAL, **bearer(other)})).status_code == 403
        inactive = add_account(app, 'inactiva@example.test')
        with app.state.SessionLocal() as db:
            db.get(User, inactive.id).active = False
            db.commit()
        assert (await c.get(PATH, headers={**LOCAL, **bearer(inactive)})).status_code == 401


@pytest.mark.anyio
async def test_local_guard_applies_before_authentication(local_app):
    app, headers, _ = local_app
    async with client(app) as c:
        for changed in ({'Origin': 'https://example.invalid'}, {'Origin': 'http://localhost:5173'}, {'X-Forwarded-For': '127.0.0.1'},
                        {'Forwarded': 'for=127.0.0.1'}, {'Host': 'evil.invalid'}, {'Host': '127.0.0.1:8765'}, {'Sec-Fetch-Site': 'cross-site'}):
            for auth in (headers, {**LOCAL}):  # the guard answers before authentication
                response = await c.get(PATH, headers={**auth, **changed})
                assert response.status_code == 403 and response.json() == {'detail': 'local_admin_only'}
        no_origin = {k: v for k, v in headers.items() if k != 'Origin'}
        assert (await c.get(PATH, headers=no_origin)).status_code == 403
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('10.0.0.8', 1234)), base_url='http://127.0.0.1:8767') as c:
        assert (await c.get(PATH, headers=headers)).status_code == 403


@pytest.mark.anyio
async def test_cors_only_for_the_local_origin(local_app):
    app, headers, _ = local_app
    async with client(app) as c:
        preflight = await c.options(PATH, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'GET',
                                                   'Access-Control-Request-Headers': 'authorization'})
        assert preflight.status_code == 200 and preflight.headers['access-control-allow-origin'] == ORIGIN
        assert '*' not in ''.join(v for k, v in preflight.headers.items() if k.startswith('access-control'))
        assert 'access-control-allow-credentials' not in preflight.headers
        other = await c.options(PATH, headers={'Origin': 'https://example.invalid', 'Access-Control-Request-Method': 'GET'})
        assert other.headers.get('access-control-allow-origin') is None
        ok = await c.get(PATH, headers=headers)
        assert ok.headers['access-control-allow-origin'] == ORIGIN and ok.headers['cache-control'] == 'no-store'


@pytest.mark.anyio
async def test_no_route_modifies_or_deletes_events(local_app):
    app, headers, _ = local_app
    async with client(app) as c:
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            assert (await c.request(method, PATH, headers=headers)).status_code == 405
            assert (await c.request(method, PATH + '/cuentas:1', headers=headers)).status_code in (404, 405)
    methods = {m for r in app.routes if getattr(r, 'path', '').startswith(PATH) for m in (getattr(r, 'methods', None) or ())}
    assert methods and methods <= {'GET', 'HEAD'}


@pytest.mark.anyio
async def test_every_category_is_listed_without_sensitive_values(local_app):
    app, headers, admin = local_app
    report = await generate_events(app, headers)
    async with client(app) as c:
        response = await c.get(PATH, headers=headers, params={'page_size': 100})
    assert response.status_code == 200
    body = response.json()
    raw = response.text
    assert {item['category'] for item in body['items']} == {'cuentas', 'reportes', 'contenido', 'alertas', 'visor'}
    for name, secret in SECRETS.items():
        assert secret not in raw, name
    for forbidden in (str(LATITUDE), str(LONGITUDE), PASSWORD):
        assert forbidden not in raw
    assert not keys(body) & {'before', 'after', 'before_json', 'after_json', 'changes_json', 'password', 'password_hash', 'hash',
                             'token', 'access_token', 'comment', 'description', 'internal_notes', 'evidence', 'latitude', 'longitude'}
    by_action = {(i['category'], i['action']): i for i in body['items']}
    assert by_action[('cuentas', 'created')]['target'] == {'account_email': 'auditada@example.test'}
    update = by_action[('reportes', 'update')]
    assert update['target'] == {'tracking_code': report.tracking_code}
    assert update['summary'] == {'changed_fields': ['status', 'public_status_message', 'internal_notes'],
                                 'status_from': 'recibido', 'status_to': 'en_revision'}
    assert by_action[('reportes', 'view_detail')]['target'] == {'tracking_code': report.tracking_code}
    assert by_action[('reportes', 'export_csv')]['summary'] == {'count': 1}
    assert by_action[('contenido', 'update')]['summary'] == {'changed_fields': ['title']}
    assert by_action[('contenido', 'publish')]['summary'] == {'version': 1}
    assert by_action[('contenido', 'create')]['target']['section_slug'] == 'auditoria-ficticia'
    assert by_action[('alertas', 'rule_created')]['target'] == {'rule_name': 'Regla ficticia'}
    assert by_action[('alertas', 'candidate_discarded')]['summary'] == {'has_comment': True, 'reason': 'false_alarm'}
    assert by_action[('alertas', 'candidate_discarded')]['target'] == {'candidate_id': 7, 'target_week': '2024-04-07', 'radio_id': 'FX0000001'}
    assert by_action[('visor', 'private_query')]['target'] == {'route': 'comparison', 'period': '2024-SE15', 'radio_id': '460140105'}
    assert all(i['actor'] == {'id': admin.id, 'email': 'admin@example.test'} for i in body['items'])
    stamps = [i['created_at'] for i in body['items']]
    assert stamps == sorted(stamps, reverse=True), 'del más reciente al más antiguo'


@pytest.mark.anyio
async def test_summaries_come_from_allowlists_unknown_fields_never_appear(local_app):
    app, headers, admin = local_app
    with app.state.engine.begin() as connection:
        connection.execute(insert(InternalAlertAudit.__table__).values(
            actor_user_id=admin.id, action='rule_updated', entity='rule', entity_id=2,
            before_json={'name': 'Regla A', 'threshold': 5, 'campo_futuro': 'antes'},
            after_json={'name': 'Regla A', 'threshold': 8, 'campo_futuro': SECRETS['new_field']}, created_at=datetime.now(timezone.utc)))
        connection.execute(text("INSERT INTO citizen_report_audit (report_id, actor_user_id, action, changes_json, created_at) "
                                "VALUES (NULL, :actor, 'update', :changes, :at)"),
                           dict(actor=admin.id, at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f'),
                                changes=json.dumps({'campo_futuro': {'from': 'a', 'to': SECRETS['new_field']},
                                                    'status': {'from': 'recibido', 'to': 'valor_inventado'}})))
    async with client(app) as c:
        response = await c.get(PATH, headers=headers)
    assert SECRETS['new_field'] not in response.text and 'campo_futuro' not in response.text
    items = {i['category']: i for i in response.json()['items']}
    assert items['alertas']['summary'] == {'changed_fields': ['threshold']}
    assert items['reportes']['summary'] == {'changed_fields': ['status']}, 'un estado fuera de la lista cerrada no se informa'


@pytest.mark.anyio
async def test_filters_order_and_pagination(local_app):
    app, headers, admin = local_app
    other = add_account(app, 'otra-admin@example.test')
    base = datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc)
    with app.state.engine.begin() as connection:
        connection.execute(insert(viewer_audit), [dict(actor_user_id=(admin.id if n % 2 else other.id), route='comparison',
                                                       period=f'2024-SE{n:02d}', radio=None, created_at=base + timedelta(hours=n)) for n in range(1, 31)])
    async with client(app) as c:
        first = (await c.get(PATH, headers=headers, params={'category': 'visor', 'page_size': 10})).json()
        assert first['total'] == 30 and first['page'] == 1 and len(first['items']) == 10
        assert first['items'][0]['target']['period'] == '2024-SE30', 'el más reciente primero'
        third = (await c.get(PATH, headers=headers, params={'category': 'visor', 'page_size': 10, 'page': 3})).json()
        assert [i['target']['period'] for i in third['items']][-1] == '2024-SE01'
        mine = (await c.get(PATH, headers=headers, params={'category': 'visor', 'actor_id': other.id, 'page_size': 100})).json()
        assert mine['total'] == 15 and all(i['actor']['id'] == other.id for i in mine['items'])
        action = (await c.get(PATH, headers=headers, params={'action': 'private_query', 'page_size': 100})).json()
        assert action['total'] == 30
        for bad in ({'page_size': 101}, {'page': 0}, {'category': 'inventada'}, {'category': 'visor', 'action': 'created'},
                    {'action': 'inexistente'}, {'date_from': '2026-03-02', 'date_to': '2026-03-01'}):
            assert (await c.get(PATH, headers=headers, params=bad)).status_code == 422, bad


@pytest.mark.anyio
async def test_dates_are_argentina_days_and_date_to_includes_the_whole_day(local_app):
    app, headers, admin = local_app
    art = timezone(timedelta(hours=-3))
    with app.state.engine.begin() as connection:
        connection.execute(insert(viewer_audit), [
            dict(actor_user_id=admin.id, route='comparison', period='ultimo-dia-23-30', radio=None,
                 created_at=datetime(2026, 3, 10, 23, 30, tzinfo=art).astimezone(timezone.utc)),   # 02:30 UTC of the 11th
            dict(actor_user_id=admin.id, route='comparison', period='dia-siguiente-00-10', radio=None,
                 created_at=datetime(2026, 3, 11, 0, 10, tzinfo=art).astimezone(timezone.utc)),
            dict(actor_user_id=admin.id, route='comparison', period='primer-dia-00-05', radio=None,
                 created_at=datetime(2026, 3, 9, 0, 5, tzinfo=art).astimezone(timezone.utc)),     # 03:05 UTC of the 9th
            dict(actor_user_id=admin.id, route='comparison', period='dia-anterior-23-50', radio=None,
                 created_at=datetime(2026, 3, 8, 23, 50, tzinfo=art).astimezone(timezone.utc)),   # 02:50 UTC of the 9th
        ])
    async with client(app) as c:
        listed = (await c.get(PATH, headers=headers, params={'category': 'visor', 'date_from': '2026-03-09', 'date_to': '2026-03-10'})).json()
        assert sorted(i['target']['period'] for i in listed['items']) == ['primer-dia-00-05', 'ultimo-dia-23-30']
        last_day = (await c.get(PATH, headers=headers, params={'category': 'visor', 'date_to': '2026-03-10'})).json()
        assert 'ultimo-dia-23-30' in {i['target']['period'] for i in last_day['items']}
        assert 'dia-siguiente-00-10' not in {i['target']['period'] for i in last_day['items']}


@pytest.mark.anyio
async def test_each_query_is_recorded_hidden_by_default_and_fails_closed(local_app):
    app, headers, admin = local_app
    async with client(app) as c:
        await c.get(PATH, headers=headers, params={'category': 'cuentas', 'date_from': '2026-01-01', 'page': 1})
        recorded = rows(app, view_log)
        assert len(recorded) == 1 and recorded[0]['actor_user_id'] == admin.id
        assert json.loads(recorded[0]['filters']) == {'category': 'cuentas', 'date_from': '2026-01-01', 'page': 1, 'page_size': 25}
        default = (await c.get(PATH, headers=headers)).json()
        assert all(i['category'] != 'auditoria' for i in default['items']), 'la categoría «auditoría» no aparece por defecto'
        own = (await c.get(PATH, headers=headers, params={'category': 'auditoria'})).json()
        assert own['total'] == 3 and {i['action'] for i in own['items']} == {'audit_viewed'}
        assert own['items'][-1]['summary'] == {'filters': {'category': 'cuentas', 'date_from': '2026-01-01', 'page': 1, 'page_size': 25}}
        assert all(set(i['target']) == set() for i in own['items'])
    with app.state.engine.begin() as connection:
        connection.execute(text('DROP TABLE admin_audit_view'))
    async with client(app) as c:
        failed = await c.get(PATH, headers=headers)
    assert failed.status_code == 503 and 'items' not in failed.json()


def run_fresh(code, tmp_path):
    """Runs `code` in a fresh interpreter (deployable/demo configuration never reaches pytest)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DATABASE_URL', 'SIGARD_'))}
    env.update(SECRET_KEY='fresh-process-secret-with-enough-entropy', DATABASE_URL=f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}",
               PYTHONPATH=str(BACKEND))
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp_path, env=env, capture_output=True,
                            text=True, timeout=120, creationflags=NO_WINDOW)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


ROUTES = '''
import json, sys
paths = sorted({getattr(r, "path", "") for r in app.routes})
modules = sorted(m for m in sys.modules if m in ("app.admin_audit", "app.alerts_local"))
'''


def test_deployable_app_main_does_not_expose_the_audit(tmp_path):
    result = run_fresh('from app.main import app\n' + ROUTES + '''
from fastapi.testclient import TestClient
with TestClient(app, base_url="http://127.0.0.1:8767") as c:
    status = c.get("/api/v1/admin/audit", headers={"Origin": "http://127.0.0.1:5173", "Authorization": "Bearer x"}).status_code
print(json.dumps({"paths": paths, "modules": modules, "status": status}))
''', tmp_path)
    assert result['paths'] and not any(p.startswith('/api/v1/admin/audit') for p in result['paths'])
    assert result['modules'] == [] and result['status'] == 404
    assert 'admin_audit' not in (BACKEND / 'app/main.py').read_text(encoding='utf-8')


def test_demo_api_does_not_expose_the_audit(tmp_path):
    result = run_fresh('''
from tempfile import TemporaryDirectory
from app.demo_local import BACKEND, checked_directory, create_demo_app
(BACKEND / ".tmp").mkdir(exist_ok=True)
holder = TemporaryDirectory(prefix="sigard-demo-", dir=BACKEND / ".tmp")
app, _ = create_demo_app(checked_directory(holder.name))
''' + ROUTES + '''
app.state.engine.dispose()
holder.cleanup()
print(json.dumps({"paths": paths, "modules": modules}))
''', tmp_path)
    assert any(p.startswith('/api/v1/admin/demo') for p in result['paths'])
    assert not any(p.startswith('/api/v1/admin/audit') for p in result['paths'])
    assert result['modules'] == []


def test_only_the_local_api_mounts_the_audit():
    source = (BACKEND / 'app/alerts_local.py').read_text(encoding='utf-8')
    calls = [line for line in source.splitlines() if line.strip() == 'mount_audit(app)']
    assert 'from app.admin_audit import mount' in source and len(calls) == 2  # the two serve paths (persistent and session)
