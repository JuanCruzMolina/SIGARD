"""Precomputed annual histories: identical to the computed ones, verified, bound and fail-closed.

Only the fictional stage-3 bundle and fictional ML overlays (v1 and v2 candidates) are used.
"""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from test_backtest_results import bundle, TRUSTED  # noqa: F401
from test_predictive_ml import RES1, RES2, RF1, RF2, install
from app import predictive_history
from predictive_admin_support import admin_app, client as admin_client
from app.experimental_results import ArtifactBlocked, clear_verification_cache
from app.predictive_history import HistoryStore, MODES, build, compare, year_bounds
from app.predictive_service import PredictiveService

OUTPUT = Path('data/interim/official/FICTIONAL-HISTORY')
PREFIX = '/api/v1/research/predictive'


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture(autouse=True)
def fresh_cache():
    clear_verification_cache(); yield; clear_verification_cache()


def services(bundle):
    computed = install(bundle)
    root = computed.reader.root
    result = build(computed, OUTPUT, root=root, today='2026-11-16')
    store = HistoryStore(root, result['registry'], result['registry_sha256'])
    stored = PredictiveService(computed.reader, ml_registries=computed.ml_registries, history_store=store)
    return computed, stored, root


def test_precomputed_history_is_identical_for_every_year_mode_and_candidate(bundle):
    computed, stored, root = services(bundle)
    catalog = computed._snapshot().catalog()
    assert sorted(year_bounds(catalog)) == [2020, 2021]
    assert compare(stored, computed) == 2 * len(MODES)
    for start, end in year_bounds(catalog).values():
        for mode in MODES:
            value = stored.history(start, end, None, mode)
            assert value == json.loads(json.dumps(computed.history(start, end, None, mode)))
            assert set(value['ml_metrics']) == {RF1, RES1, RF2, RES2}
    manifest = json.loads((root / OUTPUT / 'manifest.private.json').read_bytes())
    assert manifest['training_performed'] is False and manifest['inference_performed'] is False
    assert set(manifest['files']) == {f'history/{y}.{m}.private.json' for y in (2020, 2021) for m in MODES}
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((root / OUTPUT / name).read_bytes()).hexdigest() == digest


def test_annual_requests_are_read_not_recomputed(bundle, monkeypatch):
    computed, stored, _ = services(bundle)
    monkeypatch.setattr(PredictiveService, '_attach', staticmethod(lambda *_: pytest.fail('annual history recomputed')))
    assert stored.history('2021-01-03', '2021-01-10', None)['start'] == '2021-01-03'
    # Other ranges and single-radio histories are still projected per request.
    monkeypatch.undo()
    radio = computed._snapshot().catalog()['radio_ids'][0]
    assert stored.history('2021-01-03', '2021-01-03', None) == computed.history('2021-01-03', '2021-01-03', None)
    assert stored.history('2021-01-03', '2021-01-10', radio) == computed.history('2021-01-03', '2021-01-10', radio)


def tamper(path, change):
    value = json.loads(path.read_bytes()); change(value); path.write_bytes(json.dumps(value).encode())


@pytest.mark.parametrize('target', ['history', 'manifest', 'registry'])
def test_altered_history_manifest_or_registry_blocks(bundle, target):
    _, stored, root = services(bundle)
    folder = root / OUTPUT
    path = {'history': folder / 'history/2021.presentation.private.json', 'manifest': folder / 'manifest.private.json',
            'registry': folder / 'registry.private.json'}[target]
    stored.history('2021-01-03', '2021-01-10', None)
    tamper(path, lambda v: v.update(start='2021-01-03', FICTIONAL_ALTERED=True))
    with pytest.raises(ArtifactBlocked):
        stored.history('2021-01-03', '2021-01-10', None)


def test_stale_bindings_or_missing_year_block(bundle, monkeypatch):
    computed, stored, root = services(bundle)
    monkeypatch.setattr(predictive_history, 'code_sha256', lambda: 'f' * 64)
    with pytest.raises(ArtifactBlocked):
        stored.history('2021-01-03', '2021-01-10', None)
    monkeypatch.undo()
    # Same bundle with one overlay fewer: the stored history no longer matches its inputs.
    fewer = PredictiveService(computed.reader, ml_registries=computed.ml_registries[:1], history_store=stored.history_store)
    with pytest.raises(ArtifactBlocked):
        fewer.history('2021-01-03', '2021-01-10', None)
    # A year of the catalog absent from the manifest is never recomputed.
    folder = root / OUTPUT
    manifest = json.loads((folder / 'manifest.private.json').read_bytes()); del manifest['years']['2020']
    body = json.dumps(manifest).encode(); (folder / 'manifest.private.json').write_bytes(body)
    registry = json.dumps({'path': (OUTPUT / 'manifest.private.json').as_posix(), 'sha256': hashlib.sha256(body).hexdigest()}).encode()
    (folder / 'registry.private.json').write_bytes(registry)
    pruned = PredictiveService(computed.reader, ml_registries=computed.ml_registries,
                               history_store=HistoryStore(root, OUTPUT / 'registry.private.json', hashlib.sha256(registry).hexdigest()))
    assert pruned.history('2021-01-03', '2021-01-10', None)['start'] == '2021-01-03'
    with pytest.raises(ArtifactBlocked):
        pruned.history('2020-12-27', '2020-12-27', None)


def test_build_is_create_only_private_and_always_computed(bundle):
    computed, stored, root = services(bundle)
    for output in (OUTPUT, Path('frontend/public/history'), Path('data/interim/official/../x'), root / 'abs'):
        with pytest.raises(ArtifactBlocked):
            build(computed, output, root=root)
    with pytest.raises(ArtifactBlocked):
        build(stored, Path('data/interim/official/FICTIONAL-HISTORY-2'), root=root)


@pytest.mark.anyio
async def test_api_serves_stored_history_and_answers_503_when_altered(bundle, tmp_path):
    _, stored, root = services(bundle)
    app, TRUSTED, _ = admin_app(tmp_path, stored)
    async with admin_client(app) as client:
        query = {'start': '2021-01-03', 'end': '2021-01-10', 'disclosure': 'presentation'}
        response = await client.get(f'{PREFIX}/history', params=query, headers=TRUSTED)
        assert response.status_code == 200 and response.json()['start'] == '2021-01-03'
        tamper(root / OUTPUT / 'history/2021.presentation.private.json', lambda v: v['series'][0].update(observed=999))
        response = await client.get(f'{PREFIX}/history', params=query, headers=TRUSTED)
        assert response.status_code == 503
