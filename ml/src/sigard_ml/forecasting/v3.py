"""V3 del entrenamiento principal: tres candidatos y selección temporal interna.

Sin IO, búsqueda masiva, publicación o nueva ingestión. Reutiliza el adaptador,
los paneles/particiones V2, métricas y respaldo de columnas vacías existentes.
"""

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from sigard_ml.forecasting.contracts import require, snapshot_scenario, usable_count
from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.training import SEED
from sigard_ml.forecasting.v2 import EmptyFeatureFallback, summary_metrics
from sigard_ml.official.spatial_ml.research_training import classification_metrics, reliability_bins

VERSION = "sigard-principal-v3-experimental"
CANDIDATES = ("v3_direct_poisson", "v3_hurdle", "v3_residual_boosting")
BASELINES = ("lag_1_or_training_mean", "latest_closed_or_training_mean", "training_radio_mean")
FEATURES = ("count_origin", "cases_lag_1", "cases_lag_2", "recent_mean_3", "recent_trend",
    "known_recent_count", "neighbor_mean_origin", "neighbor_known_fraction", "temperature_origin",
    "humidity_origin", "precipitation_origin", "temperature_mean_4_origin", "precipitation_sum_4_origin",
    "season_sin", "season_cos", "population", "population_density")
METHOD_LABELS = {
    "lag_1_or_training_mean": "Persistencia con respaldo de media histórica",
    "latest_closed_or_training_mean": "Persistencia del último cierre con respaldo histórico",
    "training_radio_mean": "Media histórica de desarrollo por radio",
    "v3_direct_poisson": "ML V3 · boosting Poisson directo",
    "v3_hurdle": "ML V3 · presencia y cantidad condicional",
    "v3_residual_boosting": "ML V3 · corrección de persistencia",
}
PROTOCOL = {
    "version": VERSION, "seed": SEED, "horizons": [1, 2, 4], "candidates": list(CANDIDATES),
    "baselines": list(BASELINES), "features": list(FEATURES),
    "feature_time": "Origin t is closed at t+6 days; t and past only, never target t+h. Final snapshot availability remains unaccredited, available_on unchanged.",
    "count_parameters": dict(max_iter=100, max_leaf_nodes=7, min_samples_leaf=20,
        l2_regularization=5., learning_rate=.05, early_stopping=False),
    "conditional_parameters": dict(max_iter=80, max_leaf_nodes=3, min_samples_leaf=10,
        l2_regularization=5., learning_rate=.05, early_stopping=False),
    "residual_parameters": dict(max_iter=80, max_leaf_nodes=3, min_samples_leaf=40,
        l2_regularization=10., learning_rate=.03, early_stopping=False),
    "residual_shrinkage": .5,
    "presence_parameters": dict(max_iter=80, max_leaf_nodes=7, min_samples_leaf=20,
        l2_regularization=5., learning_rate=.05, early_stopping=False, class_weight="balanced"),
    "calibration": "Sigmoid on last max(3,20%) training target weeks; base labels end before calibration origin. No refit of base after calibration.",
    "threshold": "Training calibration block only: score quantiles .1,.25,.5,.75,.9,.95 plus .5 and above-max; max F1 subject FPR<=.20. No positive F1 => unavailable.",
    "walk_forward": "Reuse V2 expanding development blocks at 1/2,2/3,5/6,1; train target_end < first validation origin, including horizon purge",
    "promotion": "MAE at least 3% below BOTH persistence references, RMSE<=1.02 each, |bias|<=|baseline bias|+.05*mean(y), tail MAE and high-week RMSE<=1.05 each, MAE wins>=2/3 folds, no fold MAE>1.10 either; paired weekly block-bootstrap upper95 MAE difference<0 against strongest baseline",
    "bootstrap": dict(block_weeks=3, resamples=300, seed=SEED),
    "minimum_support": dict(development_weeks=18, comparison_weeks=4, development_positive=30),
    "fallback": "Keep current lag_1_or_training_mean, not a silent replacement by the latest baseline",
    "comparison_period": "V1/V2 already observed; NEVER selection, threshold fitting or independent validation",
    "presence_probability_accredited": False, "alerts_enabled": False,
}


def feature_frame(inputs, cached, horizon):
    """Extiende el panel principal sin modificar máscaras, etiquetas o calendario."""
    inputs.validate()
    require(snapshot_scenario(inputs) and inputs.training_authorized and inputs.evaluation_authorized,
            "V3 requiere snapshot experimental autorizado")
    require(horizon in (1,2,4) and (cached.target_week-cached.origin_week).map(lambda d: d.days).eq(7*horizon).all(),
            "Panel incompatible con el horizonte")
    result = cached.copy(deep=True)
    result["cutoff_date"] = result.origin_week.map(lambda d: d+timedelta(days=6))
    counts = {(row.radio_id, row.week_start): float(row.count) for row in inputs.counts.itertuples() if usable_count(inputs,row)}
    climate = {row.week_start: row for row in inputs.climate.itertuples() if row.complete}
    neighbors = {radio: [] for radio in inputs.radios}
    for left,right in inputs.edges:
        neighbors[left].append(right)
    additions = []
    for row in result.itertuples():
        origin = row.origin_week
        history = [counts.get((row.radio_id, origin-timedelta(weeks=i)), np.nan) for i in range(3)]
        known = np.isfinite(history)
        neighbor = [counts.get((radio,origin),np.nan) for radio in neighbors[row.radio_id]]
        nk = np.isfinite(neighbor)
        weather = [climate.get(origin-timedelta(weeks=i)) for i in range(4)]
        # Cierre del evento <= corte; no se inventa una llegada histórica.
        require(all(item is None or item.week_start+timedelta(days=6) <= row.cutoff_date for item in weather), "Clima posterior al corte")
        now = weather[0]
        complete_weather = all(item is not None for item in weather)
        additions.append(dict(count_origin=history[0], recent_mean_3=float(np.mean(np.array(history)[known])) if known.sum()>=2 else np.nan,
            recent_trend=history[0]-history[1], known_recent_count=int(known.sum()),
            neighbor_mean_origin=float(np.mean(np.array(neighbor)[nk])) if nk.any() else np.nan,
            neighbor_known_fraction=float(nk.mean()) if len(nk) else np.nan,
            temperature_origin=float(now.temperature) if now else np.nan, humidity_origin=float(now.humidity) if now else np.nan,
            precipitation_origin=float(now.precipitation) if now else np.nan,
            temperature_mean_4_origin=float(np.mean([item.temperature for item in weather])) if complete_weather else np.nan,
            precipitation_sum_4_origin=float(sum(item.precipitation for item in weather)) if complete_weather else np.nan))
    for name in additions[0]:
        result[name] = [item[name] for item in additions]
    require(result.target_count.equals(cached.target_count), "Se modificaron etiquetas del snapshot")
    return result


def matrix(frame):
    values = frame[list(FEATURES)].astype(float)
    require(not np.isinf(values.to_numpy()).any(), "Feature infinita")
    return values


def _fit(estimator, frame, y):
    with threadpool_limits(limits=1):
        estimator.fit(matrix(frame), y)
    return estimator


def _predict(estimator, frame):
    with threadpool_limits(limits=1):
        return np.asarray(estimator.predict(matrix(frame)),dtype=float)


def _regressor(parameters, loss):
    return make_pipeline(EmptyFeatureFallback(), HistGradientBoostingRegressor(loss=loss, random_state=SEED, **parameters))


def logits(values):
    values = np.clip(values, 1e-6, 1-1e-6)  # Only numeric stability for sigmoid, no count cap.
    return np.log(values/(1-values)).reshape(-1,1)


def choose_threshold(y, scores):
    y, scores = np.asarray(y,dtype=int), np.asarray(scores,dtype=float)
    if len(np.unique(y)) != 2:
        return None, []
    thresholds = sorted(set(np.quantile(scores,[.1,.25,.5,.75,.9,.95]).tolist()+[.5,float(scores.max())+1e-9]))
    rows = []
    for threshold in thresholds:
        predicted = scores>=threshold
        tp,fp = int((predicted & (y==1)).sum()),int((predicted & (y==0)).sum())
        precision = tp/(tp+fp) if tp+fp else 0.
        recall = tp/max(int(y.sum()),1)
        f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.
        rows.append(dict(threshold=threshold,precision=precision,recall=recall,f1=f1,
                         false_positive_rate=fp/max(int((y==0).sum()),1), predicted_positive=int(predicted.sum())))
    eligible = [row for row in rows if row["false_positive_rate"]<=.20 and row["f1"]>0]
    best = max(eligible,key=lambda r:(r["f1"],r["precision"],-r["false_positive_rate"],r["threshold"])) if eligible else None
    return best["threshold"] if best else None,rows


@dataclass
class Presence:
    estimator: object
    calibrator: object
    threshold: object
    metadata: dict

    def score(self, frame, *, raw=False):
        with threadpool_limits(limits=1):
            probability = self.estimator.predict_proba(matrix(frame))
            classes = list(self.estimator.classes_)
            values = probability[:,classes.index(1)] if 1 in classes else np.zeros(len(frame))
            if self.calibrator is not None and not raw:
                values = self.calibrator.predict_proba(logits(values))[:,1]
        return values


def fit_presence(train):
    dates = sorted(train.target_week.unique())
    calibration = train.loc[train.target_week.isin(dates[-max(3,int(len(dates)*.2)):])]
    base = train.loc[train.target_end.lt(min(calibration.origin_week))]
    supported = (len(base)>0 and base.target_count.gt(0).nunique()==2
                 and calibration.target_count.gt(0).nunique()==2 and calibration.target_count.gt(0).sum()>=3)
    if not supported:
        base = train
    y = base.target_count.gt(0).astype(int)
    classifier = (make_pipeline(EmptyFeatureFallback(), HistGradientBoostingClassifier(random_state=SEED,**PROTOCOL["presence_parameters"]))
                  if y.nunique()==2 else make_pipeline(EmptyFeatureFallback(),DummyClassifier(strategy="prior")))
    _fit(classifier,base,y)
    fitted = Presence(classifier,None,None,dict(base_rows=len(base),base_target_end=str(max(base.target_end)),
        calibration_rows=len(calibration) if supported else 0, calibrated_on_development_only=bool(supported),
        threshold_support=bool(supported), threshold_rows=[], historical_availability_accredited=False))
    if supported:
        raw = fitted.score(calibration,raw=True)
        with threadpool_limits(limits=1):
            fitted.calibrator = LogisticRegression(C=1.,random_state=SEED).fit(logits(raw),calibration.target_count.gt(0).astype(int))
        fitted.threshold,rows = choose_threshold(calibration.target_count.gt(0),fitted.score(calibration))
        fitted.metadata.update(calibration_first_origin=str(min(calibration.origin_week)),
            calibration_target_end=str(max(calibration.target_end)), threshold=fitted.threshold,threshold_rows=rows)
    return fitted


@dataclass
class Counts:
    name: str
    estimator: object
    presence: object
    radio_means: dict
    global_mean: float
    fit_cutoff: object
    horizon_weeks: int
    residual_shrinkage: float = .5

    def baseline(self, frame, *, latest=False):
        prior = frame.radio_id.map(self.radio_means).fillna(self.global_mean).to_numpy(dtype=float)
        last = frame.count_origin if latest else frame.cases_lag_1
        return np.where(last.notna(),last,prior)

    def predict_frame(self, frame):
        if self.name=="lag_1_or_training_mean": values=self.baseline(frame)
        elif self.name=="latest_closed_or_training_mean": values=self.baseline(frame,latest=True)
        elif self.name=="training_radio_mean": values=frame.radio_id.map(self.radio_means).fillna(self.global_mean).to_numpy(dtype=float)
        elif self.name=="v3_hurdle": values=self.presence.score(frame)*np.maximum(_predict(self.estimator,frame),1.)
        elif self.name=="v3_residual_boosting": values=np.maximum(0.,self.baseline(frame,latest=True)+self.residual_shrinkage*_predict(self.estimator,frame))
        else: values=_predict(self.estimator,frame)
        require(np.isfinite(values).all() and (values>=0).all(), "Predicción V3 no finita/negativa")
        return values


def fit_models(train,horizon):
    require(train.target_count.notna().all() and len(train)>0,"Ajuste sin etiquetas utilizables")
    means,mean = train.groupby("radio_id").target_count.mean().to_dict(),float(train.target_count.mean())
    presence = fit_presence(train)
    fitted = {name:Counts(name,None,None,means,mean,max(train.target_end),horizon) for name in (*CANDIDATES,*BASELINES)}
    direct = (_regressor(PROTOCOL["count_parameters"],"poisson") if train.target_count.sum()>0
              else make_pipeline(EmptyFeatureFallback(),DummyRegressor(strategy="constant",constant=0.)))
    fitted[CANDIDATES[0]].estimator=_fit(direct,train,train.target_count)
    positives=train.loc[train.target_count.gt(0)]
    conditional=(_regressor(PROTOCOL["conditional_parameters"],"poisson") if len(positives)>=10
                 else make_pipeline(EmptyFeatureFallback(),DummyRegressor(strategy="constant",constant=float(positives.target_count.mean()) if len(positives) else 1.)))
    _fit(conditional,positives if len(positives) else train,positives.target_count if len(positives) else np.ones(len(train)))
    fitted[CANDIDATES[1]].estimator, fitted[CANDIDATES[1]].presence=conditional,presence
    residual=train.target_count.to_numpy()-fitted[BASELINES[1]].baseline(train,latest=True)
    fitted[CANDIDATES[2]].estimator=_fit(_regressor(PROTOCOL["residual_parameters"],"squared_error"),train,residual)
    return fitted,presence


def count_summary(frame, values, tail_threshold, week_threshold):
    result=summary_metrics(frame,values,tail_threshold=tail_threshold,high_week_threshold=week_threshold)
    weekly=frame[["target_week","target_count"]].copy()
    weekly["predicted"]=values
    result["weekly"]=[dict(target_week=str(target),**count_metrics(group.target_count,group.predicted),
        recorded_known_subset_total=float(group.target_count.sum()),estimated_known_subset_total=float(group.predicted.sum()))
        for target,group in weekly.groupby("target_week")]
    result["prediction_max"]=float(np.max(values))
    result["observed_max"]=float(frame.target_count.max())
    result["complete_256_totals"]="unavailable_when_unknown_labels; weekly metrics are known-subset totals"
    return result


def presence_summary(frame, values, thresholds):
    y=frame.target_count.gt(0).astype(int).to_numpy()
    values=np.asarray(values,dtype=float)
    supported=np.array([value is not None and pd.notna(value) for value in thresholds])
    # Reuse metrics; binary decisions below use only thresholds learned in each training block.
    result=classification_metrics(y,values,.5)
    result["fixed_0_5_diagnostic"]={key:result[key] for key in ("precision","recall","f1","predicted_positive")}
    result["threshold"]="training_block_specific"
    if supported.any():
        actual=y[supported]
        decisions=(values[supported]>=np.asarray(thresholds,dtype=object)[supported].astype(float))
        tp,fp,fn,tn=[int(mask.sum()) for mask in (decisions&(actual==1),decisions&(actual==0),~decisions&(actual==1),~decisions&(actual==0))]
        precision=tp/(tp+fp) if tp+fp else 0.
        recall=tp/(tp+fn) if tp+fn else 0.
        result.update(precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0.,
            false_positives=fp,true_positives=tp,false_negatives=fn,true_negatives=tn,
            false_positive_rate=fp/(fp+tn) if fp+tn else None, binary_supported_rows=int(supported.sum()),
            predicted_positive=tp+fp,confusion_matrix_true_rows_predicted_columns_0_1=[[tn,fp],[fn,tp]])
    else:
        result.update(precision=None,recall=None,f1=None,binary_supported_rows=0,false_positives=None,
                      true_positives=None,predicted_positive=None,confusion_matrix_true_rows_predicted_columns_0_1=None)
    result["reliability"]=reliability_bins(y,values)
    return result


def bootstrap_difference(oof,name,baseline):
    copy=oof[["target_week","target_count",name,baseline]].copy()
    copy["delta"]=(copy[name]-copy.target_count).abs()-(copy[baseline]-copy.target_count).abs()
    grouped=copy.groupby("target_week").delta.agg(["sum","size"]).sort_index()
    dates=list(grouped.index)
    blocks=[]
    for i in range(len(dates)):
        block=[i]
        while len(block)<3 and block[-1]+1<len(dates) and (dates[block[-1]+1]-dates[block[-1]]).days==7:
            block.append(block[-1]+1)
        blocks.append(block)
    rng=np.random.default_rng(SEED)
    differences=[]
    for _ in range(PROTOCOL["bootstrap"]["resamples"]):
        indices=[]
        while len(indices)<len(dates): indices.extend(blocks[int(rng.integers(len(blocks)))])
        sample=grouped.iloc[indices[:len(dates)]]
        differences.append(float(sample["sum"].sum()/sample["size"].sum()))
    return dict(mean_mae_difference=float(copy.delta.mean()),lower95=float(np.quantile(differences,.025)),
                upper95=float(np.quantile(differences,.975)),reference=baseline,
                interpretation="paired temporal block bootstrap, descriptive internal uncertainty, not external validation")


def select_model(oof,metrics,fold_metrics):
    comparisons=(BASELINES[0],BASELINES[1])
    strongest=min(comparisons,key=lambda name:metrics[name]["mae"])
    rows={}
    mean=float(oof.target_count.mean())
    for name in CANDIDATES:
        value=metrics[name]
        gates=[]
        for reference in comparisons:
            baseline=metrics[reference]
            tail_ok=value["high_count"] is None or baseline["high_count"] is None or value["high_count"]["mae"]<=1.05*baseline["high_count"]["mae"]+1e-12
            high_ok=value["high_week_known_subset"] is None or baseline["high_week_known_subset"] is None or value["high_week_known_subset"]["rmse"]<=1.05*baseline["high_week_known_subset"]["rmse"]+1e-12
            wins=sum(f[name]["mae"]<f[reference]["mae"] for f in fold_metrics)
            stable=all(f[name]["mae"]<=1.10*f[reference]["mae"]+1e-12 for f in fold_metrics)
            gates.append(dict(reference=reference,mae=value["mae"]<=.97*baseline["mae"],rmse=value["rmse"]<=1.02*baseline["rmse"],
                bias=abs(value["mean_bias"])<=abs(baseline["mean_bias"])+.05*mean,
                high_count=tail_ok,high_week=high_ok,folds_won=wins,stable=stable))
        bootstrap=bootstrap_difference(oof,name,strongest)
        eligible=all(all(g[k] for k in ("mae","rmse","bias","high_count","high_week","stable")) and g["folds_won"]>=2 for g in gates) and bootstrap["upper95"]<0
        baseline=metrics[strongest]
        ratio=lambda a,b:a/max(b,1e-9)
        score=.30*ratio(value["mae"],baseline["mae"])+.25*ratio(value["rmse"],baseline["rmse"])+.15*abs(value["mean_bias"])/max(mean,1e-9)+.15*ratio(
            value["high_count"]["mae"] if value["high_count"] else value["mae"],baseline["high_count"]["mae"] if baseline["high_count"] else baseline["mae"])+.15*ratio(value["weekly_known_subset_rmse"],baseline["weekly_known_subset_rmse"])
        rows[name]=dict(score=score,promotion_approved=bool(eligible),gates=gates,paired_bootstrap=bootstrap)
    best=min(CANDIDATES,key=lambda name:(rows[name]["score"],CANDIDATES.index(name)))
    eligible=[name for name in CANDIDATES if rows[name]["promotion_approved"]]
    selected=min(eligible,key=lambda name:(rows[name]["score"],CANDIDATES.index(name))) if eligible else BASELINES[0]
    return dict(best_ml=best,selected=selected,promotion_approved=selected in CANDIDATES,
                strongest_baseline=strongest,candidates=rows,external_validation_pending=True)


def validate_development(inputs,cached,horizon):
    frame=feature_frame(inputs,cached,horizon)
    development=frame.loc[frame.partition.isin(["train","validation"]) & frame.predictor_admissible & frame.target_count.notna()].copy()
    require(development.target_week.nunique()>=18 and development.target_count.gt(0).sum()>=30,"Desarrollo insuficiente para V3")
    dates=sorted(development.target_week.unique())
    boundaries=[int(len(dates)*fraction) for fraction in (.5,2/3,5/6,1)]
    oof,folds,fold_counts,models=[],[],[],[]
    for fold,(left,right) in enumerate(zip(boundaries[:-1],boundaries[1:])):
        validation=development.loc[development.target_week.isin(dates[left:right])].copy()
        train=development.loc[development.target_end.lt(min(validation.origin_week))].copy()
        require(train.target_week.nunique()>=8 and len(validation)>0,"Pliegue insuficiente")
        fitted,presence=fit_models(train,horizon)
        tail=max(2.,float(train.target_count.quantile(.9)))
        high=float(train.groupby("target_week").target_count.sum().quantile(.8))
        part=validation[["radio_id","origin_week","target_week","target_count"]].copy()
        part["fold"],part["tail_threshold"],part["high_week_threshold"]=fold,tail,high
        metrics={}
        for name,model in fitted.items():
            values=model.predict_frame(validation)
            part[name]=values
            metrics[name]=count_summary(validation,values,tail,high)
        part["presence_score"]=presence.score(validation)
        part["presence_raw"]=presence.score(validation,raw=True)
        part["presence_threshold"]=presence.threshold
        part["training_prevalence"]=float(train.target_count.gt(0).mean())
        part["presence_persistence"]=np.where(validation.cases_lag_1.notna(),validation.cases_lag_1.gt(0),float(train.target_count.gt(0).mean()))
        part["training_max_count"]=float(train.target_count.max())
        folds.append(dict(fold=fold,train_rows=len(train),train_weeks=int(train.target_week.nunique()),validation_rows=len(validation),
            validation_weeks=int(validation.target_week.nunique()),train_target_end=str(max(train.target_end)),
            validation_first_origin=str(min(validation.origin_week)),validation_last_target=str(max(validation.target_week)),
            positive_train=int(train.target_count.gt(0).sum()),positive_validation=int(validation.target_count.gt(0).sum()),
            presence=presence.metadata,missing_features=matrix(train).isna().sum().to_dict()))
        oof.append(part);fold_counts.append(metrics);models.append(dict(counts=fitted,presence=presence))
    oof=pd.concat(oof,ignore_index=True)
    metrics={}
    for name in (*CANDIDATES,*BASELINES):
        value=count_summary(oof,oof[name],max(2.,float(development.target_count.quantile(.9))),float(development.groupby("target_week").target_count.sum().quantile(.8)))
        tail=oof.target_count.ge(oof.tail_threshold)
        value["high_count"]=count_metrics(oof.loc[tail,"target_count"],oof.loc[tail,name]) if tail.any() else None
        weekly=oof.groupby("target_week").agg(actual=("target_count","sum"),predicted=(name,"sum"),limit=("high_week_threshold","first"))
        high=weekly.actual.ge(weekly.limit)
        value["high_week_known_subset"]=count_metrics(weekly.loc[high,"actual"],weekly.loc[high,"predicted"]) if high.any() else None
        shifted=oof.target_count.gt(oof.training_max_count)
        value["above_training_max_cells"]=count_metrics(oof.loc[shifted,"target_count"],oof.loc[shifted,name]) if shifted.any() else None
        metrics[name]=value
    selection=select_model(oof,metrics,fold_counts)
    reference_thresholds=[.5 if pd.notna(value) else None for value in oof.presence_threshold]
    presence_metrics={name:presence_summary(oof,oof[name],oof.presence_threshold if name=="presence_score" else reference_thresholds)
        for name in ("presence_score","presence_raw","training_prevalence","presence_persistence")}
    presence_folds=[]
    for fold,group in oof.groupby("fold"):
        presence_folds.append(dict(fold=int(fold),**{name:presence_summary(group,group[name],group.presence_threshold if name=="presence_score" else [.5 if pd.notna(value) else None for value in group.presence_threshold])
            for name in ("presence_score","training_prevalence","presence_persistence")}))
    stable=sum(item["presence_score"]["brier"]<=item["training_prevalence"]["brier"] and
               item["presence_score"]["average_precision_pr_auc"] is not None and
               item["presence_score"]["average_precision_pr_auc"]>item["presence_score"]["prevalence"] for item in presence_folds)>=2
    return dict(frame=frame,development=development,oof=oof,fold_models=models,
        report=dict(version=VERSION,horizon_weeks=horizon,features=list(FEATURES),folds=folds,
            validation=metrics,fold_count_metrics=fold_counts,selection=selection,
            presence_validation=presence_metrics,presence_folds=presence_folds,presence_discrimination_stable=bool(stable),
            development_rows=len(development),development_weeks=len(dates),development_first_target=str(min(dates)),
            development_last_target=str(max(dates)),validation_rows=len(oof),validation_weeks=int(oof.target_week.nunique()),
            historical_availability_accredited=False,external_validation_pending=True,alerts_enabled=False))


def fit_final(validation,horizon):
    """Sólo desarrollo. Llamar y congelar selección antes de evaluar comparación."""
    counts,presence=fit_models(validation["development"],horizon)
    return dict(counts=counts,presence=presence,selection=validation["report"]["selection"])


def precision_recall_rows(frame,values):
    y=frame.target_count.gt(0).astype(int)
    if y.nunique()!=2:return []
    precision,recall,threshold=precision_recall_curve(y,values)
    return [dict(precision=float(p),recall=float(r),threshold=float(threshold[i]) if i<len(threshold) else None)
            for i,(p,r) in enumerate(zip(precision,recall))]
