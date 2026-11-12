"""Real PostGIS tests use the owned temporary DB and generated stage1 fixtures."""
from datetime import date
from types import SimpleNamespace
import pandas as pd
import pytest
from psycopg2.extras import Json

from test_epidemiology_database import db
from test_consolidation import seed
from sigard_ml.forecasting.consolidation import materialize
from sigard_ml.forecasting.motor_data import load_frame
from sigard_ml.forecasting.motor_protocol import PROTOCOL,PRESENCE,PRESENCE_BASELINES,COUNT_BASELINES
from sigard_ml.forecasting.motor_campaign import register_model,register_predictions
from sigard_ml.ingestion.epidemiology.resolution import original_fingerprint
from sigard_ml.data_access.tabular_guard import forbid_tabular_reads


def campaign(db,tmp_path):
    cfg=seed(db,tmp_path);result=materialize(db,cfg)
    with db:
        with db.cursor() as cur:
            cur.execute('''INSERT INTO analytics.motor_campania(version,dataset_version,protocolo,protocolo_sha256,
                dataset_sha256,codigo_sha256,entorno,autorizacion) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                ('FICTIONAL-MOTOR',cfg['dataset_version'],Json(PROTOCOL),'a'*64,result['input_sha256'],Json({}),Json({}),'FICTIONAL ONLY'))
    return cfg,result


def predictions():
    row=dict(radio_id=1,origin_week=date(2022,2,6),target_week=date(2022,2,13))
    for name in (*PRESENCE,*PRESENCE_BASELINES):row[name]=.2;row[name+'_threshold']=.5
    for name in ('residual_h1',*COUNT_BASELINES):row[name]=1.
    return pd.DataFrame([row])


def test_registry_checks_purge_scope_domains_immutability_and_preserves_sources(db,tmp_path):
    cfg,result=campaign(db,tmp_path);before=original_fingerprint(db)
    with pytest.raises(Exception):register_predictions(db,'FICTIONAL-MOTOR','FICTIONAL-BLOCK',predictions())
    for method in (*PRESENCE,'residual_h1'):
        register_model(db,'FICTIONAL-MOTOR','FICTIONAL-BLOCK','development_fold',method,
            SimpleNamespace(metadata={'FICTIONAL':True}),date(2021,1,1),tmp_path)
    register_predictions(db,'FICTIONAL-MOTOR','FICTIONAL-BLOCK',predictions())
    with pytest.raises(Exception):
        with db:
            with db.cursor() as cur:cur.execute("UPDATE analytics.motor_campania SET horizonte=2")
    other=predictions();other['origin_week']=date(2022,2,13);other['target_week']=date(2022,2,20)
    other[PRESENCE[0]]=1.1
    with pytest.raises(Exception):register_predictions(db,'FICTIONAL-MOTOR','FICTIONAL-BLOCK',other)
    assert original_fingerprint(db)==before


def test_postgresql_matrix_uses_new_policy_common_mask_and_no_tabular_sources(db,tmp_path):
    cfg,result=campaign(db,tmp_path)
    with forbid_tabular_reads():frame,metadata=load_frame(db,cfg['dataset_version'],result['input_sha256'])
    assert metadata['radios']==256 and frame.radio_id.nunique()==256
    assert frame.loc[frame.target_year.eq(2022),'target_count'].gt(0).any()
    assert frame.loc[frame.target_year.eq(2025),'target_count'].isna().all()
    assert frame.poblacion.isna().all() and frame.densidad_poblacional.isna().all()
    assert frame.loc[frame.origin_week.eq(date(2022,3,6)),'count_origin'].isna().all()
