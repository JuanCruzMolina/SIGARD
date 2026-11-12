"""Generated fixtures only. No estimators, fitting, private data or database."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pandas as pd
import pytest

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.candidate_release import (
    CandidateRelease, CANDIDATES, DATASET, POLICY, VERSION, FEATURES,
    validate_predictions, entry, checked_path,
)


def fixture_rows():
    return pd.DataFrame([dict(radio_id=i, target_week=date(2021, 1, 3), origin_week=date(2020, 12, 27),
        target_count=y, block='fictional', rf_A_epi_climate=score, rf_A_epi_climate_threshold=.3,
        presence_seasonal=.1, presence_seasonal_threshold=.5,
        residual_h1=amount, count_latest=0., count_training_mean=.2)
        for i, y, score, amount in [(1, 0, .4, .25), (2, 2, .2, 1.75)]])


def fixture_models():
    return [dict(block='fictional', method=m, state='experimental_evaluated',
        fit_last_target_end='2020-11-28', features=list(FEATURES[m]), threshold=.3 if m.startswith('rf') else None,
        calibrated=False, model_version='fictional-'+m) for m in CANDIDATES.values()]


@pytest.fixture
def release(tmp_path):
    frame=fixture_rows();models=fixture_models()
    artifact=tmp_path/'fictional-model.bin';artifact.write_bytes(b'not an executable estimator')
    for model in models:model['artifact']=entry(tmp_path,artifact)
    predictions=tmp_path/'fictional.parquet';frame.to_parquet(predictions,index=False)
    evidence=tmp_path/'evidence.json';evidence.write_text('{}')
    doc=dict(version=VERSION,dataset_version=DATASET,data_policy_version=POLICY,
        candidates=CANDIDATES,horizon_weeks=1,operational_enabled=False,promotion_approved=False,
        audit=entry(tmp_path,evidence),sources={'all-predictions.private.parquet':entry(tmp_path,predictions)},
        models=models,radio_ids=[1,2],target_weeks=['2021-01-03'],code_sha256={},
        evaluation_type='event_time_retrospective_reconstruction',limitations=['fictional_test_only'])
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(doc))
    return CandidateRelease(tmp_path,'manifest.json',entry(tmp_path,manifest)['sha256']),doc,tmp_path


def test_valid_reused_scores_counts_references_and_year_transition(release):
    reader,_,_=release
    presence=reader.week('2021-01-03','presence');quantity=reader.week('2021-01-03','quantity')
    assert presence['origin_week']=='2020-12-27' and presence['target_epi_week']==1
    assert presence['state']=='experimental_evaluated' and not presence['operational_enabled']
    assert presence['reference_state']=='reference_selected'
    assert presence['rows'][0]['predicted_presence']==1 and presence['rows'][0]['observed']==0
    assert quantity['rows'][1]['predicted']==1.75 and quantity['rows'][1]['historical_mean']==.2
    assert reader.week('2021-01-03','quantity')==quantity


@pytest.mark.parametrize('target,reason',[('2020-12-27','insufficient_training_support'),
    ('2025-01-05','outside_coverage'),('2026-01-04','outside_coverage'),('2022-01-02','saved_prediction_not_available')])
def test_unavailable_never_fabricates_zero(release,target,reason):
    result=release[0].week(target,'quantity')
    assert result['state']=='blocked' and result['reason']==reason and result['rows']==[]
    if target=='2020-12-27':assert result['target_epi_week']==53


@pytest.mark.parametrize('mutation', ['future_fit','wrong_horizon','duplicates','negative','unknown',
    'bad_score','wrong_features','operational','missing_radio','threshold'])
def test_invalid_saved_results_block(mutation):
    frame=fixture_rows();models=deepcopy(fixture_models())
    if mutation=='future_fit':models[0]['fit_last_target_end']='2020-12-01'
    elif mutation=='wrong_horizon':frame.loc[0,'origin_week']+=timedelta(days=7)
    elif mutation=='duplicates':frame=pd.concat([frame,frame.iloc[:1]],ignore_index=True)
    elif mutation=='negative':frame.loc[0,'residual_h1']=-1
    elif mutation=='unknown':frame.loc[0,'target_count']=float('nan')
    elif mutation=='bad_score':frame.loc[0,'rf_A_epi_climate']=1.1
    elif mutation=='wrong_features':models[0]['features']=['future_label']
    elif mutation=='operational':models[0]['state']='operational_approved'
    elif mutation=='missing_radio':frame=frame.iloc[:1]
    elif mutation=='threshold':frame.loc[0,'rf_A_epi_climate_threshold']=.9
    with pytest.raises(DatasetBlocked):validate_predictions(frame,models,[1,2])


@pytest.mark.parametrize('file',['fictional-model.bin','fictional.parquet','evidence.json','manifest.json'])
def test_tampered_evidence_blocks_even_after_successful_read(release,file):
    reader,_,root=release
    reader.week('2021-01-03','presence')
    with (root/file).open('ab') as stream:stream.write(b'tampered')
    with pytest.raises(DatasetBlocked):reader.week('2021-01-03','presence')


def test_unknown_capability_and_escape_are_rejected(release):
    with pytest.raises(DatasetBlocked):release[0].week('2021-01-03','hurdle')
    with pytest.raises(DatasetBlocked):checked_path(release[2],'../secret')


@pytest.mark.parametrize('key,value',[('operational_enabled',True),('promotion_approved',True),
    ('horizon_weeks',2),('data_policy_version','old_policy')])
def test_even_repinned_manifest_cannot_grant_promotion_or_change_contract(release,key,value):
    _,doc,root=release
    doc[key]=value
    path=root/'unapproved.json';path.write_text(json.dumps(doc))
    reader=CandidateRelease(root,path.name,entry(root,path)['sha256'])
    with pytest.raises(DatasetBlocked):reader.week('2021-01-03','presence')
