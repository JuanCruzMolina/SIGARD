"""Single controlled t+1 experiment: fixed recency weights on V3 Poisson.

Exactly three development fits, no final fit, no comparison predictions or
labels, no parameter search, no changes to frozen artifacts or permissions.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from sigard_ml.forecasting.adapter import AdapterRequest, EvidenceDocument, adapt_derived
from sigard_ml.forecasting.contracts import PROVISIONAL_EXPERIMENT
from sigard_ml.forecasting.thesis_validation import FrozenArtifact, digest, write_json, week_statistics, block_interval
from sigard_ml.forecasting.v2 import EmptyFeatureFallback
from sigard_ml.forecasting.v3 import BASELINES, FEATURES, PROTOCOL, VERSION, matrix
from sigard_ml.official.access import SourceAuthorization, SourceRegistry, AuthorizedUse
from sigard_ml.official.epidemiological_preflight.evidence import canonical_bytes

from diagnose_predictive_v3 import errors, protected_hashes, join_panel

NAME = 'poisson_v3_recency_13w'
HALF_LIFE_WEEKS = 13.
SPECIFICATION = dict(
    candidate=NAME, horizon_weeks=1, seed=20261026,
    modification='Only sample_weight changes: exp2(-age_calendar_weeks/13), normalized to mean 1 within training fold',
    half_life_calendar_weeks=HALF_LIFE_WEEKS,
    rationale='Development-only recency sensitivity; quantitative motivation remains in the private execution report',
    parameter_choice='One quarter of calendar time; fixed exploratory choice, no search or optimality claim',
    base_parameters=PROTOCOL['count_parameters'], features=list(FEATURES),
    selection_input='development.private.json only; comparison_diagnostic.private.json not used',
    evaluation='Same frozen V3 chronological t+1 folds, identical rows, train target_end before first validation origin',
    comparators=[*BASELINES[:2], 'v3_direct_poisson', 'v3_residual_boosting'],
    stopping_rule='If not consistent against both persistence references under unchanged V3 gates, stop and do not retain as improvement',
    authorization='Explicit user request of 2026-10-26, one development experiment; existing approved historical snapshot uses only',
    independent_delivery_training_embargo=True,
    new_outcomes_allowed=False, comparison_evaluation_allowed=False,
    final_fit_allowed=False, model_serialization_allowed=False)


def recency_weights(train):
    assert len(train) and train.target_count.notna().all()
    latest = train.target_end.max()
    ages = np.asarray([(latest-value).days/7 for value in train.target_end])
    assert np.isfinite(ages).all() and (ages>=0).all()
    weights = np.exp2(-ages/HALF_LIFE_WEEKS)
    return weights/weights.mean()


def training_window(development, validation):
    assert development.partition.isin(['train','validation']).all()
    result = development.loc[development.target_end.lt(validation.origin_week.min())].copy()
    assert len(result) and result.target_end.max() < validation.origin_week.min()
    assert not set(zip(result.radio_id,result.target_week)) & set(zip(validation.radio_id,validation.target_week))
    return result


def verify_authorization(root):
    folder=root/'data/processed/official/principal_snapshot_20261026_v2'
    manifest=json.loads((folder/'manifest.private.json').read_text(encoding='utf-8'))
    def read(name):
        path=folder/name
        assert digest(path)==manifest['outputs_sha256'][name]
        return json.loads(path.read_text(encoding='utf-8'))
    bundle, access, documents = (read(name) for name in ('derived_bundle.private.json','access.private.json','documents.private.json'))
    registry=SourceRegistry(tuple(SourceAuthorization(**dict(row,path=Path(row['path']),sheets=tuple(row['sheets']),
        uses=frozenset(AuthorizedUse(use) for use in row['uses']))) for row in access['sources']))
    docs={ref:EvidenceDocument(canonical_bytes(value['content']),value['sha256']) for ref,value in documents.items()}
    prep_ref=next(ref for ref,value in documents.items() if value['content']['role']=='provisional_experiment_preparation')
    use_ref=next(ref for ref,value in documents.items() if value['content']['role']=='provisional_experiment_use')
    prep=documents[prep_ref]['content']
    request=AdapterRequest(prep['source_id'],bundle['dataset_version'],prep['subset_ref'],
        hashlib.sha256(canonical_bytes(bundle)).hexdigest(),prep_ref,use_ref,date(2026,10,26),mode=PROVISIONAL_EXPERIMENT)
    inputs=adapt_derived(canonical_bytes(bundle),registry,request,documents=docs)
    assert inputs.training_authorized and inputs.evaluation_authorized
    # The verified package never supplies labels/features to the estimator: only
    # the separately filtered frozen development panel below is used in fitting.
    return {name:digest(folder/name) for name in ('manifest.private.json','derived_bundle.private.json','access.private.json','documents.private.json')}


def evaluate(predictions):
    methods=[NAME,*BASELINES[:2],'v3_direct_poisson','v3_residual_boosting']
    metrics={m:errors(predictions.target_count,predictions[m]) for m in methods}
    folds=[]
    for fold, part in predictions.groupby('fold',sort=True):
        folds.append(dict(fold=int(fold),metrics={m:errors(part.target_count,part[m]) for m in methods}))
    tail=predictions.target_count.ge(predictions.tail_threshold)
    high=predictions.groupby('target_week').target_count.transform('sum').ge(predictions.high_week_threshold)
    weekly=predictions.groupby('target_week').agg(actual=('target_count','sum'),threshold=('high_week_threshold','first'),**{m:(m,'sum') for m in methods})
    high_week=weekly.actual.ge(weekly.threshold)
    stratified={}
    for label, mask in {'zero':predictions.target_count.eq(0),'positive':predictions.target_count.gt(0),'high_count':tail,'high_week_cells':high}.items():
        part=predictions.loc[mask]
        stratified[label]={m:errors(part.target_count,part[m]) for m in methods}
    stratified['high_week_subtotals']={m:errors(weekly.loc[high_week,'actual'],weekly.loc[high_week,m]) for m in methods}
    gates=[]
    strongest=min(BASELINES[:2],key=lambda m:metrics[m]['mae'])
    interval=block_interval(week_statistics(predictions,NAME,strongest),3)
    mean=float(predictions.target_count.mean())
    for reference in BASELINES[:2]:
        ml, base=metrics[NAME],metrics[reference]
        gates.append(dict(reference=reference,
            mae=ml['mae']<=.97*base['mae'],rmse=ml['rmse']<=1.02*base['rmse'],
            bias=abs(ml['bias'])<=abs(base['bias'])+.05*mean,
            high_count=stratified['high_count'][NAME]['mae']<=1.05*stratified['high_count'][reference]['mae'],
            high_week=stratified['high_week_subtotals'][NAME]['rmse']<=1.05*stratified['high_week_subtotals'][reference]['rmse'],
            folds_won=sum(f['metrics'][NAME]['mae']<f['metrics'][reference]['mae'] for f in folds),
            stable=all(f['metrics'][NAME]['mae']<=1.10*f['metrics'][reference]['mae'] for f in folds)))
    keep=all(all(row[key] for key in ('mae','rmse','bias','high_count','high_week','stable')) and row['folds_won']>=2 for row in gates) and interval['intervals']['mae'][1]<0
    return dict(metrics=metrics,folds=folds,stratified=stratified,gates=gates,
                strongest_baseline=strongest,paired_weekly_interval=interval,retain_candidate=bool(keep),
                independent_superiority_confirmed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--diagnosis',type=Path,required=True)
    args=parser.parse_args()
    root,out,diagnosis=args.root.resolve(),args.output.resolve(),args.diagnosis.resolve()
    assert out.parent==root/'data/interim/official' and out.name.startswith('predictive_recency_') and not out.exists()
    assert diagnosis.parent==root/'data/interim/official' and diagnosis.name.startswith('predictive_diagnosis_')
    assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()=='entrenamiento-ML'
    authorization=verify_authorization(root)
    before=protected_hashes(root)
    artifact=FrozenArtifact(root/'ml/artifacts/official'/VERSION)
    assert digest(root/'ml/src/sigard_ml/forecasting/v3.py')==digest(artifact.path('implementation/v3.py'))
    diagnostic_manifest=json.loads((diagnosis/'manifest.private.json').read_text(encoding='utf-8'))
    assert digest(diagnosis/'development.private.json')==diagnostic_manifest['output_sha256']['development.private.json']
    # Physical output before first fit fixes the only change, inputs and stop rule.
    out.mkdir()
    write_json(out/'protocol.private.json',dict(SPECIFICATION,diagnosis_development_sha256=digest(diagnosis/'development.private.json'),authorization_inputs_sha256=authorization))
    panel=pd.read_parquet(artifact.path('horizon_1/modeling_panel.private.parquet'),filters=[('partition','in',['train','validation'])])
    development=panel.loc[panel.predictor_admissible & panel.target_count.notna()].copy()
    oof=join_panel(artifact.frame('horizon_1/development_predictions.private.parquet'),panel)
    output=[]
    training=[]
    for fold,validation in oof.groupby('fold',sort=True):
        train=training_window(development,validation)
        weights=recency_weights(train)
        estimator=make_pipeline(EmptyFeatureFallback(),HistGradientBoostingRegressor(loss='poisson',random_state=SPECIFICATION['seed'],**SPECIFICATION['base_parameters']))
        with threadpool_limits(limits=1):
            estimator.fit(matrix(train),train.target_count,histgradientboostingregressor__sample_weight=weights)
            values=estimator.predict(matrix(validation))
        part=validation[[c for c in validation.columns if c not in FEATURES]].copy()
        part[NAME]=values
        output.append(part)
        training.append(dict(fold=int(fold),n=len(train),weeks=int(train.target_week.nunique()),
            train_target_end=str(train.target_end.max()),validation_first_origin=str(validation.origin_week.min()),
            mean=float(train.target_count.mean()),weighted_mean=float(np.average(train.target_count,weights=weights)),
            weight_min=float(weights.min()),weight_max=float(weights.max()),kish_effective_rows=float(weights.sum()**2/(weights**2).sum()),
            equivalent_weighted_weeks=float(pd.Series(weights,index=train.index).groupby(train.target_week).sum().sum()**2/(pd.Series(weights,index=train.index).groupby(train.target_week).sum()**2).sum())))
        print(json.dumps(dict(fold=int(fold),fit_complete=True)),flush=True)
    predictions=pd.concat(output,ignore_index=True)
    result=evaluate(predictions)
    result.update(training=training,fit_count=3,comparison_read=False,new_outcomes_read=False,production_enabled=False)
    write_json(out/'result.private.json',result)
    predictions.to_parquet(out/'predictions.private.parquet',index=False)
    artifact.unchanged()
    assert protected_hashes(root)==before
    assert authorization==verify_authorization(root)
    write_json(out/'manifest.private.json',dict(inputs_sha256=artifact.inputs,script_sha256=digest(Path(__file__)),
        protocol_sha256=digest(out/'protocol.private.json'),protected_files=len(before),protected_unchanged=True,
        permissions_unchanged=True,independent_delivery_training_embargo=True,
        outputs_sha256={p.name:digest(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(completed=True,fit_count=3,retain_candidate=result['retain_candidate'],metrics=result['metrics'])),flush=True)


if __name__=='__main__':
    main()
