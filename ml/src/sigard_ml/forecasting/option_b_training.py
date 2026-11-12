"""Authorized local A/B/V3 research: PostgreSQL inputs, registry and inference.

This is a new data contract, not a waiver of historical reproduction checks.
Algorithms/parameters come from the frozen implementations. No public activation.
"""
from datetime import date, timedelta
import hashlib
import io
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from psycopg2.extras import Json, execute_values

from sigard_ml.data_access import DatasetBlocked, MLRepository
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.option_b_data import ZERO_POLICY, json_dump
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
from sigard_ml.official.spatial_ml.historical_expansion import FEATURES as AB_FEATURES, ab_matrix, fit_ab
from sigard_ml.official.spatial_ml.research_training import classification_metrics
from sigard_ml.forecasting.v3 import PROTOCOL as V3_PROTOCOL, FEATURES as V3_FEATURES


PROTOCOL = dict(version='sigard-postgres-option-b-research-1',zero_policy=ZERO_POLICY,
    authorization_basis='project_owner_declared_provision',research_training_authorized=True,
    initial_training_years=[2020,2021,2022],validation_year=2023,holdout_year=2024,
    later_years='conditional dataset inclusion only; no changed holdout or automatic refit',
    split='whole epidemiological weeks; train target_end strictly before first evaluated origin; horizon purge',
    test_status='not used in these fits; previously examined research history, not independent external evidence',
    ab_parameters=dict(RF_PARAMETERS),ab_features=AB_FEATURES,ab_threshold=.5,
    ab_baselines=['training_prevalence','lag_1_presence_or_training_prevalence'],
    ab_primary_metric='Brier',ab_baseline_comparison='report Brier/AP/F1 separately; no scientific promotion from one metric',
    ab_minimum_training_weeks=18,ab_minimum_classes=2,
    v3_protocol=V3_PROTOCOL,v3_features=list(V3_FEATURES),v3_horizons=[1,2,4],
    v3_default_research_method='best_ml_selected_in_development; baseline gates reported, no operational promotion',
    sensitivity='same pre-fixed splits and algorithms for approximate_included versus provisional_verified; labels differ, comparison descriptive',
    geography='stored selected candidate, not residence verification; no new geocoding',
    operational_enabled=False,alerts_enabled=False,scientifically_validated=False,
    no_tabular_operational_input=True,no_training_on_ingestion=True)


def feature_code_hashes():
    root = Path(__file__).resolve().parents[4]
    names = ['ml/src/sigard_ml/data_access/postgres.py','ml/src/sigard_ml/forecasting/option_b_data.py',
        'ml/src/sigard_ml/forecasting/v3.py','ml/src/sigard_ml/forecasting/v2.py',
        'ml/src/sigard_ml/official/calendar_rules.py','ml/src/sigard_ml/official/spatial_ml/historical_expansion.py',
        'ml/src/sigard_ml/official/spatial_ml/experiment_protocol.py']
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}


def prepared(repo, family, dataset_version, *, horizon=1):
    from sigard_ml.forecasting.training import partition
    frame = repo.research_frame(family,dataset_version,horizon=horizon)
    meta = frame.attrs['provenance']
    if canonical_hash(meta['protocolo']) != canonical_hash(PROTOCOL):
        raise DatasetBlocked('research_protocol_not_the_fixed_initial_protocol')
    if family != 'V3':
        frame['radio_id'] = frame.radio_censal
        frame['origin_week'] = frame.fecha_inicio_semana
        frame['target_week'] = frame.fecha_inicio_semana_objetivo
    frame['partition'] = partition(frame,DEFAULT_CALENDAR.week_bounds(2023,1)[0],DEFAULT_CALENDAR.week_bounds(2024,1)[0])
    # Conditional 2025/2026 data cannot silently enlarge the held-out test or fit.
    last = DEFAULT_CALENDAR.week_bounds(2024,next(y.weeks for y in DEFAULT_CALENDAR.years if y.year==2024))[1]
    frame.loc[frame.target_end.gt(last),'partition'] = 'outside_fixed_evaluation'
    frame.attrs['provenance'] = meta
    return frame


def _usable(frame, family, part):
    target = 'target_count' if family == 'V3' else 'objetivo_semana_siguiente'
    mask = frame.partition.isin(part) & frame[target].notna()
    if family == 'V3':
        mask &= frame.predictor_admissible
    return frame.loc[mask].copy()


def _check_temporal(train, evaluation):
    if train.empty or evaluation.empty or max(train.target_end) >= min(evaluation.origin_week):
        raise DatasetBlocked('temporal_leakage_or_empty_partition')


def _class_scores(estimator, frame, family):
    values = estimator.predict_proba(ab_matrix(frame,family))[:,list(estimator.classes_).index(1)]
    if not np.isfinite(values).all() or ((values<0)|(values>1)).any():
        raise DatasetBlocked('invalid_classification_output')
    return values


def _class_metrics(frame, values):
    return classification_metrics(frame.objetivo_semana_siguiente.to_numpy(int),values,.5)


def _class_comparison(estimator, train, evaluation, family):
    p = _class_scores(estimator,evaluation,family)
    prior = np.full(len(evaluation),float(train.objetivo_semana_siguiente.mean()))
    metrics = dict(model=_class_metrics(evaluation,p),training_prevalence=_class_metrics(evaluation,prior))
    if family == 'B':
        lag = evaluation.local_presencia_exp_rezago_1.astype(float)
        metrics['lag_1_presence_or_training_prevalence'] = _class_metrics(evaluation,np.where(lag.notna(),lag,prior))
    return p,metrics


def _support(train, family):
    target = train.objetivo_semana_siguiente
    if (train.origin_week.nunique()<PROTOCOL['ab_minimum_training_weeks'] or set(target.unique())!={0,1}):
        raise DatasetBlocked('classification_training_support_insufficient')


def _register(conn, version, dataset_version, family, horizon, *, payload=None, fit_end=None,
              method=None, metadata=None):
    sha = hashlib.sha256(payload).hexdigest() if payload is not None else None
    with conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO analytics.modelo_investigacion
                (version,dataset_version,familia,horizonte,estado,ultimo_objetivo_ajuste,metodo,
                 artefacto,artefacto_sha256,protocolo_sha256,metadatos)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (version,dataset_version,family,horizon,'experimental_unvalidated' if payload is not None else 'blocked',
                 fit_end,method,payload,sha,canonical_hash(PROTOCOL),Json(metadata or {},dumps=json_dump)))
    return sha


def _evaluation(conn, model_version, partition, metrics):
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO analytics.evaluacion_investigacion(modelo_version,particion,metricas) VALUES(%s,%s,%s)',
                        (model_version,partition,Json(metrics,dumps=json_dump)))


def _persist_predictions(repo, model_version, dataset_version, frame, values):
    if frame.duplicated(['radio_id','origin_week']).any() or len(values)!=len(frame) or not np.isfinite(values).all():
        raise DatasetBlocked('prediction_grid_invalid')
    ids = repo.query('''SELECT DISTINCT radio_censal,radio_id FROM analytics.base_investigacion
        WHERE dataset_version=%s''',(dataset_version,))
    radios = dict(zip(ids.radio_censal,ids.radio_id))
    previous = repo.query('SELECT radio_id,origen,valor FROM analytics.prediccion_investigacion WHERE modelo_version=%s',(model_version,))
    old = {(r.radio_id,r.origen):r.valor for r in previous.itertuples()}
    rows = []
    for row,value in zip(frame.itertuples(),values):
        rid = int(radios[row.radio_id]); key = (rid,row.origin_week)
        if key in old:
            if old[key] != float(value):
                raise DatasetBlocked('frozen_prediction_replay_changed')
        else:
            rows.append((model_version,rid,row.origin_week,float(value)))
    if rows:
        with repo.conn:
            with repo.conn.cursor() as cur:
                execute_values(cur,'INSERT INTO analytics.prediccion_investigacion VALUES %s',rows,page_size=1000)


def train(conn, *, dataset_version, family, model_version, horizon=1):
    """Fit fixed development only, register before holdout evaluation, no overwrite."""
    repo = MLRepository(conn)
    if family not in ('A','B','V3') or horizon not in (1,2,4) or (family!='V3' and horizon!=1):
        raise DatasetBlocked('unsupported_model_or_horizon')
    repo.research_metadata(dataset_version)
    if not repo.query('SELECT version FROM analytics.modelo_investigacion WHERE version=%s OR (dataset_version=%s AND familia=%s AND horizonte=%s)',
                      (model_version,dataset_version,family,horizon)).empty:
        raise DatasetBlocked('research_model_version_already_registered')
    try:
        frame = prepared(repo,family,dataset_version,horizon=horizon)
        train_part = _usable(frame,family,['train'])
        validation = _usable(frame,family,['validation'])
        development = _usable(frame,family,['train','validation'])
        test = _usable(frame,family,['test'])
        _check_temporal(train_part,validation); _check_temporal(development,test)
        features = list(V3_FEATURES if family=='V3' else AB_FEATURES[family])
        target = 'target_count' if family=='V3' else 'objetivo_semana_siguiente'
        metadata = dict(python=platform.python_version(),sklearn=sklearn.__version__,features=features,
            feature_code_sha256=feature_code_hashes(),training_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            protocol=PROTOCOL,zero_policy=ZERO_POLICY,geography_policy=frame.attrs['provenance']['politica_geografica'],
            rows=dict(train=len(train_part),validation=len(validation),development=len(development),holdout=len(test)),
            development_last_target_end=str(max(development.target_end)),holdout_first_origin=str(min(test.origin_week)),
            training_matrix_sha256=hashlib.sha256(pd.util.hash_pandas_object(development[['radio_id','origin_week',target,*features]],index=False).values.tobytes()).hexdigest(),
            retrospective=True,availability_at_origin_accredited=False,scientifically_validated=False,
            operational_enabled=False,code_contract='fixed initial estimators and parameters; new dataset policy only')
        if family in ('A','B'):
            _support(train_part,family); _support(development,family)
            initial = fit_ab(train_part,family)
            _,validation_metrics = _class_comparison(initial,train_part,validation,family)
            estimator = fit_ab(development,family)
            package = dict(family=family,estimator=estimator)
            development_metrics = dict(validation_2023=validation_metrics,
                initial_fit_last_target_end=str(max(train_part.target_end)),validation_first_origin=str(min(validation.origin_week)),
                no_threshold_or_parameter_selection=True)
            method = 'random_forest_'+family
        else:
            from sigard_ml.forecasting.v3 import validate_development_frame,fit_final
            fitted = validate_development_frame(frame,horizon)
            package = dict(family=family,**fit_final(fitted,horizon))
            development_metrics = fitted['report']
            method = fitted['report']['selection']['best_ml']
            metadata['baseline_gate_passed_in_development'] = fitted['report']['selection']['candidates'][method]['promotion_approved']
        stream = io.BytesIO(); joblib.dump(package,stream,compress=3); payload = stream.getvalue()
        sha = _register(conn,model_version,dataset_version,family,horizon,payload=payload,
            fit_end=max(development.target_end),method=method,metadata=metadata)
        _evaluation(conn,model_version,'development',development_metrics)
        # No fitting, selection or calibration below this point.
        restored = joblib.load(io.BytesIO(payload))
        if family in ('A','B'):
            predictions,metrics = _class_comparison(restored['estimator'],development,test,family)
            own = _class_scores(package['estimator'],test,family)
            baseline_names = [name for name in metrics if name!='model']
            comparison = {name:dict(brier_better=metrics['model']['brier']<metrics[name]['brier'],
                f1_better=metrics['model']['f1']>metrics[name]['f1'],
                ap_better=(metrics['model']['average_precision_pr_auc'] is not None and metrics[name]['average_precision_pr_auc'] is not None
                    and metrics['model']['average_precision_pr_auc']>metrics[name]['average_precision_pr_auc'])) for name in baseline_names}
            result = dict(metrics=metrics,baseline_comparison=comparison,primary_baseline='training_prevalence',primary_metric='brier')
        else:
            from sigard_ml.forecasting.v3 import CANDIDATES,BASELINES,count_summary
            tail=max(2.,float(development.target_count.quantile(.9)))
            high=float(development.groupby('target_week').target_count.sum().quantile(.8))
            predictions=restored['counts'][method].predict_frame(test)
            own=package['counts'][method].predict_frame(test)
            metrics={name:count_summary(test,model.predict_frame(test),tail,high) for name,model in restored['counts'].items()}
            result=dict(metrics=metrics,research_method=method,selected_in_development=package['selection']['selected'],
                baseline_comparison={name:dict(mae_better=metrics[method]['mae']<metrics[name]['mae'],
                    rmse_better=metrics[method]['rmse']<metrics[name]['rmse']) for name in BASELINES},
                primary_baseline='latest_closed_or_training_mean',primary_metric='mae',
                development_promotion_gate=metadata['baseline_gate_passed_in_development'])
        if not np.array_equal(own,predictions):
            raise DatasetBlocked('registered_serialization_changed_predictions')
        _persist_predictions(repo,model_version,dataset_version,test,predictions)
        holdout = dict(result,rows=len(test),origin_weeks=int(test.origin_week.nunique()),
            target_weeks=int(test.target_week.nunique()),first_target=str(min(test.target_week)),last_target=str(max(test.target_week)),
            model_fit_last_target_end=str(max(development.target_end)),first_origin=str(min(test.origin_week)),
            no_holdout_fit_or_tuning=True,independent_external_test=False,scientifically_validated=False)
        _evaluation(conn,model_version,'holdout',holdout)
        return dict(status='trained',model_version=model_version,dataset_version=dataset_version,
            family=family,horizon=horizon,artifact_sha256=sha,holdout=holdout,metadata=metadata)
    except (DatasetBlocked,ForecastError) as error:
        # If already registered, retain the fit and fail visibly; never rewrite it
        # as a fresh candidate after observing an evaluation failure.
        if not repo.query('SELECT version FROM analytics.modelo_investigacion WHERE version=%s',(model_version,)).empty:
            raise
        reason = str(error)
        _register(conn,model_version,dataset_version,family,horizon,metadata=dict(reasons=[reason],protocol=PROTOCOL))
        return dict(status='blocked',model_version=model_version,dataset_version=dataset_version,
                    family=family,horizon=horizon,reasons=[reason])


def infer(conn, *, model_version, origin, mode='retrospective', persist=True):
    """Only registered bytes/metadata and PostgreSQL features; never fit or file IO."""
    repo = MLRepository(conn)
    model = repo.query('''SELECT version,dataset_version,familia,horizonte,estado,ultimo_objetivo_ajuste,
        metodo,artefacto_sha256,protocolo_sha256,metadatos FROM analytics.modelo_investigacion WHERE version=%s''',(model_version,))
    base = dict(schema_version='sigard-postgres-research-prediction/1',model_version=model_version,
        origin_week=str(origin),experimental=True,scientifically_validated=False,
        operational_enabled=False,alerts_enabled=False,rows=[])
    if model.empty:
        return dict(base,status='prediction_unavailable',reasons=['unknown_research_model'])
    m = model.iloc[0].to_dict()
    try:
        meta = repo.research_metadata(m['dataset_version'])
        year,number = DEFAULT_CALENDAR.date_week(origin)
        if DEFAULT_CALENDAR.week_bounds(year,number)[0] != origin:
            raise DatasetBlocked('origin_must_be_argentine_week_start')
        base.update(model=m['familia'],dataset_version=m['dataset_version'],horizon_weeks=int(m['horizonte']),
            target_week=str(origin+timedelta(weeks=int(m['horizonte']))),zero_policy=meta['politica_ceros'],
            geography_quality=meta['politica_geografica'],retrospective=mode=='retrospective',
            result_kind='experimental_presence_score' if m['familia']!='V3' else 'expected_eligible_source_record_count')
        reasons = []
        if mode not in ('retrospective','operational'):
            raise DatasetBlocked('invalid_inference_mode')
        if m['estado']=='blocked':
            reasons.extend(m['metadatos'].get('reasons',['training_blocked']))
        covered = {date.fromisoformat(v) for v in meta['contrato']['scope']['covered_weeks']}
        if origin not in covered or origin+timedelta(weeks=int(m['horizonte'])) not in covered:
            reasons.append('current_or_target_epidemiological_data_unavailable')
        if mode=='operational':
            reasons.extend(['research_model_not_operationally_authorized','point_in_time_availability_unaccredited'])
        if m['ultimo_objetivo_ajuste'] is not None and m['ultimo_objetivo_ajuste'] >= origin:
            reasons.append('model_fitted_after_requested_origin')
        if reasons:
            return dict(base,status='prediction_unavailable',reasons=reasons)
        if (m['metadatos']['sklearn']!=sklearn.__version__ or m['metadatos']['python']!=platform.python_version()
                or m['protocolo_sha256']!=canonical_hash(PROTOCOL)):
            raise DatasetBlocked('research_inference_runtime_or_protocol_changed')
        if m['metadatos']['feature_code_sha256']!=feature_code_hashes():
            raise DatasetBlocked('research_feature_implementation_changed')
        frame = repo.research_frame(m['familia'],m['dataset_version'],outcomes=False,origin=origin,horizon=int(m['horizonte']))
        if m['familia']=='V3' and not frame.predictor_admissible.all():
            raise DatasetBlocked('fundamental_predictors_or_continuity_unavailable')
        payload = bytes(repo.query('SELECT artefacto FROM analytics.modelo_investigacion WHERE version=%s',(model_version,)).iloc[0,0])
        if hashlib.sha256(payload).hexdigest()!=m['artefacto_sha256']:
            raise DatasetBlocked('registered_research_artifact_hash_mismatch')
        package = joblib.load(io.BytesIO(payload))
        if m['familia']!='V3':
            estimator = package['estimator']
            if list(estimator.feature_names_in_)!=AB_FEATURES[m['familia']] or any(estimator.get_params()[k]!=v for k,v in RF_PARAMETERS.items()):
                raise DatasetBlocked('registered_classifier_contract_changed')
            values = _class_scores(estimator,frame,m['familia'])
            frame['radio_id']=frame.radio_censal;frame['origin_week']=frame.fecha_inicio_semana
        else:
            values = package['counts'][m['metodo']].predict_frame(frame)
        if persist:
            _persist_predictions(repo,model_version,m['dataset_version'],frame,values)
        return dict(base,status='available_private_experimental',reasons=[],
            method=m['metodo'],rows=[dict(radio=radio,target_week=base['target_week'],prediction=float(value),
                status='experimental_unvalidated',geography_quality=meta['politica_geografica'],unavailable_reason=None)
                for radio,value in zip(frame.radio_id,values)])
    except (DatasetBlocked,ValueError) as error:
        return dict(base,status='prediction_unavailable',reasons=[str(error)])


def geography_sensitivity(conn, *, model_version, alternate_dataset_version):
    """Explicit counterfactual diagnostic, no refit/selection or cached prediction.

    The same fixed model sees the other geography scenario. Its different target
    is reported separately, not treated as verified spatial ground truth.
    """
    repo=MLRepository(conn)
    model=repo.query('SELECT * FROM analytics.modelo_investigacion WHERE version=%s',(model_version,))
    if len(model)!=1 or model.iloc[0].estado!='experimental_unvalidated':
        raise DatasetBlocked('sensitivity_requires_registered_research_fit')
    m=model.iloc[0]
    first=repo.research_metadata(m.dataset_version)
    alternate=repo.research_metadata(alternate_dataset_version)
    if (first['escenario_version']!=alternate['escenario_version']
            or first['universe_version']!=alternate['universe_version']
            or first['politica_geografica']==alternate['politica_geografica']):
        raise DatasetBlocked('sensitivity_requires_paired_geography_variants')
    if m.metadatos['feature_code_sha256']!=feature_code_hashes():
        raise DatasetBlocked('research_feature_implementation_changed')
    payload=bytes(m.artefacto)
    if hashlib.sha256(payload).hexdigest()!=m.artefacto_sha256:
        raise DatasetBlocked('registered_research_artifact_hash_mismatch')
    package=joblib.load(io.BytesIO(payload))
    frame=_usable(prepared(repo,m.familia,alternate_dataset_version,horizon=int(m.horizonte)),m.familia,['test'])
    original=repo.query('''SELECT b.radio_censal radio_id,p.origen origin_week,p.valor original_prediction
        FROM analytics.prediccion_investigacion p JOIN analytics.base_investigacion b
        ON b.dataset_version=%s AND b.radio_id=p.radio_id AND b.fecha_inicio_semana=p.origen
        WHERE p.modelo_version=%s''',(m.dataset_version,model_version))
    frame=frame.merge(original,on=['radio_id','origin_week'],how='inner',validate='one_to_one')
    if frame.empty:
        raise DatasetBlocked('paired_sensitivity_weeks_unavailable')
    if m.familia in ('A','B'):
        values=_class_scores(package['estimator'],frame,m.familia)
        metric=_class_metrics(frame,values)
    else:
        from sigard_ml.forecasting.evaluation import count_metrics
        values=package['counts'][m.metodo].predict_frame(frame)
        metric=count_metrics(frame.target_count,values)
    delta=np.abs(values-frame.original_prediction.to_numpy(float))
    result=dict(alternate_dataset_version=alternate_dataset_version,rows=len(frame),
        mean_absolute_prediction_change=float(delta.mean()),maximum_absolute_prediction_change=float(delta.max()),
        alternate_target_metrics=metric,no_refit=True,no_selection=True,
        target_definitions_differ=True,spatial_accuracy_validated=False,
        meaning='fixed-model feature sensitivity; separate from refitting under the alternate labels')
    _evaluation(conn,model_version,'sensitivity',result)
    return result
