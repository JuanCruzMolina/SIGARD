"""Transactional adapter boundary for complementary sources, never model fitting.

Adapters turn file/API snapshots into typed frames. The importer archives bytes,
validates keys and domain constraints, and commits a whole version or nothing.
Existing SISA XLSX imports remain in importer.py; they are never replayed here.
"""
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd
from psycopg2.extras import Json, execute_values

from .db import get_id
from .analytics import seed_policies


@dataclass
class Adapted:
    kind: str
    frame: pd.DataFrame
    source_rows: int
    contract: dict


class Adapter(Protocol):
    name: str
    def read(self, content: bytes) -> Adapted: ...


def finite_numeric(frame, columns, *, integer=False):
    for name in columns:
        frame[name] = pd.to_numeric(frame[name], errors='raise')
        values = frame[name].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (integer and ((values < 0).any() or (values % 1 != 0).any())):
            raise ValueError('invalid_numeric_domain')


class OpenMeteoCSV:
    name = 'open-meteo-daily-csv-1'

    def read(self, content):
        text=content.decode('utf-8-sig')
        lines=text.splitlines()
        if not lines[0].startswith('latitude,longitude,elevation,') or not lines[3].startswith('time,'):
            raise ValueError('climate_structure_invalid')
        metadata=pd.read_csv(io.StringIO('\n'.join(lines[:2]))).iloc[0]
        frame=pd.read_csv(io.StringIO(text),skiprows=3)
        if len(frame.columns)!=6:raise ValueError('climate_structure_invalid')
        expected=['time','temperature_2m_max (','temperature_2m_min (','temperature_2m_mean (',
            'relative_humidity_2m_mean (%)','precipitation_sum (mm)']
        if not all(str(a).startswith(b) for a,b in zip(frame.columns,expected)):
            raise ValueError('climate_header_order_invalid')
        if any(str(c).split('(')[-1].replace('°','')!='C)' for c in frame.columns[1:4]):
            raise ValueError('climate_temperature_unit_not_celsius')
        return self._adapt(frame,metadata)

    def _adapt(self, frame, metadata):
        return climate_frame(frame,metadata)


def climate_frame(frame, metadata):
    # Header text can carry a degree sign in either UTF-8 or legacy encodings;
    # the reviewed positional layout is validated before using positions.
    if len(frame.columns)!=6:raise ValueError('climate_structure_invalid')
    frame=frame.copy()
    frame.columns=['date','temperature_max','temperature_min','temperature','humidity','precipitation']
    frame['date']=pd.to_datetime(frame.date,format='%Y-%m-%d',errors='raise').dt.date
    finite_numeric(frame,['temperature_max','temperature_min','temperature','humidity','precipitation'])
    if frame.date.duplicated().any() or not frame.humidity.between(0,100).all() or (frame.precipitation<0).any():
        raise ValueError('invalid_climate_keys_or_domain')
    if not ((frame.temperature_min<=frame.temperature)&(frame.temperature<=frame.temperature_max)).all():
        raise ValueError('invalid_temperature_range')
    return Adapted('climate_daily',frame,len(frame),dict(
        provenance='local_Open-Meteo_export; historical_product_and_retrieval_time_not_accredited',
        station=dict(latitude=float(metadata.latitude),longitude=float(metadata.longitude),
                     timezone=str(metadata.timezone)),available_on=None,
        operational_availability_verified=False,spatial_resolution='single_city_reference_point'))


class PublicDengueCSV:
    name='public-dengue-aggregate-csv-1'

    def read(self,content):
        try:text=content.decode('utf-8-sig')
        except UnicodeDecodeError:text=content.decode('cp1252')
        frame=pd.read_csv(io.StringIO(text),sep=';',dtype=str)
        required={'id_depto_indec_residencia','id_prov_indec_residencia','anio_min','sepi_min','evento','grupo_etario','cantidad'}
        if not required<=set(frame):raise ValueError('public_structure_invalid')
        total=len(frame)
        province=pd.to_numeric(frame.id_prov_indec_residencia,errors='coerce')
        dept=pd.to_numeric(frame.id_depto_indec_residencia,errors='coerce')
        frame=frame.loc[province.eq(46)&dept.eq(14)].copy()
        finite_numeric(frame,['anio_min','sepi_min','cantidad'],integer=True)
        if frame[['evento','grupo_etario']].isna().any().any():raise ValueError('public_missing_dimensions')
        if frame.duplicated(['anio_min','sepi_min','evento','grupo_etario']).any():raise ValueError('public_duplicate_key')
        return Adapted('public_aggregate',frame,total,dict(
            provenance='local_national_public_aggregate_export',scope='province=46; department=014',
            not_additive_to_sisa=True,excluded_from_main_target=True,
            reason='different_extraction_population_and_revision; event is not an independently adjudicated episode'))


class CensusCSV:
    name='census-2022-aggregate-csv-1'

    def read(self,content):
        frame=pd.read_csv(io.BytesIO(content),dtype=str)
        required={'codigo','cod_prov','cod_dep','fraccion','radio','cod_variable','cod_categoria','categoria','cantidad'}
        if not required<=set(frame):raise ValueError('census_structure_invalid')
        total=len(frame)
        from sigard_ml.validation.territorial import normalize_code
        for column,width in [('codigo',9),('cod_prov',2),('cod_dep',3),('fraccion',2),('radio',2)]:
            frame[column]=normalize_code(frame[column],width,column)
        if not frame.codigo.eq(frame.cod_prov+frame.cod_dep+frame.fraccion+frame.radio).all():
            raise ValueError('census_component_code_mismatch')
        frame=frame.loc[frame.cod_prov.eq('46')&frame.cod_dep.eq('014')].copy()
        if frame.empty:raise ValueError('census_capital_empty')
        finite_numeric(frame,['cantidad'],integer=True)
        if frame[list(required)].isna().any().any():raise ValueError('census_missing_dimensions')
        if frame[['cod_variable','cod_categoria','categoria']].apply(lambda s:s.str.strip().eq('').any()).any():
            raise ValueError('census_empty_dimensions')
        if frame.duplicated(['codigo','cod_variable','cod_categoria']).any():raise ValueError('census_duplicate_key')
        if frame.groupby(['cod_variable','cod_categoria']).categoria.nunique().gt(1).any():
            raise ValueError('census_conflicting_category_labels')
        return Adapted('census_aggregate',frame,total,dict(provenance='local_INDEC_2022_radio_aggregate',
            reference_year=2022,validation_version='census-components-2',
            scope='Capital; exact canonical radio key intersection',
            not_population_growth_estimate=True,features_in_city_model=False,
            reason='static context constant within the only defensible territorial unit'))


def withdraw(conn, batch_id, *, reason):
    if not reason.strip():raise ValueError('withdrawal_reason_required')
    with conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ingestion.estado_lote_complementario(lote_id,estado,motivo) VALUES(%s,'withdrawn',%s)", (batch_id,reason))
    return dict(batch_id=batch_id,state='withdrawn',existing_snapshots_retained=True,retraining=False)


def withdraw_sisa(conn,batch_id,*,reason):
    if not reason.strip():raise ValueError('withdrawal_reason_required')
    with conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ingestion.estado_lote_sisa(lote_id,estado,motivo) VALUES(%s,'withdrawn',%s)",(batch_id,reason))
    return dict(batch_id=batch_id,state='withdrawn',source_rows_preserved=True,retraining=False)


def import_complement(conn,path,adapter,*,expected_sha256,version,authorization_ref,fail_after=None):
    try:
        result=_import_complement(conn,path,adapter,expected_sha256=expected_sha256,version=version,
            authorization_ref=authorization_ref,fail_after=fail_after)
    except Exception as error:
        conn.rollback()
        with conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO ingestion.intento_complementario(fuente_sha256,adaptador,version,estado,codigo) VALUES(%s,%s,%s,'failed',%s)",
                    (expected_sha256,adapter.name,version,type(error).__name__))
        raise
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO ingestion.intento_complementario(fuente_sha256,adaptador,version,estado,codigo) VALUES(%s,%s,%s,%s,%s)',
                (expected_sha256,adapter.name,version,result['status'],'validated_or_idempotent'))
    return result


def _import_complement(conn,path,adapter,*,expected_sha256,version,authorization_ref,fail_after=None):
    if not version or not authorization_ref:raise ValueError('import_contract_required')
    path=Path(path)
    content=path.read_bytes()
    sha=hashlib.sha256(content).hexdigest()
    if sha!=expected_sha256:raise ValueError('source_hash_mismatch')
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827193)')
            cur.execute('''SELECT b.id,b.contrato FROM ingestion.lote_complementario b
                JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id
                WHERE a.sha256=%s AND b.adaptador=%s AND b.version=%s''',(sha,adapter.name,version))
            old=cur.fetchone()
            if old:
                cur.execute('SELECT 1 FROM ingestion.lotes_complementarios_vigentes WHERE id=%s',(old[0],))
                if not cur.fetchone():raise ValueError('withdrawn_batch_requires_new_version')
                return dict(status='already_imported',batch_id=old[0],sha256=sha)
    data=adapter.read(content)
    seed_policies(conn)
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827193)')
            fid=get_id(cur,'ingestion.archivo_fuente',dict(nombre_original=path.name,sha256=sha,bytes=len(content),
                procedencia=data.contract['provenance'],entrega_version=version,contenido_original=content),keys=['sha256'])
            radios={}
            if data.kind=='census_aggregate':
                cur.execute("SELECT r.codigo,r.id FROM territory.radio_censal r JOIN territory.miembro_universo m ON m.radio_id=r.id JOIN territory.universo u ON u.id=m.universo_id WHERE u.version='ab-263-master-v1'")
                pairs=cur.fetchall()
                if not pairs or len({code for code,_ in pairs})!=len(pairs):
                    raise ValueError('census_ambiguous_or_empty_master')
                radios=dict(pairs)
                source_codes=set(data.frame.codigo)
                data.contract['linkage'] = dict(
                    universe='ab-263-master-v1',method='exact_normalized_components',
                    missing_from_source=sorted(set(radios)-source_codes),
                    not_in_master=sorted(source_codes-set(radios)),
                    matched_radios=len(source_codes & set(radios)),
                    geometry_compatibility='requires_separate_master_hash_verification')
                data.frame=data.frame.loc[data.frame.codigo.isin(radios)].copy()
            cur.execute('''INSERT INTO ingestion.lote_complementario(archivo_id,adaptador,version,tipo,filas_fuente,filas_aceptadas,contrato)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (fid,adapter.name,version,data.kind,data.source_rows,len(data.frame),Json(dict(data.contract,authorization_ref=authorization_ref))))
            bid=cur.fetchone()[0]
            staged=json.loads(data.frame.to_json(orient='records',date_format='iso'))
            if staged:
                execute_values(cur,'INSERT INTO ingestion.fila_complementaria VALUES %s',
                    [(bid,i,Json(row),hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest())
                     for i,row in enumerate(staged,1)],page_size=1000)
            # Accepted rows are fixed at INSERT because batch evidence is immutable.
            rows=[]
            if data.kind=='climate_daily':
                station=data.contract['station'];code='open-meteo-'+sha[:16]
                cur.execute('''INSERT INTO territory.estacion_climatica(codigo,descripcion,geom,zona_horaria)
                    VALUES(%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s) ON CONFLICT(codigo) DO NOTHING''',
                    (code,'Public export reference point, no patient locations',station['longitude'],station['latitude'],station['timezone']))
                cur.execute('SELECT id FROM territory.estacion_climatica WHERE codigo=%s',(code,));sid=cur.fetchone()[0]
                rows=[(bid,sid,r.date,r.temperature_min,r.temperature_max,r.temperature,r.humidity,r.precipitation,None) for r in data.frame.itertuples()]
                if rows:execute_values(cur,'INSERT INTO epidemiology.clima_diario VALUES %s',rows,page_size=1000)
            elif data.kind=='public_aggregate':
                cur.execute("SELECT d.id FROM territory.departamento d JOIN territory.provincia p ON p.id=d.provincia_id WHERE d.codigo='014' AND p.codigo='46'")
                dept=cur.fetchone()[0]
                for r in data.frame.itertuples():
                    cur.execute('SELECT id FROM analytics.semana_epidemiologica WHERE anio=%s AND numero=%s',(int(r.anio_min),int(r.sepi_min)))
                    found=cur.fetchone()
                    if not found:raise ValueError('public_calendar_unsupported')
                    event=get_id(cur,'epidemiology.evento_agregado',dict(codigo=r.evento))
                    age=get_id(cur,'epidemiology.grupo_etario',dict(literal=r.grupo_etario))
                    rows.append((bid,dept,found[0],event,age,int(r.cantidad)))
                if rows:execute_values(cur,'INSERT INTO epidemiology.agregado_publico VALUES %s',rows)
            elif data.kind=='census_aggregate':
                categories={}
                for r in data.frame.itertuples():
                    if r.codigo not in radios:continue
                    key=(r.cod_variable,r.cod_categoria)
                    if key not in categories:
                        variable=get_id(cur,'territory.variable_censal',dict(codigo=r.cod_variable))
                        categories[key]=get_id(cur,'territory.categoria_censal',dict(variable_id=variable,codigo=r.cod_categoria,descripcion=r.categoria),keys=['variable_id','codigo'])
                    rows.append((bid,radios[r.codigo],categories[key],int(r.cantidad)))
                if rows:execute_values(cur,'INSERT INTO territory.observacion_censal VALUES %s',rows,page_size=1000)
            else:raise ValueError('unsupported_adapter_kind')
            if fail_after is not None:raise ValueError('injected_transaction_failure')
            cur.execute("INSERT INTO ingestion.estado_lote_complementario(lote_id,estado,motivo) VALUES(%s,'accepted',%s)",(bid,'validated_transaction; accepted_rows='+str(len(rows))))
            if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('source_changed_during_import')
    return dict(status='imported',batch_id=bid,sha256=sha,source_rows=data.source_rows,accepted_rows=len(rows),not_in_scope=data.source_rows-len(rows),retraining=False)
