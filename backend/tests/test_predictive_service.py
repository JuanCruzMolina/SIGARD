"""Final module tests use only generated aggregates/polygons from the stage3 fixture."""
import copy
import hashlib
import json
from pathlib import Path
import httpx
import pytest
from test_backtest_results import bundle, TRUSTED  # noqa: F401
from app.predictive_service import PredictiveService, protect_week, MODULE
from app.experimental_api import create_research_app
from app.experimental_results import ArtifactBlocked

PREFIX='/api/v1/research/predictive'


@pytest.fixture
def anyio_backend():return 'asyncio'


def high_cells(bundle):
    factory,write,documents,_=bundle
    doc=copy.deepcopy(documents['weeks/2021-01-03.private.json'])
    for row in doc['rows'][:2]:
        row['observed'].update(quantity=7,presence=1,assigned_records=7,quality_counts=dict(approximate=7,provisional=0,verified=0))
        row['predicted']['quantity']=6;row['baseline']['quantity']=6;row['difference']=-1;row['absolute_error']=1;row['confusion']='TP'
    doc['department'].update(observed_total=14,assigned_common_total=14)
    write('weeks/2021-01-03.private.json',doc)
    return factory()


def test_presentation_protects_zero_small_counts_origins_quality_and_complements(bundle):
    reader=high_cells(bundle);service=PredictiveService(reader)
    raw=reader.week(2021,1);safe=service.week(2021,1)
    assert raw['rows'][2]['observed']['quantity']==0
    assert safe['rows'][2]['availability_status']=='privacy_suppressed'
    for row in safe['rows'][2:256]:
        assert all(v is None for v in row['predicted'].values())
        assert all(v is None for k,v in row['observed'].items() if k!='quality_counts')
        assert all(v is None for v in row['observed']['quality_counts'].values())
        assert row['baseline']['quantity'] is None and row['confusion'] is None and row['difference'] is None
    assert all(v is None for v in safe['department'].values())
    assert safe['rows'][-1]['availability_status']=='outside_common_territory'
    assert safe['metrics']['n_comparable']==2 and safe['metrics']['totals']['observed']==14
    assert safe['disclosure']['metrics_scope']=='disclosable_subset_not_full_study'
    assert raw==reader.week(2021,1), 'projection must not mutate archived inputs'
    assert service.week(2021,1,mode='private')['metrics']==raw['metrics']
    # Differences/baselines would reveal suppressed origin counts if left visible.
    doc=copy.deepcopy(raw);doc['rows'][0]['baseline']['quantity']=2
    assert protect_week(doc,'presentation')['rows'][0]['predicted']['quantity'] is None


def test_history_has_no_small_cells_no_subtraction_totals_and_preserves_unknowns(bundle):
    service=PredictiveService(high_cells(bundle))
    safe=service.history('2020-12-27','2021-01-10')
    assert safe['series'][0]['predicted'] is None
    assert safe['series'][1]['observed']==14 and safe['series'][1]['disclosure_status']=='disclosable_subset'
    assert safe['series'][2]['predicted'] is None and safe['series'][2]['observed'] is None
    one=service.history('2020-12-27','2021-01-10','999000002')
    assert all(w['observed'] is None and w['predicted'] is None and w['baseline'] is None for w in one['series'])
    exact=service.history('2020-12-27','2021-01-10',mode='private')
    assert exact['series'][1]['metrics']['n_comparable']==256


def test_snapshot_is_request_scoped_and_tampering_after_first_query_blocks(bundle):
    service=PredictiveService(bundle[0]());service.week(2021,1)
    (bundle[3]/'weeks/2021-01-03.private.json').write_text('{}')
    with pytest.raises(ArtifactBlocked):service.week(2021,1)


def test_climate_context_rejects_future_period_and_never_pretends_predictor_use(bundle):
    reader=bundle[0]();service=PredictiveService(reader)
    assert service.week(2021,1)['climate']['availability_status']=='not_available'
    folder=bundle[3];root=reader.root;week=reader.week(2021,1)
    context=dict(availability_status='available',origin_week=week['origin_week'],origin_end=week['origin_end'],
        period_end=week['target_week'],temperature_mean=20.,humidity_mean=40.,precipitation_total=1.,days=7,
        availability_basis='event_dates_only_arrival_not_accredited',usage='context_only_not_used_by_selected_methods',spatial_support='FICTIONAL single point')
    body=json.dumps(dict(dataset_version=week['dataset_version'],usage=context['usage'],weeks={week['target_week']:context})).encode()
    (folder/'context.private.json').write_bytes(body)
    registry=dict(dataset_version=week['dataset_version'],path=(folder/'context.private.json').relative_to(root).as_posix(),sha256=hashlib.sha256(body).hexdigest())
    body=json.dumps(registry).encode();(folder/'context-registry.private.json').write_bytes(body)
    service=PredictiveService(reader,context_registry=(folder/'context-registry.private.json').relative_to(root),context_sha256=hashlib.sha256(body).hexdigest())
    with pytest.raises(ArtifactBlocked):service.week(2021,1)


@pytest.mark.anyio
async def test_final_routes_exclude_archived_flows_guard_exact_and_safe_projections(bundle):
    service=PredictiveService(high_cells(bundle))
    app=create_research_app(predictive=service,legacy=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234)),base_url='http://127.0.0.1:8765') as client:
        for old in ('spatial/models','spatial/query?date=2024-01-07&model=B','backtest/comparison?year=2021&week=1'):
            assert (await client.get('/api/v1/research/'+old,headers=TRUSTED)).status_code==404
        assert (await client.get(PREFIX+'/calendar')).status_code==403
        calendar=(await client.get(PREFIX+'/calendar',headers=TRUSTED)).json()
        assert calendar['module_version']==MODULE and calendar['training_enabled'] is False
        for kind in ('comparison','predicted','observed','metrics'):
            response=await client.get(PREFIX+f'/{kind}?year=2021&week=1',headers=TRUSTED)
            assert response.status_code==200 and response.json()['disclosure']['mode']=='presentation'
            assert 'PRIVATE_FICTIONAL' not in response.text and 'no-store' in response.headers['cache-control']
        exact=await client.get(PREFIX+'/comparison?year=2021&week=1&disclosure=private',headers=TRUSTED)
        assert exact.json()['metrics']['n_comparable']==256
        assert (await client.get(PREFIX+'/comparison?year=2021&week=1&disclosure=public',headers=TRUSTED)).status_code==400
        assert (await client.get(PREFIX+'/comparison?year=2021&week=1&disclosure=private')).status_code==403
        assert (await client.post(PREFIX+'/train',headers=TRUSTED)).status_code==405
        assert (await client.get(PREFIX+'/calendar',headers={**TRUSTED,'Origin':'https://example.invalid'})).status_code==403
        metadata=(await client.get(PREFIX+'/metadata',headers=TRUSTED)).json()
        assert metadata['climate_usage']=='context_only_not_used_by_selected_methods'
        assert any(x['component']=='A_original_and_B' and x['state']=='archived' for x in metadata['lifecycle'])


def test_public_app_never_registers_final_module(client):
    assert client.get(PREFIX+'/calendar',headers=TRUSTED).status_code==404

