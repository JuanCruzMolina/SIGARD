"""Read-only local source inventory. Never deserialize estimators or emit rows.

The private manifest distinguishes byte-identical copies, tabular datasets and
non-data supporting artifacts. XLSX structure is read from archived DB staging.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def category(path):
    text = path.as_posix().lower()
    if any(s in text for s in ('artifacts/', 'predic', 'model', 'forecast', 'training', 'entrenamiento', 'principal_', 'research', 'evaluation')):
        return 'previous_results_and_models'
    if any(s in text for s in ('meteo', 'clima', 'weather')):
        return 'meteorological'
    if any(s in text for s in ('46-la-rioja', 'censal_context', 'poblacion')):
        return 'demographic'
    if any(s in text for s in ('radio', 'territor', 'geograph', 'geometr', 'boundary')):
        return 'geographic'
    if any(s in text for s in ('datos oficiales', 'casos_dengue', 'sisa', 'normalized', 'observed', 'vinculacion', 'correccion')):
        return 'epidemiological'
    return 'historical_derivatives'


def frame_profile(frame):
    result = dict(rows=len(frame), variables=list(map(str, frame.columns)),
                  missing={str(k): int(v) for k, v in frame.isna().sum().items()})
    periods = {}
    for col in frame:
        key = str(col).lower()
        if key in ('year','anio','anio_min','año','ano'):
            years=pd.to_numeric(frame[col],errors='coerce')
            valid=years.loc[years.between(1900,2100)]
            if len(valid):periods[str(col)]=dict(first=str(int(valid.min())),last=str(int(valid.max())),parsed=len(valid))
        if any(s in key for s in ('fecha', 'week_start', 'origin_week', 'target_week', 'date', 'time')) and not any(s in key for s in ('missing', 'invalid', 'estado', 'reason', 'version')):
            series = pd.to_datetime(frame[col], errors='coerce', format='mixed', utc=True)
            if series.notna().any():
                periods[str(col)] = dict(first=series.min().isoformat(), last=series.max().isoformat(), parsed=int(series.notna().sum()))
    result['period'] = periods
    return result


def csv_profile(path):
    try:
        with path.open(encoding='utf-8-sig') as stream:
            prefix = stream.read(8192)
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        encoding = 'cp1252'
        with path.open(encoding=encoding) as stream:
            prefix = stream.read(8192)
    skip = 3 if prefix.startswith('latitude,longitude,elevation') else 0
    delimiter = ';' if prefix.splitlines()[skip].count(';') > prefix.splitlines()[skip].count(',') else ','
    total, missing, variables, periods = 0, Counter(), [], {}
    for chunk in pd.read_csv(path, sep=delimiter, encoding=encoding, skiprows=skip, chunksize=50000, low_memory=False):
        info = frame_profile(chunk)
        total += len(chunk); variables = info['variables']; missing.update(info['missing'])
        for col, bounds in info['period'].items():
            if col not in periods: periods[col] = bounds
            else:
                periods[col]['first'] = min(periods[col]['first'], bounds['first'])
                periods[col]['last'] = max(periods[col]['last'], bounds['last'])
                periods[col]['parsed'] += bounds['parsed']
    return dict(rows=total, variables=variables, missing=dict(missing), period=periods, encoding=encoding, delimiter=delimiter)


def json_profile(value):
    tables, keys = [], set()
    def visit(item, location='$'):
        if isinstance(item, dict):
            keys.update(map(str, item))
            for key, child in item.items():
                if isinstance(child, (dict, list)):visit(child, location + '.' + str(key))
        elif isinstance(item, list):
            if item and all(isinstance(row, dict) for row in item):
                columns = sorted({str(k) for row in item for k in row})
                tables.append(dict(location=location, rows=len(item), variables=columns,
                    missing={col:sum(row.get(col) is None for row in item) for col in columns}))
                # Nested records are inspected for schema without retaining values.
                for child in item:visit(child, location+'[]')
            else:
                for child in item:
                    if isinstance(child,(dict,list)):visit(child,location+'[]')
    visit(value)
    # Repeated nested structures can produce many equal profiles.
    unique = {json.dumps(row,sort_keys=True):row for row in tables}
    return dict(top_level_variables=sorted(keys), tables=list(unique.values()))


def database_sources(conn):
    sources = {}
    with conn.cursor() as cur:
        cur.execute('SELECT id,sha256,nombre_original,procedencia FROM ingestion.archivo_fuente')
        for fid, sha, name, provenance in cur.fetchall():
            cur.execute('''SELECT h.nombre,count(DISTINCT s.id) FROM ingestion.hoja_fuente h
                LEFT JOIN ingestion.fila_staging s ON s.hoja_id=h.id WHERE h.archivo_id=%s GROUP BY h.id''',(fid,))
            sheets=cur.fetchall()
            cur.execute('''SELECT c.nombre_original,c.campo_propuesto,
                count(*) FILTER(WHERE s.contenido->(c.ordinal-1)->>'value' IS NULL)
                FROM ingestion.columna_fuente c JOIN ingestion.hoja_fuente h ON h.id=c.hoja_id
                LEFT JOIN ingestion.fila_staging s ON s.hoja_id=h.id WHERE h.archivo_id=%s GROUP BY c.id''',(fid,))
            columns=cur.fetchall()
            cur.execute('''SELECT t.codigo,min(f.valor),max(f.valor),count(f.valor) FROM epidemiology.fecha_registro f
                JOIN epidemiology.tipo_fecha t ON t.id=f.tipo_id JOIN epidemiology.registro_epidemiologico r ON r.id=f.registro_id
                JOIN ingestion.fila_staging s ON s.id=r.fila_id JOIN ingestion.lote_importacion l ON l.id=s.lote_id
                WHERE l.archivo_id=%s GROUP BY t.codigo''',(fid,))
            sources[sha]=dict(database_file_id=fid,name=name,provenance=provenance,rows=sum(n for _,n in sheets),
                variables=[dict(name=n,field=f,missing=m) for n,f,m in columns],
                period=[dict(variable=t,first=str(a),last=str(b),valid=n) for t,a,b,n in cur.fetchall()],
                sheets=[dict(name=n,rows=c) for n,c in sheets],content_review='archived_typed_staging_no_excel_reopen')
    return sources


def build_inventory(root, conn, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():raise ValueError('inventory_refuses_overwrite')
    db = database_sources(conn)
    files = sorted([p for p in (root/'data').rglob('*') if p.is_file() and not p.is_symlink() and not p.is_relative_to(output.parent)]
                   + [p for p in (root/'ml').rglob('*') if p.is_file() and not any(s in p.parts for s in ('venv','.venv','.tmp','__pycache__','.pytest_cache'))])
    items, copies = [], defaultdict(list)
    for path in files:
        rel = path.relative_to(root).as_posix()
        row = dict(path=rel,bytes=path.stat().st_size,format=path.suffix.lower(),category=category(Path(rel)),
                   kind='original' if any(rel.startswith(s) for s in ('data/datos oficiales/','data/casos_dengue_confirmados/','data/open-meteo/','data/46-la-rioja-2022/','data/radios-censales/','data/raw/')) else 'derivative_or_support',
                   restrictions='private_local_only; no individual data publication; historical models frozen')
        row['provenance']='local file; original upstream and transformation must be traced through companion manifests' if row['kind']!='original' else 'local source delivery; see dataset-level source contract'
        row['geographic_resolution']=('source-declared residence; individual points are approximate' if '/datos oficiales/' in rel else
            'census radio, categorical aggregates' if '/46-la-rioja-2022/' in rel else
            'department/week/age-group' if '/casos_dengue_confirmados/' in rel else
            'single reference point, daily weather' if '/open-meteo/' in rel else
            'see schema and companion territorial universe')
        row['predictive_utility']=('frozen antecedent only; never an observed label' if row['category']=='previous_results_and_models' else
            'context/validation or source candidate; inclusion requires the explicit predictive contract')
        if any(s in path.name.lower() for s in ('connection','password','credential','.env')):
            row['inspection']='secret_configuration_content_not_read';items.append(row);continue
        try:sha=digest(path)
        except OSError:
            row['inspection']='unreadable_file';items.append(row);continue
        row['sha256']=sha;copies[sha].append(rel)
        row['incorporated_postgresql']=sha in db
        if sha in db:row['database_reference']=dict(file_id=db[sha]['database_file_id'],provenance=db[sha]['provenance'])
        try:
            if sha in db and path.suffix.lower()=='.xlsx':row['profile']=db[sha]
            elif path.suffix.lower()=='.parquet':
                table=pq.read_table(path)
                row['profile']=frame_profile(table.to_pandas().drop(columns=['geometry'],errors='ignore'))
            elif path.suffix.lower()=='.csv':row['profile']=csv_profile(path)
            elif path.suffix.lower() in ('.json','.geojson'):
                value=json.loads(path.read_text(encoding='utf-8-sig'))
                if isinstance(value,dict) and value.get('type')=='FeatureCollection':
                    row['profile']=frame_profile(pd.DataFrame([x.get('properties',{}) for x in value['features']]))
                    row['profile']['geometry_records']=len(value['features'])
                else:row['profile']=json_profile(value)
            elif path.suffix.lower()=='.shp':
                import pyogrio
                info=pyogrio.read_info(path)
                row['profile']=dict(rows=int(info['features']),variables=list(info['fields']),crs=info['crs'],
                    attribute_profile=frame_profile(pyogrio.read_dataframe(path,read_geometry=False)))
            elif path.suffix.lower()=='.ndjson':
                count=0;keys=set()
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        if line.strip():
                            value=json.loads(line);count+=1
                            if isinstance(value,dict):keys.update(value)
                row['profile']=dict(rows=count,variables=sorted(keys))
            elif path.suffix.lower() in ('.joblib','.pkl'):
                row['inspection']='hash_only_frozen_model_not_deserialized'
            else:row['inspection']='support_or_component_file_not_independent_dataset'
        except Exception as error:
            row['inspection']='profile_failed';row['error_type']=type(error).__name__
        items.append(row)
    result=dict(version='sigard-source-inventory-1',root='SIGARD',files=items,
        duplicate_content_groups=[dict(sha256=k,paths=v) for k,v in copies.items() if len(v)>1],
        counts=dict(files=len(items),by_category=dict(Counter(i['category'] for i in items)),
                    failed_profiles=sum(i.get('inspection')=='profile_failed' for i in items)),
        scope='all regular files under data and ml excluding environments/caches and this output directory; hashes never imply independent sources')
    output.write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result['counts']
