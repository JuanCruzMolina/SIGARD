"""Explicit local stage-2 campaign. Training never runs on import or API startup."""
import argparse
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess

import joblib
import numpy as np
import pandas as pd
import sklearn
from psycopg2.extras import Json,execute_values

from sigard_ml.data_access import DatasetBlocked,MLRepository
from sigard_ml.data_access.tabular_guard import forbid_tabular_reads
from sigard_ml.forecasting.consolidation import ROOT,PRIVATE
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_protocol import PROTOCOL,PRESENCE,FEATURES,PRESENCE_BASELINES,COUNT_BASELINES
from sigard_ml.forecasting.motor_data import load_frame
from sigard_ml.forecasting.motor_models import fit_presence,fit_count,baselines,baseline_thresholds,purge_training
from sigard_ml.forecasting.motor_evaluation import summarize,select_presence,select_counts,granular_metrics,paired_interval
from sigard_ml.forecasting.option_b_data import json_dump
from sigard_ml.ingestion.epidemiology.db import connect,migrate


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x',encoding='utf-8') as stream:stream.write(json_dump(value))


def code_hashes():
    paths=list(Path(__file__).parent.glob('motor_*.py'))
    paths += [ROOT/p for p in ('ml/src/sigard_ml/forecasting/v3.py','ml/src/sigard_ml/forecasting/v2.py',
        'ml/src/sigard_ml/forecasting/core_data.py','ml/src/sigard_ml/forecasting/evaluation.py',
        'ml/src/sigard_ml/official/spatial_ml/experiment_protocol.py','ml/src/sigard_ml/official/spatial_ml/research_training.py',
        'ml/src/sigard_ml/official/calendar_rules.py','backend/database/epidemiology/010_consolidation.sql',
        'backend/database/epidemiology/011_motor_registry.sql')]
    return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths)}


def folds(frame, years):
    for year in years:
        dates=sorted(frame.loc[frame.target_year.eq(year)&frame.target_count.notna(),'target_week'].unique())
        if not dates:continue
        for left in range(0,len(dates),13):
            validation=frame.loc[frame.target_week.isin(dates[left:left+13])&frame.target_count.notna()].copy()
            train=purge_training(frame,validation.origin_week.min())
            if train.target_week.nunique()<PROTOCOL['minimum_training_weeks']:
                raise DatasetBlocked('motor_insufficient_expanding_training_support')
            yield f'{year}-q{left//13+1}',train,validation


def calculate_fold(train, evaluation):
    fitted={name:fit_presence(train,name) for name in PRESENCE}
    fitted['residual_h1']=fit_count(train)
    result=evaluation[['radio_id','radio_codigo','origin_week','target_week','target_end','target_year',
        'target_count','count_origin']].copy()
    reference=baselines(train,evaluation)
    for name,values in reference.items():result[name]=values
    for name in PRESENCE:
        result[name]=fitted[name].score(evaluation)
        result[name+'_raw']=fitted[name].score(evaluation,raw=True)
        result[name+'_threshold']=fitted[name].threshold
        result[name+'_calibrated']=fitted[name].calibrator is not None
    for name,threshold in baseline_thresholds(train).items():result[name+'_threshold']=threshold
    result['residual_h1']=fitted['residual_h1'].predict(evaluation,reference['count_latest'])
    result['tail_limit']=max(2.,float(train.target_count.quantile(.9)))
    result['week_limit']=max(1.,float(train.groupby('target_week').target_count.sum().quantile(.8)))
    if not np.isfinite(result[[*PRESENCE,*PRESENCE_BASELINES,'residual_h1',*COUNT_BASELINES]].to_numpy(float)).all():
        raise DatasetBlocked('motor_nonfinite_prediction')
    return result,fitted


def register_evaluation(conn,campaign,stage,result):
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO analytics.motor_evaluacion(campania_version,etapa,resultado,resultado_sha256) VALUES(%s,%s,%s,%s)',
                (campaign,stage,Json(result,dumps=json_dump),canonical_hash(result)))


def register_model(conn,campaign,block,level,method,model,fit_end,output):
    buffer=io.BytesIO();joblib.dump(model,buffer,compress=3);payload=buffer.getvalue()
    sha=hashlib.sha256(payload).hexdigest()
    path=output/f'{block}-{method}.private.joblib'
    with path.open('xb') as stream:stream.write(payload)
    with conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO analytics.motor_modelo(version,campania_version,metodo,capacidad,bloque,nivel,
                ultimo_objetivo_ajuste,artefacto,artefacto_sha256,metadatos) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (f'{campaign}-{block}-{method}',campaign,method,'counts' if method=='residual_h1' else 'presence',
                 block,level,fit_end,payload,sha,Json(model.metadata,dumps=json_dump)))
    return dict(method=method,block=block,artifact_sha256=sha,artifact_bytes=len(payload),
        fit_last_target_end=str(fit_end),metadata=model.metadata)


def register_predictions(conn,campaign,block,predictions):
    values=[]
    for row in predictions.itertuples(index=False):
        values.append((campaign,int(row.radio_id),row.origin_week,row.target_week,block,
            Json({name:float(getattr(row,name)) for name in (*PRESENCE,*PRESENCE_BASELINES)}),
            Json({name:float(getattr(row,name+'_threshold')) for name in (*PRESENCE,*PRESENCE_BASELINES)}),
            Json({name:float(getattr(row,name)) for name in ('residual_h1',*COUNT_BASELINES)})))
    with conn:
        with conn.cursor() as cur:
            execute_values(cur,'''INSERT INTO analytics.motor_prediccion(campania_version,radio_id,origen,
                semana_objetivo,bloque,presencia,umbrales,cantidad) VALUES %s''',values,page_size=1000)


def baseline_parameters(train):
    result=dict(training_first_target=str(train.target_week.min()),training_last_target_end=str(train.target_end.max()),
        training_rows=len(train),trained_ml=False,protocol='training-only means and seasonality; persistence uses closed origin')
    counts=train.assign(presence=train.target_count.gt(0).astype(int)).groupby(['radio_id','target_number']).agg(
        n=('target_count','size'),count_sum=('target_count','sum'),presence_sum=('presence','sum')).reset_index()
    result['sufficient_statistics']=counts.to_dict('records')
    return result


def run_campaign(conn,config,output,progress=None):
    if (config.get('research_training_authorized') is not True or not config.get('authorization_ref')
            or config.get('authorization_basis')!='project_owner_declared_provision'):
        raise DatasetBlocked('explicit_stage2_research_training_authorization_required')
    output=Path(output).resolve()
    if not output.is_relative_to(PRIVATE):raise DatasetBlocked('motor_private_output_required')
    output.mkdir(parents=True,exist_ok=True)
    campaign=config['campaign_version']
    with forbid_tabular_reads():
        frame,metadata=load_frame(conn,config['dataset_version'],config['dataset_sha256'])
    hashes=code_hashes()
    environment=dict(python=platform.python_version(),sklearn=sklearn.__version__,numpy=np.__version__,pandas=pd.__version__)
    frozen=dict(protocol=PROTOCOL,protocol_sha256=canonical_hash(PROTOCOL),code_sha256=hashes,
        input=metadata,environment=environment,authorization_ref=config['authorization_ref'])
    # This durable record and SQL registration both precede the first fit.
    write_new(output/'protocol-before-fit.private.json',frozen)
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO analytics.motor_campania(version,dataset_version,protocolo,protocolo_sha256,dataset_sha256,codigo_sha256,entorno,autorizacion) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                (campaign,config['dataset_version'],Json(PROTOCOL),canonical_hash(PROTOCOL),config['dataset_sha256'],Json(hashes),Json(environment),config['authorization_ref']))
    parts=[];registry=[];fold_metadata=[]
    decision=None;dev_metrics=None;comparison_metrics=None
    for phase,years in [('development',PROTOCOL['development_target_years']),('comparison',PROTOCOL['comparison_target_years'])]:
        period=[]
        for block,train,evaluation in folds(frame,years):
            if code_hashes()!=hashes:raise DatasetBlocked('motor_code_changed_during_campaign')
            if progress:progress(dict(phase=phase,block=block,status='fitting',train_rows=len(train),evaluation_rows=len(evaluation)))
            with forbid_tabular_reads():
                predicted,models=calculate_fold(train,evaluation)
            predicted['block']=block
            entries=[]
            for method,model in models.items():
                entry=register_model(conn,campaign,block,'development_fold' if phase=='development' else 'comparison_fold',
                    method,model,train.target_end.max(),output)
                # Registered bytes must reproduce the exact same predictions.
                restored=joblib.load(output/f'{block}-{method}.private.joblib')
                expected=predicted[method].to_numpy(float)
                actual=restored.predict(evaluation,predicted.count_latest) if method=='residual_h1' else restored.score(evaluation)
                if not np.array_equal(expected,actual):raise DatasetBlocked('motor_artifact_roundtrip_changed_predictions')
                entries.append(entry)
            register_predictions(conn,campaign,block,predicted)
            # Research run is DB-only; writing its derived predictions does not read tabular files.
            predicted.to_parquet(output/f'{block}-predictions.private.parquet',index=False)
            fold_metadata.append(dict(block=block,phase=phase,training_rows=len(train),training_weeks=int(train.target_week.nunique()),
                training_first_target=str(train.target_week.min()),training_last_target_end=str(train.target_end.max()),
                first_origin=str(evaluation.origin_week.min()),last_target=str(evaluation.target_week.max()),
                matrix_sha256=canonical_hash(train[['radio_id','origin_week','target_count']].to_dict('records')),
                methods=entries))
            registry.extend(entries);period.append(predicted);parts.append(predicted)
            if progress:progress(dict(phase=phase,block=block,status='registered'))
        combined=pd.concat(period,ignore_index=True)
        metrics=summarize(combined)
        write_new(output/f'{phase}-metrics.private.json',metrics)
        register_evaluation(conn,campaign,'development' if phase=='development' else 'comparison_2024',metrics)
        if phase=='development':
            dev_metrics=metrics
            decision=dict(presence=select_presence(combined,metrics),counts=select_counts(combined,metrics),
                climate_contribution=dict(brier_with_climate=metrics['presence'][PRESENCE[1]]['brier'],
                    brier_without_climate=metrics['presence'][PRESENCE[2]]['brier'],
                    paired_interval=paired_interval(combined,PRESENCE[1],PRESENCE[2],'brier')),
                independent_external_validation=False,operational_enabled=False)
            write_new(output/'decision-before-2024.private.json',decision)
            register_evaluation(conn,campaign,'decision',decision)
        else:comparison_metrics=metrics
        write_new(output/f'{phase}-granular.private.json',granular_metrics(combined))
    final_train=frame.loc[frame.target_count.notna()&frame.target_year.le(2024)].copy()
    final=dict(selected_presence=decision['presence']['selected'],selected_counts=decision['counts']['selected'],
        baseline_parameters=baseline_parameters(final_train),models=[],operational_enabled=False)
    selected=[decision['presence']['selected'],decision['counts']['selected']]
    for method in selected:
        if method not in FEATURES:continue
        with forbid_tabular_reads():
            model=fit_count(final_train) if method=='residual_h1' else fit_presence(final_train,method)
        entry=register_model(conn,campaign,'final','final_refit',method,model,final_train.target_end.max(),output)
        final['models'].append(entry)
    write_new(output/'final-methods.private.json',final)
    register_evaluation(conn,campaign,'final_refit',final)
    write_new(output/'fold-registry.private.json',fold_metadata)
    all_predictions=pd.concat(parts,ignore_index=True)
    all_predictions.to_parquet(output/'all-predictions.private.parquet',index=False)
    result=dict(campaign_version=campaign,dataset=metadata,decision=decision,
        development=dev_metrics,comparison_2024=comparison_metrics,final=final,
        model_artifacts=len(registry)+len(final['models']),prediction_rows=len(all_predictions),
        protocol_sha256=canonical_hash(PROTOCOL),code_sha256=hashes,
        retrospective_only=True,operational_enabled=False)
    write_new(output/'campaign-result.private.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if any(not p.resolve().is_relative_to(PRIVATE) for p in (args.connection,args.config,args.output)):
            raise DatasetBlocked('motor_private_paths_required')
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='entrenamiento-ML':
            raise DatasetBlocked('wrong_branch')
        url=json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
        config=json.loads(args.config.read_text(encoding='utf-8-sig'))
        migrate(url)
        with connect(url) as conn:
            result=run_campaign(conn,config,args.output,progress=lambda p:print(json.dumps(p),flush=True))
        print(json.dumps(dict(status='complete',presence=result['decision']['presence']['selected'],
            counts=result['decision']['counts']['selected'],operational_enabled=False)))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='failed',error_class=type(error).__name__,
            reason=str(error) if isinstance(error,DatasetBlocked) else 'inspect_private_motor_campaign')))
        return 1


if __name__=='__main__':raise SystemExit(main())
