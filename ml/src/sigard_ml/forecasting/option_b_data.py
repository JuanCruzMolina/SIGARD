"""New versioned research targets from PostgreSQL, separate from old masks.

Zeros mean no eligible SOURCE RECORD in this explicitly assumed scenario.
Unknown clinical dates/identity/classification are excluded, never fabricated.
Spatial variants retain their assignment IDs and different uncertainty levels.
"""
from collections import Counter
from datetime import date, timedelta

from psycopg2.extras import Json, execute_values

from sigard_ml.data_access import DatasetBlocked, MLRepository
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR

ZERO_POLICY = 'option_b_complete_years_assumed_zero_v1'
GEO_POLICIES = ('approximate_included', 'provisional_verified')
UNIVERSES = {'ab': ('ab-263-master-v1', 263), 'v3': ('v3-256-subset-v1', 256)}


def context_contract(repo, universe):
    context = repo.query('''SELECT r.codigo radio_censal,x.superficie_km2,x.poblacion,x.cantidad_vecinos,
        g.version version_territorial,x.fuente_sha256 contexto_sha256
        FROM territory.miembro_universo m JOIN territory.universo u ON u.id=m.universo_id
        JOIN territory.radio_censal r ON r.id=m.radio_id
        JOIN territory.version_geometria g ON g.id=r.version_geometria_id
        JOIN analytics.contexto_radio x ON x.universo_id=m.universo_id AND x.radio_id=m.radio_id
        WHERE u.version=%s ORDER BY r.codigo''',(universe,))
    edges = repo.query('''SELECT a.codigo origen,b.codigo vecino FROM territory.vecindad n
        JOIN territory.radio_censal a ON a.id=n.radio_id JOIN territory.radio_censal b ON b.id=n.vecino_id
        JOIN territory.miembro_universo ma ON ma.radio_id=a.id
        JOIN territory.miembro_universo mb ON mb.radio_id=b.id AND mb.universo_id=ma.universo_id
        JOIN territory.universo u ON u.id=ma.universo_id WHERE u.version=%s ORDER BY a.codigo,b.codigo''',(universe,))
    return dict(context_sha256=canonical_hash(context.to_dict('records')),edges_sha256=canonical_hash(edges.to_dict('records')))


def eligible(row, today):
    if row['exact_duplicate']:
        return 'exact_duplicate'
    if row['pending_identity']:
        return 'unresolved_identifier_or_revision'
    if not row['classes'] or any(v is None for v in row['classes']) or set(row['classes']) != {'confirmado'}:
        return 'classification_not_unambiguously_confirmed'
    if (row['province'], row['department'], row['locality']) != ('la rioja', 'capital', 'la rioja'):
        return 'source_residence_outside_definition_or_missing'
    when = row['reference_date']
    if when is None:
        return 'missing_clinical_reference_date'
    if when > today:
        return 'clinical_date_after_asof'
    try:
        DEFAULT_CALENDAR.date_week(when)
    except ValueError:
        return 'outside_calendar'
    # No new class mapping is applied to 2022 (or to any other year).
    return 'included'


def cutoff(source):
    candidates = [source.get('fecha_extraccion')]
    declaration = source.get('declaracion') or {}
    for key in ('fecha_corte', 'cutoff_date', 'cutoff', 'fecha_extraccion'):
        value = declaration.get(key)
        if isinstance(value, str):
            try:
                candidates.append(date.fromisoformat(value))
            except ValueError:
                pass
    return max((v for v in candidates if type(v) is date), default=None)


def coverage_scope(records, sources, calendar, *, today):
    """The clinical reference date, never a file name, decides optional years."""
    clinical = Counter()
    available_2026 = []
    source_by_batch = {r['lote_id']: r for r in sources}
    for row in records:
        seen = set()
        for when in row.get('clinical_dates', [row['reference_date']]):
            if when is None or when > today:
                continue
            try:
                year, _ = DEFAULT_CALENDAR.date_week(when)
            except ValueError:
                continue
            seen.add(year)
            if year == 2026:
                bound = cutoff(source_by_batch[row['batch_id']])
                if bound is not None and bound >= when:
                    available_2026.append(min(bound, today))
        clinical.update(seen)
    years = list(range(2020, 2025))
    if clinical[2025]:
        years.append(2025)
    upper_2026 = max(available_2026, default=None)
    if clinical[2026] and upper_2026:
        years.append(2026)
    covered = []
    for row in calendar.itertuples():
        if row.anio not in years:
            continue
        start, end = DEFAULT_CALENDAR.week_bounds(int(row.anio), int(row.numero))
        if (row.inicio, row.fin, row.semanas_anio) != (start, end, next(y.weeks for y in DEFAULT_CALENDAR.years if y.year == row.anio)):
            raise DatasetBlocked('calendar_rows_do_not_match_argentine_contract')
        if end > today or (row.anio == 2026 and end > upper_2026):
            continue
        covered.append(row.inicio)
    for year in range(2020, 2025):
        expected = {DEFAULT_CALENDAR.week_bounds(year, n)[0] for n in range(1, next(y.weeks for y in DEFAULT_CALENDAR.years if y.year == year) + 1)}
        actual = {w for w in covered if DEFAULT_CALENDAR.date_week(w)[0] == year}
        if actual != expected:
            raise DatasetBlocked('mandatory_2020_2024_calendar_incomplete')
    return dict(years=years, covered_weeks=sorted(covered), clinical_years=dict(clinical),
        cutoff_2026=upper_2026,
        optional_years={str(y): dict(clinical_records=int(clinical[y]), included=y in years,
            reason=('clinical_dates_absent' if not clinical[y] else 'source_cutoff_not_supported' if y == 2026 and not upper_2026
                    else 'clinical_dates_present_full_year_assumed' if y == 2025 else 'source_cutoff_bounded_complete_weeks')) for y in (2025, 2026)})


def read_inputs(repo, *, resolution_version, batch_ids):
    pending = repo.query('''WITH selected AS (
        SELECT r.id FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
        WHERE s.lote_id=ANY(%s)) SELECT
        (SELECT count(*) FROM epidemiology.clasificacion_registro c JOIN selected r ON r.id=c.registro_id
          LEFT JOIN epidemiology.revision_clasificacion rev ON rev.observacion_id=c.id AND rev.version=%s
          WHERE rev.observacion_id IS NULL) missing_classes,
        (SELECT count(*) FROM epidemiology.fecha_registro f JOIN selected r ON r.id=f.registro_id
          JOIN epidemiology.tipo_fecha t ON t.id=f.tipo_id AND t.codigo IN ('symptom_onset','sample_on')
          LEFT JOIN epidemiology.revision_fecha rev ON rev.fecha_id=f.id AND rev.version=%s
          WHERE rev.fecha_id IS NULL) missing_dates,
        (SELECT count(*) FROM territory.geocodificacion g JOIN selected r ON r.id=g.registro_id
          JOIN territory.asignacion_radio a ON a.geocodificacion_id=g.id
          LEFT JOIN territory.revision_asignacion rev ON rev.asignacion_id=a.id AND rev.version=%s
          WHERE rev.asignacion_id IS NULL AND a.estado<>'verified') missing_assignments''',
        (list(batch_ids),resolution_version,resolution_version,resolution_version))
    if pending.iloc[0].ne(0).any():
        raise DatasetBlocked('selected_clinical_observations_or_assignments_not_reviewed')
    records = repo.records(resolution_version=resolution_version, batch_ids=batch_ids)
    dates = repo.query('''SELECT f.registro_id,array_agg(DISTINCT rev.valor) dates
        FROM epidemiology.fecha_registro f JOIN epidemiology.revision_fecha rev
          ON rev.fecha_id=f.id AND rev.version=%s AND rev.estado='valid'
        JOIN epidemiology.tipo_fecha t ON t.id=f.tipo_id AND t.codigo IN ('symptom_onset','sample_on')
        JOIN epidemiology.registro_epidemiologico r ON r.id=f.registro_id
        JOIN ingestion.fila_staging s ON s.id=r.fila_id WHERE s.lote_id=ANY(%s)
        GROUP BY f.registro_id''',(resolution_version,list(batch_ids)))
    clinical_dates = {int(r.registro_id):list(r.dates) for r in dates.itertuples()}
    sources = repo.query('''SELECT b.id lote_id,a.id archivo_id,a.sha256,a.fecha_extraccion,a.periodo_declarado,
        a.procedencia,a.entrega_version,rv.declaracion
        FROM ingestion.lotes_sisa_vigentes b JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id
        LEFT JOIN epidemiology.revision_extraccion rv ON rv.archivo_id=a.id AND rv.version=%s
        WHERE b.id=ANY(%s) ORDER BY b.id''', (resolution_version, list(batch_ids))).to_dict('records')
    if {r['lote_id'] for r in sources} != set(batch_ids) or len({r['archivo_id'] for r in sources}) != len(sources):
        raise DatasetBlocked('source_selection_not_unique_or_not_current')
    # Different versions of the same named delivery must never be summed.
    names = repo.query('''SELECT a.nombre_original FROM ingestion.lotes_sisa_vigentes b
        JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id WHERE b.id=ANY(%s)''', (list(batch_ids),))
    if names.nombre_original.duplicated().any():
        raise DatasetBlocked('multiple_snapshots_of_same_source')
    geography = repo.query('''SELECT DISTINCT ON (g.registro_id) g.registro_id,a.id asignacion_id,
        CASE WHEN rev.version IS NOT NULL THEN rev.radio_id WHEN a.estado='verified' THEN ca.radio_id END radio_id,
        CASE WHEN rev.version IS NOT NULL THEN CASE rev.estado WHEN 'point_only' THEN 'approximate'
          WHEN 'unique_provisional' THEN 'provisional' ELSE 'unassigned' END
          WHEN a.estado='verified' AND ca.radio_id IS NOT NULL THEN 'verified' ELSE 'unassigned' END quality
        FROM territory.geocodificacion g JOIN territory.asignacion_radio a ON a.geocodificacion_id=g.id
        LEFT JOIN territory.revision_asignacion rev ON rev.asignacion_id=a.id AND rev.version=%s
        LEFT JOIN territory.candidato_asignacion ca ON ca.asignacion_id=a.id AND ca.seleccionado
        JOIN epidemiology.registro_epidemiologico r ON r.id=g.registro_id
        JOIN ingestion.fila_staging s ON s.id=r.fila_id WHERE s.lote_id=ANY(%s)
        ORDER BY g.registro_id,a.id''', (resolution_version, list(batch_ids)))
    geo = {int(r.registro_id): r for r in geography.itertuples()}
    for row in records:
        row['clinical_dates'] = clinical_dates.get(row['record_id'], [])
        assignment = geo.get(row['record_id'])
        row['assignment_id'] = int(assignment.asignacion_id) if assignment else None
        row['quality'] = assignment.quality if assignment else 'unassigned'
        row['radio_id'] = int(assignment.radio_id) if assignment and assignment.radio_id is not None and str(assignment.radio_id) != 'nan' else None
        if row['radio_id'] is None:
            row['quality'] = 'unassigned'
    return records, sources


def materialize(conn, *, version, resolution_version, batch_ids, climate_batch_id,
                protocol, authorization_ref, today):
    if not authorization_ref or protocol.get('zero_policy') != ZERO_POLICY or protocol.get('research_training_authorized') is not True:
        raise DatasetBlocked('explicit_option_b_training_contract_required')
    repo = MLRepository(conn)
    review = repo.query('SELECT entrada_sha256 FROM epidemiology.version_resolucion WHERE version=%s', (resolution_version,))
    if review.empty:
        raise DatasetBlocked('source_resolution_missing')
    records, sources = read_inputs(repo, resolution_version=resolution_version, batch_ids=batch_ids)
    calendar = repo.calendar()
    scope = coverage_scope(records, sources, calendar, today=today)
    covered = set(scope['covered_weeks'])
    weeks = repo.query('''SELECT id,inicio,fin,anio FROM analytics.semana_epidemiologica
        WHERE calendario_version=%s AND inicio=ANY(%s) ORDER BY inicio''', (CALENDAR_VERSION, list(covered)))
    week_ids = dict(zip(weeks.inicio, weeks.id))
    weather = repo.query('''SELECT c.fecha,c.temperatura_media,c.humedad_media,c.precipitacion,
        c.disponible_desde,c.estacion_id,b.archivo_id FROM epidemiology.clima_diario c
        JOIN ingestion.lotes_complementarios_vigentes b ON b.id=c.lote_id
        WHERE c.lote_id=%s ORDER BY c.fecha''', (climate_batch_id,))
    if weather.empty or weather.estacion_id.nunique() != 1 or weather.fecha.duplicated().any():
        raise DatasetBlocked('climate_batch_missing_or_station_ambiguous')
    contract = dict(zero_policy=ZERO_POLICY,calendar_version=CALENDAR_VERSION,
        resolution_version=resolution_version,batch_ids=list(batch_ids),climate_batch_id=climate_batch_id,
        historical_review_fingerprint=review.iloc[0,0],
        review_integrity='selected clinical observations and assignments linked to immutable review; unrelated complementary imports do not invalidate it',
        scope=scope,authorization_ref=authorization_ref,authorization_basis='project_owner_declared_provision',
        target='confirmed_eligible_source_records_not_accredited_episodes',reference_date='symptom_onset_else_sample_on',
        eligibility='same explicit confirmed mapping; unique source versions; exclude exact duplicates and unresolved identity; declared Capital residence; valid clinical date',
        zeros='assumed experimentally across covered weeks; never verified epidemiological absence',
        classification_2022='unchanged mapping; zero confirmed records does not mean no dengue',
        unknown_dates='excluded from filtered estimand, never imputed',retrospective=True,
        operational_authorized=False,created_as_of=str(today),source_metadata=sources)
    contract['territory'] = {u:context_contract(repo,u) for u,_ in UNIVERSES.values()}
    fingerprint = canonical_hash(dict(contract=contract,protocol=protocol,records=records,weather=weather.to_dict('records')))
    if not repo.query('SELECT version FROM analytics.escenario_investigacion WHERE version=%s', (version,)).empty:
        raise DatasetBlocked('research_scenario_version_already_exists')
    selections = []
    included = Counter(); excluded = Counter(); geo = Counter()
    for row in records:
        reason = eligible(row, today)
        when = row['reference_date']
        w = None
        if when:
            try:
                w = DEFAULT_CALENDAR.week_bounds(*DEFAULT_CALENDAR.date_week(when))[0]
            except ValueError:
                pass
        if reason == 'included' and w not in covered:
            reason = 'outside_explicit_scenario_scope'
        usable = reason == 'included'
        if usable:
            included[DEFAULT_CALENDAR.date_week(when)[0]] += 1
            geo[row['quality']] += 1
        else:
            excluded[reason] += 1
        selections.append((version,row['record_id'],row['batch_id'],week_ids.get(w),usable,reason,
            row['date_type'],row['assignment_id'],row['radio_id'],row['quality']))
    daily = {r.fecha: r for r in weather.itertuples()}
    climates = []
    for row in weeks.itertuples():
        days = [daily[d] for i in range(7) if (d := row.inicio + timedelta(days=i)) in daily]
        values = (sum(d.temperatura_media for d in days)/7,sum(d.humedad_media for d in days)/7,
                  sum(d.precipitacion for d in days)) if len(days) == 7 else (None,None,None)
        available = max(d.disponible_desde for d in days) if len(days) == 7 and all(d.disponible_desde is not None for d in days) else None
        climates.append((version,int(row.id),*values,len(days),available))
    datasets = []
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827194)')
            cur.execute('INSERT INTO analytics.escenario_investigacion(version,calendario_version,resolucion_version,clima_lote_id,politica_ceros,contrato,protocolo,entrada_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                (version,CALENDAR_VERSION,resolution_version,climate_batch_id,ZERO_POLICY,Json(contract,dumps=json_dump),Json(protocol,dumps=json_dump),fingerprint))
            execute_values(cur,'INSERT INTO analytics.fuente_escenario_ml VALUES %s',[(version,b) for b in batch_ids])
            execute_values(cur,'INSERT INTO analytics.registro_escenario_ml VALUES %s',selections)
            execute_values(cur,'INSERT INTO analytics.clima_escenario_ml VALUES %s',climates)
            for short,(universe,size) in UNIVERSES.items():
                cur.execute('SELECT u.id,count(m.radio_id) FROM territory.universo u JOIN territory.miembro_universo m ON m.universo_id=u.id WHERE u.version=%s GROUP BY u.id',(universe,))
                found = cur.fetchone()
                if not found or found[1] != size:
                    raise DatasetBlocked('territorial_universe_incomplete')
                for geography_policy in GEO_POLICIES:
                    suffix = 'approx' if geography_policy == 'approximate_included' else 'higher'
                    dataset_version = f'{version}-{short}-{suffix}'
                    summary = dict(calendar_weeks=len(weeks),years=scope['years'],included_source_records=dict(included),
                        excluded_source_records=dict(excluded),geography=dict(geo),radios=size,
                        geography_policy=geography_policy,climate_missing_weeks=sum(r[-2] != 7 for r in climates))
                    cur.execute('INSERT INTO analytics.dataset_investigacion VALUES(%s,%s,%s,%s,%s,%s)',
                        (dataset_version,version,found[0],geography_policy,canonical_hash(dict(contract=contract,universe=universe,geo=geography_policy)),Json(summary)))
                    cur.execute('''INSERT INTO analytics.conteo_investigacion
                        SELECT %s,m.radio_id,w.id,count(r.registro_id)::integer,count(r.registro_id)=0,
                        count(r.registro_id) FILTER(WHERE r.calidad_geografica='approximate')::integer,
                        count(r.registro_id) FILTER(WHERE r.calidad_geografica='provisional')::integer,
                        count(r.registro_id) FILTER(WHERE r.calidad_geografica='verified')::integer
                        FROM territory.miembro_universo m
                        CROSS JOIN analytics.semana_epidemiologica w
                        LEFT JOIN analytics.registro_escenario_ml r ON r.escenario_version=%s AND r.elegible
                          AND r.radio_id=m.radio_id AND r.semana_id=w.id
                          AND (%s='approximate_included' OR r.calidad_geografica IN ('provisional','verified'))
                        WHERE m.universo_id=%s AND w.calendario_version=%s AND w.inicio=ANY(%s)
                        GROUP BY m.radio_id,w.id''',
                        (dataset_version,version,geography_policy,found[0],CALENDAR_VERSION,list(covered)))
                    datasets.append(dataset_version)
    return dict(scenario_version=version,datasets=datasets,scope=scope,
        included_source_records=dict(included),geography=dict(geo),excluded_source_records=dict(excluded),
        climate_missing_weeks=sum(r[-2] != 7 for r in climates),fingerprint=fingerprint)


def json_dump(value):
    import json
    def native(item):
        if isinstance(item,date):
            return item.isoformat()
        if hasattr(item,'item'):
            return item.item()
        if hasattr(item,'tolist'):
            return item.tolist()
        raise TypeError('unsupported_private_report_type')
    return json.dumps(value,default=native,allow_nan=False,ensure_ascii=False)
