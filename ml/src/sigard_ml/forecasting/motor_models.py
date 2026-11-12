"""Only authorized RF variants and the residual correction of persistence."""
from dataclasses import dataclass
from datetime import timedelta
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.motor_protocol import PROTOCOL,FEATURES,PRESENCE
from sigard_ml.forecasting.v3 import _regressor


def matrix(frame, method, features=None):
    if method not in FEATURES:raise DatasetBlocked('motor_method_not_authorized')
    names=FEATURES[method] if features is None else tuple(features)
    if not names or len(names)!=len(set(names)) or not set(names)<=set(FEATURES[method]):
        raise DatasetBlocked('motor_feature_subset_required')
    result=frame[list(names)].astype(float)
    if np.isinf(result.to_numpy()).any():raise DatasetBlocked('motor_infinite_feature')
    return result


def purge_training(frame, first_origin):
    cutoff=first_origin-timedelta(weeks=PROTOCOL['purge_weeks'])
    result=frame.loc[frame.target_count.notna() & frame.target_end.lt(cutoff)].copy()
    if len(result) and not result.target_end.max()<cutoff:
        raise DatasetBlocked('motor_temporal_training_leakage')
    return result


def choose_threshold(y, values):
    y=np.asarray(y,dtype=int);values=np.asarray(values,float)
    if len(np.unique(y))<2:return .5
    choices=[]
    for threshold in PROTOCOL['thresholds']:
        positive=values>=threshold
        tp=int((positive&(y==1)).sum());fp=int((positive&(y==0)).sum())
        precision=tp/(tp+fp) if tp+fp else 0.
        recall=tp/max(int(y.sum()),1)
        f1=2*precision*recall/(precision+recall) if precision+recall else 0.
        if fp/max(int((y==0).sum()),1)<=.20:
            choices.append((f1,precision,threshold))
    return max(choices)[2] if choices else .5


def _logits(values):
    p=np.clip(np.asarray(values,float),1e-6,1-1e-6)
    return np.log(p/(1-p)).reshape(-1,1)


@dataclass
class PresenceModel:
    method: str
    estimator: object
    calibrator: object
    threshold: float
    constant: float
    metadata: dict
    features: tuple | None = None

    def score(self, frame, raw=False):
        if self.estimator is None:return np.full(len(frame),self.constant,dtype=float)
        with threadpool_limits(limits=1):
            probabilities=self.estimator.predict_proba(matrix(frame,self.method,self.features))
            classes=list(self.estimator.classes_)
            values=probabilities[:,classes.index(1)] if 1 in classes else np.zeros(len(frame))
            if self.calibrator is not None and not raw:
                values=self.calibrator.predict_proba(_logits(values))[:,1]
        return values


def inner_blocks(train):
    dates=sorted(train.target_week.unique())
    if len(dates)<PROTOCOL['calibration']['inner_weeks']:
        empty=train.iloc[:0].copy()
        return train,empty,empty,False,False
    inner=train.loc[train.target_week.isin(dates[-26:])]
    first=sorted(inner.target_week.unique())[:13]
    calibration=inner.loc[inner.target_week.isin(first)]
    threshold=inner.loc[~inner.target_week.isin(first)]
    calibration=purge_training(calibration,threshold.origin_week.min())
    base=purge_training(train,inner.origin_week.min())
    cfg=PROTOCOL['calibration']
    positive=lambda f:int(f.target_count.gt(0).sum())
    weeks=lambda f:int(f.loc[f.target_count.gt(0),'target_week'].nunique())
    base_ok=(base.target_week.nunique()>=cfg['base_min_weeks'] and positive(base)>=cfg['base_min_positive']
             and base.target_count.gt(0).nunique()==2)
    threshold_ok=(base_ok and threshold.target_count.gt(0).nunique()==2
        and positive(threshold)>=cfg['threshold_min_positive'] and weeks(threshold)>=cfg['threshold_min_positive_weeks'])
    calibration_ok=(threshold_ok and calibration.target_count.gt(0).nunique()==2
        and positive(calibration)>=cfg['calibration_min_positive'] and weeks(calibration)>=cfg['calibration_min_positive_weeks']
        and len(calibration)-positive(calibration)>=cfg['calibration_min_negative'])
    return base,calibration,threshold,threshold_ok,calibration_ok


def fit_presence(train, method, *, features=None):
    if method not in PRESENCE:raise DatasetBlocked('only_three_authorized_RF_variants')
    if train.empty or train.target_count.isna().any():raise DatasetBlocked('motor_known_training_targets_required')
    base,calibration,threshold,threshold_ok,calibration_ok=inner_blocks(train)
    fitting=base if threshold_ok else train
    y=fitting.target_count.gt(0).astype(int)
    metadata=dict(training_rows=len(train),training_first_target=str(train.target_week.min()),
        training_last_target_end=str(train.target_end.max()),base_last_target_end=str(fitting.target_end.max()),
        base_rows=len(fitting),calibrated=False,threshold_source='fixed_protocol_0.5',
        raw_score_not_accredited_probability=True,features=list(FEATURES[method] if features is None else features),
        missing_features=matrix(fitting,method,features).isna().sum().astype(int).to_dict())
    fitted=PresenceModel(method,None,None,.5,float(y.mean()),metadata,
        None if features is None else tuple(features))
    if y.nunique()<2:
        fitted.metadata['support']='single_class_training_constant_reference_no_RF_fit'
        return fitted
    with threadpool_limits(limits=1):
        fitted.estimator=RandomForestClassifier(**PROTOCOL['rf_parameters']).fit(matrix(fitting,method,features),y)
        if calibration_ok:
            fitted.calibrator=LogisticRegression(C=1.,random_state=PROTOCOL['bootstrap']['seed']).fit(
                _logits(fitted.score(calibration,raw=True)),calibration.target_count.gt(0).astype(int))
            fitted.metadata.update(calibrated=True,calibration_first_origin=str(calibration.origin_week.min()),
                calibration_last_target_end=str(calibration.target_end.max()),calibration_rows=len(calibration))
    if threshold_ok:
        fitted.threshold=choose_threshold(threshold.target_count.gt(0),fitted.score(threshold))
        fitted.metadata.update(threshold_source='chronological_inner_development_only',
            threshold_first_origin=str(threshold.origin_week.min()),threshold_last_target_end=str(threshold.target_end.max()))
    fitted.metadata.update(threshold=fitted.threshold,calibration_support_sufficient=calibration_ok,
        threshold_support_sufficient=threshold_ok)
    return fitted


def baselines(train, evaluation):
    if train.empty or train.target_count.isna().any():raise DatasetBlocked('motor_baseline_needs_training_labels')
    global_mean=float(train.target_count.mean())
    means=train.groupby('radio_id').target_count.mean()
    prior=evaluation.radio_id.map(means).fillna(global_mean).to_numpy(float)
    latest=np.where(evaluation.count_origin.notna(),evaluation.count_origin,prior)
    lag=np.where(evaluation.count_lag_1.notna(),evaluation.count_lag_1,prior)
    global_presence=float(train.target_count.gt(0).mean())
    grouped=train.assign(y=train.target_count.gt(0).astype(int)).groupby('radio_id').y.agg(['sum','size'])
    weight=PROTOCOL['baseline_territorial_prior_weight']
    probabilities=(grouped['sum']+weight*global_presence)/(grouped['size']+weight)
    territory=evaluation.radio_id.map(probabilities).fillna(global_presence).to_numpy(float)
    seasonal=np.empty(len(evaluation),dtype=float)
    for number in evaluation.target_number.unique():
        distance=(train.target_number-number).abs()
        sub=train.loc[np.minimum(distance,53-distance)<=PROTOCOL['baseline_seasonal_window_weeks']]
        counts=sub.assign(y=sub.target_count.gt(0).astype(int)).groupby('radio_id').y.agg(['sum','size'])
        p=(counts['sum']+weight*global_presence)/(counts['size']+weight)
        mask=evaluation.target_number.eq(number).to_numpy()
        seasonal[mask]=evaluation.loc[mask,'radio_id'].map(p).fillna(global_presence)
    return dict(count_latest=latest,count_historical_lag1=lag,count_training_mean=prior,
        presence_latest=np.where(evaluation.count_origin.notna(),evaluation.count_origin.gt(0),territory),
        presence_prior=np.full(len(evaluation),global_presence),presence_territorial=territory,presence_seasonal=seasonal)


def baseline_thresholds(train):
    base,_,threshold,supported,_=inner_blocks(train)
    names=('presence_latest','presence_prior','presence_territorial','presence_seasonal')
    if not supported:return {name:.5 for name in names}
    scores=baselines(base,threshold)
    return {name:choose_threshold(threshold.target_count.gt(0),scores[name]) for name in names}


@dataclass
class CountModel:
    estimator: object
    metadata: dict
    features: tuple | None = None

    def predict(self, frame, baseline):
        with threadpool_limits(limits=1):
            residual=np.asarray(self.estimator.predict(matrix(frame,'residual_h1',self.features)),dtype=float)
        result=np.maximum(0.,np.asarray(baseline,float)+PROTOCOL['residual_shrinkage']*residual)
        if not np.isfinite(result).all():raise DatasetBlocked('motor_invalid_count_prediction')
        return result


def fit_count(train, *, features=None):
    reference=baselines(train,train)['count_latest']
    residual=train.target_count.to_numpy(float)-reference
    estimator=_regressor(PROTOCOL['residual_parameters'],'squared_error')
    with threadpool_limits(limits=1):estimator.fit(matrix(train,'residual_h1',features),residual)
    return CountModel(estimator,dict(method='residual_h1',training_rows=len(train),
        training_last_target_end=str(train.target_end.max()),features=list(FEATURES['residual_h1'] if features is None else features),
        count_is_probability_product=False),None if features is None else tuple(features))
