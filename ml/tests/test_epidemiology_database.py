"""Fictional workbooks/geometries only. Integration tests require owned PostGIS test DB."""
from datetime import date,datetime,timezone,timedelta
import hashlib
import os
from pathlib import Path

import pytest
from openpyxl import Workbook
from sigard_ml.ingestion.epidemiology.reader import read_book,profile,identifier
from sigard_ml.ingestion.epidemiology.importer import import_book

def workbook(path,*,year=2024,identifier_value='FICTIONAL-ID',classification='Confirmado',
             when=date(2024,2,4),longitude=10.04,latitude=10.04,extra=False):
    book=Workbook();sheet=book.active;sheet.title='Fictional'
    headers=['Id Evento caso','Clasificación manual del caso','Fecha de inicio de síntomas',
        'geocod_latitud','geocod_longitud','geocod_requiere_revision','Unknown field']
    values=[identifier_value,classification,when,latitude,longitude,False,'FICTIONAL payload']
    if year<2024:
        headers+=['Fecha de toma de muestra','Grupo etario diagnóstico'];values+=[date(2024,2,5),'FICTIONAL group']
    if year==2021:sheet.append(['Fictional preamble'])
    sheet.append(headers);sheet.append(values)
    if extra:sheet.append(values)
    book.save(path)
    return path

@pytest.mark.parametrize('year',[2020,2021,2022,2023,2024])
def test_five_structural_formats_preserve_all_cells(tmp_path,year):
    path=workbook(tmp_path/f'fictional-{year}.xlsx',year=year)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    book=read_book(path);p=profile(book)
    assert p['sheets'][0]['rows']==1
    assert book['sheets'][0]['rows'][0]['content'][-1]['value'] is not None
    assert any(c['field'] is None for c in p['sheets'][0]['columns'])
    assert p['sheets'][0]['header_row']==(2 if year==2021 else 1)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before

def test_identifier_leading_zeros(tmp_path):
    book=Workbook();cell=book.active['A1'];cell.value=12;cell.number_format='000000'
    assert identifier(cell)=='000012'

def test_unrecognized_sheet_preserves_first_row_and_formulas(tmp_path):
    book=Workbook();s=book.active;s.append(['FICTIONAL-UNMAPPED','=1+2']);s.append([None,'second row'])
    path=tmp_path/'unknown-sheet.xlsx';book.save(path)
    sheet=read_book(path)['sheets'][0]
    assert sheet['header_row']==0 and len(sheet['rows'])==2
    assert sheet['rows'][0]['content'][1]['type']=='formula'

@pytest.fixture
def db():
    from sigard_ml.ingestion.epidemiology.db import connect,connection_url,migrate
    url=os.environ.get('SIGARD_EPI_DATABASE_URL')
    if not url:pytest.skip('Owned real PostgreSQL/PostGIS test instance not configured')
    if not connection_url(url).database.startswith('sigard_epi_test_'):raise ValueError('Never run tests on non-test database')
    with connect() as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()');assert cur.fetchone()[0].startswith('sigard_epi_test_')
                cur.execute('DROP SCHEMA IF EXISTS ingestion,epidemiology,territory,analytics CASCADE')
    migrate();migrate()
    with connect() as conn:yield conn

def seed_geometry(conn):
    from sigard_ml.ingestion.epidemiology.db import get_id
    with conn:
        with conn.cursor() as c:
            country=get_id(c,'territory.pais',dict(nombre='fictional country'))
            province=get_id(c,'territory.provincia',dict(pais_id=country,nombre='fictional province'))
            dept=get_id(c,'territory.departamento',dict(provincia_id=province,nombre='fictional department'))
            fraction=get_id(c,'territory.fraccion_censal',dict(departamento_id=dept,codigo='F00'))
            version=get_id(c,'territory.version_geometria',dict(version='fictional-geometry-1',fuente_sha256='a'*64,crs='EPSG:4326'))
            u=get_id(c,'territory.universo',dict(version='ab-263-master-v1',descripcion='FICTIONAL geometry fixture, unrelated to official cartography'))
            v=get_id(c,'territory.universo',dict(version='v3-256-subset-v1',descripcion='FICTIONAL subset fixture'))
            for i in range(263):
                x=10+(i%20)*.1;y=10+(i//20)*.1
                c.execute('INSERT INTO territory.radio_censal(fraccion_id,version_geometria_id,codigo,geom) VALUES(%s,%s,%s,ST_Multi(ST_MakeEnvelope(%s,%s,%s,%s,4326))) RETURNING id',(fraction,version,f'F{i:03}',x,y,x+.08,y+.08))
                rid=c.fetchone()[0]
                for universe in [u,v] if i<256 else [u]:
                    c.execute('INSERT INTO territory.miembro_universo VALUES(%s,%s)',(universe,rid))
                    c.execute('INSERT INTO analytics.contexto_radio VALUES(%s,%s,1,100,0,%s)',(universe,rid,'a'*64))
            return u,v,version

def test_real_postgis_migrations_constraints_and_roles(db):
    from sigard_ml.ingestion.epidemiology.db import get_id
    seed_geometry(db)
    with db.cursor() as c:
        c.execute('SELECT postgis_version()');assert c.fetchone()[0]
        c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='epidemiology'");assert c.fetchone()[0]>=12
        c.execute("SELECT has_schema_privilege('public','ingestion','USAGE')");assert c.fetchone()[0] is False
        c.execute("SELECT has_table_privilege('sigard_epi_analytics_reader','territory.domicilio','SELECT')");assert c.fetchone()[0] is False
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:c.execute("INSERT INTO territory.provincia(pais_id,nombre) VALUES(-99,'fictional')")
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:c.execute("INSERT INTO territory.pais(nombre) VALUES('fictional country')")

def test_idempotence_raw_archive_new_version_and_rollback(db,tmp_path):
    from sigard_ml.ingestion.db_import import validate_db
    p=workbook(tmp_path/'fictional.xlsx')
    one=import_book(db,p);two=import_book(db,p)
    assert one['read']==one['normalized']==one['preserved']==1 and two['status']=='already_imported'
    other=workbook(tmp_path/'fictional-updated.xlsx',identifier_value='FICTIONAL-ID-NEW')
    with pytest.raises(ValueError):import_book(db,other,fail_after=1)
    assert len(validate_db(db)['files'])==1
    assert import_book(db,other)['preserved']==1
    assert validate_db(db)['reconciled']

def test_changed_workbook_same_name_becomes_new_version(db,tmp_path):
    from sigard_ml.ingestion.db_import import validate_db
    path=workbook(tmp_path/'fictional.xlsx')
    import_book(db,path)
    workbook(path,identifier_value='FICTIONAL NEW VERSION')
    import_book(db,path)
    report=validate_db(db)
    assert len(report['files'])==2 and report['typed_payload_hashes_valid']

def test_explicit_extraction_metadata_is_preserved_without_becoming_arrival(db,tmp_path):
    path=workbook(tmp_path/'fictional.xlsx')
    metadata=dict(fecha_extraccion='2024-03-01',entrega_version='fictional-delivery-1',procedencia='fictional-owner-declaration')
    import_book(db,path,metadata=metadata)
    import_book(db,path,metadata=metadata)
    with db.cursor() as c:
        c.execute('SELECT fecha_extraccion,entrega_version FROM ingestion.archivo_fuente')
        assert c.fetchone()==(date(2024,3,1),'fictional-delivery-1')
        c.execute('SELECT count(*) FROM epidemiology.registro_epidemiologico WHERE disponible_desde IS NOT NULL')
        assert c.fetchone()[0]==0
    with pytest.raises(ValueError):import_book(db,path,metadata={**metadata,'fecha_extraccion':'2024-03-02'})

@pytest.mark.parametrize('url',['sqlite:///fake.db','postgresql://x@127.0.0.1:5432/sigard_epi_test_bad',
    'postgresql://x@remote.invalid:55439/sigard_epi_test_bad','postgresql://x@127.0.0.1:55439/public_store'])
def test_connection_guard_blocks_before_network(url):
    from sigard_ml.ingestion.epidemiology.db import connection_url
    with pytest.raises(ValueError):connection_url(url)

@pytest.mark.parametrize('mutation',['invalid_date','incomplete','unknown_class','repeated'])
def test_incomplete_unknown_and_duplicate_rows_not_lost(db,tmp_path,mutation):
    kwargs={}
    if mutation=='invalid_date':kwargs['when']='not-a-date'
    elif mutation=='incomplete':kwargs['identifier_value']=None
    elif mutation=='unknown_class':kwargs['classification']='FICTIONAL UNKNOWN CLASS'
    else:kwargs['extra']=True
    p=workbook(tmp_path/'fictional.xlsx',**kwargs)
    result=import_book(db,p)
    assert result['preserved']==(2 if mutation=='repeated' else 1)
    with db.cursor() as c:
        c.execute('SELECT count(*) FROM epidemiology.registro_epidemiologico');assert c.fetchone()[0]==result['preserved']
        if mutation=='repeated':
            c.execute("SELECT count(*) FROM epidemiology.relacion_registro WHERE tipo='exact_duplicate'");assert c.fetchone()[0]==1

def test_geographic_boundaries_invalid_and_subset(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    u,v,gv=seed_geometry(db)
    for name,kw in [('interior',{}),('boundary',dict(longitude=10)),('invalid',dict(latitude=91)),('outside',dict(longitude=80))]:
        import_book(db,workbook(tmp_path/(name+'.xlsx'),identifier_value='FICTIONAL-'+name,**kw))
    states=assign_radios(db)
    assert states['unique_provisional']==1 and states['boundary']==1 and states['invalid']==1 and states['outside']==1
    with db.cursor() as c:
        c.execute('SELECT count(*) FROM analytics.correspondencia_universos WHERE universo_a=%s AND universo_b=%s',('ab-263-master-v1','v3-256-subset-v1'));assert c.fetchone()[0]==256
        c.execute("SELECT count(*) FROM territory.candidato_asignacion ca JOIN territory.asignacion_radio a ON a.id=ca.asignacion_id WHERE a.estado IN ('invalid','ambiguous','boundary') AND ca.seleccionado");assert c.fetchone()[0]==0

def test_overlapping_candidates_never_selected_and_srid_enforced(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db)
    with db:
        with db.cursor() as c:c.execute("INSERT INTO territory.radio_censal(fraccion_id,version_geometria_id,codigo,geom) SELECT fraccion_id,version_geometria_id,'FICTIONAL-OVERLAP',geom FROM territory.radio_censal WHERE codigo='F000'")
    import_book(db,workbook(tmp_path/'fictional.xlsx'))
    assert assign_radios(db)['ambiguous']==1
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:c.execute("UPDATE territory.geocodificacion SET geom=ST_SetSRID(ST_MakePoint(1,1),3857)")

def test_observation_cannot_reference_different_source_column(db,tmp_path):
    import_book(db,workbook(tmp_path/'one.xlsx'))
    import_book(db,workbook(tmp_path/'two.xlsx',identifier_value='FICTIONAL SECOND'))
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:
                c.execute('UPDATE epidemiology.fecha_registro SET columna_id=(SELECT max(id) FROM ingestion.columna_fuente) WHERE id=(SELECT min(id) FROM epidemiology.fecha_registro)')

def test_calendar_coverage_null_zero_and_ml_lags(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize,seed_policies
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db)
    import_book(db,workbook(tmp_path/'fictional.xlsx',when=date(2024,2,4)))
    assign_radios(db)
    weeks={date(2024,1,21)+timedelta(weeks=i) for i in range(6)}
    with pytest.raises(ValueError):materialize(db,version='bad',universe_version='ab-263-master-v1',start=min(weeks),end=max(weeks),scenario='experimental_assumed')
    conservative=materialize(db,version='fictional-conservative',universe_version='ab-263-master-v1',start=min(weeks),end=max(weeks),accept_provisional=True)
    assumed=materialize(db,version='fictional-assumed',universe_version='ab-263-master-v1',start=min(weeks),end=max(weeks)+timedelta(weeks=1),scenario='experimental_assumed',coverage_weeks=weeks,coverage_ref='FICTIONAL owner declaration',accept_provisional=True)
    with db.cursor() as c:
        c.execute("SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s AND cantidad_registros=0",(conservative['run_id'],));assert c.fetchone()[0]==0
        c.execute("SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s AND cantidad_registros=0",(assumed['run_id'],));assert c.fetchone()[0]>0
        c.execute("SELECT local_presencia_exp_rezago_1,local_presencia_exp_rezago_2 FROM analytics.ml_b WHERE ejecucion_id=%s AND radio_censal='F000' AND fecha_inicio_semana='2024-02-11'",(assumed['run_id'],));assert c.fetchone()==(1,0)
        c.execute("SELECT inicio,fin FROM analytics.semana_epidemiologica WHERE anio=2020 AND numero=53");assert c.fetchone()==(date(2020,12,27),date(2021,1,2))
        c.execute("SELECT inicio FROM analytics.semana_epidemiologica WHERE anio=2026 AND numero=1");assert c.fetchone()[0]==date(2026,1,4)
        c.execute("SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s AND cobertura_estado='out_of_scope' AND cantidad_registros IS NOT NULL",(assumed['run_id'],));assert c.fetchone()[0]==0

def test_2022_class_not_reinterpreted_and_unknown_date_blocks(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db)
    import_book(db,workbook(tmp_path/'fictional-2022.xlsx',classification='Caso sospechoso',when=date(2022,2,1)))
    import_book(db,workbook(tmp_path/'fictional-undated.xlsx',identifier_value='FICTIONAL UNDATED',when=None))
    assign_radios(db)
    result=materialize(db,version='fictional-2022',universe_version='ab-263-master-v1',start=date(2022,1,2),end=date(2022,2,27),scenario='experimental_assumed',coverage_weeks={date(2022,1,2)+timedelta(weeks=i) for i in range(9)},coverage_ref='fictional scope, not real 2022',accept_provisional=True)
    assert result['included_records']==0
    assert result['excluded_records']['classification_not_in_definition']==1
    with db.cursor() as c:
        c.execute("SELECT count(*) FROM analytics.conteos_radio_semana cs JOIN territory.radio_censal r ON r.id=cs.radio_id WHERE cs.ejecucion_id=%s AND r.codigo='F000' AND cs.cantidad_registros IS NOT NULL",(result['run_id'],));assert c.fetchone()[0]==0
        c.execute('SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s AND (cantidad_registros IS NOT NULL OR presencia IS NOT NULL)',(result['run_id'],));assert c.fetchone()[0]==0

def test_as_of_late_data_never_reaches_earlier_b_features(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    with db:
        with db.cursor() as c:c.execute("UPDATE epidemiology.registro_epidemiologico SET disponible_desde='2024-03-01T00:00:00Z'")
    result=materialize(db,version='fictional-asof',universe_version='ab-263-master-v1',start=date(2024,1,21),end=date(2024,3,17),accept_provisional=True,mode='as_of',cutoff=datetime(2024,4,1,tzinfo=timezone.utc))
    with db.cursor() as c:
        c.execute("SELECT local_presencia_exp_rezago_1 FROM analytics.ml_b WHERE ejecucion_id=%s AND radio_censal='F000' AND fecha_inicio_semana='2024-02-11'",(result['run_id'],));assert c.fetchone()[0] is None
        c.execute("SELECT poblacion FROM analytics.ml_a WHERE ejecucion_id=%s AND radio_censal='F000' AND fecha_inicio_semana='2024-02-11'",(result['run_id'],));assert c.fetchone()[0] is None

def test_verified_empty_weeks_make_real_definition_zeros(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize,seed_policies,declare_coverage
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    from sigard_ml.ingestion.epidemiology.db import get_id
    u,v,gv=seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    temporal,classification=seed_policies(db)
    with db:
        with db.cursor() as c:
            criterion=get_id(c,'epidemiology.criterio_cobertura',dict(version='fictional-verified',politica_clasificacion_id=classification,definicion_poblacion='fictional definition',filtro_extraccion='fictional complete extract'))
            c.execute('SELECT id FROM ingestion.archivo_fuente');file=c.fetchone()[0]
    declare_coverage(db,file_id=file,universe_id=u,criterion_id=criterion,start=date(2024,1,21),end=date(2024,3,9),state='verified',evidence='FICTIONAL verified complete export evidence',reviewer='FICTIONAL reviewer')
    result=materialize(db,version='fictional-verified-run',universe_version='ab-263-master-v1',start=date(2024,1,21),end=date(2024,3,3),accept_provisional=True,criterion_id=criterion)
    with db.cursor() as c:
        c.execute("SELECT cantidad_registros,presencia,cobertura_estado FROM analytics.conteos_radio_semana cs JOIN territory.radio_censal r ON r.id=cs.radio_id JOIN analytics.semana_epidemiologica w ON w.id=cs.semana_id WHERE cs.ejecucion_id=%s AND r.codigo='F000' AND w.inicio='2024-01-21'",(result['run_id'],));assert c.fetchone()==(0,0,'verified')
        c.execute('SELECT sum(registros_fuente) FROM analytics.registros_fuente_semana WHERE ejecucion_id=%s',(result['run_id'],));assert c.fetchone()[0]==1

def test_climate_future_availability_blocked_v3_and_no_automatic_equivalence(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    from sigard_ml.ingestion.epidemiology.climate import load_climate
    import json
    seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    package=tmp_path/'fictional-climate.json'
    package.write_text(json.dumps(dict(climate=[dict(week_start='2024-02-04',temperature=20,humidity=40,precipitation=0,complete=True,available_on='2024-03-01T00:00:00+00:00')])),encoding='utf-8')
    load_climate(db,package,expected_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),version='fictional-climate')
    result=materialize(db,version='fictional-climate-run',universe_version='v3-256-subset-v1',start=date(2024,1,21),end=date(2024,3,3),accept_provisional=True,mode='as_of',cutoff=datetime(2024,4,1,tzinfo=timezone.utc),climate_version='fictional-climate')
    with db.cursor() as c:
        c.execute("SELECT temperature_origin,equivalencia_ml_verificada FROM analytics.ml_v3 WHERE ejecucion_id=%s AND radio_id='F000' AND origin_week='2024-02-04' LIMIT 1",(result['run_id'],));assert c.fetchone()==(None,False)

def test_partial_analysis_week_cannot_create_zero(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    run=materialize(db,version='fictional-partial',universe_version='ab-263-master-v1',start=date(2024,1,24),end=date(2024,2,10),scenario='experimental_assumed',coverage_weeks={date(2024,1,21),date(2024,1,28),date(2024,2,4)},coverage_ref='fictional complete-week declaration',accept_provisional=True)
    with db.cursor() as c:
        c.execute('SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s AND ventana_parcial AND cantidad_registros IS NOT NULL',(run['run_id'],));assert c.fetchone()[0]==0

def test_future_outcome_does_not_change_v3_origin_features(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    weeks={date(2024,1,21)+timedelta(weeks=i) for i in range(8)}
    run=materialize(db,version='fictional-future',universe_version='v3-256-subset-v1',start=min(weeks),end=max(weeks)+timedelta(days=6),scenario='experimental_assumed',coverage_weeks=weeks,coverage_ref='fictional scope',accept_provisional=True)
    with db.cursor() as c:
        query="SELECT count_origin,cases_lag_1,cases_lag_2,recent_mean_3,recent_trend,known_recent_count FROM analytics.ml_v3 WHERE ejecucion_id=%s AND radio_id='F000' AND origin_week='2024-02-04' ORDER BY horizon_weeks"
        c.execute(query,(run['run_id'],));before=c.fetchall()
        c.execute("UPDATE analytics.conteos_radio_semana SET cantidad_registros=99,registros_observados=99,presencia=1 WHERE ejecucion_id=%s AND semana_id=(SELECT id FROM analytics.semana_epidemiologica WHERE inicio='2024-02-18') AND radio_id=(SELECT id FROM territory.radio_censal WHERE codigo='F000')",(run['run_id'],))
        c.execute(query,(run['run_id'],));assert before==c.fetchall()

def test_count_cannot_mix_v3_and_ab_only_radios(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db);import_book(db,workbook(tmp_path/'fictional.xlsx'));assign_radios(db)
    run=materialize(db,version='fictional-scope',universe_version='v3-256-subset-v1',start=date(2024,1,21),end=date(2024,2,10),accept_provisional=True)
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:
                c.execute("UPDATE analytics.conteos_radio_semana SET radio_id=(SELECT id FROM territory.radio_censal WHERE codigo='F262') WHERE ejecucion_id=%s AND radio_id=(SELECT id FROM territory.radio_censal WHERE codigo='F000')",(run['run_id'],))
