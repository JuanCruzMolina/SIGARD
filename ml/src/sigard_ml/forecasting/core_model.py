"""One fixed V3 direct-Poisson strategy, chronological comparison, no search."""
from datetime import timedelta
import hashlib
import io
import json

import joblib
import numpy as np
import pandas as pd
import sklearn
from psycopg2.extras import Json
from threadpoolctl import threadpool_limits

from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.v3 import _regressor, PROTOCOL as V3_PROTOCOL
from sigard_ml.forecasting.core_data import UNIT, TARGET, canonical_hash, read_series

FEATURES=('count_origin','cases_lag_1','cases_lag_2','recent_mean_3','recent_trend',
          'temperature_origin','humidity_origin','precipitation_origin',
          'temperature_mean_4_origin','precipitation_sum_4_origin','season_sin','season_cos')
MODEL_PARAMETERS=dict(V3_PROTOCOL['count_parameters'])
PROTOCOL=dict(version='sigard-predictive-core-protocol-1',strategy='V3_direct_Poisson_only',horizon_weeks=1,
    target=TARGET,spatial_unit=UNIT,features=list(FEATURES),parameters=MODEL_PARAMETERS,
    primary_baseline='latest_closed_count',secondary_baseline='training_mean',
    primary_metric='MAE',complementary_metrics=['RMSE','mean_bias'],
    provisional_minimum_relative_mae_improvement=.05,
    acceptance='at least 5% lower pooled MAE than persistence, no worse pooled RMSE, paired 95% temporal block-bootstrap upper difference <0; minimum 12 evaluation weeks; tutor approval pending',
    development_years=[2020,2021,2023],development_validation_years=[2021,2023],comparison_year=2024,
    split='expanding fixed-year blocks; train target_end < first validation origin; no random split; no cross-gap lags',
    required_history='three consecutive covered counts at t,t-1,t-2; weather at t complete; four-week climate windows optional NaN',
    comparison='chronological retrospective previously examined historical period; not independent',
    final_refit='after comparison closes, all eligible mature labels; never a new validation',
    uncertainty=dict(method='paired moving blocks of contiguous target weeks within each calendar year',
        block_weeks=3,resamples=1000,seed=20261021,interpretation='descriptive conditional uncertainty; no clinical or predictive interval'),
    missing='counts not imputed; optional climate windows NaN; no geography or future values',
    training_is_not_source_ingestion=True,no_hyperparameter_search=True,alerts_enabled=False,
    production_activation=False,model_probability_output=False)


def feature_panel(series):
    if series.inicio.duplicated().any():raise ValueError('duplicate_week_key')
    source={r.inicio:r for r in series.itertuples()}
    rows=[]
    for current in series.itertuples():
        origin=current.inicio
        history=[source.get(origin-timedelta(weeks=i)) for i in range(4)]
        # Do not carry prior seasons or leap over a missing source week.
        counts=[float(r.conteo_experimental) if r is not None and r.cobertura=='experimental_assumed'
                and r.anio==current.anio and pd.notna(r.conteo_experimental) else np.nan for r in history[:3]]
        weather=[r if r is not None and r.dias==7 else None for r in history]
        present=weather[0]
        target=source.get(origin+timedelta(weeks=1))
        row=dict(origin_week=origin,origin_end=current.fin,target_week=origin+timedelta(weeks=1),
            target_end=origin+timedelta(days=13),year=int(current.anio),
            target_count=float(target.conteo_experimental) if target is not None and target.anio==current.anio
                and target.cobertura=='experimental_assumed' and pd.notna(target.conteo_experimental) else np.nan,
            count_origin=counts[0],cases_lag_1=counts[1],cases_lag_2=counts[2],
            recent_mean_3=float(np.mean(counts)) if np.isfinite(counts).all() else np.nan,
            recent_trend=counts[0]-counts[1],temperature_origin=float(present.temperatura) if present else np.nan,
            humidity_origin=float(present.humedad) if present else np.nan,
            precipitation_origin=float(present.precipitacion) if present else np.nan,
            temperature_mean_4_origin=float(np.mean([r.temperatura for r in weather])) if all(r is not None for r in weather) else np.nan,
            precipitation_sum_4_origin=float(sum(r.precipitacion for r in weather)) if all(r is not None for r in weather) else np.nan,
            season_sin=float(np.sin(2*np.pi*(current.numero-1)/current.semanas_anio)),
            season_cos=float(np.cos(2*np.pi*(current.numero-1)/current.semanas_anio)))
        required=(*FEATURES[:5],*FEATURES[5:8])
        row['admissible']=all(np.isfinite(row[name]) for name in required)
        rows.append(row)
    return pd.DataFrame(rows)


def fit(frame):
    if len(frame)<18 or frame.target_count.isna().any() or frame.target_count.sum()<=0:
        raise ValueError('insufficient_positive_mature_training_support')
    estimator=_regressor(MODEL_PARAMETERS,'poisson')
    with threadpool_limits(limits=1):estimator.fit(frame[list(FEATURES)].astype(float),frame.target_count)
    return estimator


def predict(estimator,frame):
    with threadpool_limits(limits=1):values=np.asarray(estimator.predict(frame[list(FEATURES)].astype(float)),dtype=float)
    if not np.isfinite(values).all() or (values<0).any():raise ValueError('invalid_model_output')
    return values


def uncertainty(predictions):
    ordered=predictions.sort_values('target_week').reset_index(drop=True)
    delta=(ordered.model-ordered.target_count).abs()-(ordered.persistence-ordered.target_count).abs()
    blocks=[]
    for start in range(len(ordered)):
        block=[start]
        while len(block)<3 and block[-1]+1<len(ordered):
            a,b=ordered.iloc[block[-1]],ordered.iloc[block[-1]+1]
            if (b.target_week-a.target_week).days!=7 or a.year!=b.year:break
            block.append(block[-1]+1)
        blocks.append(block)
    rng=np.random.default_rng(20261021);sampled=[]
    for _ in range(1000):
        indices=[]
        while len(indices)<len(ordered):indices.extend(blocks[int(rng.integers(len(blocks)))])
        sampled.append(float(delta.iloc[indices[:len(ordered)]].mean()))
    return dict(mean_mae_difference=float(delta.mean()),lower95=float(np.quantile(sampled,.025)),
        upper95=float(np.quantile(sampled,.975)),**PROTOCOL['uncertainty'])


def score(frame,values):
    return {name:count_metrics(frame.target_count,pred) for name,pred in values.items()}


def evaluate_panel(panel):
    usable=panel.loc[panel.admissible&panel.target_count.notna()].copy()
    periods={};outputs=[]
    for year in (*PROTOCOL['development_validation_years'],PROTOCOL['comparison_year']):
        validation=usable.loc[usable.year.eq(year)]
        if validation.empty:
            periods[str(year)]=dict(status='unavailable',reason='no_eligible_evaluation_weeks');continue
        first=min(validation.origin_week)
        train=usable.loc[usable.target_end.lt(first)]
        if len(train)<18 or train.target_count.sum()<=0:
            periods[str(year)]=dict(status='unavailable',reason='insufficient_training_support',train_rows=len(train));continue
        assert max(train.target_end)<first
        estimator=fit(train)
        values=dict(model=predict(estimator,validation),persistence=validation.count_origin.to_numpy(dtype=float),
                    training_mean=np.full(len(validation),float(train.target_count.mean())))
        result=validation[['origin_week','target_week','target_count','year']].copy()
        for name,pred in values.items():result[name]=pred
        result['stage']='comparison_previously_observed' if year==2024 else 'development_walk_forward'
        outputs.append(result)
        periods[str(year)]=dict(status='evaluated',stage=result.stage.iloc[0],train_rows=len(train),evaluation_rows=len(validation),
            train_first_target=str(min(train.target_week)),train_last_target_end=str(max(train.target_end)),
            first_origin=str(first),last_target=str(max(validation.target_week)),metrics=score(validation,values),
            observed_max=float(validation.target_count.max()),training_max=float(train.target_count.max()))
    if not outputs:raise ValueError('no_supported_temporal_evaluation')
    predictions=pd.concat(outputs,ignore_index=True)
    comparison=predictions.loc[predictions.stage.eq('comparison_previously_observed')]
    if comparison.empty:raise ValueError('comparison_not_supported')
    pooled=score(comparison,{name:comparison[name] for name in ('model','persistence','training_mean')})
    boot=uncertainty(comparison)
    relative=1-pooled['model']['mae']/pooled['persistence']['mae'] if pooled['persistence']['mae']>0 else None
    passed=bool(relative is not None and relative>=.05 and pooled['model']['rmse']<=pooled['persistence']['rmse']
                and boot['upper95']<0 and len(comparison)>=12)
    report=dict(protocol=PROTOCOL,periods=periods,comparison=pooled,relative_mae_improvement=relative,
        paired_uncertainty=boot,provisional_criterion_met=passed,independent_test=False,
        academic_approval=False,territorial_prioritization_supported=False,
        rows=dict(panel=len(panel),eligible=len(usable),unknown_targets=int(panel.target_count.isna().sum()),
                  inadmissible_history=int((~panel.admissible).sum())),
        feature_missingness={name:int(usable[name].isna().sum()) for name in FEATURES},
        final_fit_rows=len(usable),final_fit_last_target_end=str(max(usable.target_end)))
    return report,predictions,usable


def train_and_register(conn,*,dataset_version,model_version,protocol_sha256):
    if protocol_sha256!=canonical_hash(PROTOCOL):raise ValueError('protocol_must_be_frozen_before_fit')
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM analytics.modelo_predictivo WHERE componente='principal'")
        if cur.fetchone():raise ValueError('single_candidate_already_registered')
        cur.execute('SELECT entrada_sha256 FROM analytics.dataset_predictivo WHERE version=%s',(dataset_version,))
        found=cur.fetchone()
        if not found:raise ValueError('unknown_dataset_version')
        input_sha=found[0]
        cur.execute('SELECT lotes_vigentes FROM analytics.disponibilidad_dataset_predictivo WHERE version=%s',(dataset_version,))
        current=cur.fetchone()
        if not current or not current[0]:raise ValueError('dataset_contains_withdrawn_source')
    panel=feature_panel(read_series(conn,dataset_version))
    report,predictions,train=evaluate_panel(panel)
    # Comparison is now closed. No parameters/labels/features change in the final fit.
    estimator=fit(train)
    metadata=dict(features=list(FEATURES),spatial_unit=UNIT,target=TARGET,horizon_weeks=1,
        dataset_sha256=input_sha,protocol_sha256=protocol_sha256,sklearn_version=sklearn.__version__,
        fit_last_target_end=str(max(train.target_end)),fit_rows=len(train),
        training_matrix_sha256=canonical_hash(train[['origin_week','target_week','target_count',*FEATURES]].to_dict('records')),
        final_refit_not_evaluation=True,model_version=model_version,relative_activity_indicator=None,
        reason_no_indicator='single_territorial_unit; no spatial rank or outbreak probability',
        prior_A_B_V1_V2_V3_frozen=True)
    stream=io.BytesIO();joblib.dump(estimator,stream,compress=3);payload=stream.getvalue()
    sha=hashlib.sha256(payload).hexdigest()
    restored=joblib.load(io.BytesIO(payload))
    if not np.allclose(predict(estimator,train),predict(restored,train),rtol=0,atol=0):raise ValueError('serialization_mismatch')
    state='candidate_retrospective' if report['provisional_criterion_met'] else 'candidate_failed'
    with conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO analytics.modelo_predictivo(version,componente,dataset_version,estado,artefacto,artefacto_sha256,protocolo,metadatos,metricas)
                VALUES(%s,'principal',%s,%s,%s,%s,%s,%s,%s)''',
                (model_version,dataset_version,state,payload,sha,Json(PROTOCOL),Json(metadata),Json(report)))
    return dict(report=report,metadata=metadata,artifact_sha256=sha,state=state),predictions,panel,payload


def infer(conn,*,model_version,origin,mode='operational'):
    if mode not in ('operational','retrospective'):raise ValueError('invalid_inference_mode')
    result=dict(model_version=model_version,origin_week=str(origin),target_week=str(origin+timedelta(weeks=1)),
        horizon_weeks=1,spatial_unit=UNIT,unit_code='capital',target=TARGET,
        expected_count=None,relative_activity=None,probability=None,alerts_enabled=False,
        retrospective=mode=='retrospective',status='prediction_unavailable',reasons=[])
    with conn.cursor() as cur:
        cur.execute('SELECT dataset_version,estado,artefacto,artefacto_sha256,metadatos,protocolo FROM analytics.modelo_predictivo WHERE version=%s',(model_version,))
        registered=cur.fetchone()
    if not registered:result['reasons'].append('unknown_model_version');return result
    version,state,payload,sha,metadata,protocol=registered
    with conn.cursor() as cur:
        cur.execute('SELECT lotes_vigentes FROM analytics.disponibilidad_dataset_predictivo WHERE version=%s',(version,))
        live=cur.fetchone()
    if not live or not live[0]:result['reasons'].append('dataset_source_batch_withdrawn')
    if (metadata.get('features')!=list(FEATURES) or protocol!=PROTOCOL or metadata.get('spatial_unit')!=UNIT
            or metadata.get('target')!=TARGET or metadata.get('horizon_weeks')!=1
            or metadata.get('sklearn_version')!=sklearn.__version__):
        result['reasons'].append('incompatible_model_contract')
    if state=='candidate_failed':result['reasons'].append('model_did_not_meet_baseline_criterion')
    series=read_series(conn,version)
    frame=feature_panel(series)
    selected=frame.loc[frame.origin_week.eq(origin)]
    if origin.weekday()!=6:result['reasons'].append('origin_must_be_argentine_epi_week_start')
    if selected.empty or not bool(selected.iloc[0].admissible):result['reasons'].append('fundamental_features_or_coverage_missing')
    if date_from_iso(metadata['fit_last_target_end'])>origin+timedelta(days=6):result['reasons'].append('model_trained_after_prediction_origin')
    if mode=='operational':
        recent=series.loc[series.inicio.isin([origin-timedelta(weeks=i) for i in range(3)])]
        if len(recent)!=3 or not recent.disponibilidad_verificada.all():result['reasons'].append('source_arrival_and_coverage_not_verified_at_origin')
        if len(recent)!=3 or recent.clima_disponible_desde.isna().any():result['reasons'].append('historical_weather_not_accredited_for_realtime_inference')
        from datetime import datetime,time,timezone
        cutoff=datetime.combine(origin+timedelta(days=7),time.min,tzinfo=timezone.utc)+timedelta(hours=3)
        for col,reason in [('disponible_desde','source_arrival_after_origin'),('clima_disponible_desde','weather_arrival_after_origin')]:
            if any(value is not None and pd.notna(value) and value>=cutoff for value in recent[col]):result['reasons'].append(reason)
        # A snapshot scenario is not an operational coverage declaration.
        result['reasons'].append('retrospective_candidate_not_activated_for_production')
    if not result['reasons']:
        if hashlib.sha256(bytes(payload)).hexdigest()!=sha:raise ValueError('registered_artifact_hash_mismatch')
        estimator=joblib.load(io.BytesIO(bytes(payload)))
        result.update(status='available_retrospective_candidate',expected_count=float(predict(estimator,selected)[0]))
    result['dataset_version']=version;result['validation_state']=state
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO analytics.prediccion_predictiva(modelo_version,origen,modo,resultado) VALUES(%s,%s,%s,%s)',
                (model_version,origin,mode,Json(result)))
    return result


def date_from_iso(value):
    from datetime import date
    return date.fromisoformat(value)
