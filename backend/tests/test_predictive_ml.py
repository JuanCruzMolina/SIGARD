"""Entirely fictional aggregates/artifact bytes. No estimators or clinical fixtures."""
import ast
import hashlib
import json
from pathlib import Path

import pytest
import httpx
from test_backtest_results import bundle  # noqa: F401
from test_backtest_results import TRUSTED
from test_predictive_service import high_cells
from app.predictive_service import PredictiveService
from app.predictive_ml import V1_CANDIDATES
from app.experimental_results import ArtifactBlocked
from app.experimental_api import create_research_app

RF2, RES2 = 'rf_v2_city_propensity', 'residual_v2'
RF1, RES1 = V1_CANDIDATES['presence'], V1_CANDIDATES['quantity']


def writer(bundle):
    folder = bundle[3]
    def write(name, doc, root):
        p = folder / name
        body = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
        p.write_bytes(body)
        return dict(path=p.relative_to(root).as_posix(), sha256=hashlib.sha256(body).hexdigest())
    return write


def context(base):
    return {k: base[k] for k in ('dataset_version', 'data_policy_version', 'campaign_version', 'territory_version')}


def v1_overlay(reader, write, base, mutation=None):
    artifact = write('fake-model.private.bin', b'FICTIONAL_NON_EXECUTABLE', reader.root)
    models = {c: dict(method=m, state='experimental_evaluated', model_version='FICTIONAL/' + m,
              fit_last_target_end='2020-11-21', features=['FICTIONAL_origin'], calibrated=False,
              artifact=artifact, artifact_sha256=artifact['sha256']) for c, m in V1_CANDIDATES.items()}
    rows = [dict(radio_id=r['radio_id'], observed=r['observed']['quantity'], baseline=r['baseline']['quantity'],
                 baseline_score=r['predicted']['presence_score'], presence_score=.7, presence_threshold=.5, quantity=6.25)
            for r in base['rows'] if r['common_mask']]
    doc = dict(target_week=base['target_week'], origin_week=base['origin_week'], models=models, rows=rows)
    if mutation: mutation(doc)
    week = write('ml-week.private.json', doc, reader.root)
    manifest = dict(context(base), schema_version='sigard-predictive-ml-overlay/1', candidates=V1_CANDIDATES, horizon_weeks=1,
                    operational_enabled=False, radio_ids=[r['radio_id'] for r in rows],
                    features={c: ['FICTIONAL_origin'] for c in V1_CANDIDATES}, weeks={base['target_week']: week})
    manifest = write('ml-manifest.private.json', manifest, reader.root)
    return write('ml-pointer.private.json', manifest, reader.root)


def v2_overlay(reader, write, base, mutation=None, manifest_mutation=None, artifact=b'FICTIONAL_V2_NON_EXECUTABLE'):
    artifact = write('fake-v2-model.private.bin', artifact, reader.root)
    features = ['FICTIONAL_city_origin']
    models = {m: dict(method=m, capability=c, state='experimental_not_promoted', block='FICTIONAL-q1',
              model_version='FICTIONAL/' + m, fit_last_target_end='2020-11-21', features=features, calibrated=False,
              artifact=artifact, artifact_sha256=artifact['sha256']) for m, c in ((RF2, 'presence'), (RES2, 'quantity'))}
    common = [r for r in base['rows'] if r['common_mask']]
    rows = [dict(radio_id=r['radio_id'], observed=r['observed']['quantity'], baseline=r['baseline']['quantity'],
                 onset_eligible=r['baseline']['quantity'] == 0, presence_score=round(1 - i / 1000, 4), topk_rank=i + 1,
                 quantity=5.5) for i, r in enumerate(common)]
    doc = dict(target_week=base['target_week'], origin_week=base['origin_week'], models=models, rows=rows)
    if mutation: mutation(doc)
    week = write('ml-v2-week.private.json', doc, reader.root)
    candidates = [
        dict(id=RF2, capability='presence', state='experimental_not_promoted', calibrated=False, features=features,
             decision_rule=dict(type='top_k', k=10, scope='per_target_week_common_territory'),
             promotion=dict(decision='not_promoted')),
        dict(id=RES2, capability='quantity', state='experimental_not_promoted', calibrated=False, features=features,
             decision_rule=dict(type='count_estimate'), promotion=dict(decision='not_promoted'))]
    manifest = dict(context(base), schema_version='sigard-predictive-ml-overlay/2', ml_campaign_version='FICTIONAL-v2',
                    candidates=candidates, horizon_weeks=1, operational_enabled=False, training_performed=False,
                    inference_performed=False, radio_ids=[r['radio_id'] for r in rows], weeks={base['target_week']: week})
    if manifest_mutation: manifest_mutation(manifest)
    manifest = write('ml-v2-manifest.private.json', manifest, reader.root)
    return write('ml-v2-pointer.private.json', manifest, reader.root)


def install(bundle, mutation=None, v2=True, v1=True, **v2_options):
    reader = high_cells(bundle); write = writer(bundle)
    base = reader.week(2021, 1)
    registries = []
    if v1: registries.append(v1_overlay(reader, write, base, mutation))
    if v2: registries.append(v2_overlay(reader, write, base, **v2_options))
    return PredictiveService(reader, ml_registries=[(r['path'], r['sha256']) for r in registries])


def test_v1_candidate_values_baseline_observed_and_protected_derivatives(bundle):
    s = install(bundle, v2=False); exact = s.week(2021, 1, mode='private'); safe = s.week(2021, 1)
    r = exact['rows'][0]
    assert (r['ml'][RES1]['quantity'], r['baseline']['quantity'], r['observed']['quantity']) == (6.25, 6, 7)
    assert r['ml'][RES1]['difference'] == -.75 and r['difference'] == -1
    assert r['ml'][RF1]['presence_threshold'] == .5 and r['ml'][RF1]['topk_rank'] is None
    assert exact['ml_metrics'][RF1]['presence']['n'] == 256
    assert safe['ml_metrics'][RF1]['presence']['n'] == 2
    assert safe['ml_metrics'][RES1]['quantity']['mae'] == .75
    for r in safe['rows'][2:256]:
        assert all(v is None for values in r['ml'].values() for v in values.values())
        assert set(r['ml_availability'].values()) == {'privacy_suppressed'}
    assert exact == s.week(2021, 1, mode='private')
    history = s.history('2020-12-27', '2021-01-10', mode='private')
    assert history['series'][1]['ml_predicted'][RES1] == 6.25 * 256
    assert history['series'][2]['ml_predicted'][RES1] is None and history['series'][2]['baseline'] is not None
    assert s.week(2020, 53)['ml'][RF1]['availability_status'] == 'not_available'


def test_v2_topk_rule_confusion_and_private_only_recall(bundle):
    s = install(bundle)
    exact = s.week(2021, 1, mode='private')
    rf2 = exact['ml'][RF2]
    assert rf2['availability_status'] == 'available' and rf2['state'] == 'experimental_not_promoted'
    assert rf2['decision_rule'] == dict(type='top_k', k=10, scope='per_target_week_common_territory')
    flagged = [r for r in exact['rows'] if r['ml'][RF2]['presence'] == 1]
    assert len(flagged) == 10 and all(r['ml'][RF2]['topk_rank'] <= 10 for r in flagged)
    assert [r['ml'][RF2]['confusion'] for r in exact['rows'][:3]] == ['TP', 'TP', 'FP']
    assert exact['rows'][2]['ml'][RF2]['presence_threshold'] is None
    topk = exact['ml_metrics'][RF2]['topk']
    assert (topk['positives'], topk['hits'], topk['recall'], topk['flagged'], topk['precision']) == (2, 2, 1.0, 10, .2)
    assert topk['status'] == 'all_comparable' and topk['onset_events'] == 0 and topk['onset_recall'] is None
    assert exact['rows'][0]['ml'][RES2]['quantity'] == 5.5 and exact['rows'][0]['ml'][RF2]['quantity'] is None
    safe = s.week(2021, 1)
    hidden = safe['ml_metrics'][RF2]['topk']
    assert hidden['status'] == 'private_only_selection_bias' and hidden['k'] == 10
    assert all(hidden[k] is None for k in hidden if k not in ('k', 'status'))
    assert all(r['ml'][RF2]['topk_rank'] is None for r in safe['rows'][2:256])
    # Rows below 5 records (including v2 quantity 5.5 here is >= 5, so only observed/baseline decide).
    assert safe['rows'][0]['ml'][RF2]['topk_rank'] == 1
    history = s.history('2020-12-27', '2021-01-10', mode='private')
    assert history['ml_by_year']['2021'][RF2]['topk']['recall'] == 1.0
    assert s.history('2020-12-27', '2021-01-10')['ml_by_year']['2021'][RF2]['topk']['recall'] is None


def test_candidates_from_manifests_defaults_and_calendar_availability(bundle):
    s = install(bundle)
    calendar = s.catalog(); metadata = s.metadata()
    assert [c['id'] for c in calendar['experimental_candidates']] == [RF1, RES1, RF2, RES2]
    assert calendar['default_candidates'] == metadata['default_candidates'] == {'presence': RF2, 'quantity': RES2}
    assert {c['id']: c['state'] for c in metadata['experimental_candidates']} == {
        RF1: 'experimental_evaluated', RES1: 'experimental_evaluated', RF2: 'experimental_not_promoted', RES2: 'experimental_not_promoted'}
    assert all(c['promotion']['decision'] == 'not_promoted' for c in metadata['experimental_candidates'])
    weeks = {w['target_week']: w['ml_availability'] for w in calendar['weeks']}
    assert weeks['2021-01-03'] == {RF1: 'available', RES1: 'available', RF2: 'available', RES2: 'available'}
    assert set(weeks['2021-01-10'].values()) == {'not_available'}
    assert calendar['operational_enabled'] is False and metadata['selected_methods'] == {'presence': 'presence_seasonal', 'quantity': 'count_latest'}
    only_v1 = install(bundle, v2=False).catalog()
    assert only_v1['default_candidates'] == {'presence': RF1, 'quantity': RES1}


def test_altered_v2_artifact_blocks_only_v2_and_keeps_v1_and_reference(bundle):
    s = install(bundle); s.week(2021, 1)
    (bundle[3] / 'fake-v2-model.private.bin').write_bytes(b'CHANGED')
    r = s.week(2021, 1, mode='private')
    assert r['ml'][RF2]['reason'] == r['ml'][RES2]['reason'] == 'ml_integrity_or_compatibility_blocked'
    assert r['ml'][RF1]['availability_status'] == 'available'
    assert r['rows'][0]['ml'][RF2]['presence'] is None and r['rows'][0]['ml'][RF1]['presence'] == 1
    assert r['rows'][0]['baseline']['quantity'] == 6


def test_artifacts_above_json_limit_are_hashed_not_rejected(bundle):
    s = install(bundle, artifact=b'F' * (17 * 1024 * 1024))
    assert s.week(2021, 1)['ml'][RF2]['availability_status'] == 'available'


@pytest.mark.parametrize('kind', ['duplicate_rank', 'observed', 'future', 'features', 'unknown_model'])
def test_re_signed_incompatible_v2_week_is_rejected(bundle, kind):
    def mutate(d):
        if kind == 'duplicate_rank': d['rows'][1]['topk_rank'] = 1
        elif kind == 'observed': d['rows'][0]['observed'] = 100
        elif kind == 'future': d['models'][RF2]['fit_last_target_end'] = '2021-01-02'
        elif kind == 'features': d['models'][RES2]['features'] = ['future']
        else: d['models']['FICTIONAL_unknown'] = d['models'].pop(RES2)
    reader = high_cells(bundle); write = writer(bundle); base = reader.week(2021, 1)
    pin = v2_overlay(reader, write, base, mutation=mutate)
    r = PredictiveService(reader, ml_registries=[(pin['path'], pin['sha256'])]).week(2021, 1, mode='private')
    assert r['ml'][RF2]['reason'] == 'ml_integrity_or_compatibility_blocked'
    assert r['rows'][0]['ml'][RES2]['quantity'] is None and r['rows'][0]['baseline']['quantity'] == 6


@pytest.mark.parametrize('field,value', [('state', 'operational_approved'), ('calibrated', True),
                                         ('promotion', {'decision': 'promoted'}), ('decision_rule', {'type': 'top_k', 'k': 0})])
def test_manifest_claiming_promotion_or_invalid_rule_blocks_module(bundle, field, value):
    def mutate(manifest): manifest['candidates'][0][field] = value
    s = install(bundle, manifest_mutation=mutate)
    with pytest.raises(ArtifactBlocked):
        s.catalog()


def test_http_modules_cannot_train_infer_or_deserialize():
    root = Path(__file__).resolve().parents[1] / 'app'
    for name in ('predictive_ml.py', 'predictive_service.py'):
        tree = ast.parse((root / name).read_text())
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(m.split('.')[0] in {'sklearn', 'psycopg2', 'joblib', 'pickle', 'sigard_ml'} for m in imports)
        assert not any(isinstance(n, ast.Attribute) and n.attr in ('fit', 'predict', 'predict_proba') for n in ast.walk(tree))


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.anyio
async def test_ml_http_projection_missing_results_and_access_guards(bundle):
    s = install(bundle)
    app = create_research_app(predictive=s, legacy=False)
    prefix = '/api/v1/research/predictive'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8765') as client:
        for endpoint in ('comparison', 'predicted', 'metrics'):
            response = await client.get(prefix + '/' + endpoint + '?year=2021&week=1', headers=TRUSTED)
            assert response.status_code == 200 and response.json()['ml'][RF2]['state'] == 'experimental_not_promoted'
            assert 'FICTIONAL_NON_EXECUTABLE' not in response.text and 'FICTIONAL_V2_NON_EXECUTABLE' not in response.text
            if 'rows' in response.json(): assert response.json()['rows'][2]['ml'][RES2]['quantity'] is None
        absent = (await client.get(prefix + '/comparison?year=2021&week=2&disclosure=private', headers=TRUSTED)).json()
        assert absent['ml'][RF2]['availability_status'] == 'not_available'
        assert absent['rows'][0]['baseline']['quantity'] is not None
        assert (await client.get(prefix + '/comparison?year=2021&week=1')).status_code == 403
        assert (await client.post(prefix + '/train', headers=TRUSTED)).status_code == 405
