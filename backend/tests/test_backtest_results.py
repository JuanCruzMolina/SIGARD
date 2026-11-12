"""Abstract generated polygons/records exclusively; no historical project data."""
import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from app.backtest_results import BacktestResults, CONTEXT, EVALUATION, METHODS, SCHEMA, metrics
from app.experimental_api import create_research_app
from app.experimental_results import ArtifactBlocked, InvalidDate
from app.backtest_api import PREFIX

TRUSTED={'Origin':'http://127.0.0.1:5173','X-Sigard-Research':'local-read'}


@pytest.fixture
def bundle(tmp_path):
    base=Path('data/interim/official/FICTIONAL-BACKTEST');folder=tmp_path/base;folder.mkdir(parents=True)
    context=dict(schema_version=SCHEMA,dataset_version='FICTIONAL-DATA',campaign_version='FICTIONAL-CAMPAIGN',
                 data_policy_version='FICTIONAL-2022-POSITIVE',territory_version='FICTIONAL-POLYGONS')
    radios=[f'999{i:06}' for i in range(263)]
    files={};documents={}
    def write(name,value):
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
        body=json.dumps(value).encode();path.write_bytes(body);files[name]=hashlib.sha256(body).hexdigest();documents[name]=value
    weeks=[]
    for i in range(3):
        start=date(2020,12,27)+timedelta(weeks=i);status='insufficient_training_support' if i==0 else 'available'
        item=dict(target_year=2020 if i==0 else 2021,target_epi_week=53 if i==0 else i,
                  target_week=str(start),target_end=str(start+timedelta(days=6)),origin_week=str(start-timedelta(days=7)),
                  origin_end=str(start-timedelta(days=1)),availability_status=status,
                  unavailable_reason='warmup' if i==0 else None)
        weeks.append(item);rows=[]
        for n,radio in enumerate(radios):
            common=n<256;available=common and i>0;y=1 if n==0 and i==1 else 0
            score=.8 if n<2 else .1;p=int(score>=.5)
            row=dict(radio_id=radio,common_mask=common,availability_status=status if common else 'outside_common_territory',
                unavailable_reason=None if available else 'FICTIONAL unavailable',territorial_quality='approximate' if y else 'no_assigned_record',
                coverage_status='covered_observed' if y else 'covered_assumed_zero',zero_provenance=None if y else 'project_owner_declared_coverage_2020_2024',
                predicted=dict(presence_score=score if available else None,presence=p if available else None,quantity=.75 if available else None),
                observed=dict(quantity=y if common else None,presence=y if common else None,assigned_records=y,
                    quality_counts=dict(approximate=y,provisional=0,verified=0)),
                baseline=dict(quantity=.75 if available else None),presence_threshold=.5 if available else None,
                confusion=('TP' if p and y else 'FP' if p else 'FN' if y else 'TN') if available else None,
                difference=.75-y if available else None,absolute_error=abs(.75-y) if available else None,
                PRIVATE_FICTIONAL_NAME='PRIVATE_FICTIONAL_DO_NOT_EXPOSE')
            rows.append(row)
        doc=dict(**context,**item,evaluation_type=EVALUATION,fit_last_target_end='2020-11-21' if i else None,
                 model_version=dict(presence='FICTIONAL/presence',quantity='FICTIONAL/count') if i else dict(presence=None,quantity=None),
                 department=dict(observed_total=int(i==1),assigned_common_total=int(i==1),assigned_masked_total=0,unassigned_total=0,reconciled=True),rows=rows)
        write(f'weeks/{start}.private.json',doc)
    write('calendar.private.json',dict(**context,calendar_version='ar-snvs-2020-2026-v1',weeks=weeks,radio_ids=radios))
    features=[]
    for n,radio in enumerate(radios):
        x,y=10+n%20/10,10+n//20/10
        features.append(dict(type='Feature',properties=dict(radio_id=radio,common_mask=n<256,PRIVATE_FICTIONAL_NAME='PRIVATE_FICTIONAL_DO_NOT_EXPOSE'),
            geometry=dict(type='Polygon',coordinates=[[[x,y],[x+.01,y],[x+.01,y+.01],[x,y+.01],[x,y]]])))
    write('geometry.private.json',dict(type='FeatureCollection',features=features))
    write('metadata.private.json',dict(**context,evaluation_type=EVALUATION,selected_methods=METHODS,
        method_kinds=dict(presence='statistical_reference',quantity='statistical_reference'),
        method_labels=dict(presence='FICTIONAL presence',quantity='FICTIONAL count'),arrival_availability='not_accredited',
        scores='experimental_uncalibrated_not_health_probabilities',operational_enabled=False,alerts_enabled=False,
        coverage_basis='project_owner_declared_coverage_2020_2024',included_2022_policy='FICTIONAL positive original classifications preserved',
        territory_radios=263,common_radios=256,dataset_sha256='f'*64,protocol_sha256='e'*64,horizon_weeks=1,purge_weeks=4,
        reference_is_not_trained_ml=True,PRIVATE_FICTIONAL_NAME='PRIVATE_FICTIONAL_DO_NOT_EXPOSE'))
    def adapter():
        manifest=dict(**context,local_read_authorized=True,selected_methods=METHODS,training_performed=False,files=files)
        body=json.dumps(manifest).encode();(folder/'manifest.private.json').write_bytes(body)
        registry=dict(local_read_authorized=True,manifest_path=(base/'manifest.private.json').as_posix(),manifest_sha256=hashlib.sha256(body).hexdigest())
        body=json.dumps(registry).encode();(folder/'registry.private.json').write_bytes(body)
        return BacktestResults(base/'registry.private.json',hashlib.sha256(body).hexdigest(),root=tmp_path)
    return adapter,write,documents,folder


def test_projection_metrics_history_unknowns_and_reproducibility(bundle):
    adapter=bundle[0]();result=adapter.week('2021','1')
    assert result==adapter.week(2021,1) and result['metrics']['n_comparable']==256
    assert result['metrics']['totals']==dict(predicted=192.,observed=1,baseline=192.)
    assert result['metrics']['presence']['confusion']==dict(TP=1,FP=1,FN=0,TN=254)
    assert result['rows'][0]['difference']==-.25 and result['rows'][0]['absolute_error']==.25
    assert result['rows'][-1]['observed']['quantity'] is None
    assert 'PRIVATE_FICTIONAL_DO_NOT_EXPOSE' not in json.dumps(result)
    assert 'PRIVATE_FICTIONAL_DO_NOT_EXPOSE' not in json.dumps(adapter.geometry())
    assert 'PRIVATE_FICTIONAL_DO_NOT_EXPOSE' not in json.dumps(adapter.metadata())
    assert len(adapter.geometry()['features'])==263
    warmup=adapter.week(2020,53)
    assert warmup['target_week']=='2020-12-27' and warmup['target_end']=='2021-01-02'
    assert warmup['rows'][0]['observed']['quantity']==0 and warmup['rows'][0]['predicted']['quantity'] is None
    zero=adapter.week(2021,2)['rows'][0]
    assert zero['observed']['quantity']==0 and zero['zero_provenance']
    history=adapter.history('2020-12-27','2021-01-10')
    assert history['series'][0]['predicted'] is None and history['series'][0]['observed']==0
    assert history['series'][1]['observed']==1 and history['metrics']['n_comparable']==512
    assert history['by_year']['2020']['n_comparable']==0
    one=adapter.week(2021,1,'999000000')
    assert len(one['rows'])==1 and one['metrics']['totals']['observed']==1
    masked=adapter.history('2020-12-27','2021-01-10','999000262')['series'][1]
    assert masked['observed'] is None and masked['availability_status']=='outside_common_territory'
    with pytest.raises(InvalidDate):adapter.week(2021,53)
    with pytest.raises(InvalidDate):adapter.history('2021-01-10','2020-12-27')


@pytest.mark.parametrize('mutation',['cutoff','negative','confusion','universe','department','score'])
def test_inconsistent_compiled_results_block_even_if_resigned(bundle,mutation):
    adapter,write,documents,_=bundle;name='weeks/2021-01-03.private.json';value=copy.deepcopy(documents[name])
    if mutation=='cutoff':value['fit_last_target_end']='2021-01-02'
    elif mutation=='negative':value['rows'][0]['observed']['quantity']=-1
    elif mutation=='confusion':value['rows'][0]['confusion']='TN'
    elif mutation=='universe':value['rows'].pop()
    elif mutation=='department':value['department']['observed_total']=2
    else:value['rows'][0]['predicted']['presence_score']=1.1
    write(name,value)
    with pytest.raises(ArtifactBlocked):adapter().week(2021,1)


def test_changed_bytes_or_manifest_do_not_fallback(bundle):
    adapter=bundle[0]();path=bundle[3]/'weeks/2021-01-03.private.json';path.write_text('{}')
    with pytest.raises(ArtifactBlocked):adapter.week(2021,1)
    (bundle[3]/'manifest.private.json').write_text('{}')
    with pytest.raises(ArtifactBlocked):adapter.catalog()


@pytest.fixture
def anyio_backend():return 'asyncio'


@pytest.mark.anyio
async def test_protected_api_read_only_privacy_validation_and_consistency(bundle):
    app=create_research_app(None,bundle[0]())
    transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234))
    async with httpx.AsyncClient(transport=transport,base_url='http://127.0.0.1:8765') as client:
        for endpoint in ('calendar','geometry','metadata','comparison?year=2021&week=1','predicted?year=2021&week=1',
                         'observed?year=2021&week=1','metrics?year=2021&week=1','history?start=2020-12-27&end=2021-01-10'):
            path=PREFIX+'/'+endpoint
            assert (await client.get(path)).status_code==403
            response=await client.get(path,headers=TRUSTED)
            assert response.status_code==200 and response.headers['cache-control']=='no-store, private'
            assert 'PRIVATE_FICTIONAL_DO_NOT_EXPOSE' not in response.text and str(bundle[3]) not in response.text
            assert (await client.post(path,headers=TRUSTED)).status_code==405
        result=(await client.get(PREFIX+'/comparison?year=2021&week=1',headers=TRUSTED)).json()
        observed=(await client.get(PREFIX+'/observed?year=2021&week=1',headers=TRUSTED)).json()
        assert [r['observed'] for r in observed['rows']]==[r['observed'] for r in result['rows']]
        for suffix in ('?year=2021&week=53','?year=2021&week=1&path=secret','?year=2021&week=1&week=2'):
            assert (await client.get(PREFIX+'/comparison'+suffix,headers=TRUSTED)).status_code==400
        assert (await client.get(PREFIX+'/comparison?year=2021&week=1&radio=secret',headers=TRUSTED)).status_code==404
        for headers in ({**TRUSTED,'Origin':'https://example.invalid'},{**TRUSTED,'X-Forwarded-For':'127.0.0.1'},{**TRUSTED,'Host':'evil.invalid'}):
            assert (await client.get(PREFIX+'/calendar',headers=headers)).status_code==403
        (bundle[3]/'weeks/2021-01-03.private.json').write_text('{}')
        response=await client.get(PREFIX+'/comparison?year=2021&week=1',headers=TRUSTED)
        assert response.status_code==503 and response.json()=={'detail':'backtest_artifacts_blocked'}


def test_http_runtime_has_no_training_database_or_deserialization_imports():
    import ast
    root=Path(__file__).resolve().parents[1]/'app'
    for name in ('backtest_api.py','backtest_results.py'):
        tree=ast.parse((root/name).read_text())
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(m.split('.')[0] in {'sklearn','psycopg2','joblib','pickle','sigard_ml'} for m in imports)


def test_backtest_not_installed_in_public_app(client):
    assert client.get(PREFIX+'/calendar',headers=TRUSTED).status_code==404
    assert '/research/backtest' not in json.dumps(client.get('/openapi.json').json())
