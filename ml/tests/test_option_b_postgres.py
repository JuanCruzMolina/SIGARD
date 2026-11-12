"""Generated abstract geography and clinical fixtures; only owned PostGIS test DB."""
from datetime import date,timedelta
import hashlib

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from test_epidemiology_database import db,seed_geometry
from sigard_ml.data_access import MLRepository,DatasetBlocked
from sigard_ml.data_access.tabular_guard import forbid_tabular_reads
from sigard_ml.forecasting.option_b_data import materialize,coverage_scope
from sigard_ml.forecasting.option_b_training import PROTOCOL,train,infer,geography_sensitivity
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR


def calendar():
    return pd.DataFrame([dict(inicio=DEFAULT_CALENDAR.week_bounds(y.year,n)[0],
        fin=DEFAULT_CALENDAR.week_bounds(y.year,n)[1],anio=y.year,numero=n,semanas_anio=y.weeks)
        for y in DEFAULT_CALENDAR.years for n in range(1,y.weeks+1)])


def test_complete_years_and_conditional_recent_years_use_clinical_dates_and_source_cutoff():
    sources=[dict(lote_id=1,fecha_extraccion=date(2026,5,13),declaracion={})]
    rec=lambda when,**extra:dict(reference_date=when,batch_id=1,**extra)
    base=coverage_scope([],sources,calendar(),today=date(2026,10,29))
    assert base['years']==[2020,2021,2022,2023,2024] and len(base['covered_weeks'])==261
    # A valid 2025 sample also supports including 2025 even if onset was 2024.
    rows=[rec(date(2024,12,1),clinical_dates=[date(2024,12,1),date(2025,1,5)]),rec(date(2026,3,2))]
    scoped=coverage_scope(rows,sources,calendar(),today=date(2026,5,11))
    assert scoped['years']==list(range(2020,2027))
    assert max(scoped['covered_weeks'])+timedelta(days=6)<=date(2026,5,11)
    unknown=coverage_scope([rec(date(2026,3,2))],[dict(lote_id=1,declaracion={})],calendar(),today=date(2026,10,29))
    assert 2026 not in unknown['years'] and unknown['optional_years']['2026']['reason']=='source_cutoff_not_supported'
    future=coverage_scope([rec(date(2026,12,1))],sources,calendar(),today=date(2026,10,29))
    assert 2026 not in future['years']


def seed(db,tmp_path,*,recent=False):
    from sigard_ml.ingestion.epidemiology.analytics import seed_policies
    from sigard_ml.ingestion.epidemiology.importer import import_book
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    from sigard_ml.ingestion.epidemiology.resolution import resolve
    from sigard_ml.ingestion.epidemiology.complementary import OpenMeteoCSV,import_complement
    from test_predictive_core import climate_bytes
    seed_policies(db);seed_geometry(db)
    path=tmp_path/'FICTIONAL-OPTION-B.xlsx'
    book=Workbook();sheet=book.active
    sheet.append(['Id Evento caso','Clasificacion manual del caso','Fecha de inicio de sintomas',
        'Fecha de toma de muestra','Pais de residencia','Provincia de residencia','Departamento de residencia',
        'Localidad de residencia','geocod_latitud','geocod_longitud','geocod_requiere_revision',
        'geocod_precision','geocod_confianza','geocod_metodo_resolucion','geocod_radio_censal'])
    for year in range(2020,2025):
        for number in range(4,49,4):
            when=DEFAULT_CALENDAR.week_bounds(year,number)[0]+timedelta(days=1)
            sheet.append([f'FICTIONAL-{year}-{number}','Caso sospechoso' if year==2022 else 'Confirmado',
                when if number!=8 else None,when,'argentina','la rioja','capital','la rioja',10.04,10.04,False,
                'calle' if number%8 else 'altura_interpolada','media','exacto','F000'])
    if recent:
        for year,when in [(2025,date(2025,2,3)),(2026,date(2026,3,2))]:
            sheet.append([f'FICTIONAL-RECENT-{year}','Confirmado',when,when,'argentina','la rioja','capital','la rioja',
                10.04,10.04,False,'altura_interpolada','media','exacto','F000'])
    book.save(path)
    metadata=dict(fecha_extraccion='2026-05-13',procedencia='FICTIONAL generated source',entrega_version='FICTIONAL-RECENT') if recent else None
    import_book(db,path,metadata=metadata);assign_radios(db)
    resolve(db,version='FICTIONAL-OPTION-B-R',evidence={'ref':'FICTIONAL ONLY'})
    with db.cursor() as c:c.execute('SELECT id FROM ingestion.lote_importacion');bid=c.fetchone()[0]
    weather=tmp_path/'FICTIONAL-CLIMATE.csv'
    prefix=climate_bytes().split(b'2024-02-04')[0]
    start=date(2019,12,29);stop=date(2024,12,28)
    weather.write_bytes(prefix+b''.join(f'{day},25,15,20,45,1\n'.encode() for i in range((stop-start).days+1)
        if (day:=start+timedelta(days=i))!=date(2022,6,18)))
    loaded=import_complement(db,weather,OpenMeteoCSV(),expected_sha256=hashlib.sha256(weather.read_bytes()).hexdigest(),
        version='FICTIONAL-OPTION-B-C',authorization_ref='FICTIONAL')
    return dict(version='FICTIONAL-OPTION-B',resolution_version='FICTIONAL-OPTION-B-R',batch_ids=[bid],
        climate_batch_id=loaded['batch_id'],protocol=PROTOCOL,authorization_ref='FICTIONAL',today=date(2026,10,29))


def test_new_datasets_zeros_climate_geography_and_originals_preserved(db,tmp_path):
    from sigard_ml.ingestion.epidemiology.resolution import original_fingerprint
    opts=seed(db,tmp_path);before=original_fingerprint(db)
    with forbid_tabular_reads():
        report=materialize(db,**opts)
        assert report['scope']['years']==list(range(2020,2025))
        assert report['climate_missing_weeks']==1
        repo=MLRepository(db)
        a=repo.research_frame('A','FICTIONAL-OPTION-B-ab-approx')
        b=repo.research_frame('B','FICTIONAL-OPTION-B-ab-approx')
        v=repo.research_frame('V3','FICTIONAL-OPTION-B-v3-approx')
        assert len(a)==263*261 and len(v)==256*261
        y2022=a.fecha_inicio_semana.map(lambda d:DEFAULT_CALENDAR.date_week(d+timedelta(days=7))[0]).eq(2022)
        assert a.loc[y2022,'objetivo_semana_siguiente'].eq(0).all()
        assert b.loc[b.fecha_inicio_semana.eq(min(b.fecha_inicio_semana)),'local_presencia_exp_rezago_1'].isna().all()
        assert v.loc[v.origin_week.eq(date(2022,6,12)),'temperature_origin'].isna().all()
        for version in report['datasets']:
            counts=repo.query('SELECT sum(cantidad) n,count(*) rows,count(*) FILTER(WHERE cero_asumido) zeros FROM analytics.conteo_investigacion WHERE dataset_version=%s',(version,))
            assert counts.iloc[0].zeros>0 and counts.iloc[0].n>0
        high=repo.query("SELECT sum(cantidad) n FROM analytics.conteo_investigacion WHERE dataset_version='FICTIONAL-OPTION-B-ab-higher'").iloc[0,0]
        approx=repo.query("SELECT sum(cantidad) n FROM analytics.conteo_investigacion WHERE dataset_version='FICTIONAL-OPTION-B-ab-approx'").iloc[0,0]
        assert high<approx
        assert original_fingerprint(db)==before
    with pytest.raises(Exception):
        with db:
            with db.cursor() as c:c.execute("UPDATE analytics.conteo_investigacion SET cantidad=99 WHERE dataset_version='FICTIONAL-OPTION-B-ab-approx'")
    with pytest.raises(Exception,match='research_count_universe_or_week_mismatch'):
        with db:
            with db.cursor() as c:
                c.execute('''INSERT INTO analytics.conteo_investigacion
                    SELECT 'FICTIONAL-OPTION-B-v3-approx',r.id,w.id,0,true,0,0,0
                    FROM territory.radio_censal r CROSS JOIN analytics.semana_epidemiologica w
                    WHERE r.codigo='F262' AND w.inicio='2024-02-04' ''')
    with pytest.raises(Exception,match='research_count_universe_or_week_mismatch'):
        with db:
            with db.cursor() as c:
                c.execute('''INSERT INTO analytics.conteo_investigacion
                    SELECT 'FICTIONAL-OPTION-B-ab-approx',r.id,w.id,0,true,0,0,0
                    FROM territory.radio_censal r CROSS JOIN analytics.semana_epidemiologica w
                    WHERE r.codigo='F000' AND w.anio=2025 AND w.numero=1''')


def test_real_postgis_fit_registry_metrics_inference_no_tabular_io_or_leakage(db,tmp_path,monkeypatch):
    opts=seed(db,tmp_path)
    with forbid_tabular_reads():
        materialize(db,**opts)
        fitted=[]
        for family in ('A','B','V3'):
            dataset='FICTIONAL-OPTION-B-'+('v3' if family=='V3' else 'ab')+'-approx'
            result=train(db,dataset_version=dataset,family=family,model_version='FICTIONAL-NEW-'+family)
            assert result['status']=='trained',result
            assert result['metadata']['development_last_target_end']<result['holdout']['first_origin']
            fitted.append(result)
        from sklearn.ensemble import RandomForestClassifier,HistGradientBoostingRegressor
        with monkeypatch.context() as patch:
            for cls in (RandomForestClassifier,HistGradientBoostingRegressor):
                patch.setattr(cls,'fit',lambda *a,**k:pytest.fail('inference must never fit'))
            for result in fitted:
                prediction=infer(db,model_version=result['model_version'],origin=date(2024,2,4))
                assert prediction['status']=='available_private_experimental',prediction
                assert len(prediction['rows']) in (256,263)
                assert all(row['status']=='experimental_unvalidated' for row in prediction['rows'])
                current=infer(db,model_version=result['model_version'],origin=date(2026,10,25),mode='operational')
                assert current['status']=='prediction_unavailable' and not current['rows']
                assert 'current_or_target_epidemiological_data_unavailable' in current['reasons']
                old=infer(db,model_version=result['model_version'],origin=date(2021,2,7))
                assert 'model_fitted_after_requested_origin' in old['reasons']
            sensitivity=geography_sensitivity(db,model_version='FICTIONAL-NEW-V3',alternate_dataset_version='FICTIONAL-OPTION-B-v3-higher')
            assert sensitivity['no_refit'] and sensitivity['mean_absolute_prediction_change']>=0
        repo=MLRepository(db)
        assert repo.query('SELECT count(*) n FROM analytics.modelo_investigacion').iloc[0,0]==3
        assert repo.query('SELECT count(*) n FROM analytics.evaluacion_investigacion').iloc[0,0]==7
        blocked=train(db,dataset_version='FICTIONAL-OPTION-B-v3-higher',family='V3',model_version='FICTIONAL-HIGHER-BLOCKED')
        assert blocked['status']=='blocked' and not any('equivalence' in v for v in blocked['reasons'])
        # Reader may infer aggregates, never inspect individual selections.
        with db.cursor() as c:
            c.execute("SELECT has_table_privilege('sigard_epi_analytics_reader','analytics.registro_escenario_ml','SELECT')")
            assert c.fetchone()[0] is False
            c.execute('SET ROLE sigard_epi_analytics_reader')
        assert infer(db,model_version='FICTIONAL-NEW-A',origin=date(2024,2,4))['status']=='available_private_experimental'
        db.rollback()
        with pytest.raises(Exception,match='research_prediction_contract_or_origin_mismatch'):
            with db:
                with db.cursor() as c:
                    c.execute('''INSERT INTO analytics.prediccion_investigacion
                        SELECT 'FICTIONAL-NEW-A',id,'2021-02-07',0.5 FROM territory.radio_censal WHERE codigo='F000' ''')
        # New run, same training data; corrupt only test labels in a fixture
        # returned by SQL. Learned state must not depend on those labels.
        materialize(db,**dict(opts,version='FICTIONAL-OPTION-B-SECOND'))
        original=MLRepository.research_frame
        def changed(self,family,version,**kwargs):
            frame=original(self,family,version,**kwargs)
            if family=='A' and kwargs.get('outcomes',True):
                future=frame.fecha_inicio_semana.ge(DEFAULT_CALENDAR.week_bounds(2024,1)[0])
                frame.loc[future&frame.objetivo_semana_siguiente.notna(),'objetivo_semana_siguiente']=1-frame.loc[future&frame.objetivo_semana_siguiente.notna(),'objetivo_semana_siguiente']
            return frame
        monkeypatch.setattr(MLRepository,'research_frame',changed)
        second=train(db,dataset_version='FICTIONAL-OPTION-B-SECOND-ab-approx',family='A',model_version='FICTIONAL-UNCHANGED-FIT')
        assert second['artifact_sha256']==fitted[0]['artifact_sha256']
        assert second['metadata']['training_matrix_sha256']==fitted[0]['metadata']['training_matrix_sha256']


def test_unreviewed_new_clinical_batch_is_blocked_without_invalidating_old_selection(db,tmp_path):
    from test_epidemiology_database import workbook
    from sigard_ml.ingestion.epidemiology.importer import import_book
    opts=seed(db,tmp_path)
    path=workbook(tmp_path/'FICTIONAL-UNREVIEWED.xlsx',identifier_value='FICTIONAL-NEW-UNREVIEWED')
    import_book(db,path)
    repo=MLRepository(db)
    bids=repo.query('SELECT id FROM ingestion.lote_importacion ORDER BY id').id.tolist()
    with forbid_tabular_reads():
        with pytest.raises(DatasetBlocked,match='not_reviewed'):
            materialize(db,**dict(opts,batch_ids=bids))
        # An unrelated newly imported batch must not falsely stale a complete,
        # explicitly selected immutable clinical review (nor join it implicitly).
        assert materialize(db,**opts)['scope']['years']==list(range(2020,2025))


def test_conditional_2025_2026_materialization_stops_at_source_cutoff_and_keeps_missing_weather(db,tmp_path):
    opts=seed(db,tmp_path,recent=True)
    with forbid_tabular_reads():
        result=materialize(db,**opts)
        assert result['scope']['years']==list(range(2020,2027))
        repo=MLRepository(db)
        weeks=repo.query('''SELECT DISTINCT w.anio,w.inicio,w.fin FROM analytics.conteo_investigacion c
            JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
            WHERE c.dataset_version='FICTIONAL-OPTION-B-ab-approx' ORDER BY w.inicio''')
        assert len(weeks.loc[weeks.anio.eq(2025)])==next(y.weeks for y in DEFAULT_CALENDAR.years if y.year==2025)
        assert max(weeks.loc[weeks.anio.eq(2026),'fin'])<=date(2026,5,13)
        assert not weeks.fin.gt(date(2026,5,13)).any()
        v3=repo.research_frame('V3','FICTIONAL-OPTION-B-v3-approx')
        recent=v3.origin_week.ge(DEFAULT_CALENDAR.week_bounds(2025,1)[0])
        assert v3.loc[recent,'temperature_origin'].isna().all()
        latest=v3.origin_week.ge(date(2026,1,4))
        assert not v3.loc[latest,'predictor_admissible'].any()
