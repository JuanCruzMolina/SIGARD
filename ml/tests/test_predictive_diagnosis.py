"""Generated fixtures only; no private reads, geography or estimator fitting."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('diagnose_predictive_v3', (Path(__file__).resolve().parents[2]/'tools'/'diagnose_predictive_v3.py'))
diagnosis = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = diagnosis
spec.loader.exec_module(diagnosis)
experiment_spec = importlib.util.spec_from_file_location('experiment_predictive_v3_recency', (Path(__file__).resolve().parents[2]/'tools'/'experiment_predictive_v3_recency.py'))
experiment = importlib.util.module_from_spec(experiment_spec)
experiment_spec.loader.exec_module(experiment)


def fixture_frame():
    rows=[]
    for i in range(4):
        for j in range(3):
            target = date(2020,1,5)+timedelta(weeks=i)
            row = dict(radio_id=f'fictional-{j}', origin_week=target-timedelta(weeks=1),
                       target_week=target, target_end=target+timedelta(days=6),
                       target_count=float(j), partition='train', predictor_admissible=True)
            row.update({feature:float(i+j) for feature in diagnosis.FEATURES})
            for feature in diagnosis.GROUPS['climate']+diagnosis.GROUPS['season']:
                row[feature]=float(i)
            rows.append(row)
    return pd.DataFrame(rows)


def test_errors_and_unknowns_are_distinct_from_zero():
    assert diagnosis.errors([0,2],[1,1]) == dict(n=2,mae=1.,rmse=1.,bias=0.,observed_mean=1.,predicted_mean=1.)
    assert diagnosis.describe([0,None,2])['missing']==1
    assert diagnosis.describe([0,None,2])['zero_fraction']==.5
    with pytest.raises(AssertionError):
        diagnosis.errors([0,np.nan],[0,0])


def test_joint_weekly_permutation_preserves_shared_climate():
    frame=fixture_frame()
    result=diagnosis.permute_group(frame,diagnosis.GROUPS['climate'],'climate',np.random.default_rng(7))
    assert result.groupby('target_week').temperature_origin.nunique().eq(1).all()
    assert not result.temperature_origin.equals(frame.temperature_origin)
    assert result.target_count.equals(frame.target_count)
    assert result.count_origin.equals(frame.count_origin)


def test_within_week_permutation_preserves_distribution_and_labels():
    frame=fixture_frame()
    result=diagnosis.permute_group(frame,diagnosis.GROUPS['count_history'],'count_history',np.random.default_rng(7))
    for week, group in frame.groupby('target_week'):
        assert sorted(group.count_origin)==sorted(result.loc[result.target_week.eq(week),'count_origin'])
    assert result.target_count.equals(frame.target_count)


def test_join_rejects_changed_labels_and_duplicate_keys():
    frame=fixture_frame()
    pred=frame[['radio_id','origin_week','target_week','target_count']].copy()
    assert len(diagnosis.join_panel(pred,frame))==len(frame)
    pred.loc[0,'target_count']=99
    with pytest.raises(AssertionError):
        diagnosis.join_panel(pred,frame)
    with pytest.raises(AssertionError):
        diagnosis.join_panel(pd.concat([pred,pred]),frame)


def test_predictor_shift_keeps_missing_values():
    frame=fixture_frame()
    other=frame.copy()
    other['count_origin']=np.nan
    result=diagnosis.shift_profile(frame,other)
    assert result['count_origin']['comparison_missing']==1.
    assert result['count_origin']['outside_development_range'] is None


def test_recency_weights_use_calendar_time_and_normalize_regularization_scale():
    frame=fixture_frame().iloc[[0,3]].copy()
    frame.loc[frame.index[1],'target_end']=frame.iloc[0].target_end+timedelta(weeks=13)
    weights=experiment.recency_weights(frame)
    assert weights.mean()==pytest.approx(1.)
    assert weights[1]/weights[0]==pytest.approx(2.)
    changed=frame.copy()
    changed['target_count']=99.
    np.testing.assert_array_equal(weights,experiment.recency_weights(changed))


def test_training_window_purges_labels_and_rejects_test_partition():
    frame=fixture_frame()
    validation=frame.loc[frame.target_week.eq(frame.target_week.max())]
    train=experiment.training_window(frame,validation)
    assert train.target_end.max()<validation.origin_week.min()
    frame.loc[0,'partition']='test'
    with pytest.raises(AssertionError):
        experiment.training_window(frame,validation)


def test_candidate_cannot_pass_with_only_one_persistence_beaten(monkeypatch):
    frame=fixture_frame()
    frame['target_count']=2.
    frame['fold']=np.arange(len(frame))//4
    frame['tail_threshold']=2.
    frame['high_week_threshold']=1.
    frame[experiment.NAME]=2.1
    for method in experiment.SPECIFICATION['comparators']:
        frame[method]=3.
    frame[experiment.BASELINES[1]]=2.
    monkeypatch.setattr(experiment,'block_interval',lambda *args:dict(intervals=dict(mae=[-.5,-.1])))
    result=experiment.evaluate(frame)
    assert not result['retain_candidate']
    assert result['gates'][0]['mae']
    assert not result['gates'][1]['mae']
