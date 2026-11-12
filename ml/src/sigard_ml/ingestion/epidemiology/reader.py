"""Read every nonempty original XLSX row without altering the workbook.

Cells are positional and typed, so duplicate/unknown headers and formulas remain
recoverable. Never send raw rows or exceptions to logs.
"""
from collections import Counter
from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import re

from openpyxl import load_workbook
from sigard_ml.official.normalization import normalize_text, parse_date, parse_coordinate
from sigard_ml.official.settings import identify_column, normalize_header

VERSION = "sigard-epi-db-import-1"
ROOT = Path(__file__).resolve().parents[5]
REFERENCE_ROOT = ROOT / "data/datos oficiales"
SOURCE_NAMES = [f"Sisa_{year}_calles_corregidas_coordenadas(2).xlsx" for year in [2020,2021,2022,2023,"2024-2026"]]
EXTRA = {
    "grupo etario diagnostico":"age_group", "calle domicilio":"address", "numero domicilio":"street_number",
    "pais residencia":"country", "clasificacion caso":"classification",
    "geocod estado":"geocoding_status", "geocod direccion normalizada":"normalized_address",
    "geocod calle oficial":"official_street", "geocod calle id":"official_street_id",
    "geocod metodo resolucion":"geocoding_method", "geocod proveedor":"geocoding_provider",
    "geocod precision":"coordinate_precision", "geocod confianza":"geocoding_confidence",
    "geocod latitud":"latitude", "geocod longitud":"longitude", "geocod radio censal":"radio",
    "geocod fraccion censal":"fraction", "geocod requiere revision":"geocoding_review",
    "geocod motivo":"geocoding_reason", "fila original":"upstream_row", "archivo de origen":"upstream_file",
    "id evento caso":"event_id", "clasificacion manual del caso":"classification",
    "departamento de residencia":"department", "localidad de residencia":"locality",
    "provincia de residencia":"province", "pais de residencia":"country",
    "pais":"country", "fraccion":"fraction", "fraccion censal":"fraction",
    "radio":"radio", "radio censal":"radio", "grupo etario":"age_group",
    "confianza geocodificacion":"geocoding_confidence", "metodo geocodificacion":"geocoding_method",
    "proveedor geocodificacion":"geocoding_provider", "calle normalizada":"normalized_address",
    "direccion normalizada":"normalized_address", "numero":"street_number",
    "fecha de notificacion":"notification_on", "fecha de registro":"system_on",
    "fecha de ultima actualizacion":"updated_on", "confianza":"geocoding_confidence",
}
DATE_TYPES={"symptom_onset":"symptom_onset", "sample_on":"sample_on", "opened_on":"notification_on",
    "notification_on":"notification_on", "updated_on":"updated_on", "system_on":"system_on", "birth_on":"birth_on"}

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def field_for(header):return EXTRA.get(normalize_header(header),identify_column(header))

def resolve_sources(root=None):
    root=Path(root or os.environ.get('SIGARD_SISA_SOURCE_ROOT',REFERENCE_ROOT)).resolve()
    if not root.is_dir():raise ValueError('source_directory_missing')
    sources=[];missing=[]
    for name in SOURCE_NAMES:
        exact=root/name
        alternate=root/name.replace('(2)','')
        if exact.is_file():sources.append(exact)
        elif alternate.is_file():sources.append(alternate)
        else:missing.append(name)
    return sources,missing

def typed(cell):
    v=cell.value
    if isinstance(v,(datetime,date,time)):value=v.isoformat();kind=type(v).__name__
    elif v is None:value=None;kind='null'
    elif isinstance(v,bool):value=v;kind='bool'
    elif isinstance(v,(int,float)):value=v;kind='number'
    else:value=str(v);kind='formula' if cell.data_type=='f' else 'text'
    return dict(value=value,type=kind,excel_type=cell.data_type,number_format=cell.number_format)

def identifier(cell):
    value=normalize_text(cell.value)
    if isinstance(cell.value,(int,float)) and re.fullmatch('0+',cell.number_format or ''):
        value=str(int(cell.value)).zfill(len(cell.number_format))
    return value

def read_book(path):
    path=Path(path);before=digest(path)
    workbook=load_workbook(path,read_only=True,data_only=False,keep_links=False)
    sheets=[]
    try:
        for ordinal,ws in enumerate(workbook.worksheets,1):
            data=list(ws.iter_rows())
            first=next((i for i,row in enumerate(data) if sum(field_for(c.value) is not None for c in row)>=2),None)
            if first is None:
                if not any(any(c.value is not None for c in row) for row in data):
                    sheets.append(dict(name=ws.title,ordinal=ordinal,header_row=0,columns=[],rows=[],preamble=[]));continue
                # Unrecognized sheets have NO assumed header: preserve every row.
                first=-1
                cols=[dict(ordinal=i,label=None,field=None) for i in range(1,ws.max_column+1)]
            else:
                headers=data[first]
                cols=[dict(ordinal=i,label=normalize_text(c.value),field=field_for(c.value)) for i,c in enumerate(headers,1)]
            rows=[]
            for rownum,cells in enumerate(data[first+1:],first+2):
                if not any(c.value is not None for c in cells):continue
                payload=[typed(c) for c in cells]
                rawhash=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
                values={}
                for col,cell in zip(cols,cells):
                    field=col['field']
                    if field and field not in values:values[field]=dict(value=cell.value,column=col['ordinal'],text=identifier(cell))
                rows.append(dict(row_number=rownum,content=payload,row_hash=rawhash,values=values))
            layout_hash=hashlib.sha256(json.dumps(cols,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            sheets.append(dict(name=ws.title,ordinal=ordinal,header_row=first+1,columns=cols,rows=rows,layout_hash=layout_hash,
                preamble=[[typed(c) for c in row] for row in data[:first]] if first>=0 else []))
    finally:workbook.close()
    if digest(path)!=before:raise ValueError('source_changed_during_read')
    return dict(path=path,name=path.name,sha256=before,size=path.stat().st_size,sheets=sheets)

def profile(book):
    result=dict(name=book['name'],sha256=book['sha256'],size=book['size'],sheets=[])
    for sheet in book['sheets']:
        columns=[]
        for col in sheet['columns']:
            values=[r['content'][col['ordinal']-1] for r in sheet['rows']]
            field=col['field'];dest='ingestion.fila_staging.content'
            if field in DATE_TYPES:dest='epidemiology.fecha_registro'
            elif field in ['classification','algorithm_classification']:dest='epidemiology.clasificacion_registro'
            elif field in ['latitude','longitude','geocoding_status','coordinate_precision','geocoding_method','geocoding_confidence','geocoding_provider']:dest='territory.geocodificacion'
            elif field in ['country','province','department','locality','address','normalized_address','street_number']:dest='territory.domicilio / catálogos'
            elif field in ['event_id','age','age_group','sex']:dest='epidemiology.registro_epidemiologico'
            columns.append(dict(**col,types=dict(Counter(c['type'] for c in values)),nulls=sum(c['value'] is None for c in values),destination=dest))
        ids=[r['values'].get('event_id',{}).get('text') for r in sheet['rows']]
        counts=Counter(i for i in ids if i)
        classes=Counter(r['values'].get('classification',{}).get('text') for r in sheet['rows'])
        dates={}
        for field in DATE_TYPES:
            observations=[parse_date(r['values'].get(field,{}).get('value')) for r in sheet['rows']]
            known=[d for d,state in observations if d]
            if any(field in r['values'] for r in sheet['rows']):
                dates[field]=dict(states=dict(Counter(s for d,s in observations)),years=dict(Counter(d.year for d in known)),
                    first=str(min(known)) if known else None,last=str(max(known)) if known else None)
        result['sheets'].append(dict(name=sheet['name'],header_row=sheet['header_row'],columns=columns,rows=len(sheet['rows']),
            repeated_identifier_groups=sum(v>1 for v in counts.values()),repeated_identifier_rows=sum(v for v in counts.values() if v>1),
            exact_repeated_rows=len(sheet['rows'])-len({r['row_hash'] for r in sheet['rows']}),classifications=dict(classes),dates=dates))
    return result
