"""Generated, unrelated fixtures; real PostGIS test base only. Never private data."""
from datetime import date, timedelta
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest

from test_epidemiology_database import db, seed_geometry, workbook
from sigard_ml.data_access import DatasetBlocked, MLRepository
from sigard_ml.data_access.equivalence import compare_frames
from sigard_ml.forecasting import database_pipeline as pipeline


@contextmanager
def forbid_tabular(monkeypatch):
    import openpyxl
    import pyarrow.parquet as pq
    import pyarrow.csv as pc
    import pyarrow.dataset as ds
    import geopandas as gpd
    import builtins
    import io
    from pathlib import Path
    def forbidden(*args, **kwargs):
        raise AssertionError('operational tabular file IO forbidden')
    original_open = builtins.open
    original_io_open = io.open
    def checked_open(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).suffix.lower() in ('.csv', '.tsv', '.xlsx', '.xls', '.parquet', '.feather'):
            forbidden()
        return original_open(file, *args, **kwargs)
    def checked_io_open(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).suffix.lower() in ('.csv', '.tsv', '.xlsx', '.xls', '.parquet', '.feather'):
            forbidden()
        return original_io_open(file, *args, **kwargs)
    with monkeypatch.context() as patch:
        for name in ('read_csv', 'read_table', 'read_parquet', 'read_excel', 'read_feather'):
            patch.setattr(pd, name, forbidden)
        patch.setattr(openpyxl, 'load_workbook', forbidden)
        patch.setattr(pq, 'read_table', forbidden)
        patch.setattr(pq, 'ParquetFile', forbidden)
        patch.setattr(pc, 'read_csv', forbidden)
        patch.setattr(ds, 'dataset', forbidden)
        patch.setattr(gpd, 'read_parquet', forbidden)
        patch.setattr(gpd, 'read_file', forbidden)
        patch.setattr(builtins, 'open', checked_open)
        patch.setattr(io, 'open', checked_io_open)
        yield


def seeded(db, tmp_path, *, universe='ab-263-master-v1', version='FICTIONAL-ML', verified=False):
    from sigard_ml.ingestion.epidemiology.importer import import_book
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    seed_geometry(db)
    import_book(db, workbook(tmp_path/'FICTIONAL.xlsx'))
    assign_radios(db)
    first = date(2023, 10, 1) if universe == 'v3-256-subset-v1' else date(2023, 12, 24)
    last = date(2024, 6, 16)
    weeks = {first + timedelta(weeks=i) for i in range((last-first).days//7+1)}
    result = materialize(db, version=version, universe_version=universe, start=first, end=last+timedelta(days=6),
        scenario='experimental_assumed', coverage_weeks=weeks, coverage_ref='FICTIONAL ONLY', accept_provisional=True)
    with db:
        with db.cursor() as c:
            # Entirely generated target fixture; no real cartography/cases.
            c.execute('''UPDATE analytics.conteos_radio_semana SET cantidad_registros=(radio_id+semana_id)%%3,
                registros_observados=(radio_id+semana_id)%%3,
                presencia=(((radio_id+semana_id)%%3)>0)::integer,pendientes_posibles=0,
                fechas_aproximadas=0,ventana_parcial=false WHERE ejecucion_id=%s''', (result['run_id'],))
            c.execute('UPDATE analytics.ejecucion SET equivalencia_ml_verificada=%s,clima_version=%s WHERE id=%s',
                      (verified, 'FICTIONAL-WEATHER', result['run_id']))
            c.execute('''INSERT INTO analytics.clima_semana(version,semana_id,temperatura,humedad,precipitacion,
                disponible_desde,fuente_sha256,compatible)
                SELECT 'FICTIONAL-WEATHER',id,20,45,7,NULL,%s,true
                FROM analytics.semana_epidemiologica WHERE inicio BETWEEN %s AND %s''', ('a'*64,first,last))
    return MLRepository(db), result


def test_equivalence_checker_catches_missing_keys_labels_nulls_features_and_time():
    old = pd.DataFrame(dict(radio=['FICTIONAL-a','FICTIONAL-b'],week=[date(2024,1,7)]*2,
                            x=[1.,np.nan],y=[0,1],end=[date(2024,1,13)]*2))
    kwargs = dict(keys=['radio','week'],features=['x'],labels=['y'],temporal=['end'])
    assert compare_frames(old, old.copy(), **kwargs)['equivalent']
    for column, value in [('x',0.),('y',0),('end',date(2024,1,20))]:
        new = old.copy();new.loc[1,column] = value
        assert not compare_frames(old,new,**kwargs)['equivalent']
    assert not compare_frames(old,old.iloc[:1],**kwargs)['equivalent']
    assert not compare_frames(old,pd.concat([old,old]),**kwargs)['equivalent']
    missing_key=old.copy();missing_key.loc[0,'radio']=None
    assert not compare_frames(missing_key,missing_key,**kwargs)['equivalent']


def test_unverified_equivalence_blocks_fit_and_inference_before_estimator(db,tmp_path,monkeypatch):
    repo,_ = seeded(db,tmp_path)
    from sklearn.ensemble import RandomForestClassifier
    monkeypatch.setattr(RandomForestClassifier,'fit',lambda *a,**k: pytest.fail('no fit'))
    with forbid_tabular(monkeypatch):
        with pytest.raises(DatasetBlocked,match='equivalence_unverified'):
            pipeline.train(repo,'A','FICTIONAL-ML',training_authorized=True)
        fake = pipeline.ResearchFit('B','FICTIONAL-ML',1,date(2024,2,1),None,{})
        with pytest.raises(DatasetBlocked,match='equivalence_unverified'):
            pipeline.predict(repo,fake,origin=date(2024,5,5))


@pytest.mark.parametrize('family',['A','B'])
def test_ab_actual_fit_and_prediction_only_postgres_preserve_features_and_lags(db,tmp_path,monkeypatch,family):
    repo,_ = seeded(db,tmp_path,verified=True)
    from sigard_ml.official.spatial_ml.historical_expansion import FEATURES, LAGS, MISSING
    from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
    with forbid_tabular(monkeypatch):
        frame = pipeline.dataset(repo,family,'FICTIONAL-ML')
        assert frame.radio_censal.nunique()==263
        if family=='B':
            source = repo.weekly('FICTIONAL-ML').set_index(['radio_codigo','semana_inicio']).presencia
            for lag,column in enumerate(LAGS,1):
                expected = [source.get((r,d-timedelta(weeks=lag)),np.nan) for r,d in
                            frame[['radio_censal','fecha_inicio_semana']].itertuples(index=False,name=None)]
                assert np.allclose(frame[column].astype(float),expected,equal_nan=True)
                assert frame[column+'_missing'].eq(frame[column].isna()).all()
        fitted = pipeline.train(repo,family,'FICTIONAL-ML',training_authorized=True)
        estimator = fitted.models['random_forest_'+family]
        assert list(estimator.feature_names_in_)==FEATURES[family]
        assert all(estimator.get_params()[k]==v for k,v in RF_PARAMETERS.items())
        result = pipeline.predict(repo,fitted,origin=date(2024,5,5))
        assert len(result['values'])==263 and result['data_source']=='postgresql'
        from sklearn.ensemble import RandomForestClassifier
        monkeypatch.setattr(RandomForestClassifier,'fit',lambda *a,**k: pytest.fail('infer cannot fit'))
        assert pipeline.predict(repo,fitted,origin=date(2024,5,5))==result
        with pytest.raises(DatasetBlocked,match='not_fitted_before'):
            pipeline.predict(repo,fitted,origin=fitted.fit_cutoff)


def test_v3_db_features_admissibility_horizons_and_no_target_read_on_inference(db,tmp_path,monkeypatch):
    repo,_=seeded(db,tmp_path,universe='v3-256-subset-v1',verified=True)
    from sigard_ml.forecasting.v3 import FEATURES
    with forbid_tabular(monkeypatch):
        # Independently replay the original pure transformations using only
        # generated fixtures fetched from SQL, without a bundle or tabular file.
        from types import SimpleNamespace
        from sigard_ml.forecasting.contracts import PROVISIONAL_EXPERIMENT
        from sigard_ml.forecasting.dataset import build_dataset
        from sigard_ml.forecasting.v3 import feature_frame
        weekly=repo.weekly('FICTIONAL-ML')
        counts=weekly[['radio_codigo','semana_inicio','cantidad_registros']].rename(columns={
            'radio_codigo':'radio_id','semana_inicio':'week_start','cantidad_registros':'count'})
        counts=counts.assign(available_on=None,state='provisional',pending=False,
            coverage_complete=False,mature=False,source_ref='FICTIONAL-DB-COUNTS')
        weather=repo.climate('FICTIONAL-ML').rename(columns={'inicio':'week_start','temperatura':'temperature',
            'humedad':'humidity','precipitacion':'precipitation','compatible':'complete'})
        weather=weather.assign(available_on=None,source_ref='FICTIONAL-DB-WEATHER')
        territory=repo.territory('v3-256-subset-v1').assign(available_on=None,source_ref='FICTIONAL-DB-CONTEXT')
        inputs=SimpleNamespace(validate=lambda:None,radios=tuple(territory.radio_id),counts=counts,
            climate=weather,territory=territory,edges=(),graph_available_on=None,graph_ref='FICTIONAL-DB-GRAPH',
            dataset_version='FICTIONAL-ML',data_kind='FICTIONAL',count_unit='snapshot_record_count',
            experiment_mode=PROVISIONAL_EXPERIMENT,training_authorized=True,evaluation_authorized=True,
            input_evidence={'fixture':'FICTIONAL generated SQL rows'})
        for h in (1,2,4):
            frame=pipeline.dataset(repo,'V3','FICTIONAL-ML',horizon=h,
                validation_start=date(2024,3,3),test_start=date(2024,5,5))
            assert frame.radio_id.nunique()==256
            assert frame.target_week.eq(frame.origin_week.map(lambda d:d+timedelta(weeks=h))).all()
            assert set(FEATURES)<=set(frame)
            assert frame.predictor_admissible.any()
            original=build_dataset(inputs,start=min(frame.origin_week),end=max(frame.origin_week),
                evaluation_as_of=date(2026,10,29),horizon_weeks=h)
            original=feature_frame(inputs,original,h)
            check=compare_frames(original,frame,keys=['radio_id','origin_week'],features=FEATURES,
                labels=['target_count'],temporal=['target_week','cutoff_date'])
            assert check['equivalent'],check
        original=repo.query
        statements=[]
        def trace(statement,parameters=()):
            text=statement.as_string(db) if hasattr(statement,'as_string') else statement
            statements.append(text)
            return original(statement,parameters)
        monkeypatch.setattr(repo,'query',trace)
        infer_frame=pipeline.dataset(repo,'V3','FICTIONAL-ML',outcomes=False,origin=date(2024,4,7))
        assert 'target_count' not in infer_frame
        assert not any('target_count' in s for s in statements)
        fitted=pipeline.train(repo,'V3','FICTIONAL-ML',training_authorized=True,
            validation_start=date(2024,3,3),test_start=date(2024,5,5))
        from sigard_ml.forecasting.v3 import CANDIDATES
        assert set(CANDIDATES)<=set(fitted.report['validation'])
        # The reference remains selectable without promoting any ML candidate.
        fitted.models['selection']=dict(fitted.models['selection'],selected='lag_1_or_training_mean')
        predicted=pipeline.predict(repo,fitted,origin=date(2024,5,12))
        assert len(predicted['values'])==256
        # Change only an outcome in the fictitious base: origin predictors must
        # remain unchanged; neither label-free query reads that future value.
        with db:
            with db.cursor() as c:
                c.execute('''UPDATE analytics.conteos_radio_semana SET cantidad_registros=99,registros_observados=99,presencia=1
                    WHERE semana_id=(SELECT id FROM analytics.semana_epidemiologica WHERE inicio='2024-04-14')''')
        after=pipeline.dataset(repo,'V3','FICTIONAL-ML',outcomes=False,origin=date(2024,4,7))
        pd.testing.assert_frame_equal(infer_frame[list(FEATURES)],after[list(FEATURES)])


def test_new_authorized_batch_needs_new_materialization_never_trains(db,tmp_path,monkeypatch):
    repo,run=seeded(db,tmp_path)
    from sigard_ml.ingestion.epidemiology.importer import import_book
    from sigard_ml.ingestion.epidemiology.analytics import materialize
    from sigard_ml.ingestion.epidemiology.territory import assign_radios
    before=repo.weekly('FICTIONAL-ML')
    path=workbook(tmp_path/'FICTIONAL-NEW.xlsx',identifier_value='FICTIONAL NEW LOT',when=date(2024,3,24))
    from sklearn.ensemble import RandomForestClassifier,HistGradientBoostingRegressor
    for cls in (RandomForestClassifier,HistGradientBoostingRegressor):
        monkeypatch.setattr(cls,'fit',lambda *a,**k:pytest.fail('ingestion/materialization must not train'))
    new=import_book(db,path)
    assign_radios(db)
    with forbid_tabular(monkeypatch):
        fresh=materialize(db,version='FICTIONAL-UPDATED',universe_version='ab-263-master-v1',
            start=date(2024,3,17),end=date(2024,4,6),scenario='experimental_assumed',
            coverage_weeks={date(2024,3,17),date(2024,3,24),date(2024,3,31)},coverage_ref='FICTIONAL NEW SCOPE',accept_provisional=True)
        assert fresh['run_id']!=run['run_id']
        updated=repo.legacy_frame('B','FICTIONAL-UPDATED',require_equivalence=False)
        assert updated.objetivo_semana_siguiente.notna().any()
        assert repo.run('FICTIONAL-UPDATED')['equivalencia_ml_verificada'] is False
        pd.testing.assert_frame_equal(before,repo.weekly('FICTIONAL-ML'))
        with db.cursor() as c:
            c.execute('SELECT count(*) FROM analytics.modelo_predictivo');assert c.fetchone()[0]==0


def test_reader_metadata_without_private_records_and_withdrawn_batch_blocks(db,tmp_path):
    repo,run=seeded(db,tmp_path)
    with db.cursor() as c:c.execute('SET ROLE sigard_epi_analytics_reader')
    assert repo.run('FICTIONAL-ML')['version']=='FICTIONAL-ML'
    assert len(repo.legacy_frame('A','FICTIONAL-ML',require_equivalence=False))>0
    db.rollback()
    from psycopg2.extras import Json
    with db:
        with db.cursor() as c:
            c.execute('''INSERT INTO ingestion.estado_lote_sisa(lote_id,estado,motivo)
                VALUES((SELECT min(lote_id) FROM analytics.fuente_ejecucion WHERE ejecucion_id=%s),'withdrawn','FICTIONAL')''',(run['run_id'],))
    with pytest.raises(DatasetBlocked,match='withdrawn'):
        repo.legacy_frame('A','FICTIONAL-ML',require_equivalence=False)
