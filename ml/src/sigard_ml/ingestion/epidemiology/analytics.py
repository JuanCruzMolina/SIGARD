"""DB-only, reproducible record-count projections. Does not train or query models."""
from collections import Counter,defaultdict
from datetime import date,datetime,time,timezone,timedelta
from psycopg2.extras import execute_values
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR,CALENDAR_VERSION
from .db import get_id

def seed_policies(conn):
    with conn:
        with conn.cursor() as cur:
            for entry in DEFAULT_CALENDAR.years:
                for number in range(1,entry.weeks+1):
                    start,end=DEFAULT_CALENDAR.week_bounds(entry.year,number)
                    cur.execute('INSERT INTO analytics.semana_epidemiologica(calendario_version,anio,numero,inicio,fin,semanas_anio) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(CALENDAR_VERSION,entry.year,number,start,end,entry.weeks))
            temporal=get_id(cur,'epidemiology.politica_temporal',dict(version='expanded-reference-db-1',descripcion='Symptoms, then sample. Never notification or arrival substitution.'))
            for n,code in enumerate(['symptom_onset','sample_on'],1):
                kind=get_id(cur,'epidemiology.tipo_fecha',dict(codigo=code))
                cur.execute('INSERT INTO epidemiology.prioridad_fecha VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(temporal,kind,n))
            classification=get_id(cur,'epidemiology.politica_clasificacion',dict(version='confirmed-provisional-db-1',definicion='Provisional records with explicit confirmed literal mapping; not accredited episodes'))
            confirmed=get_id(cur,'epidemiology.catalogo_clasificacion',dict(codigo='confirmado'))
            cur.execute('INSERT INTO epidemiology.clase_admitida VALUES(%s,%s) ON CONFLICT DO NOTHING',(classification,confirmed))
            return temporal,classification

def declare_coverage(conn,*,file_id,universe_id,criterion_id,start,end,state,evidence,reviewer):
    if state not in ['verified','experimental_assumed','unknown','out_of_scope'] or not evidence or not reviewer:raise ValueError('coverage_evidence_required')
    with conn:
        with conn.cursor() as cur:
            claim=get_id(cur,'epidemiology.cobertura_fuente',dict(archivo_id=file_id,universo_id=universe_id,criterio_id=criterion_id,inicio=start,fin=end))
            cur.execute('INSERT INTO epidemiology.revision_cobertura(cobertura_id,estado,evidencia,responsable) VALUES(%s,%s,%s,%s)',(claim,state,evidence,reviewer))

def materialize(conn,*,version,universe_version,start,end,scenario='conservative',coverage_weeks=None,coverage_ref=None,
                accept_provisional=False,mode='retrospective',cutoff=None,criterion_id=None,batch_ids=None,climate_version=None,
                resolution_version=None):
    temporal,classification=seed_policies(conn)
    cutoff=cutoff or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:raise ValueError('timezone_aware_cutoff_required')
    if scenario=='experimental_assumed' and (not coverage_weeks or not coverage_ref):raise ValueError('explicit_zero_scope_required')
    with conn:
        with conn.cursor() as cur:
            resolution_available=None
            if resolution_version:
                from .resolution import original_fingerprint
                cur.execute('SELECT entrada_sha256,creada_en FROM epidemiology.version_resolucion WHERE version=%s',(resolution_version,))
                reviewed=cur.fetchone()
                if not reviewed or reviewed[0]!=original_fingerprint(conn):raise ValueError('review_missing_or_stale')
                resolution_available=reviewed[1]
                if mode=='as_of' and resolution_available>cutoff:raise ValueError('review_not_available_at_cutoff')
            cur.execute('SELECT id FROM territory.universo WHERE version=%s',(universe_version,));row=cur.fetchone()
            if not row:raise ValueError('unknown_universe')
            universe=row[0]
            criterion=criterion_id or get_id(cur,'epidemiology.criterio_cobertura',dict(version=version+'-coverage',politica_clasificacion_id=classification,
                definicion_poblacion='Selected source records; not infections or episodes',filtro_extraccion=coverage_ref or 'No complete coverage evidence; unknown by default'))
            cur.execute('SELECT politica_clasificacion_id FROM epidemiology.criterio_cobertura WHERE id=%s',(criterion,))
            if cur.fetchone()[0]!=classification:raise ValueError('coverage_definition_mismatch')
            cur.execute('SELECT l.id,l.archivo_id,a.nombre_original FROM ingestion.lotes_sisa_vigentes l JOIN ingestion.archivo_fuente a ON a.id=l.archivo_id WHERE l.estado=%s',('complete',))
            available_batches=cur.fetchall()
            selected=[r for r in available_batches if batch_ids is None or r[0] in batch_ids]
            if len({r[2] for r in selected})!=len(selected) or len({r[1] for r in selected})!=len(selected):raise ValueError('select_one_batch_per_source_version')
            if batch_ids is not None and {r[0] for r in selected}!=set(batch_ids):raise ValueError('unknown_or_incomplete_batch')
            batches=[r[:2] for r in selected]
            if not batches:raise ValueError('no_imported_batches')
            # Source selection is explicit and versioned; same hash/importer cannot be counted twice.
            run=get_id(cur,'analytics.ejecucion',dict(version=version,universo_id=universe,politica_temporal_id=temporal,
                politica_clasificacion_id=classification,criterio_cobertura_id=criterion,inicio=start,fin=end,
                calendario_version=CALENDAR_VERSION,escenario=scenario,aceptar_geografia_provisional=accept_provisional,
                corte_informacion=cutoff,modo=mode,clima_version=climate_version,resolucion_version=resolution_version),keys=['version'])
            cur.execute('SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s',(run,))
            if cur.fetchone()[0]:raise ValueError('do_not_overwrite_analytics_run')
            for batch,file in batches:cur.execute('INSERT INTO analytics.fuente_ejecucion VALUES(%s,%s)',(run,batch))
            if scenario=='experimental_assumed':
                for week in coverage_weeks:
                    if not start<=week<=end:continue
                    for batch,file in batches:
                        claim=get_id(cur,'epidemiology.cobertura_fuente',dict(archivo_id=file,universo_id=universe,criterio_id=criterion,inicio=week,fin=week+timedelta(days=6)))
                        cur.execute('INSERT INTO epidemiology.revision_cobertura(cobertura_id,estado,evidencia,responsable) VALUES(%s,%s,%s,%s)',(claim,'experimental_assumed',coverage_ref,'project_owner_declared_provision'))
            cur.execute('SELECT r.id,r.codigo FROM territory.radio_censal r JOIN territory.miembro_universo m ON m.radio_id=r.id WHERE m.universo_id=%s',(universe,));radios=dict(cur.fetchall())
            cur.execute('SELECT id,inicio,fin FROM analytics.semana_epidemiologica WHERE calendario_version=%s AND inicio<=%s AND fin>=%s ORDER BY inicio',(CALENDAR_VERSION,end,start));weeks=cur.fetchall();week_map={w:(i,fin) for i,w,fin in weeks}
            cur.execute('''WITH effective_dates AS NOT MATERIALIZED (
                SELECT f.registro_id,f.tipo_id,
                CASE WHEN rev.fecha_id IS NOT NULL THEN rev.valor ELSE f.valor END valor,
                CASE WHEN rev.fecha_id IS NOT NULL THEN rev.estado ELSE f.estado END estado
                FROM epidemiology.fecha_registro f LEFT JOIN epidemiology.revision_fecha rev ON rev.fecha_id=f.id AND rev.version=%s),
                effective_classes AS (
                SELECT obs.registro_id,c.codigo FROM epidemiology.clasificacion_registro obs
                JOIN epidemiology.normalizacion_clasificacion n ON n.observacion_id=obs.id
                JOIN epidemiology.regla_normalizacion_clasificacion rule ON rule.id=n.regla_id
                JOIN epidemiology.catalogo_clasificacion c ON c.id=rule.catalogo_id WHERE %s IS NULL
                UNION ALL
                SELECT obs.registro_id,c.codigo FROM epidemiology.clasificacion_registro obs
                JOIN epidemiology.revision_clasificacion rev ON rev.observacion_id=obs.id AND rev.version=%s
                LEFT JOIN epidemiology.catalogo_clasificacion c ON c.id=rev.catalogo_id)
                SELECT r.id,r.disponible_desde, l.archivo_id,
                ARRAY(SELECT c.codigo FROM effective_classes c WHERE c.registro_id=r.id),
                (SELECT f.valor FROM effective_dates f JOIN epidemiology.prioridad_fecha p ON p.tipo_id=f.tipo_id WHERE f.registro_id=r.id AND p.politica_id=%s AND f.estado='valid' ORDER BY p.prioridad LIMIT 1),
                (SELECT t.codigo FROM effective_dates f JOIN epidemiology.tipo_fecha t ON t.id=f.tipo_id JOIN epidemiology.prioridad_fecha p ON p.tipo_id=f.tipo_id WHERE f.registro_id=r.id AND p.politica_id=%s AND f.estado='valid' ORDER BY p.prioridad LIMIT 1),
                CASE WHEN %s IS NULL THEN candidate.radio_id WHEN rev.estado='unique_provisional' THEN rev.radio_id END,
                CASE WHEN %s IS NULL THEN a.estado ELSE rev.estado END,
                EXISTS(SELECT 1 FROM epidemiology.relacion_registro rel WHERE rel.registro_id=r.id AND rel.tipo='exact_duplicate'),
                EXISTS(SELECT 1 FROM epidemiology.relacion_registro rel WHERE (rel.registro_id=r.id OR rel.otro_id=r.id) AND rel.tipo IN ('same_external_id','possible_revision') AND rel.revision_estado='pending')
                FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id JOIN ingestion.lote_importacion l ON l.id=s.lote_id
                JOIN analytics.fuente_ejecucion fe ON fe.lote_id=l.id AND fe.ejecucion_id=%s
                LEFT JOIN territory.geocodificacion g ON g.registro_id=r.id
                LEFT JOIN territory.asignacion_radio a ON a.geocodificacion_id=g.id
                AND a.version_geometria_id=(SELECT min(version_geometria_id) FROM territory.radio_censal rr JOIN territory.miembro_universo mm ON mm.radio_id=rr.id WHERE mm.universo_id=%s)
                LEFT JOIN territory.candidato_asignacion candidate ON candidate.asignacion_id=a.id AND candidate.seleccionado
                LEFT JOIN territory.revision_asignacion rev ON rev.asignacion_id=a.id AND rev.version=%s''',
                (resolution_version,resolution_version,resolution_version,temporal,temporal,
                 resolution_version,resolution_version,run,universe,resolution_version))
            records=cur.fetchall();observed=Counter();pending=Counter();approx=Counter();unassigned=0;excluded=Counter();availability=defaultdict(list)
            for rid,available,file,classes,ref,kind,radio,state,duplicate,repeated in records:
                reason=None
                if duplicate:reason='exact_duplicate'
                elif classes and all(c is not None for c in classes) and 'confirmado' not in classes:reason='classification_not_in_definition'
                elif mode=='as_of' and (available is None or available>cutoff):reason='availability_unverified_or_late'
                elif ref and not start<=ref<=end:reason='outside_analysis_interval'
                if reason:
                    excluded[reason]+=1;cur.execute('INSERT INTO analytics.exclusion_registro VALUES(%s,%s,%s)',(run,rid,reason));continue
                source_week=DEFAULT_CALENDAR.week_bounds(*DEFAULT_CALENDAR.date_week(ref))[0] if ref else None
                if radio is not None and radio not in radios:
                    reason='outside_selected_universe';excluded[reason]+=1
                    cur.execute('INSERT INTO analytics.exclusion_registro VALUES(%s,%s,%s)',(run,rid,reason));continue
                accepted=state=='verified' or (accept_provisional and state=='unique_provisional')
                problematic=(not classes or any(c is None for c in classes) or len(set(classes))>1 or not ref or repeated or not accepted)
                if problematic:
                    reason='pending_class_date_identity_or_geography';excluded[reason]+=1
                    cur.execute('INSERT INTO analytics.exclusion_registro VALUES(%s,%s,%s)',(run,rid,reason))
                    if not accepted:unassigned+=1
                    # Known exterior geometry is not an unknown city-wide location.
                    if state=='outside':continue
                    affected_radios=[radio] if radio in radios else list(radios)
                    affected_weeks=[source_week] if source_week in week_map else list(week_map) if not ref else []
                    for radio_id in affected_radios:
                        for w in affected_weeks:pending[radio_id,w]+=1
                    continue
                if source_week not in week_map:continue
                observed[radio,source_week]+=1
                if kind!='symptom_onset':approx[radio,source_week]+=1
                availability[radio,source_week].append(available)
            cur.execute('''SELECT c.inicio,c.fin,r.estado,r.revisada_en,c.archivo_id FROM epidemiology.cobertura_fuente c
                JOIN LATERAL (SELECT estado,revisada_en FROM epidemiology.revision_cobertura WHERE cobertura_id=c.id ORDER BY revisada_en DESC,id DESC LIMIT 1) r ON true
                WHERE c.universo_id=%s AND c.criterio_id=%s''',(universe,criterion))
            claims=cur.fetchall();rows=[];state_counts=Counter()
            for week_id,w,fin in weeks:
                scoped={file:state for a,b,state,reviewed,file in claims if a<=w and b>=fin and (mode=='retrospective' or reviewed<=cutoff)}
                selected_files={file for batch,file in batches}
                state='verified' if all(scoped.get(f)=='verified' for f in selected_files) else 'experimental_assumed' if scenario=='experimental_assumed' and all(scoped.get(f) in ['verified','experimental_assumed'] for f in selected_files) else 'unknown'
                if scenario=='experimental_assumed' and w not in set(coverage_weeks):state='out_of_scope'
                for radio in radios:
                    key=radio,w;obs=observed[key];pend=pending[key];near=approx[key]
                    partial=w<start or fin>end
                    count=obs if state in ['verified','experimental_assumed'] and pend==0 and near==0 and not partial else None
                    presence=1 if obs>0 else 0 if count==0 else None
                    # No reviewed compatibility for supervised 2022 objectives.
                    # Preserve observations; coverage assumptions cannot lift it.
                    if DEFAULT_CALENDAR.date_week(w)[0]==2022:
                        count=None;presence=None
                    # In as-of mode undated arrival information must not manufacture negatives.
                    if mode=='as_of' and excluded['availability_unverified_or_late']:
                        count=None;presence=1 if obs>0 else None
                    arrived=availability[key]
                    complete_arrival=bool(arrived) and all(v is not None for v in arrived)
                    coverage_arrivals=[reviewed for a,b,st,reviewed,file in claims if a<=w and b>=fin and st in ['verified','experimental_assumed']]
                    times=([v for v in arrived if v is not None]+coverage_arrivals
                           +([resolution_available] if resolution_available and mode=='as_of' else []))
                    last_available=max(times) if times else None
                    verified_availability=mode=='as_of' and (complete_arrival or (obs==0 and state=='verified'))
                    rows.append((run,radio,week_id,obs,count,None,presence,pend,near,state,'provisional_allowed' if accept_provisional else 'verified_only',last_available,verified_availability,partial))
                    state_counts[state]+=1
            execute_values(cur,'''INSERT INTO analytics.conteos_radio_semana(ejecucion_id,radio_id,semana_id,registros_observados,cantidad_registros,episodios_acreditados,presencia,pendientes_posibles,fechas_aproximadas,cobertura_estado,estado_asignacion,ultimo_disponible,disponibilidad_verificada,ventana_parcial) VALUES %s''',rows,page_size=1000)
            return dict(run_id=run,version=version,cells=len(rows),source_records=len(records),included_records=sum(observed.values()),
                excluded_records=dict(excluded),unassigned_records=unassigned,known_counts=sum(r[4] is not None for r in rows),
                positive_presence=sum(r[6]==1 for r in rows),coverage_cells=dict(state_counts),unit='source_records_not_episodes',unsupported_ml_years=[2022])
