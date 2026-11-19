"""Entirely fictional aggregates/artifact bytes. No estimators or clinical fixtures."""
import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest
import httpx
from test_backtest_results import bundle  # noqa: F401
from test_backtest_results import TRUSTED
from test_predictive_service import high_cells
from app.predictive_service import PredictiveService
from app.predictive_ml import CANDIDATES
from app.experimental_results import ArtifactBlocked
from app.experimental_api import create_research_app


def install(bundle, mutation=None):
    reader = high_cells(bundle); folder = bundle[3]; root = reader.root
    base = reader.week(2021, 1)
    def write(name, doc):
        p = folder / name
        body = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
        p.write_bytes(body)
        return dict(path=p.relative_to(root).as_posix(), sha256=hashlib.sha256(body).hexdigest())
    artifact = write('fake-model.private.bin', b'FICTIONAL_NON_EXECUTABLE')
    models = {c: dict(method=m, state='experimental_evaluated', model_version='FICTIONAL/'+m,
              fit_last_target_end='2020-11-21', features=['FICTIONAL_origin'], calibrated=False,
              artifact=artifact, artifact_sha256=artifact['sha256']) for c,m in CANDIDATES.items()}
    rows = [dict(radio_id=r['radio_id'], observed=r['observed']['quantity'], baseline=r['baseline']['quantity'],
                 baseline_score=r['predicted']['presence_score'], presence_score=.7, presence_threshold=.5, quantity=6.25)
            for r in base['rows'] if r['common_mask']]
    doc = dict(target_week=base['target_week'], origin_week=base['origin_week'], models=models, rows=rows)
    if mutation: mutation(doc)
    week = write('ml-week.private.json', doc)
    manifest = {k: base[k] for k in ('dataset_version','data_policy_version','campaign_version','territory_version')}
    manifest.update(schema_version='sigard-predictive-ml-overlay/1', candidates=CANDIDATES, horizon_weeks=1,
                    operational_enabled=False, radio_ids=[r['radio_id'] for r in rows],
                    features={c:['FICTIONAL_origin'] for c in CANDIDATES}, weeks={base['target_week']:week})
    manifest = write('ml-manifest.private.json', manifest)
    pointer = write('ml-pointer.private.json', manifest)
    return PredictiveService(reader, ml_registry=pointer['path'], ml_sha256=pointer['sha256'])


def test_independent_ml_baseline_observed_and_protected_derivatives(bundle):
    s = install(bundle); exact = s.week(2021,1,mode='private'); safe = s.week(2021,1)
    r = exact['rows'][0]
    assert (r['ml']['quantity'],r['baseline']['quantity'],r['observed']['quantity']) == (6.25,6,7)
    assert r['ml']['difference'] == -.75 and r['difference'] == -1
    assert exact['ml_metrics']['presence']['n'] == 256
    assert safe['ml_metrics']['presence']['n'] == 2
    assert safe['ml_metrics']['quantity']['mae'] == .75
    for r in safe['rows'][2:256]:
        assert all(v is None for v in r['ml'].values())
        assert set(r['ml_availability'].values()) == {'privacy_suppressed'}
    assert exact == s.week(2021,1,mode='private')
    history = s.history('2020-12-27','2021-01-10',mode='private')
    assert history['series'][1]['ml_predicted'] == 6.25*256
    assert history['series'][2]['ml_predicted'] is None and history['series'][2]['baseline'] is not None
    assert s.week(2020,53)['ml']['presence']['availability_status'] == 'not_available'


def test_missing_one_capability_keeps_other_and_references(bundle):
    s = install(bundle, lambda d: d['models'].pop('quantity'))
    r = s.week(2021,1,mode='private')
    assert r['rows'][0]['ml']['presence_score'] == .7 and r['rows'][0]['ml']['quantity'] is None
    assert r['rows'][0]['baseline']['quantity'] == 6
    assert r['ml_metrics']['quantity']['n'] == 0 and r['ml_metrics']['presence']['n'] == 256


@pytest.mark.parametrize('kind', ['future','universe','observed','score','features','origin'])
def test_re_signed_incompatible_overlay_is_rejected(bundle,kind):
    def mutate(d):
        if kind == 'future': d['models']['presence']['fit_last_target_end']='2021-01-02'
        elif kind == 'universe': d['rows'].pop()
        elif kind == 'observed': d['rows'][0]['observed']=100
        elif kind == 'score': d['rows'][0]['presence_score']=1.1
        elif kind == 'features': d['models']['presence']['features']=['future']
        else: d['origin_week']='2021-01-03'
    r = install(bundle,mutate).week(2021,1,mode='private')
    assert r['ml']['presence']['reason'] == 'ml_integrity_or_compatibility_blocked'
    assert r['rows'][0]['ml']['quantity'] is None and r['rows'][0]['baseline']['quantity'] == 6


def test_artifact_and_result_hashes_checked_on_next_request(bundle):
    s = install(bundle); s.week(2021,1)
    (bundle[3]/'fake-model.private.bin').write_bytes(b'CHANGED')
    r = s.week(2021,1)
    assert r['ml']['presence']['reason'] == 'ml_integrity_or_compatibility_blocked'
    assert r['rows'][0]['baseline']['quantity'] == 6


def test_http_modules_cannot_train_infer_or_deserialize():
    root = Path(__file__).resolve().parents[1]/'app'
    for name in ('predictive_ml.py','predictive_service.py'):
        tree=ast.parse((root/name).read_text())
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(m.split('.')[0] in {'sklearn','psycopg2','joblib','pickle','sigard_ml'} for m in imports)
        assert not any(isinstance(n,ast.Attribute) and n.attr in ('fit','predict','predict_proba') for n in ast.walk(tree))


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.anyio
async def test_ml_http_projection_missing_results_and_access_guards(bundle):
    s = install(bundle)
    app = create_research_app(predictive=s, legacy=False)
    prefix = '/api/v1/research/predictive'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1',1234)), base_url='http://127.0.0.1:8765') as client:
        for endpoint in ('comparison','predicted','metrics'):
            response=await client.get(prefix+'/'+endpoint+'?year=2021&week=1',headers=TRUSTED)
            assert response.status_code==200 and response.json()['ml']['presence']['state']=='experimental_evaluated'
            assert 'FICTIONAL_NON_EXECUTABLE' not in response.text
            if 'rows' in response.json(): assert response.json()['rows'][2]['ml']['quantity'] is None
        absent=(await client.get(prefix+'/comparison?year=2021&week=2&disclosure=private',headers=TRUSTED)).json()
        assert absent['ml']['presence']['availability_status']=='not_available'
        assert absent['rows'][0]['baseline']['quantity'] is not None
        assert (await client.get(prefix+'/comparison?year=2021&week=1')).status_code==403
        assert (await client.post(prefix+'/train',headers=TRUSTED)).status_code==405
