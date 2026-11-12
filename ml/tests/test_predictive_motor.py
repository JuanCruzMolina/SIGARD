"""Fictional weekly grids only; no clinical files or historical artifacts."""
from datetime import date,timedelta
import io
import joblib
import numpy as np
import pandas as pd
import pytest

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.motor_protocol import PROTOCOL,PRESENCE,FEATURES,PRESENCE_BASELINES,COUNT_BASELINES
from sigard_ml.forecasting.motor_data import build_frame
from sigard_ml.forecasting.motor_models import (fit_presence,fit_count,baselines,inner_blocks,purge_training,matrix)
from sigard_ml.forecasting.motor_evaluation import summarize,select_presence,select_counts,paired_interval,top_zones,presence_metrics
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR


def raw_grid(radios=4,weeks=120):
    start=DEFAULT_CALENDAR.week_bounds(2020,1)[0];rows=[]
    for radio in range(1,radios+1):
        for i in range(weeks):
            day=start+timedelta(weeks=i);year,number=DEFAULT_CALENDAR.date_week(day)
            rows.append(dict(radio_id=radio,radio_codigo=f'FICTIONAL-Z{radio:03}',inicio=day,fin=day+timedelta(days=6),
                anio=year,numero=number,cantidad_sigard=float((radio+i)%3==0)*2,
                poblacion_predictor_asof=np.nan,poblacion_contexto_2022=99999,superficie_km2=float(radio),
                clima_historia_hasta=day-timedelta(days=1),temperatura=20.+i%4,humedad=50.,precipitacion=2.,
                temperatura_lag_1=19.,humedad_lag_1=49.,precipitacion_lag_1=1.,temperatura_media_4=20.,
                precipitacion_suma_4=8.,temperatura_historia_previa=18.,humedad_historia_previa=45.,
                precipitacion_media_historia_previa=1.))
    edges=[(i,j) for i in range(1,radios+1) for j in range(1,radios+1) if abs(i-j)==1]
    return pd.DataFrame(rows),edges


@pytest.fixture
def frame():
    raw,edges=raw_grid();return build_frame(raw,edges)


def small_forest(monkeypatch):
    import sigard_ml.forecasting.motor_models as models
    original=models.RandomForestClassifier
    def make(**params):return original(**dict(params,n_estimators=5))
    monkeypatch.setattr(models,'RandomForestClassifier',make)


def test_only_two_families_three_rf_variants_and_h1():
    assert PROTOCOL['horizon_weeks']==1 and len(PROTOCOL['active_ml_families'])==2
    assert len(PRESENCE)==3 and PROTOCOL['count_candidates']==['residual_h1']
    assert PROTOCOL['rf_parameters']['n_estimators']==400
    assert all(not any(x in name for x in ('target','objetivo','radio_id')) for names in FEATURES.values() for name in names)


@pytest.mark.parametrize('name',['B','v3_hurdle','v3_direct_poisson','poisson_boosting','stacking'])
def test_disallowed_methods_cannot_fit(frame,name):
    with pytest.raises(DatasetBlocked):fit_presence(frame,name)


def test_exact_week_lags_and_neighbors_keep_missing_values():
    raw,edges=raw_grid(3,12);missing=raw.inicio.unique()[5]
    raw=raw.loc[~(raw.radio_id.eq(2)&raw.inicio.eq(missing))]
    result=build_frame(raw,edges)
    row=result.loc[result.radio_id.eq(2)&result.origin_week.eq(missing+timedelta(days=7))].iloc[0]
    assert pd.isna(row.count_lag_1) and pd.isna(row.mean_2)
    neighbor=result.loc[result.radio_id.eq(1)&result.origin_week.eq(missing)].iloc[0]
    assert neighbor.neighbor_known_fraction==0 and pd.isna(neighbor.neighbor_count_mean)


def test_future_rows_and_targets_do_not_change_previous_predictors():
    raw,edges=raw_grid(3,261);a=build_frame(raw,edges)
    raw.loc[raw.inicio.ge(date(2024,1,1)),['cantidad_sigard','temperatura','poblacion_predictor_asof']]=[888,999,777]
    b=build_frame(raw,edges)
    mask=a.origin_week.lt(date(2023,12,1));features=list(FEATURES['rf_A_epi_climate'])
    pd.testing.assert_frame_equal(a.loc[mask,features],b.loc[mask,features])
    assert a.loc[a.origin_week.lt(date(2022,1,1)),'poblacion'].isna().all()
    assert a.loc[a.target_year.eq(2025),'target_count'].isna().all()


def test_calendar_53_and_positive_2022_come_from_new_counts(frame):
    assert frame.loc[frame.target_year.eq(2022),'target_presence'].eq(1).any()
    assert frame.loc[frame.anio.eq(2020),'semana_epidemiologica'].max()==53
    assert frame.target_end.eq(frame.origin_week.map(lambda d:d+timedelta(days=13))).all()


def test_duplicate_keys_invalid_graph_future_weather_are_blocked():
    raw,edges=raw_grid(3,10)
    with pytest.raises(DatasetBlocked):build_frame(pd.concat([raw,raw.iloc[:1]]),edges)
    with pytest.raises(DatasetBlocked):build_frame(raw,edges[:-1])
    raw.loc[0,'clima_historia_hasta']=raw.loc[0,'inicio']
    with pytest.raises(DatasetBlocked,match='future_weather'):build_frame(raw,edges)


def test_purge_keeps_whole_weeks_and_mature_labels(frame):
    first=date(2022,1,2);train=purge_training(frame,first)
    assert train.target_end.max()<first-timedelta(weeks=4)
    assert train.groupby('target_week').radio_id.nunique().eq(4).all()


def test_inner_calibration_and_threshold_have_separate_mature_outcomes():
    raw,edges=raw_grid(32,150);train=build_frame(raw,edges).dropna(subset=['target_count'])
    base,calibration,threshold,threshold_ok,cal_ok=inner_blocks(train)
    assert threshold_ok and cal_ok
    assert base.target_end.max()<calibration.origin_week.min()-timedelta(weeks=4)
    assert calibration.target_end.max()<threshold.origin_week.min()-timedelta(weeks=4)


def test_rf_calibration_and_roundtrip_use_training_only(monkeypatch):
    small_forest(monkeypatch)
    raw,edges=raw_grid(32,160);data=build_frame(raw,edges).dropna(subset=['target_count'])
    evaluation=data.loc[data.origin_week.ge(date(2022,9,1))]
    train=purge_training(data,evaluation.origin_week.min())
    model=fit_presence(train,'rf_A_epi_climate')
    scores=model.score(evaluation)
    changed=evaluation.copy();changed['target_count']=999
    assert np.array_equal(scores,model.score(changed))
    assert pd.isna(matrix(train,'rf_A_reference').poblacion).all()
    stream=io.BytesIO();joblib.dump(model,stream);stream.seek(0)
    assert np.array_equal(scores,joblib.load(stream).score(evaluation))
    assert date.fromisoformat(model.metadata['training_last_target_end'])<evaluation.origin_week.min()-timedelta(weeks=4)


def test_insufficient_calibration_keeps_raw_score(monkeypatch,frame):
    small_forest(monkeypatch)
    train=frame.dropna(subset=['target_count']).iloc[:40]
    model=fit_presence(train,'rf_A_reference')
    assert model.calibrator is None and model.threshold==.5
    assert model.metadata['threshold_source']=='fixed_protocol_0.5'


def test_baseline_never_uses_evaluation_labels(frame):
    evaluation=frame.loc[frame.origin_week.ge(date(2021,8,1))];train=purge_training(frame,evaluation.origin_week.min())
    a=baselines(train,evaluation)
    changed=evaluation.copy();changed['target_count']=777
    b=baselines(train,changed)
    assert all(np.array_equal(a[n],b[n]) for n in a)


def test_residual_counts_are_independent_of_RF_scores_and_nonnegative(frame):
    evaluation=frame.loc[frame.origin_week.ge(date(2021,8,1))];train=purge_training(frame,evaluation.origin_week.min())
    model=fit_count(train);reference=baselines(train,evaluation)['count_latest']
    a=model.predict(evaluation,reference)
    changed=evaluation.copy();changed['rf_A_epi_climate']=1.
    assert np.array_equal(a,model.predict(changed,reference)) and (a>=0).all()


def prediction_fixture():
    rows=[]
    for year in (2021,2022,2023):
        for week in range(1,9):
            start=DEFAULT_CALENDAR.week_bounds(year,week)[0]
            for radio in range(1,5):
                y=float((week+radio)%3==0)
                row=dict(radio_id=radio,radio_codigo=f'FICTIONAL-{radio}',origin_week=start-timedelta(days=7),
                    target_week=start,target_year=year,target_count=y,count_origin=0.,tail_limit=2.,week_limit=1.)
                for name in (*PRESENCE,*PRESENCE_BASELINES):
                    row[name]=y if name in PRESENCE[1:] else (.3 if y==0 else .7) if name==PRESENCE[0] else .5
                    row[name+'_threshold']=.5
                for name in COUNT_BASELINES:row[name]=0.
                row['residual_h1']=2.
                rows.append(row)
    return pd.DataFrame(rows)


def test_metrics_selection_and_negative_count_result_are_explicit():
    frame=prediction_fixture();metrics=summarize(frame)
    assert select_presence(frame,metrics)['selected']=='rf_A_epi_no_climate'
    decision=select_counts(frame,metrics)
    assert decision['selected']=='count_latest' and not decision['is_trained_ml']
    assert not decision['promotion_approved']


def test_selection_rejects_previously_observed_2024():
    frame=prediction_fixture();frame['target_year']=2024
    with pytest.raises(DatasetBlocked):select_presence(frame,{})
    with pytest.raises(DatasetBlocked):select_counts(frame,{})


def test_temporal_block_interval_is_reproducible_and_paired():
    frame=prediction_fixture()
    a=paired_interval(frame,PRESENCE[1],PRESENCE[0],'brier')
    b=paired_interval(frame,PRESENCE[1],PRESENCE[0],'brier')
    assert a==b and a['upper95']<0


def test_single_class_metrics_and_tied_zone_ranks_are_honest():
    frame=prediction_fixture().iloc[:4].copy();frame.target_count=0.
    metric=presence_metrics(frame,PRESENCE[0])
    assert metric['roc_auc'] is None and metric['average_precision_pr_auc'] is None
    assert metric['false_negatives']==0
    frame=prediction_fixture().iloc[:4].copy();frame[PRESENCE[0]]=.5
    zones=top_zones(frame,PRESENCE[0])
    assert zones['k']==10 and zones['weekly'][0]['top_k']==4
