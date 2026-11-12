"""DB-only reconstruction of the single principal count target.

Target: eligible confirmed source records by recorded clinical reference week,
source-declared Capital residence. This is a filtered retrospective snapshot,
not all infections, accredited episodes, or a complete city surveillance total.
"""
from collections import Counter
from datetime import date, timedelta
import hashlib
import json

from psycopg2.extras import Json, execute_values

from sigard_ml.ingestion.epidemiology.analytics import seed_policies
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR, CALENDAR_VERSION

UNIT='capital_source_residence'
TARGET='eligible_confirmed_source_records_clinical_reference_week'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def read_records(conn, *, resolution_version, batch_ids):
    if not batch_ids or len(set(batch_ids))!=len(batch_ids):raise ValueError('explicit_unique_batches_required')
    with conn.cursor() as cur:
        cur.execute('SELECT version FROM epidemiology.version_resolucion WHERE version=%s',(resolution_version,))
        if not cur.fetchone():raise ValueError('unknown_resolution')
        cur.execute('''SELECT r.id,s.lote_id,r.disponible_desde,
            ARRAY(SELECT cc.codigo FROM epidemiology.clasificacion_registro obs
                LEFT JOIN epidemiology.revision_clasificacion rev ON rev.observacion_id=obs.id AND rev.version=%s
                LEFT JOIN epidemiology.catalogo_clasificacion cc ON cc.id=rev.catalogo_id WHERE obs.registro_id=r.id),
            ref.valor,ref.tipo,
            EXISTS(SELECT 1 FROM epidemiology.relacion_registro rel WHERE rel.registro_id=r.id AND rel.tipo='exact_duplicate'),
            EXISTS(SELECT 1 FROM epidemiology.relacion_registro rel WHERE (rel.registro_id=r.id OR rel.otro_id=r.id)
                AND rel.tipo IN ('same_external_id','possible_revision') AND rel.revision_estado='pending'),
            p.nombre,d.nombre,loc.nombre,
            geo.estado,geo.radio_id,geo.fraccion_id
            FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
            JOIN ingestion.lotes_sisa_vigentes batch ON batch.id=s.lote_id
            LEFT JOIN territory.domicilio dom ON dom.id=r.domicilio_id
            LEFT JOIN territory.localidad loc ON loc.id=dom.localidad_id
            LEFT JOIN territory.departamento d ON d.id=loc.departamento_id
            LEFT JOIN territory.provincia p ON p.id=d.provincia_id
            LEFT JOIN LATERAL(SELECT rev.valor,t.codigo tipo FROM epidemiology.fecha_registro f
                JOIN epidemiology.revision_fecha rev ON rev.fecha_id=f.id AND rev.version=%s AND rev.estado='valid'
                JOIN epidemiology.tipo_fecha t ON t.id=f.tipo_id AND t.codigo IN ('symptom_onset','sample_on')
                WHERE f.registro_id=r.id ORDER BY CASE t.codigo WHEN 'symptom_onset' THEN 0 ELSE 1 END,f.id LIMIT 1) ref ON true
            LEFT JOIN LATERAL(SELECT rev.estado,rev.radio_id,rr.fraccion_id FROM territory.geocodificacion g
                JOIN territory.asignacion_radio a ON a.geocodificacion_id=g.id
                JOIN territory.revision_asignacion rev ON rev.asignacion_id=a.id AND rev.version=%s
                LEFT JOIN territory.radio_censal rr ON rr.id=rev.radio_id
                WHERE g.registro_id=r.id ORDER BY a.id LIMIT 1) geo ON true
            WHERE s.lote_id=ANY(%s) ORDER BY r.id''',
            (resolution_version,resolution_version,resolution_version,list(batch_ids)))
        columns=['record_id','batch_id','available_on','classes','reference_date','date_type','exact_duplicate',
            'pending_identity','province','department','locality','geography_state','radio_id','fraction_id']
        rows=[dict(zip(columns,row)) for row in cur.fetchall()]
        cur.execute('SELECT id FROM ingestion.lotes_sisa_vigentes WHERE id=ANY(%s)',(list(batch_ids),))
        if {r[0] for r in cur.fetchall()}!=set(batch_ids):raise ValueError('missing_or_incomplete_batch')
    return rows


def spatial_support(records):
    selected=[r for r in records if eligibility(r)=='included']
    states=Counter(r['geography_state'] or 'missing' for r in selected)
    provisional=[r for r in selected if r['geography_state']=='unique_provisional']
    counts={}
    for key in ('radio_id','fraction_id'):
        optimistic=Counter(r[key] for r in selected if r[key] is not None)
        restricted=Counter(r[key] for r in provisional if r[key] is not None)
        counts[key]=dict(candidate_point_units=len(optimistic),provisional_only_units=len(restricted),
            candidate_point_records=sum(optimistic.values()),provisional_only_records=sum(restricted.values()),
            maximum_candidate_point_records_per_unit=max(optimistic.values(),default=0),
            minimum_candidate_point_records_per_unit=min(optimistic.values(),default=0),
            units_with_at_least_30_provisional_records=sum(n>=30 for n in restricted.values()))
    return dict(eligible_records=len(selected),precision_states=dict(states),units=counts,
        uncertain_fraction=1-len(provisional)/len(selected) if selected else None,
        accredited_radio_assignments=0,provisional_does_not_mean_verified_residence=True,
        error_bound_in_meters=None,fraction_error_bound_available=False,
        sensitivity='replacing point assignments by provisional-only membership removes all point_only records; no model fit on the artificial spatial labels',
        capital_count_invariant_to_point_reassignment=True,
        rationale='source residence identifies Capital for all eligible records; no documented error envelope to certify a radio or fraction')


def eligibility(row):
    if row['exact_duplicate']:return 'exact_duplicate'
    if row['pending_identity']:return 'unresolved_identifier_or_revision'
    if not row['classes'] or any(c is None for c in row['classes']) or set(row['classes'])!={'confirmado'}:
        return 'classification_not_unambiguously_confirmed'
    if (row['province'],row['department'],row['locality'])!=('la rioja','capital','la rioja'):
        return 'source_residence_outside_definition_or_missing'
    if row['reference_date'] is None:return 'missing_clinical_reference_date'
    try:year,_=DEFAULT_CALENDAR.date_week(row['reference_date'])
    except ValueError:return 'date_outside_verified_calendar'
    if year==2022:return '2022_classification_policy_separate'
    return 'included'


def proposed_coverage(records):
    """An explicit EXPERIMENTAL support envelope, never evidence of coverage.

    Missing weeks inside each observed year's envelope are assumed snapshot
    zeros only for this exactly filtered target. No gap between years is bridged.
    """
    by_year={}
    for row in records:
        if eligibility(row)!='included':continue
        year,number=DEFAULT_CALENDAR.date_week(row['reference_date'])
        week=DEFAULT_CALENDAR.week_bounds(year,number)[0]
        by_year.setdefault(year,[]).append(week)
    weeks=[]
    for year,values in sorted(by_year.items()):
        current=min(values)
        while current<=max(values):weeks.append(current);current+=timedelta(weeks=1)
    return weeks


def materialize_dataset(conn, *, version, resolution_version, batch_ids, climate_batch_id, covered_weeks,
                        authorization_ref, complementary_batch_ids=()):
    if not authorization_ref or not covered_weeks:raise ValueError('explicit_experimental_coverage_contract_required')
    seed_policies(conn)
    records=read_records(conn,resolution_version=resolution_version,batch_ids=batch_ids)
    covered=set(covered_weeks)
    if any(w.weekday()!=6 or DEFAULT_CALENDAR.date_week(w)[0]==2022 for w in covered):raise ValueError('invalid_coverage_week')
    # This separate definition does not lift the older radio masks or conservative labels.
    contract=dict(target=TARGET,unit=UNIT,reference_date='symptom_onset_else_sample_on; source date, not infection date',
        snapshot_population='only confirmed, dated, source-resident records without unresolved duplicate/revision relations',
        unknown_dates_excluded_from_filtered_target_not_imputed=True,
        scenario='experimental_assumed',covered_weeks=sorted(map(str,covered)),
        coverage_basis='explicit bounded project-owner-request scenario; envelope is not source completeness evidence',
        authorization_ref=authorization_ref,authorization_basis='project_owner_declared_provision',
        no_verified_city_surveillance_counts=True,retrospective_only=True,calendar=CALENDAR_VERSION,
        resolution_version=resolution_version,batch_ids=list(batch_ids),climate_batch_id=climate_batch_id,
        complementary_batch_ids=list(complementary_batch_ids),zero_is_epidemiological_absence=False)
    with conn.cursor() as cur:
        cur.execute('''SELECT c.fecha,c.temperatura_media,c.humedad_media,c.precipitacion,c.disponible_desde
            FROM epidemiology.clima_diario c JOIN ingestion.lotes_complementarios_vigentes b ON b.id=c.lote_id
            WHERE c.lote_id=%s ORDER BY c.fecha''',(climate_batch_id,));climate=cur.fetchall()
        if not climate:raise ValueError('climate_batch_not_available')
        cur.execute('SELECT version FROM analytics.dataset_predictivo WHERE version=%s',(version,))
        if cur.fetchone():raise ValueError('dataset_version_immutable')
        cur.execute('SELECT id,inicio,fin,anio FROM analytics.semana_epidemiologica WHERE calendario_version=%s ORDER BY inicio',(CALENDAR_VERSION,))
        weeks=cur.fetchall()
        if not covered<={w[1] for w in weeks}:raise ValueError('coverage_outside_calendar')
    fingerprint=canonical_hash(dict(contract=contract,records=records,climate=climate))
    counts=Counter();samples=Counter();exclusions=Counter();selected=[]
    included=[]
    for row in records:
        reason=eligibility(row);selected.append((version,row['record_id'],reason,reason=='included'))
        if reason!='included':exclusions[reason]+=1;continue
        year,number=DEFAULT_CALENDAR.date_week(row['reference_date'])
        start=DEFAULT_CALENDAR.week_bounds(year,number)[0]
        counts[start]+=1;samples[start]+=row['date_type']=='sample_on';included.append(row)
    pending_dates=exclusions['missing_clinical_reference_date']
    daily={r[0]:r for r in climate}
    series=[];weather=[]
    for wid,start,end,year in weeks:
        scope=start in covered
        # Conservative complete counts remain unknown, including positive subtotals.
        series.append((version,wid,'capital',counts[start],None,counts[start] if scope else None,
            'experimental_assumed' if scope else 'out_of_scope',samples[start],pending_dates,None,False))
        days=[daily[d] for i in range(7) if (d:=start+timedelta(days=i)) in daily]
        complete=len(days)==7
        values=(sum(r[1] for r in days)/7,sum(r[2] for r in days)/7,sum(r[3] for r in days)) if complete else (None,None,None)
        available=max(r[4] for r in days) if complete and all(r[4] is not None for r in days) else None
        weather.append((version,wid,*values,len(days),available))
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827193)')
            cur.execute('INSERT INTO analytics.dataset_predictivo(version,contrato,entrada_sha256,calendario_version,resolucion_version,unidad_espacial) VALUES(%s,%s,%s,%s,%s,%s)',
                (version,Json(contract),fingerprint,CALENDAR_VERSION,resolution_version,UNIT))
            execute_values(cur,'INSERT INTO analytics.fuente_dataset_predictivo VALUES %s',[(version,b) for b in batch_ids])
            complements=sorted(set([climate_batch_id,*complementary_batch_ids]))
            execute_values(cur,'INSERT INTO analytics.complemento_dataset_predictivo VALUES %s',[(version,b) for b in complements])
            execute_values(cur,'INSERT INTO analytics.seleccion_registro_predictivo VALUES %s',selected)
            execute_values(cur,'INSERT INTO analytics.serie_predictiva VALUES %s',series)
            execute_values(cur,'INSERT INTO analytics.clima_predictivo VALUES %s',weather)
    by_year={}
    for year in sorted({DEFAULT_CALENDAR.date_week(w)[0] for w in counts}):
        selected_weeks=[w for w in counts if DEFAULT_CALENDAR.date_week(w)[0]==year]
        by_year[str(year)]=dict(records=sum(counts[w] for w in selected_weeks),sample_date_proxy=sum(samples[w] for w in selected_weeks),
            observed_weeks=len(selected_weeks),assumed_weeks=sum(DEFAULT_CALENDAR.date_week(w)[0]==year for w in covered),
            first=str(min(selected_weeks)),last=str(max(selected_weeks)))
    return dict(dataset_version=version,entry_sha256=fingerprint,source_records=len(records),included_records=len(included),
        exclusions=dict(exclusions),by_year=by_year,conservative_trainable_rows=0,
        assumed_trainable_weeks=len(covered),contract=contract)


def read_series(conn, version):
    from sigard_ml.data_access import MLRepository
    return MLRepository(conn).core_series(version)
