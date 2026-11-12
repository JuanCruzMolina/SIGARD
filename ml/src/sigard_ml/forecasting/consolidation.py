"""Stage 1: one immutable, DB-only research snapshot for presence and counts.

No estimator imports, training, inference, source reimport or historical rewrite.
Only the inventory helper reads reviewed climate/territorial evidence files.
"""
import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess

from psycopg2.extras import Json, execute_values

from sigard_ml.data_access import MLRepository, DatasetBlocked
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.option_b_data import read_inputs, json_dump
from sigard_ml.ingestion.epidemiology.db import connect, migrate
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR, CALENDAR_VERSION

POLICY = 'sigard-project-positive-2022-covered-2020-2024-v1'
ROOT = Path(__file__).resolve().parents[4]
PRIVATE = ROOT / 'data/interim/official'


def decision(row, *, source_year, override_scope, as_of):
    """All failure reasons are retained, independently of clinical classification."""
    if override_scope not in ('delivery_2022', 'clinical_year_2022'):
        raise DatasetBlocked('explicit_2022_scope_required')
    failures = []
    when = row['reference_date']
    week = None
    if when is not None:
        try:
            week = DEFAULT_CALENDAR.date_week(when)
        except ValueError:
            failures.append('outside_verified_calendar')
    if row['exact_duplicate']:
        failures.append('exact_duplicate')
    if row['pending_identity']:
        failures.append('unresolved_identifier_or_revision')
    if not row['has_identifier']:
        failures.append('missing_source_identifier')
    if (row['province'], row['department'], row['locality']) != ('la rioja', 'capital', 'la rioja'):
        failures.append('source_residence_outside_definition_or_missing')
    if when is None:
        failures.append('missing_clinical_reference_date')
    elif when > as_of:
        failures.append('clinical_date_after_asof')
    if week and not 2020 <= week[0] <= 2024:
        failures.append('outside_declared_2020_2024_coverage')
    override = (source_year == 2022 if override_scope == 'delivery_2022' else bool(week and week[0] == 2022))
    confirmed = bool(row['classes']) and set(row['classes']) == {'confirmado'}
    if not (override or confirmed):
        failures.append('classification_not_unambiguously_confirmed_outside_override')
    return dict(eligible=not failures, reason=failures[0] if failures else 'included',
        checks=dict(failures=failures,classification_exception_2022=override,
            original_clinically_confirmed=confirmed,has_identifier=row['has_identifier'],
            exact_duplicate=row['exact_duplicate'],pending_identity=row['pending_identity'],
            source_year=source_year,clinical_year=when.year if when else None,
            epidemiological_year=week[0] if week else None,
            clinical_confirmation_changed=False))


def aggregate_weather(rows):
    """Sunday/Saturday weeks from all daily history, without inventing epi years."""
    daily = {}
    for row in rows:
        if row['fecha'] in daily:
            raise DatasetBlocked('duplicate_climate_day')
        daily[row['fecha']] = row
    if not daily:
        raise DatasetBlocked('missing_climate')
    first, last = min(daily), max(daily)
    start = first - timedelta(days=(first.weekday()+1) % 7)
    result = []
    while start <= last:
        days = [daily[start+timedelta(days=i)] for i in range(7) if start+timedelta(days=i) in daily]
        complete = len(days) == 7 and all(d[k] is not None for d in days for k in ('temperatura_media','humedad_media','precipitacion'))
        values = (sum(d['temperatura_media'] for d in days)/7,
            sum(d['humedad_media'] for d in days)/7,sum(d['precipitacion'] for d in days)) if complete else (None,None,None)
        available = max(d['disponible_desde'] for d in days) if complete and all(d['disponible_desde'] is not None for d in days) else None
        result.append((start,start+timedelta(days=6),len(days),*values,available))
        start += timedelta(days=7)
    return result


def load_inputs(conn, config):
    repo = MLRepository(conn)
    records, sources = read_inputs(repo, resolution_version=config['resolution_version'], batch_ids=config['batch_ids'])
    extras = repo.query('''SELECT r.id,(nullif(btrim(r.identificador_externo),'') IS NOT NULL) has_identifier,
        s.numero_fila,ARRAY(SELECT c.valor_literal FROM epidemiology.clasificacion_registro c
        WHERE c.registro_id=r.id ORDER BY c.id) original_classes
        FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
        WHERE s.lote_id=ANY(%s) ORDER BY r.id''', (config['batch_ids'],))
    extra = {int(r.id):r for r in extras.itertuples()}
    for row in records:
        e = extra[row['record_id']]
        row.update(has_identifier=bool(e.has_identifier),source_row=int(e.numero_fila),original_classes=list(e.original_classes))
        row['classes'] = sorted(row['classes'],key=lambda v:(v is None,str(v)))
    for source in sources:
        expected = config['source_contract'][str(source['lote_id'])]
        if source['sha256'] != expected['sha256']:
            raise DatasetBlocked('pinned_source_changed')
    weather = repo.query('''SELECT c.* FROM epidemiology.clima_diario c
        JOIN ingestion.lotes_complementarios_vigentes b ON b.id=c.lote_id
        JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id
        WHERE c.lote_id=%s AND a.sha256=%s ORDER BY c.fecha''',
        (config['climate_batch_id'],config['climate_sha256'])).to_dict('records')
    if not weather or len({r['estacion_id'] for r in weather}) != 1:
        raise DatasetBlocked('climate_station_missing_or_ambiguous')
    weeks = repo.calendar()
    expected = {DEFAULT_CALENDAR.week_bounds(y.year,n)[0] for y in DEFAULT_CALENDAR.years for n in range(1,y.weeks+1)}
    if set(weeks.inicio) != expected or weeks.inicio.duplicated().any():
        raise DatasetBlocked('calendar_incomplete_or_duplicated')
    for row in weeks.itertuples():
        if (row.inicio,row.fin) != DEFAULT_CALENDAR.week_bounds(int(row.anio),int(row.numero)):
            raise DatasetBlocked('calendar_bounds_mismatch')
    territory = repo.query('''SELECT r.id,r.codigo,g.version,g.fuente_sha256,
        ST_IsValid(r.geom) valid,ST_IsEmpty(r.geom) empty,ST_SRID(r.geom) srid,
        x.poblacion,x.superficie_km2,x.cantidad_vecinos,x.fuente_sha256 contexto_sha256,x.disponible_desde,
        EXISTS(SELECT 1 FROM territory.miembro_universo m JOIN territory.universo v ON v.id=m.universo_id
            WHERE m.radio_id=r.id AND v.version='v3-256-subset-v1') en_v3
        FROM territory.miembro_universo m JOIN territory.universo u ON u.id=m.universo_id
        JOIN territory.radio_censal r ON r.id=m.radio_id JOIN territory.version_geometria g ON g.id=r.version_geometria_id
        LEFT JOIN analytics.contexto_radio x ON x.radio_id=r.id AND x.universo_id=u.id
        WHERE u.version='ab-263-master-v1' ORDER BY r.codigo''').to_dict('records')
    if len(territory) != 263 or sum(r['en_v3'] for r in territory) != 256:
        raise DatasetBlocked('territorial_membership_contract_changed')
    for r in territory:
        if not r['valid'] or r['empty'] or r['srid'] != 4326:
            raise DatasetBlocked('invalid_postgis_master')
    return records,sources,weather,weeks,territory


def materialize(conn, config):
    """Idempotent for identical pinned inputs; conflicting versions fail closed."""
    if (config.get('authorization_basis') != 'project_owner_declared_provision'
            or not config.get('authorization_ref') or config.get('training_authorized') is not False):
        raise DatasetBlocked('stage1_owner_declaration_without_training_required')
    if config.get('policy_version') != POLICY or config.get('coverage_years') != list(range(2020,2025)):
        raise DatasetBlocked('stage1_policy_contract_required')
    records,sources,weather,weeks,territory = load_inputs(conn,config)
    version = config['dataset_version']
    as_of = date.fromisoformat(config['as_of'])
    selection = []
    # Existing repository calendar projects only dates; obtain stable FK IDs separately.
    with conn.cursor() as cur:
        cur.execute('SELECT inicio,id FROM analytics.semana_epidemiologica WHERE calendario_version=%s',(CALENDAR_VERSION,))
        week_ids = dict(cur.fetchall())
    decisions = []
    for r in records:
        source_year = config['source_contract'][str(r['batch_id'])]['delivery_year']
        choice = decision(r,source_year=source_year,override_scope=config['override_2022_scope'],as_of=as_of)
        decisions.append(dict(record_id=r['record_id'],**choice))
        start = None
        if r['reference_date']:
            try: start = DEFAULT_CALENDAR.week_bounds(*DEFAULT_CALENDAR.date_week(r['reference_date']))[0]
            except ValueError: pass
        selection.append((version,r['record_id'],r['batch_id'],r['reference_date'],week_ids.get(start),r['date_type'],
            Json(r['original_classes']),Json(r['classes']),choice['eligible'],choice['eligible'],choice['reason'],Json(choice['checks']),
            r['assignment_id'],r['radio_id'],r['quality'],r['available_on']))
    climate = aggregate_weather(weather)
    evidence = config['territorial_evidence']
    masks = []
    for r in territory:
        common = r['en_v3'] and r['poblacion'] is not None and r['superficie_km2'] is not None
        reason = 'common_valid_256' if common else 'excluded_from_historical_v3_locality_scope' if not r['en_v3'] else 'missing_census_context'
        masks.append((version,r['id'],True,r['en_v3'],common,reason,Json(evidence.get(r['codigo'],{}))))
    contract = dict(config=config,calendar_version=CALENDAR_VERSION,target='eligible_SIGARD_source_records_not_clinical_confirmation',
        coverage_basis='project_owner_declared_coverage_2020_2024_not_institutional_certification',
        climate_resolution='single_reference_point_shared_context_not_radio_measurements',
        retrospective=True,operational_authorized=False,training_performed=False,
        census_context='2022 fixed descriptive context; asof predictor requires known availability and year>=2022',
        source_metadata=sources)
    fingerprint = canonical_hash(dict(contract=contract,records=records,decisions=decisions,
        weather=weather,territory=territory,climate=climate))
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827195)')
            cur.execute('SELECT entrada_sha256 FROM analytics.consolidacion_dataset WHERE version=%s',(version,))
            old = cur.fetchone()
            if old:
                if old[0] != fingerprint:
                    raise DatasetBlocked('immutable_consolidation_version_conflict')
                return dict(status='already_materialized',dataset_version=version,input_sha256=fingerprint,training_performed=False)
            cur.execute("SELECT id FROM territory.universo WHERE version='ab-263-master-v1'")
            universe = cur.fetchone()[0]
            cur.execute('INSERT INTO analytics.consolidacion_dataset(version,politica_version,calendario_version,resolucion_version,universo_id,clima_lote_id,contrato,entrada_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                (version,POLICY,CALENDAR_VERSION,config['resolution_version'],universe,config['climate_batch_id'],Json(contract,dumps=json_dump),fingerprint))
            execute_values(cur,'INSERT INTO analytics.consolidacion_fuente VALUES %s',[(version,r['lote_id'],config['source_contract'][str(r['lote_id'])]['delivery_year'],r['sha256']) for r in sources])
            execute_values(cur,'INSERT INTO analytics.consolidacion_territorio VALUES %s',masks)
            execute_values(cur,'INSERT INTO analytics.consolidacion_registro VALUES %s',selection)
            execute_values(cur,'INSERT INTO analytics.consolidacion_clima VALUES %s',[(version,*r) for r in climate])
    return dict(status='materialized',dataset_version=version,input_sha256=fingerprint,
        source_records=len(records),included=sum(r['eligible'] for r in decisions),
        exclusions=dict(Counter(r['reason'] for r in decisions if not r['eligible'])),
        climate_weeks=len(climate),common_radios=sum(r[4] for r in masks),training_performed=False)


def reconcile(conn, version):
    repo = MLRepository(conn)
    params = (version,)
    def rows(statement):
        frame = repo.query(statement,params)
        return frame.astype(object).where(frame.notna(),None).to_dict('records')
    return dict(dataset_version=version,
        by_delivery_year=rows('''SELECT f.anio_entrega,count(*) originales,
            count(*) FILTER(WHERE r.elegible) incluidos,count(*) FILTER(WHERE NOT r.elegible) excluidos,
            count(*) FILTER(WHERE r.fecha_referencia IS NULL) sin_fecha,
            count(*) FILTER(WHERE (r.comprobaciones->>'pending_identity')::boolean) identidad_pendiente,
            count(*) FILTER(WHERE (r.comprobaciones->>'exact_duplicate')::boolean) duplicados_tecnicos
            FROM analytics.consolidacion_registro r JOIN analytics.consolidacion_fuente f
            ON f.dataset_version=r.dataset_version AND f.lote_id=r.lote_id
            WHERE r.dataset_version=%s GROUP BY f.anio_entrega ORDER BY 1'''),
        by_epidemiological_year=rows('''SELECT anio,count(*) semanas,sum(cantidad_sigard) registros,
            count(*) FILTER(WHERE cantidad_sigard>0) semanas_positivas,
            count(*) FILTER(WHERE cantidad_sigard=0) semanas_cero,
            count(*) FILTER(WHERE cantidad_sigard IS NULL) no_disponibles,
            min(inicio) inicio,max(fin) fin FROM analytics.consolidacion_departamento
            WHERE dataset_version=%s GROUP BY anio ORDER BY anio'''),
        by_reference_year=rows('''SELECT extract(year FROM fecha_referencia)::integer anio_clinico,
            count(*) originales,count(*) FILTER(WHERE elegible) incluidos,
            count(*) FILTER(WHERE NOT elegible) excluidos FROM analytics.consolidacion_registro
            WHERE dataset_version=%s GROUP BY 1 ORDER BY 1 NULLS LAST'''),
        weekly=rows('''SELECT * FROM analytics.consolidacion_departamento WHERE dataset_version=%s ORDER BY inicio'''),
        reconciliation=repo.query('''SELECT count(*) FILTER(WHERE r.elegible) seleccion,
              count(*) FILTER(WHERE r.elegible AND t.mascara_comun) asignados_comunes,
              count(*) FILTER(WHERE r.elegible AND r.radio_id IS NOT NULL AND NOT coalesce(t.mascara_comun,false)) asignados_fuera_comun,
              count(*) FILTER(WHERE r.elegible AND r.radio_id IS NULL) sin_asignacion
              FROM analytics.consolidacion_registro r LEFT JOIN analytics.consolidacion_territorio t
                ON t.dataset_version=r.dataset_version AND t.radio_id=r.radio_id WHERE r.dataset_version=%s''',params).to_dict('records'),
        audit_2022=rows('''SELECT r.registro_id,s.numero_fila,r.fecha_referencia,r.tipo_fecha,r.clases_originales,r.clases_revisadas,
            r.elegible,r.positivo_sigard,r.motivo,r.comprobaciones,r.calidad_geografica,r.radio_id
            FROM analytics.consolidacion_registro r JOIN analytics.consolidacion_fuente f
              ON f.dataset_version=r.dataset_version AND f.lote_id=r.lote_id
            JOIN epidemiology.registro_epidemiologico e ON e.id=r.registro_id JOIN ingestion.fila_staging s ON s.id=e.fila_id
            WHERE r.dataset_version=%s AND f.anio_entrega=2022 ORDER BY r.registro_id'''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','inspect'])
    parser.add_argument('--connection',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    try:
        if any(not p.resolve().is_relative_to(PRIVATE) for p in (args.connection,args.config,args.report)) or args.report.exists():
            raise DatasetBlocked('new_private_report_and_private_configuration_required')
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip() != 'entrenamiento-ML':
            raise DatasetBlocked('wrong_branch')
        cfg = json.loads(args.config.read_text(encoding='utf-8-sig'))
        url = json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
        if args.action == 'prepare': migrate(url)
        with connect(url) as conn:
            if args.action == 'prepare': result = materialize(conn,cfg)
            else: result = reconcile(conn,cfg['dataset_version'])
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8') as stream:
            stream.write(json_dump(result))
        print(json.dumps(dict(status='complete',action=args.action,training_performed=False)))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='failed',error_class=type(error).__name__,
            reason=str(error) if isinstance(error,DatasetBlocked) else 'check_private_stage1_contract')))
        return 1


if __name__ == '__main__': raise SystemExit(main())
