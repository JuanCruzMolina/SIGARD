"""One prespecified, private census ablation; SELECT-only DB and no promotion."""
import argparse
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn

from sigard_ml.ingestion.census_2022 import digest
from sigard_ml.ingestion.epidemiology.db import connect, connection_url
from sigard_ml.forecasting.motor_data import load_frame
from sigard_ml.forecasting.motor_campaign import folds, write_new, code_hashes
from sigard_ml.forecasting.motor_models import fit_presence, fit_count, baselines, baseline_thresholds, matrix, inner_blocks
from sigard_ml.forecasting.motor_protocol import FEATURES, PROTOCOL, PRESENCE_BASELINES, COUNT_BASELINES
from sigard_ml.forecasting.motor_evaluation import presence_metrics, count_summary, paired_interval

METHODS=('rf_A_epi_climate','residual_h1')
CENSUS=('poblacion','densidad_poblacional')
VERSION='census-ablation-20261105-v1'


def scenarios(frame, context, master):
    """The original frame is unchanged; only B overrides as-of census features."""
    if context.radio_id.duplicated().any() or master.radio_id.duplicated().any():
        raise ValueError('duplicate_census_context')
    attributes=context.merge(master[['radio_id','superficie_km2']],on='radio_id',validate='one_to_one')
    if len(attributes)!=len(context) or attributes.superficie_km2.le(0).any():
        raise ValueError('missing_or_invalid_census_area')
    attributes['densidad_2022']=attributes.poblacion_2022/attributes.superficie_km2
    if not np.isfinite(attributes[['poblacion_2022','densidad_2022','superficie_km2']].to_numpy(float)).all():
        raise ValueError('invalid_census_context')
    selected=attributes.rename(columns={'radio_id':'radio_codigo','superficie_km2':'census_area'})
    joined=frame.merge(selected[['radio_codigo','poblacion_2022','densidad_2022','hogares_2022','viviendas_2022','census_area']],
                       on='radio_codigo',how='left',validate='many_to_one')
    if joined.poblacion_2022.isna().any() or not np.allclose(joined.superficie_km2,joined.census_area,rtol=1e-12,atol=0):
        raise ValueError('predictive_census_link_or_area_mismatch')
    strict=joined.copy();strict['census_scenario']='A_strict_historical_availability'
    retrospective=joined.copy();retrospective['census_scenario']='B_fixed_2022_retrospective_not_ex_ante'
    retrospective['poblacion']=retrospective.poblacion_2022
    retrospective['densidad_poblacional']=retrospective.densidad_2022
    return {'A':strict,'B':retrospective},attributes


def summarize(frame):
    presence=['rf_A_epi_climate_'+v for v in ('with_census','without_census')]+list(PRESENCE_BASELINES)
    counts=['residual_h1_'+v for v in ('with_census','without_census')]+list(COUNT_BASELINES)
    return dict(rows=len(frame),weeks=int(frame.target_week.nunique()),
        presence={name:presence_metrics(frame,name) for name in presence},
        counts={name:count_summary(frame,name) for name in counts},
        paired={method:paired_interval(frame,method+'_with_census',method+'_without_census',loss)
                for method,loss in zip(METHODS,('brier','mae'))})


def run(connection, output, evidence, context_dir, master_path):
    if output.exists():raise ValueError('new_campaign_directory_required')
    root=Path(__file__).resolve().parents[4]
    if not output.resolve().is_relative_to(root/'data/interim/official'):
        raise ValueError('private_output_required')
    proof=json.loads(evidence.read_text(encoding='utf-8'))
    if not proof['verified'] or proof['radios']!=263 or proof['common']!=256:
        raise ValueError('database_verification_required')
    manifest=json.loads((context_dir/'manifest.json').read_text(encoding='utf-8'))
    for name,sha in manifest['outputs_sha256'].items():
        if digest(context_dir/name)!=sha:raise ValueError('frozen_context_changed')
    if digest(master_path)!=manifest['master_sha256']:raise ValueError('master_changed')
    url=json.loads(connection.read_text(encoding='utf-8-sig'))['url'];parsed=connection_url(url)
    if parsed.port!=55439 or parsed.database!='sigard_epi_local_v1':raise ValueError('wrong_database')
    with connect(url) as conn:
        conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with conn.cursor() as cur:
            cur.execute('SELECT version,artefacto_sha256,md5(artefacto) FROM analytics.motor_modelo ORDER BY version')
            before=cur.fetchall()
            if [(a,b) for a,b,_ in before]!=[tuple(x) for x in proof['artifacts_before']]:
                raise ValueError('artifact_registry_changed_since_verification')
        version,sha,policy=proof['datasets'][0]
        frame,metadata=load_frame(conn,version,sha)
    context=pd.read_parquet(context_dir/'context.parquet')
    master=pd.read_parquet(master_path,columns=['radio_id','superficie_km2'])
    variants,attributes=scenarios(frame,context,master)
    # Audit every fold and inner RF fitting matrix BEFORE any estimator is fit.
    audit=[];eligible={}
    for scenario,data in variants.items():
        ok=True
        for block,train,evaluation in folds(data,[2021,2022,2023,2024]):
            base,_,_,threshold_ok,_=inner_blocks(train)
            for method in METHODS:
                fitting=base if method==METHODS[0] and threshold_ok else train
                counts=matrix(fitting,method)[list(CENSUS)].notna().sum().astype(int).to_dict()
                finite=all(v==len(fitting) for v in counts.values())
                ok &= finite and evaluation[list(CENSUS)].notna().all().all()
                audit.append(dict(scenario=scenario,block=block,method=method,fit_rows=len(fitting),
                    nonnull_census=counts,complete_census=bool(finite),
                    train_last_target=str(train.target_end.max()),first_evaluation_origin=str(evaluation.origin_week.min())))
        eligible[scenario]=bool(ok)
    output.mkdir(parents=True)
    frozen=dict(version=VERSION,authorization='explicit_project_owner_census_comparison_2026-11-05',
        methods=METHODS,features_with={m:list(FEATURES[m]) for m in METHODS},
        features_without={m:[x for x in FEATURES[m] if x not in CENSUS] for m in METHODS},
        unchanged_protocol=PROTOCOL,input=metadata,source_policy=policy,
        context_manifest_sha256=digest(context_dir/'manifest.json'),verification_sha256=digest(evidence),
        eligible_scenarios=eligible,matrix_audit=audit,code=code_hashes(),
        campaign_code_sha256=digest(__file__),environment=dict(python=platform.python_version(),sklearn=sklearn.__version__),
        comparison='paired refits with versus without population/density on identical folds; no old predictions mixed',
        primary_losses={'presence':'Brier','counts':'MAE'},development=[2021,2022,2023],
        comparison_2024='exploratory previously examined',warmup=2020,
        promotion=False,final_refit=False,db_writes=False,
        interpretation='B uses future census information for early years; never ex ante; A/B metrics never pooled')
    write_new(output/'protocol-before-fit.private.json',frozen)
    for name,data in variants.items():data.to_parquet(output/f'dataset-{name}.private.parquet',index=False)
    attributes.to_parquet(output/'census-context-263.private.parquet',index=False)
    results={};registry=[]
    for scenario,data in variants.items():
        if not eligible[scenario]:
            results[scenario]=dict(status='not_evaluated',reason='census_not_available_in_all_required_fitting_and_evaluation_matrices')
            continue
        parts=[]
        for block,train,evaluation in folds(data,[2021,2022,2023,2024]):
            if code_hashes()!=frozen['code'] or digest(__file__)!=frozen['campaign_code_sha256']:
                raise ValueError('campaign_code_changed')
            print(json.dumps(dict(scenario=scenario,block=block,status='fitting')),flush=True)
            predicted=evaluation[['radio_id','radio_codigo','origin_week','target_week','target_year','target_count','count_origin']].copy()
            references=baselines(train,evaluation)
            for name,values in references.items():predicted[name]=values
            for name,value in baseline_thresholds(train).items():predicted[name+'_threshold']=value
            predicted['tail_limit']=max(2.,float(train.target_count.quantile(.9)))
            predicted['week_limit']=max(1.,float(train.groupby('target_week').target_count.sum().quantile(.8)))
            for variant in ('without_census','with_census'):
                for method in METHODS:
                    names=frozen['features_without' if variant=='without_census' else 'features_with'][method]
                    model=fit_presence(train,method,features=names) if method==METHODS[0] else fit_count(train,features=names)
                    key=method+'_'+variant
                    score=lambda obj: obj.score(evaluation) if method==METHODS[0] else obj.predict(evaluation,references['count_latest'])
                    values=score(model)
                    if not np.isfinite(values).all():raise ValueError('nonfinite_campaign_predictions')
                    predicted[key]=values
                    if method==METHODS[0]:predicted[key+'_threshold']=model.threshold
                    path=output/f'{scenario}-{block}-{key}.private.joblib'
                    joblib.dump(model,path,compress=3)
                    if not np.array_equal(values,score(joblib.load(path))):raise ValueError('artifact_roundtrip_mismatch')
                    registry.append(dict(scenario=scenario,block=block,method=key,sha256=digest(path),metadata=model.metadata))
            predicted['block']=block;parts.append(predicted)
            predicted.to_parquet(output/f'{scenario}-{block}-predictions.private.parquet',index=False)
            print(json.dumps(dict(scenario=scenario,block=block,status='complete')),flush=True)
        combined=pd.concat(parts,ignore_index=True)
        combined.to_parquet(output/f'{scenario}-predictions.private.parquet',index=False)
        results[scenario]=dict(status='evaluated',development=summarize(combined.loc[combined.target_year.le(2023)]),
            exploratory_2024=summarize(combined.loc[combined.target_year.eq(2024)]),
            by_year={str(y):summarize(g) for y,g in combined.groupby('target_year')})
        write_new(output/f'{scenario}-metrics.private.json',results[scenario])
    with connect(url) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute('SELECT version,artefacto_sha256,md5(artefacto) FROM analytics.motor_modelo ORDER BY version')
            after=cur.fetchall()
    if before!=after:raise ValueError('existing_artifact_registry_changed')
    report=dict(version=VERSION,database_verified=True,valid_population_density_radios=len(attributes),common_radios=256,
        original_artifacts_verified_unchanged=len(before),new_local_artifacts=len(registry),
        scenarios=results,operational_promotion=False,
        files_sha256={p.name:digest(p) for p in output.iterdir() if p.is_file()})
    write_new(output/'artifact-registry.private.json',registry)
    write_new(output/'report.private.json',report)
    print(json.dumps(dict(status='complete',scenarios=eligible,new_artifacts=len(registry))),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('connection','output','evidence','context-dir','master-path'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.connection,args.output,args.evidence,args.context_dir,args.master_path)


if __name__=='__main__':main()
