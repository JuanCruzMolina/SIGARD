"""Read-only offline projection of the selected stage2 outputs and stage1 labels.

No fitting, source mutations, migrations, estimators or individual point export.
The HTTP process reads the resulting pinned aggregate bundle, not PostgreSQL.
"""
import argparse
from collections import defaultdict
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from sigard_ml.data_access import MLRepository,DatasetBlocked
from sigard_ml.forecasting.consolidation import ROOT,PRIVATE,POLICY
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_data import load_frame
from sigard_ml.forecasting.motor_models import baselines,baseline_thresholds,purge_training
from sigard_ml.forecasting.motor_protocol import PROTOCOL
from sigard_ml.forecasting.option_b_data import json_dump
from sigard_ml.ingestion.epidemiology.db import connect

SCHEMA='sigard-historical-backtest/1'
EVALUATION='event_time_retrospective_reconstruction'
SELECTED={'presence':'presence_seasonal','quantity':'count_latest'}


def number(value,integer=False):
    if value is None or (isinstance(value,float) and np.isnan(value)):return None
    value=float(value)
    if not np.isfinite(value) or value<0:raise DatasetBlocked('backtest_invalid_nonnegative_value')
    if integer and not value.is_integer():raise DatasetBlocked('backtest_observed_count_not_integer')
    return int(value) if integer else value


def project_week(week,source,predictions,training,context):
    """Whitelist aggregate fields, preserving unknowns and the seven masked units."""
    covered=2020<=int(week['anio'])<=2024
    target=week['inicio'];origin=target-timedelta(days=7)
    if not covered:status,reason='outside_coverage','no_eligible_source_coverage'
    elif any(row['mascara_comun'] and row['cantidad_sigard'] is None for row in source):
        status,reason='territorial_uncertainty','territorial_attribution_not_complete'
    elif not training:status,reason='insufficient_training_support','no_verified_stage2_prediction_for_warmup'
    else:status,reason='available',None
    if training and date.fromisoformat(str(training['fit_end']))>=origin-timedelta(days=28):
        raise DatasetBlocked('backtest_fit_not_before_purged_origin')
    output=[]
    for r in source:
        common=bool(r['mascara_comun']);pred=predictions.get(int(r['radio_id']))
        row_status=status if common else 'outside_common_territory'
        row_reason=reason if common else 'excluded_by_versioned_common_mask'
        if status=='outside_coverage':row_status,row_reason=status,reason
        if row_status=='available' and pred is None:raise DatasetBlocked('backtest_incomplete_frozen_predictions')
        available=row_status=='available'
        score=number(pred['presencia'][SELECTED['presence']]) if available else None
        threshold=number(pred['umbrales'][SELECTED['presence']]) if available else None
        predicted_count=number(pred['cantidad'][SELECTED['quantity']]) if available else None
        baseline=number(pred['cantidad']['count_latest']) if available else None
        if available and (score>1 or threshold>1):raise DatasetBlocked('backtest_invalid_presence_score')
        observed_count=number(r['cantidad_sigard'],True) if covered else None
        observed_presence=number(r['presencia_sigard'],True) if covered else None
        decision=int(score>=threshold) if available else None
        confusion=None
        if decision is not None and observed_presence is not None:
            confusion='TP' if decision and observed_presence else 'FP' if decision else 'FN' if observed_presence else 'TN'
        difference=predicted_count-observed_count if predicted_count is not None and observed_count is not None else None
        output.append(dict(radio_id=r['radio_codigo'],availability_status=row_status,unavailable_reason=row_reason,
            common_mask=common,territorial_quality=r['calidad_geografica'],coverage_status=r['cobertura_estado'],
            zero_provenance=r['procedencia_cero'],predicted=dict(presence_score=score,presence=decision,quantity=predicted_count),
            observed=dict(quantity=observed_count,presence=observed_presence,
                assigned_records=int(r['registros_asignados']) if covered else None,
                quality_counts={name:int(r[key]) if covered else None for name,key in
                    [('approximate','registros_aproximados'),('provisional','registros_provisionales'),('verified','registros_verificados')]}),
            baseline=dict(quantity=baseline),presence_threshold=threshold,confusion=confusion,
            difference=difference,absolute_error=abs(difference) if difference is not None else None))
    assigned_common=sum(r['observed']['assigned_records'] or 0 for r in output if r['common_mask'])
    assigned_masked=sum(r['observed']['assigned_records'] or 0 for r in output if not r['common_mask'])
    unassigned=int(source[0]['registros_sin_radio']) if covered else None
    department=week.get('department_count') if covered else None
    balanced=department==assigned_common+assigned_masked+(unassigned or 0) if covered else None
    if covered and not balanced:raise DatasetBlocked('backtest_department_not_reconciled')
    return dict(schema_version=SCHEMA,**context,target_year=int(week['anio']),target_epi_week=int(week['numero']),
        target_week=target.isoformat(),target_end=week['fin'].isoformat(),origin_week=origin.isoformat(),
        origin_end=(target-timedelta(days=1)).isoformat(),availability_status=status,unavailable_reason=reason,
        evaluation_type=EVALUATION,fit_last_target_end=str(training['fit_end']) if training else None,
        model_version={name:f"{context['campaign_version']}/{training['block']}/{method}" if training else None
            for name,method in SELECTED.items()},
        department=dict(observed_total=department,assigned_common_total=assigned_common if covered else None,
            assigned_masked_total=assigned_masked if covered else None,unassigned_total=unassigned,reconciled=balanced),rows=output)


def build_bundle(conn,config,output):
    repo=MLRepository(conn);campaign=config['campaign_version'];dataset=config['dataset_version']
    record=repo.query('SELECT * FROM analytics.motor_campania WHERE version=%s',(campaign,))
    if len(record)!=1 or record.iloc[0].dataset_version!=dataset or record.iloc[0].dataset_sha256!=config['dataset_sha256']:
        raise DatasetBlocked('backtest_stage2_campaign_or_dataset_mismatch')
    saved=record.iloc[0].to_dict()
    if saved['protocolo_sha256']!=canonical_hash(PROTOCOL):raise DatasetBlocked('backtest_protocol_changed')
    for path,sha in saved['codigo_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=sha:raise DatasetBlocked('backtest_stage2_code_changed')
    decision=repo.query("SELECT resultado FROM analytics.motor_evaluacion WHERE campania_version=%s AND etapa='decision'",(campaign,))
    if len(decision)!=1 or {k:decision.iloc[0,0][k]['selected'] for k in ('presence','counts')}!={
        'presence':SELECTED['presence'],'counts':SELECTED['quantity']}:
        raise DatasetBlocked('backtest_only_selected_stage2_references_supported')
    closure=repo.query("SELECT resultado FROM analytics.motor_evaluacion WHERE campania_version=%s AND etapa='closure'",(campaign,))
    if len(closure)!=1 or closure.iloc[0,0].get('operational_enabled') is not False:
        raise DatasetBlocked('backtest_verified_stage2_closure_required')
    frame,metadata=load_frame(conn,dataset,config['dataset_sha256'])
    source=repo.query('SELECT * FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s ORDER BY inicio,radio_codigo',(dataset,))
    source=source.astype(object).where(source.notna(),None).to_dict('records')
    weeks=repo.query('''SELECT w.*,d.cantidad_sigard department_count FROM analytics.semana_epidemiologica w
        JOIN analytics.consolidacion_dataset c ON c.version=%s AND c.calendario_version=w.calendario_version
        JOIN analytics.consolidacion_departamento d ON d.dataset_version=c.version AND d.semana_id=w.id ORDER BY w.inicio''',(dataset,))
    weeks=weeks.astype(object).where(weeks.notna(),None).to_dict('records')
    predictions=repo.query('SELECT * FROM analytics.motor_prediccion WHERE campania_version=%s ORDER BY semana_objetivo,radio_id',(campaign,)).to_dict('records')
    periods=repo.query('''SELECT bloque,min(ultimo_objetivo_ajuste) fit_end,max(ultimo_objetivo_ajuste) fit_end_max,count(*) methods
        FROM analytics.motor_modelo WHERE campania_version=%s AND nivel<>'final_refit' GROUP BY bloque''',(campaign,))
    by_block={r.bloque:dict(block=r.bloque,fit_end=r.fit_end) for r in periods.itertuples()}
    if any(r.methods!=4 or r.fit_end!=r.fit_end_max for r in periods.itertuples()):
        raise DatasetBlocked('backtest_block_training_metadata_inconsistent')
    # Verify selected baseline outputs using exactly the frozen stage2 routines.
    # This computes statistics; it never calls fit, train, calibrate or deserialize.
    by_prediction=defaultdict(dict);by_target=defaultdict(list)
    for p in predictions:
        if p['semana_objetivo']!=p['origen']+timedelta(days=7):raise DatasetBlocked('backtest_wrong_horizon')
        if p['radio_id'] in by_prediction[p['semana_objetivo']]:raise DatasetBlocked('backtest_duplicate_prediction')
        by_prediction[p['semana_objetivo']][p['radio_id']]=p
        by_target[p['bloque']].append(p)
    for block,rows in by_target.items():
        first=min(p['origen'] for p in rows);train=purge_training(frame,first)
        if train.target_end.max()!=by_block[block]['fit_end']:raise DatasetBlocked('backtest_training_cutoff_mismatch')
        lookup={(int(r['radio_id']),r['origen']):r for r in rows}
        evaluation=frame.loc[frame.apply(lambda row:(int(row.radio_id),row.origin_week) in lookup,axis=1)]
        values=baselines(train,evaluation);threshold=baseline_thresholds(train)[SELECTED['presence']]
        for i,r in enumerate(evaluation.itertuples()):
            p=lookup[(int(r.radio_id),r.origin_week)]
            if not (float(p['presencia'][SELECTED['presence']])==float(values[SELECTED['presence']][i])
                and float(p['cantidad'][SELECTED['quantity']])==float(values[SELECTED['quantity']][i])
                and float(p['umbrales'][SELECTED['presence']])==threshold):
                raise DatasetBlocked('backtest_selected_prediction_not_reproducible')
    geometry=repo.query('''SELECT r.codigo,t.mascara_comun,g.version,ST_AsGeoJSON(r.geom,9)::json geometry
        FROM analytics.consolidacion_territorio t JOIN territory.radio_censal r ON r.id=t.radio_id
        JOIN territory.version_geometria g ON g.id=r.version_geometria_id WHERE t.dataset_version=%s ORDER BY r.codigo''',(dataset,))
    if len(geometry)!=263 or geometry.mascara_comun.sum()!=256 or geometry.version.nunique()!=1:
        raise DatasetBlocked('backtest_territorial_universe_mismatch')
    context=dict(dataset_version=dataset,campaign_version=campaign,data_policy_version=POLICY,
        territory_version=geometry.version.iloc[0])
    by_source=defaultdict(list)
    for row in source:by_source[row['inicio']].append(row)
    output=Path(output).resolve()
    if not output.is_relative_to(PRIVATE) or output.exists():raise DatasetBlocked('backtest_new_private_output_required')
    output.mkdir(parents=True)
    files={}
    def write(name,value):
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        body=json_dump(value).encode('utf-8');path.write_bytes(body)
        files[name]=hashlib.sha256(body).hexdigest()
    geo=dict(type='FeatureCollection',features=[dict(type='Feature',properties=dict(radio_id=r.codigo,
        common_mask=bool(r.mascara_comun)),geometry=r.geometry) for r in geometry.itertuples()])
    write('geometry.private.json',geo)
    calendar=[]
    for week in weeks:
        candidates=list(by_prediction[week['inicio']].values())
        block={p['bloque'] for p in candidates}
        if len(block)>1:raise DatasetBlocked('backtest_multiple_prediction_blocks_for_week')
        training=by_block[next(iter(block))] if block else None
        document=project_week(week,by_source[week['inicio']],by_prediction[week['inicio']],training,context)
        write(f"weeks/{week['inicio']}.private.json",document)
        calendar.append({key:document[key] for key in ('target_year','target_epi_week','target_week','target_end',
            'origin_week','origin_end','availability_status','unavailable_reason')})
    write('calendar.private.json',dict(schema_version=SCHEMA,calendar_version='ar-snvs-2020-2026-v1',**context,
        weeks=calendar,radio_ids=geometry.codigo.tolist()))
    metadata_doc=dict(schema_version=SCHEMA,**context,evaluation_type=EVALUATION,selected_methods=SELECTED,
        method_kinds=dict(presence='statistical_reference',quantity='statistical_reference'),
        method_labels=dict(presence='Referencia territorial y estacional',quantity='Persistencia del último cierre'),
        arrival_availability='not_accredited',scores='experimental_uncalibrated_not_health_probabilities',
        operational_enabled=False,alerts_enabled=False,coverage_basis='project_owner_declared_coverage_2020_2024',
        included_2022_policy='project_positive_eligible_delivery_2022_original_clinical_classification_preserved',
        territory_radios=263,common_radios=256,dataset_sha256=config['dataset_sha256'],
        protocol_sha256=saved['protocolo_sha256'],horizon_weeks=1,purge_weeks=28//7,
        reference_is_not_trained_ml=True)
    write('metadata.private.json',metadata_doc)
    manifest=dict(schema_version=SCHEMA,local_read_authorized=True,**context,selected_methods=SELECTED,
        files=files,matrix_sha256=metadata['matrix_sha256'],prediction_rows=len(predictions),
        source_access='read_only_postgresql',training_performed=False)
    (output/'manifest.private.json').write_text(json_dump(manifest),encoding='utf-8')
    return dict(status='compiled',weeks=len(calendar),evaluable_weeks=sum(w['availability_status']=='available' for w in calendar),
        source_rows_unchanged=True,training_performed=False,manifest_sha256=hashlib.sha256((output/'manifest.private.json').read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection',type=Path,required=True);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:
        if any(not p.resolve().is_relative_to(PRIVATE) for p in (args.connection,args.config,args.output)):
            raise DatasetBlocked('backtest_private_paths_required')
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='entrenamiento-ML':raise DatasetBlocked('wrong_branch')
        cfg=json.loads(args.config.read_text(encoding='utf-8-sig'));url=json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
        with connect(url) as conn:
            conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
            result=build_bundle(conn,cfg,args.output);conn.rollback()
        print(json_dump(result));return 0
    except Exception as exc:
        print(json.dumps(dict(status='failed',error_class=type(exc).__name__,reason=str(exc) if isinstance(exc,DatasetBlocked) else 'check_backtest_compilation')));return 1


if __name__=='__main__':raise SystemExit(main())
