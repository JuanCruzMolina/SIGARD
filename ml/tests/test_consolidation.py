"""Stage 1 contracts use generated records and abstract polygons only."""
from datetime import date, timedelta
import hashlib

import pytest
import pandas as pd
from openpyxl import Workbook

from sigard_ml.forecasting.consolidation import POLICY, decision, aggregate_weather, materialize, reconcile
from sigard_ml.data_access import MLRepository, DatasetBlocked
from sigard_ml.data_access.tabular_guard import forbid_tabular_reads
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from test_epidemiology_database import db, seed_geometry


def record(**extra):
    row=dict(reference_date=date(2022,2,6),classes=['sospechoso'],exact_duplicate=False,
        pending_identity=False,has_identifier=True,province='la rioja',department='capital',locality='la rioja')
    row.update(extra)
    return row


@pytest.mark.parametrize('clinical_class',['sospechoso','probable','descartado',None])
def test_2022_project_positive_preserves_all_original_classifications(clinical_class):
    row=record(classes=[clinical_class]);before=list(row['classes'])
    result=decision(row,source_year=2022,override_scope='delivery_2022',as_of=date(2026,11,2))
    assert result['eligible'] and row['classes']==before
    assert result['checks']['clinical_confirmation_changed'] is False


def test_delivery_year_does_not_rewrite_the_clinical_date():
    row=record(reference_date=date(2021,12,20))
    assert decision(row,source_year=2022,override_scope='delivery_2022',as_of=date(2026,11,2))['eligible']
    assert not decision(row,source_year=2022,override_scope='clinical_year_2022',as_of=date(2026,11,2))['eligible']
    assert row['reference_date']==date(2021,12,20)


@pytest.mark.parametrize('extra,reason',[
    ({'reference_date':None},'missing_clinical_reference_date'),
    ({'pending_identity':True},'unresolved_identifier_or_revision'),
    ({'exact_duplicate':True},'exact_duplicate'),
    ({'has_identifier':False},'missing_source_identifier'),
    ({'department':'FICTIONAL-OUTSIDE'},'source_residence_outside_definition_or_missing'),
    ({'reference_date':date(2025,3,2)},'outside_declared_2020_2024_coverage')])
def test_project_exception_never_bypasses_other_filters(extra,reason):
    result=decision(record(**extra),source_year=2022,override_scope='delivery_2022',as_of=date(2026,11,2))
    assert not result['eligible'] and reason in result['checks']['failures']


def test_calendar_has_261_continuous_weeks_and_2020_week53():
    weeks=[DEFAULT_CALENDAR.week_bounds(y,n) for y in range(2020,2025)
        for n in range(1,next(r.weeks for r in DEFAULT_CALENDAR.years if r.year==y)+1)]
    assert len(weeks)==261 and DEFAULT_CALENDAR.week_bounds(2020,53) in weeks
    assert all(a.weekday()==6 and b.weekday()==5 for a,b in weeks)
    assert all(b+timedelta(days=1)==c for (_,b),(c,_) in zip(weeks,weeks[1:]))


def weather_rows():
    return [dict(fecha=date(2015,1,4)+timedelta(days=i),temperatura_media=20.,humedad_media=50.,
        precipitacion=2.,disponible_desde=None) for i in range(14)]


def test_weather_requires_seven_complete_days_and_keeps_unknown_availability():
    days=weather_rows();weekly=aggregate_weather(days)
    assert weekly[0][2:]==(7,20.,50.,14.,None)
    assert aggregate_weather(days[:-1])[-1][3:6]==(None,None,None)
    days[0]['humedad_media']=None
    assert aggregate_weather(days)[0][3:6]==(None,None,None)
    with pytest.raises(DatasetBlocked):aggregate_weather([*weather_rows(),weather_rows()[0]])


@pytest.mark.parametrize('config',[{}, {'authorization_basis':'project_owner_declared_provision','training_authorized':True},
    {'authorization_basis':'project_owner_declared_provision','training_authorized':False}])
def test_prepare_requires_owner_declaration_and_cannot_authorize_training(config):
    with pytest.raises(DatasetBlocked,match='stage1_owner_declaration_without_training_required'):
        materialize(None,config)


def seed(conn,tmp_path):
    from sigard_ml.ingestion.epidemiology.analytics import seed_policies
    from sigard_ml.ingestion.epidemiology.importer import import_book
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    from sigard_ml.ingestion.epidemiology.resolution import resolve
    from sigard_ml.ingestion.epidemiology.complementary import import_complement,OpenMeteoCSV
    from test_predictive_core import climate_bytes
    seed_policies(conn);seed_geometry(conn)
    path=tmp_path/'FICTIONAL-STAGE1.xlsx'
    book=Workbook();sheet=book.active
    sheet.append(['Id Evento caso','Clasificacion manual del caso','Fecha de inicio de sintomas',
        'Pais de residencia','Provincia de residencia','Departamento de residencia','Localidad de residencia',
        'geocod_latitud','geocod_longitud','geocod_requiere_revision','geocod_precision','geocod_confianza',
        'geocod_metodo_resolucion','geocod_radio_censal'])
    specs=[('S','Caso sospechoso',date(2022,2,6)),('P','Probable',date(2022,2,6)),
        ('D','Descartado',date(2022,2,13)),('OLD','Caso sospechoso',date(2021,12,20)),
        ('NO-DATE','Caso sospechoso',None),('DUP','Caso sospechoso',date(2022,2,20)),
        ('DUP','Probable',date(2022,2,21)),('MASK','Caso sospechoso',date(2022,2,27)),
        ('UNKNOWN-GEO','Caso sospechoso',date(2022,3,6)),('KNOWN-GEO','Caso sospechoso',date(2022,3,6)),
        ('FUTURE','Confirmado',date(2025,2,2))]
    for key,cls,when in specs:
        lat,lon,radio=(11.34,10.24,'F262') if key=='MASK' else (20.,20.,'') if key=='UNKNOWN-GEO' else (10.04,10.04,'F000')
        sheet.append(['FICTIONAL-'+key,cls,when,'argentina','la rioja','capital','la rioja',
            lat,lon,False,'altura_interpolada','media','exacto',radio])
    book.save(path);import_book(conn,path);assign_radios(conn)
    resolve(conn,version='FICTIONAL-STAGE1-REVIEW',evidence={'ref':'FICTIONAL ONLY'})
    climate=tmp_path/'FICTIONAL-STAGE1-CLIMATE.csv'
    prefix=climate_bytes().split(b'2024-02-04')[0]
    first,last=date(2015,1,1),date(2024,12,31)
    climate.write_bytes(prefix+b''.join(f'{day},25,15,20,45,1\n'.encode() for i in range((last-first).days+1)
        if (day:=first+timedelta(days=i))!=date(2022,6,18)))
    sha=hashlib.sha256(climate.read_bytes()).hexdigest()
    loaded=import_complement(conn,climate,OpenMeteoCSV(),expected_sha256=sha,version='FICTIONAL-CLIMATE',authorization_ref='FICTIONAL')
    repo=MLRepository(conn)
    sources=repo.query('SELECT b.id,a.sha256 FROM ingestion.lote_importacion b JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id')
    return dict(dataset_version='FICTIONAL-STAGE1',policy_version=POLICY,resolution_version='FICTIONAL-STAGE1-REVIEW',
        batch_ids=list(map(int,sources.id)),source_contract={str(r.id):dict(delivery_year=2022,sha256=r.sha256) for r in sources.itertuples()},
        climate_batch_id=loaded['batch_id'],climate_sha256=sha,territorial_evidence={},
        override_2022_scope='delivery_2022',coverage_years=list(range(2020,2025)),as_of='2026-11-02',
        authorization_basis='project_owner_declared_provision',authorization_ref='FICTIONAL-stage1',training_authorized=False)


def test_postgis_consolidation_reconciles_masks_zeros_sources_and_rebuilds(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.resolution import original_fingerprint
    cfg=seed(db,tmp_path);before=original_fingerprint(db)
    with forbid_tabular_reads():
        result=materialize(db,cfg);again=materialize(db,cfg)
    assert result['input_sha256']==again['input_sha256'] and again['status']=='already_materialized'
    assert original_fingerprint(db)==before
    repo=MLRepository(db);report=reconcile(db,cfg['dataset_version'])
    assert report['by_delivery_year'][0]['originales']==11
    assert report['by_delivery_year'][0]['incluidos']==7
    total=report['reconciliation'][0]
    assert total['seleccion']==total['asignados_comunes']+total['asignados_fuera_comun']+total['sin_asignacion']==7
    assert total['sin_asignacion']==1 and total['asignados_fuera_comun']==1
    year2022=next(y for y in report['by_epidemiological_year'] if y['anio']==2022)
    assert year2022['registros']==6
    assert all(pd.isna(y['registros']) for y in report['by_epidemiological_year'] if y['anio']>=2025)
    r=repo.query("SELECT cantidad_sigard,presencia_sigard,procedencia_cero FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s AND radio_codigo='F000' AND inicio='2020-02-02'",(cfg['dataset_version'],)).iloc[0]
    assert r.cantidad_sigard==0 and r.presencia_sigard==0 and r.procedencia_cero
    r=repo.query("SELECT cantidad_sigard,presencia_sigard,cobertura_estado FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s AND radio_codigo='F001' AND inicio='2022-03-06'",(cfg['dataset_version'],)).iloc[0]
    assert r.cantidad_sigard is None and r.presencia_sigard is None and r.cobertura_estado=='territorial_uncertainty'
    r=repo.query("SELECT cantidad_sigard,registros_asignados,cobertura_estado FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s AND radio_codigo='F262' AND inicio='2022-02-27'",(cfg['dataset_version'],)).iloc[0]
    assert r.cantidad_sigard is None and r.registros_asignados==1 and r.cobertura_estado=='outside_common_territory'
    assert all(not r['comprobaciones']['clinical_confirmation_changed'] for r in report['audit_2022'])
    amounts=repo.query('''SELECT count(*) FILTER(WHERE cantidad_sigard<0) negativos,
        count(*) FILTER(WHERE cantidad_sigard=0 AND procedencia_cero IS NULL) ceros_sin_procedencia,
        count(*) FILTER(WHERE cobertura_estado IN ('out_of_coverage','outside_common_territory','territorial_uncertainty')
            AND cantidad_sigard IS NOT NULL) desconocidos_imputados
        FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s''',(cfg['dataset_version'],)).iloc[0]
    assert amounts.eq(0).all()
    clone=dict(cfg,dataset_version='FICTIONAL-STAGE1-RECONSTRUCTION')
    materialize(db,clone)
    stmt='''SELECT anio,numero,registros_observados,cantidad_sigard,cobertura_estado
        FROM analytics.consolidacion_departamento WHERE dataset_version=%s ORDER BY inicio'''
    pd.testing.assert_frame_equal(repo.query(stmt,(cfg['dataset_version'],)),repo.query(stmt,(clone['dataset_version'],)))
    corrupt=repo.query('''SELECT count(*) n FROM analytics.consolidacion_registro r
        WHERE dataset_version=%s AND r.clases_originales<>(SELECT coalesce(jsonb_agg(c.valor_literal ORDER BY c.id),'[]'::jsonb)
        FROM epidemiology.clasificacion_registro c WHERE c.registro_id=r.registro_id)''',(cfg['dataset_version'],))
    assert corrupt.iloc[0,0]==0
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:c.execute("UPDATE analytics.consolidacion_dataset SET politica_version='FICTIONAL-MUTATION'")
    with pytest.raises(DatasetBlocked):materialize(db,dict(cfg,as_of='2026-11-03'))


def test_postgis_features_never_use_future_weather_outcomes_or_census(db,tmp_path):
    cfg=seed(db,tmp_path);materialize(db,cfg);repo=MLRepository(db)
    stmt="SELECT * FROM analytics.consolidacion_predictores WHERE dataset_version=%s AND radio_codigo='F000' AND origen='2021-01-03'"
    before=repo.query(stmt,(cfg['dataset_version'],)).drop(columns=['dataset_version','entrada_sha256'])
    assert before.poblacion_predictor_asof.isna().all()
    assert before.clima_historia_hasta.iloc[0]<date(2021,1,3)
    assert before.clima_historia_semanas.iloc[0]>250
    from sigard_ml.ingestion.epidemiology.complementary import import_complement,OpenMeteoCSV
    lines=(tmp_path/'FICTIONAL-STAGE1-CLIMATE.csv').read_text(encoding='utf-8').splitlines()
    modified=[]
    for line in lines[4:]:
        cells=line.split(',')
        if cells[0]>='2024-01-01':cells[-1]='999'
        modified.append(','.join(cells))
    path=tmp_path/'FICTIONAL-FUTURE-CLIMATE.csv'
    path.write_text('\n'.join([*lines[:4],*modified])+'\n',encoding='utf-8')
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    loaded=import_complement(db,path,OpenMeteoCSV(),expected_sha256=sha,version='FICTIONAL-FUTURE',authorization_ref='FICTIONAL')
    other=dict(cfg,dataset_version='FICTIONAL-STAGE1-FUTURE-CHANGE',climate_batch_id=loaded['batch_id'],climate_sha256=sha)
    materialize(db,other)
    after=repo.query(stmt,(other['dataset_version'],)).drop(columns=['dataset_version','entrada_sha256'])
    pd.testing.assert_frame_equal(before,after)
    incomplete=repo.query("SELECT temperatura,humedad,precipitacion FROM analytics.consolidacion_clima WHERE dataset_version=%s AND inicio='2022-06-12'",(cfg['dataset_version'],))
    assert incomplete.isna().all().all()
    future=repo.query("SELECT objetivo_cantidad,objetivo_presencia FROM analytics.consolidacion_entrenamiento WHERE dataset_version=%s AND radio_codigo='F000' AND origen='2024-12-22'",(cfg['dataset_version'],))
    assert future.isna().all().all()
