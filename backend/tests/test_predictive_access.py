"""F2: the predictive viewer API requires a DB-verified administrator (generated fixtures only).

Covers the local guard, JWT access (missing, invalid, expired, revoked, deactivated, other
role), CORS, private-mode auditing without values, an unchanged response contract, and
that neither the deployable `app.main` nor the demo API (8766) contain the routes.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.encoders import jsonable_encoder
from jose import jwt
import pytest
from sqlalchemy import inspect, select

from test_backtest_results import bundle  # noqa: F401
from app.config import get_settings
from app.models import User
from app.predictive_admin import PREFIX, audit
from app.predictive_service import MODULE, PredictiveService
from predictive_admin_support import LOCAL, ORIGIN, add_account, admin_app, bearer, client

# Windows: a child of a process without a console would open its own console window; then
# hide it. With a console (visible or hidden) children keep sharing it, as before.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) and (
    0 if __import__("ctypes").windll.kernel32.GetConsoleWindow() else subprocess.CREATE_NO_WINDOW)

BACKEND = Path(__file__).resolve().parents[1]
WEEK = '?year=2021&week=1'


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture
def viewer(bundle, tmp_path):
    service = PredictiveService(bundle[0]())
    app, headers, admin = admin_app(tmp_path, service)
    return app, headers, admin, service


def audit_rows(app):
    with app.state.engine.connect() as connection:
        return [dict(r) for r in connection.execute(select(audit).order_by(audit.c.id)).mappings()]


@pytest.mark.anyio
async def test_access_requires_a_valid_current_administrator(viewer):
    app, headers, admin, _ = viewer
    settings = get_settings()
    async with client(app) as c:
        ok = await c.get(PREFIX + '/calendar', headers=headers)
        assert ok.status_code == 200 and ok.json()['module_version'] == MODULE == 'sigard-predictive-experimental/2'

        missing = await c.get(PREFIX + '/calendar', headers=LOCAL)
        assert missing.status_code == 401 and missing.headers['www-authenticate'] == 'Bearer'
        assert missing.headers['access-control-allow-origin'] == ORIGIN  # the browser can read the 401
        for token in ('not-a-jwt', jwt.encode({'sub': str(admin.id), 'role': 'admin', 'ver': 0,
                                               'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                                              'another-secret-of-sufficient-length', algorithm=settings.algorithm),
                      jwt.encode({'sub': str(admin.id), 'role': 'admin', 'ver': 0,
                                  'exp': datetime.now(timezone.utc) - timedelta(minutes=1)},
                                 settings.secret_key, algorithm=settings.algorithm)):
            response = await c.get(PREFIX + '/calendar', headers={**LOCAL, 'Authorization': 'Bearer ' + token})
            assert response.status_code == 401
        assert (await c.get(PREFIX + '/calendar', headers={**LOCAL, 'Authorization': 'Basic abc'})).status_code == 401

        other = add_account(app, 'user@example.test', role='user')
        forbidden = await c.get(PREFIX + '/comparison' + WEEK, headers={**LOCAL, **bearer(other)})
        assert forbidden.status_code == 403 and forbidden.json()['detail'] == 'Rol administrador requerido'

        # Revocation (password rotation / logout everywhere bumps token_version): 401 at once.
        with app.state.SessionLocal() as db:
            db.get(User, admin.id).token_version += 1
            db.commit()
        assert (await c.get(PREFIX + '/calendar', headers=headers)).status_code == 401
        # A fresh token works again; deactivating the account revokes it too.
        with app.state.SessionLocal() as db:
            current = db.get(User, admin.id)
            renewed = {**LOCAL, **bearer(current)}
        assert (await c.get(PREFIX + '/calendar', headers=renewed)).status_code == 200
        with app.state.SessionLocal() as db:
            db.get(User, admin.id).active = False
            db.commit()
        assert (await c.get(PREFIX + '/calendar', headers=renewed)).status_code == 401


@pytest.mark.anyio
async def test_local_guard_applies_before_authentication(viewer):
    app, headers, _, _ = viewer
    async with client(app) as c:
        for changed in ({'Origin': 'https://example.invalid'}, {'Origin': 'http://localhost:5173'},
                        {'X-Forwarded-For': '127.0.0.1'}, {'Forwarded': 'for=127.0.0.1'}, {'Host': 'evil.invalid'},
                        {'Host': '127.0.0.1:8765'}, {'Sec-Fetch-Site': 'cross-site'}):
            response = await c.get(PREFIX + '/calendar', headers={**headers, **changed})
            assert response.status_code == 403 and response.json() == {'detail': 'local_research_only'}
            assert 'access-control-allow-origin' not in response.headers
        no_origin = {k: v for k, v in headers.items() if k != 'Origin'}
        assert (await c.get(PREFIX + '/calendar', headers=no_origin)).status_code == 403
        no_read = {k: v for k, v in headers.items() if k != 'X-Sigard-Research'}
        assert (await c.get(PREFIX + '/calendar', headers=no_read)).json() == {'detail': 'local_read_header_required'}
        for method in ('POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'):
            assert (await c.request(method, PREFIX + '/calendar', headers=headers)).status_code == 405
    import httpx
    remote = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('10.0.0.8', 1234)), base_url='http://127.0.0.1:8767')
    async with remote as c:
        assert (await c.get(PREFIX + '/calendar', headers=headers)).status_code == 403


@pytest.mark.anyio
async def test_cors_allows_only_the_local_origin_get_and_authorization(viewer):
    app, _, _, _ = viewer
    preflight = {'Origin': ORIGIN, 'Access-Control-Request-Method': 'GET',
                 'Access-Control-Request-Headers': 'authorization,x-sigard-research'}
    async with client(app) as c:
        response = await c.options(PREFIX + '/comparison', headers=preflight)
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == ORIGIN
        assert response.headers['access-control-allow-methods'] == 'GET'
        assert response.headers['access-control-allow-headers'] == 'Authorization, X-Sigard-Research'
        assert '*' not in ''.join(v for k, v in response.headers.items() if k.startswith('access-control'))
        assert 'access-control-allow-credentials' not in response.headers
        for changed in ({'Access-Control-Request-Method': 'POST'}, {'Access-Control-Request-Headers': 'authorization,cookie'}):
            assert (await c.options(PREFIX + '/comparison', headers={**preflight, **changed})).status_code == 400
        assert (await c.options(PREFIX + '/comparison', headers={**preflight, 'Origin': 'https://example.invalid'})).status_code == 403
        # The administrative API keeps its single configured origin (no wildcard) elsewhere too.
        session = await c.options('/api/v1/admin/session', headers={'Origin': 'https://example.invalid',
                                                                   'Access-Control-Request-Method': 'POST'})
        assert session.headers.get('access-control-allow-origin') in (None, ORIGIN)


@pytest.mark.anyio
async def test_private_queries_are_audited_without_values_protected_ones_are_not(viewer):
    app, headers, admin, _ = viewer
    async with client(app) as c:
        for path in ('/calendar', '/geometry', '/metadata', '/comparison' + WEEK,
                     '/comparison' + WEEK + '&disclosure=presentation', '/history?start=2020-12-27&end=2021-01-10'):
            assert (await c.get(PREFIX + path, headers=headers)).status_code == 200
        assert audit_rows(app) == []
        exact = await c.get(PREFIX + '/comparison' + WEEK + '&disclosure=private', headers=headers)
        assert exact.status_code == 200 and exact.json()['disclosure']['mode'] == 'private'
        await c.get(PREFIX + '/observed' + WEEK + '&radio=000001&disclosure=private', headers=headers)
        await c.get(PREFIX + '/history?start=2020-12-27&end=2021-01-10&disclosure=private', headers=headers)
        # Unauthenticated private requests never reach the audit (nor the data).
        assert (await c.get(PREFIX + '/comparison' + WEEK + '&disclosure=private', headers=LOCAL)).status_code == 401
    rows = audit_rows(app)
    assert [(r['actor_user_id'], r['route'], r['period'], r['radio']) for r in rows] == [
        (admin.id, 'comparison', '2021-SE1', None),
        (admin.id, 'observed', '2021-SE1', '000001'),
        (admin.id, 'history', '2020-12-27..2021-01-10', None)]
    assert all(r['created_at'] is not None for r in rows)
    columns = {c['name'] for c in inspect(app.state.engine).get_columns('predictive_view_audit')}
    assert columns == {'id', 'actor_user_id', 'route', 'period', 'radio', 'created_at'}  # no returned values
    stored = json.dumps(rows, default=str)
    assert 'quantity' not in stored and 'rows' not in stored


@pytest.mark.anyio
async def test_audit_failure_blocks_the_private_query(viewer):
    app, headers, _, _ = viewer
    with app.state.engine.begin() as connection:
        audit.drop(connection)
    async with client(app) as c:
        with pytest.raises(Exception):
            await c.get(PREFIX + '/comparison' + WEEK + '&disclosure=private', headers=headers)
        # Protected mode does not depend on the audit table.
        assert (await c.get(PREFIX + '/comparison' + WEEK, headers=headers)).status_code == 200


@pytest.mark.anyio
async def test_contract_and_protection_are_unchanged(viewer):
    app, headers, _, service = viewer
    async with client(app) as c:
        for mode in ('presentation', 'private'):
            response = await c.get(PREFIX + '/comparison' + WEEK + f'&disclosure={mode}', headers=headers)
            assert response.json() == jsonable_encoder(service.week('2021', '1', None, mode=mode))
        protected = (await c.get(PREFIX + '/comparison' + WEEK, headers=headers)).json()
        assert protected['disclosure']['minimum_count'] == 5 and protected['disclosure']['mode'] == 'presentation'
        assert response.headers['cache-control'] == 'no-store, private'
        assert response.headers['x-frame-options'] == 'DENY'


@pytest.mark.anyio
async def test_viewer_bytes_are_exactly_what_jsonresponse_would_send(viewer):
    """F6.1 contention fix: the body is encoded in the threadpool, byte for byte as before."""
    from starlette.responses import JSONResponse
    app, headers, _, service = viewer
    async with client(app) as c:
        for path, value in (('/calendar', service.catalog()), ('/geometry', service.geometry()), ('/metadata', service.metadata()),
                            ('/comparison' + WEEK, service.week('2021', '1', None, mode='presentation'))):
            response = await c.get(PREFIX + path, headers=headers)
            assert response.status_code == 200
            assert response.content == JSONResponse(jsonable_encoder(value)).body, path
            assert response.headers['content-type'] == 'application/json'


@pytest.mark.anyio
async def test_abandoned_viewer_requests_are_not_computed(tmp_path):
    """F6.1: a queued viewer request whose client already disconnected is dropped unanswered work."""
    from app.predictive_admin import PredictiveGate, PREFIX as GATE_PREFIX
    calls, sent = [], []

    async def viewer(scope, receive, send):
        calls.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{}'})

    async def other(scope, receive, send):
        raise AssertionError('viewer paths never reach the admin app')

    gate = PredictiveGate(other, viewer)
    scope = {'type': 'http', 'method': 'GET', 'scheme': 'http', 'path': GATE_PREFIX + '/history', 'raw_path': b'', 'query_string': b'',
             'client': ('127.0.0.1', 1234), 'server': ('127.0.0.1', 8767), 'root_path': '', 'http_version': '1.1',
             'headers': [(b'host', b'127.0.0.1:8767'), (b'origin', ORIGIN.encode()), (b'x-sigard-research', b'local-read')]}

    async def send(message):
        sent.append(message)

    def receiver(messages):
        queue = list(messages)
        async def receive():
            if queue:
                return queue.pop(0)
            import anyio
            await anyio.sleep_forever()
        return receive

    await gate(scope, receiver([{'type': 'http.request', 'body': b'', 'more_body': False}, {'type': 'http.disconnect'}]), send)
    assert calls == [] and sent[0]['status'] == 499
    sent.clear()
    await gate(scope, receiver([{'type': 'http.request', 'body': b'', 'more_body': False}]), send)
    assert calls == [GATE_PREFIX + '/history'] and sent[0]['status'] == 200


class _HeavyService:
    """Fictitious service whose geometry is large enough to take seconds to encode."""
    def __init__(self, features):
        self.features = features

    def geometry(self):
        return {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'id': f'FX{i:07d}', 'value': i / 7}, 'geometry': None} for i in range(self.features)]}


@pytest.mark.anyio
async def test_large_viewer_responses_do_not_block_alerts_or_accounts(tmp_path):
    """Viewer JSON was encoded on the event loop; alerts/accounts waited behind it (F6.1)."""
    import asyncio
    import time
    features = 150_000
    started = time.perf_counter(); jsonable_encoder(_HeavyService(features).geometry()); encode_s = time.perf_counter() - started
    assert encode_s > 0.4, f'the payload must be slow to encode to make this check meaningful ({encode_s:.2f} s)'
    app, headers, admin = admin_app(tmp_path, _HeavyService(features))
    gaps, done = [], False

    async def ticker():
        last = time.perf_counter()
        while not done:
            await asyncio.sleep(0.01)
            now = time.perf_counter(); gaps.append(now - last); last = now

    async with client(app) as c:
        assert (await c.get('/api/v1/admin/users?page=1', headers=bearer(admin))).status_code == 200  # warm the route
        tick = asyncio.create_task(ticker())
        heavy = asyncio.create_task(c.get(PREFIX + '/geometry', headers=headers))
        await asyncio.sleep(0.05)
        light = []
        while not heavy.done():
            t = time.perf_counter()
            assert (await c.get('/api/v1/admin/users?page=1', headers=bearer(admin))).status_code == 200
            light.append((time.perf_counter() - t, heavy.done()))
            await asyncio.sleep(0.02)
        response = await heavy
        done = True; await tick
    assert response.status_code == 200 and len(response.json()['features']) == features
    # Before the fix the whole encoding ran on the event loop: one gap as long as the encoding and
    # no other route answered until the viewer response was done. Light routes still share the CPU
    # (GIL) with the viewer thread, so their latency varies and is not asserted here.
    assert max(gaps) < max(0.25, encode_s / 4), f'event loop blocked {max(gaps):.2f} s (encoding takes {encode_s:.2f} s)'
    assert light, 'the accounts route was queried while the viewer encoded its response'


@pytest.mark.anyio
async def test_unavailable_service_answers_503_after_authentication(tmp_path):
    app, headers, _ = admin_app(tmp_path, None)
    async with client(app) as c:
        assert (await c.get(PREFIX + '/calendar', headers=LOCAL)).status_code == 401
        response = await c.get(PREFIX + '/calendar', headers=headers)
        assert response.status_code == 503 and response.json() == {'detail': 'backtest_bundle_unavailable'}


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
modules = sorted(m for m in sys.modules if m in ("app.predictive_admin", "app.predictive_service", "app.alerts_local"))
print(json.dumps({"paths": paths, "modules": modules}))
'''


def test_deployable_app_main_has_no_predictive_routes_with_or_without_auth(tmp_path):
    result = run_fresh('from app.main import app\n' + ROUTES + '''
from fastapi.testclient import TestClient
with TestClient(app, base_url="http://127.0.0.1:8767") as c:
    status = [c.get("/api/v1/research/predictive/calendar", headers={"Origin": "http://127.0.0.1:5173",
              "X-Sigard-Research": "local-read", "Authorization": auth}).status_code for auth in ("", "Bearer x")]
print(json.dumps({"paths": paths, "modules": modules, "status": status}))
''', tmp_path)
    assert result['paths'] and not any(p.startswith('/api/v1/research') for p in result['paths'])
    assert result['modules'] == [] and result['status'] == [404, 404]
    source = (BACKEND / 'app/main.py').read_text(encoding='utf-8')
    assert 'predictive_admin' not in source and 'predictive_service' not in source


def test_demo_api_has_no_predictive_routes(tmp_path):
    result = run_fresh('''
from pathlib import Path
from tempfile import TemporaryDirectory
from app.demo_local import BACKEND, checked_directory, create_demo_app
(BACKEND / ".tmp").mkdir(exist_ok=True)
holder = TemporaryDirectory(prefix="sigard-demo-", dir=BACKEND / ".tmp")
app, _ = create_demo_app(checked_directory(holder.name))
''' + ROUTES + '''
app.state.engine.dispose()
holder.cleanup()
''', tmp_path)
    assert any(p.startswith('/api/v1/admin/demo') for p in result['paths'])
    assert not any(p.startswith('/api/v1/research') for p in result['paths'])
    assert result['modules'] == []


def test_only_the_local_launcher_imports_the_viewer_mount():
    import ast
    importers = []
    for path in sorted((BACKEND / 'app').rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        if any(m.endswith('predictive_admin') for m in names):
            importers.append(path.name)
    assert importers == ['alerts_local.py']


def test_local_launcher_process_serves_the_viewer_behind_login(tmp_path):
    """Real `alerts_local session --source fictional` process (no private artifacts): the
    viewer answers 401 without a session and 503 (no module) with one; never 500. Regression:
    importing predictive_admin before build_app bound the inherited settings (500)."""
    import socket
    import httpx
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8767)) == 0:
            pytest.skip('8767 ocupado; no se detiene ningún servicio existente')
    (BACKEND / '.tmp').mkdir(exist_ok=True)
    from tempfile import TemporaryDirectory
    env = {k: v for k, v in os.environ.items() if k not in ('SECRET_KEY', 'DATABASE_URL')}
    with TemporaryDirectory(prefix='sigard-alerts-', dir=BACKEND / '.tmp') as directory:
        process = subprocess.Popen([sys.executable, '-I', '-B', str(BACKEND / 'app/alerts_local.py'), 'session',
                                    '--directory', directory, '--source', 'fictional'], cwd=directory, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, creationflags=NO_WINDOW)
        try:
            ready = json.loads(process.stdout.readline())
            assert ready['predictive'] is False and ready['storage'] == 'disposable-sqlite'
            with httpx.Client(base_url='http://127.0.0.1:8767', timeout=20, trust_env=False) as c:
                token = c.post('/api/v1/admin/session', json={'email': ready['email'], 'password': ready['password']}).json()['access_token']
                assert c.get(PREFIX + '/calendar', headers=LOCAL).status_code == 401
                viewer = c.get(PREFIX + '/calendar', headers={**LOCAL, 'Authorization': 'Bearer ' + token})
                assert viewer.status_code == 503 and viewer.json() == {'detail': 'backtest_bundle_unavailable'}
                assert c.get('/api/v1/admin/alerts/status', headers={'Authorization': 'Bearer ' + token}).status_code == 200
                assert c.get(PREFIX + '/calendar', headers={'Authorization': 'Bearer ' + token}).status_code == 403  # guard
        finally:
            process.stdin.write('stop\n'); process.stdin.flush()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
