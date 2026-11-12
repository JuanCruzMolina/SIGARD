"""Transactional, idempotent XLSX preservation and conservative normalization."""
import hashlib
import json
from datetime import date
from collections import Counter
from pathlib import Path

from psycopg2.extras import Json
from sigard_ml.official.classification import classification_key
from sigard_ml.official.normalization import parse_date,parse_coordinate
from .db import get_id
from .reader import DATE_TYPES,VERSION,read_book,digest

CLASS_MAP={
 'Caso confirmado':'confirmado','Caso confirmado DEN-1':'confirmado','Caso confirmado DEN-2':'confirmado',
 'Caso confirmado por nexo epidemiológico autóctono':'confirmado',
 'Caso confirmado por nexo epidemiológico importado':'confirmado','Caso confirmado sin serotipo':'confirmado',
 'Confirmado':'confirmado','Caso sospechoso':'sospechoso','Sospechoso':'sospechoso',
 'Caso probable':'probable','Probable':'probable','Descartado':'descartado','Caso descartado':'descartado',
 'Caso descartado por diagnóstico diferencial':'descartado','Caso descartado por diagnostico diferencial':'descartado',
 'Indeterminado':'indeterminado','Sin clasificar':'indeterminado'}
CLASS_MAP={classification_key(k):v for k,v in CLASS_MAP.items()}

class Catalogs:
    def __init__(self,cur):self.cur=cur;self.cache={}
    def id(self,table,values):
        key=(table,tuple(values.items()))
        if key not in self.cache:self.cache[key]=get_id(self.cur,table,values)
        return self.cache[key]

def source_metadata(cur,sha,metadata):
    """Attach explicit delivery metadata; never infer arrival from extraction."""
    if not metadata:return
    allowed={'fecha_extraccion','periodo_declarado','entrega_version','procedencia'}
    if set(metadata)-allowed or not metadata.get('procedencia'):
        raise ValueError('explicit_metadata_provenance_required')
    metadata=dict(metadata)
    if metadata.get('fecha_extraccion') is not None:
        metadata['fecha_extraccion']=date.fromisoformat(str(metadata['fecha_extraccion']))
    cur.execute('SELECT fecha_extraccion,periodo_declarado,entrega_version,procedencia FROM ingestion.archivo_fuente WHERE sha256=%s',(sha,))
    found=cur.fetchone()
    if not found:raise ValueError('metadata_source_not_imported')
    current=dict(zip(['fecha_extraccion','periodo_declarado','entrega_version','procedencia'],found))
    defaults={'entrega_version':sha[:16],'procedencia':'project_owner_declared_provision'}
    for key,value in metadata.items():
        if current[key] is not None and current[key]!=value and current[key]!=defaults.get(key):
            raise ValueError('conflicting_source_metadata_requires_review')
    from psycopg2 import sql
    for key,value in metadata.items():
        cur.execute(sql.SQL('UPDATE ingestion.archivo_fuente SET {}=%s WHERE sha256=%s').format(sql.Identifier(key)),(value,sha))


def import_book(conn,path,*,expected_sha256=None,fail_after=None,metadata=None):
    path=Path(path)
    initial_hash=digest(path)
    if expected_sha256 and initial_hash!=expected_sha256:raise ValueError('source_hash_not_authorized')
    # Reimport of unchanged content only hashes bytes; no workbook parsing needed.
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT l.filas_leidas FROM ingestion.lote_importacion l JOIN ingestion.archivo_fuente a ON a.id=l.archivo_id WHERE a.sha256=%s AND l.importador_version=%s',(initial_hash,VERSION))
            found=cur.fetchone()
            if found:
                source_metadata(cur,initial_hash,metadata)
                return dict(name=path.name,status='already_imported',rows=found[0])
    book=read_book(path)
    if book['sha256']!=initial_hash:raise ValueError('source_changed_during_import')
    if expected_sha256 and book['sha256']!=expected_sha256:raise ValueError('source_hash_not_authorized')
    total=sum(len(s['rows']) for s in book['sheets'])
    with conn:
        with conn.cursor() as cur:
            # Serialize imports to avoid simultaneous catalog and duplicate-group races.
            cur.execute('SELECT pg_advisory_xact_lock(734827193)')
            cur.execute('SELECT l.id FROM ingestion.lote_importacion l JOIN ingestion.archivo_fuente a ON a.id=l.archivo_id WHERE a.sha256=%s AND l.importador_version=%s', (book['sha256'],VERSION))
            if cur.fetchone():return dict(name=book['name'],status='already_imported',rows=total)
            raw=book['path'].read_bytes()
            if hashlib.sha256(raw).hexdigest()!=book['sha256']:raise ValueError('source_changed')
            file_id=get_id(cur,'ingestion.archivo_fuente',dict(nombre_original=book['name'],sha256=book['sha256'],bytes=book['size'],
                periodo_declarado=None,fecha_extraccion=None,procedencia='project_owner_declared_provision',entrega_version=book['sha256'][:16],contenido_original=raw),keys=['sha256'])
            source_metadata(cur,book['sha256'],metadata)
            batch_id=get_id(cur,'ingestion.lote_importacion',dict(archivo_id=file_id,importador_version=VERSION,estado='loading'),keys=['archivo_id','importador_version'])
            cat=Catalogs(cur);processed=0;partial=0
            for sheet in book['sheets']:
                sheet_id=get_id(cur,'ingestion.hoja_fuente',dict(archivo_id=file_id,ordinal=sheet['ordinal'],nombre=sheet['name'],
                    fila_encabezado=sheet['header_row'],layout_sha256=sheet.get('layout_hash'),preambulo=Json(sheet['preamble'])),keys=['archivo_id','ordinal'])
                columns={c['ordinal']:get_id(cur,'ingestion.columna_fuente',dict(hoja_id=sheet_id,ordinal=c['ordinal'],nombre_original=c['label'],campo_propuesto=c['field'])) for c in sheet['columns']}
                for row in sheet['rows']:
                    values=row['values']
                    txt=lambda field:values.get(field,{}).get('text')
                    issues=[]
                    if not txt('event_id'):issues.append('missing_external_identifier')
                    if not txt('classification'):issues.append('missing_classification')
                    address_id=None
                    locality_id=None
                    if all(txt(f) for f in ['country','province','department','locality']):
                        country=cat.id('territory.pais',dict(nombre=txt('country').casefold()))
                        province=cat.id('territory.provincia',dict(pais_id=country,nombre=txt('province').casefold()))
                        department=cat.id('territory.departamento',dict(provincia_id=province,nombre=txt('department').casefold()))
                        locality_id=cat.id('territory.localidad',dict(departamento_id=department,nombre=txt('locality').casefold()))
                    if txt('address') or txt('street_number') or locality_id:
                        address_id=get_id(cur,'territory.domicilio',dict(localidad_id=locality_id,calle_original=txt('address'),numero_original=txt('street_number')))
                        if txt('normalized_address'):
                            get_id(cur,'territory.normalizacion_domicilio',dict(domicilio_id=address_id,version=VERSION,
                                direccion_normalizada=txt('normalized_address'),calle_oficial=txt('official_street'),calle_codigo=txt('official_street_id'),estado='source_provided'))
                    group=cat.id('epidemiology.grupo_etario',dict(literal=txt('age_group'))) if txt('age_group') else None
                    dates=[]
                    for field,kind in DATE_TYPES.items():
                        if field not in values:continue
                        parsed,state=parse_date(values[field]['value'])
                        dates.append((kind,columns[values[field]['column']],parsed,state))
                        if state not in ['valid','missing']:issues.append('invalid_date_'+kind)
                    if not any(d and kind in ['symptom_onset','sample_on'] for kind,col,d,state in dates):issues.append('no_clinical_reference_date')
                    lon,lons,_=parse_coordinate(values.get('longitude',{}).get('value'))
                    lat,lats,_=parse_coordinate(values.get('latitude',{}).get('value'))
                    valid=lon is not None and lat is not None and -180<=lon<=180 and -90<=lat<=90
                    if not valid:issues.append('invalid_or_missing_coordinates')
                    cur.execute('INSERT INTO ingestion.fila_staging(lote_id,hoja_id,numero_fila,contenido,sha256,estado) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',
                        (batch_id,sheet_id,row['row_number'],Json(row['content']),row['row_hash'],'partial' if issues else 'normalized'))
                    staging=cur.fetchone()[0]
                    cur.execute('INSERT INTO epidemiology.registro_epidemiologico(fila_id,identificador_externo,grupo_etario_id,domicilio_id,estado_normalizacion) VALUES(%s,%s,%s,%s,%s) RETURNING id',
                        (staging,txt('event_id'),group,address_id,'partial' if issues else 'complete'))
                    record=cur.fetchone()[0]
                    for kind,col,parsed,state in dates:
                        type_id=cat.id('epidemiology.tipo_fecha',dict(codigo=kind))
                        cur.execute('INSERT INTO epidemiology.fecha_registro(registro_id,tipo_id,columna_id,valor,estado,parser_version) VALUES(%s,%s,%s,%s,%s,%s)',(record,type_id,col,parsed,state,VERSION))
                    for field in ['classification','algorithm_classification']:
                        if not txt(field):continue
                        cur.execute('INSERT INTO epidemiology.clasificacion_registro(registro_id,columna_id,valor_literal) VALUES(%s,%s,%s) RETURNING id',(record,columns[values[field]['column']],txt(field)))
                        obs=cur.fetchone()[0];key=classification_key(txt(field));canonical=CLASS_MAP.get(key)
                        if canonical:
                            canonical_id=cat.id('epidemiology.catalogo_clasificacion',dict(codigo=canonical))
                            rule=cat.id('epidemiology.regla_normalizacion_clasificacion',dict(version='classification-explicit-0.4.0',literal_canonico=key,catalogo_id=canonical_id,estado_validacion='provisional'))
                            cur.execute('INSERT INTO epidemiology.normalizacion_clasificacion(observacion_id,regla_id) VALUES(%s,%s)',(obs,rule))
                        else:issues.append('unmapped_classification')
                    process=cat.id('territory.proceso_geocodificacion',dict(proveedor=txt('geocoding_provider') or 'unknown',metodo=txt('geocoding_method') or 'unknown',version=VERSION))
                    review=(txt('geocoding_review') or '').casefold() not in ['false','no','0']
                    cur.execute('INSERT INTO territory.geocodificacion(registro_id,proceso_id,geom,estado,precision_literal,confianza,requiere_revision,crs_estado,radio_declarado,fraccion_declarada) VALUES(%s,%s,CASE WHEN %s THEN ST_SetSRID(ST_MakePoint(%s,%s),4326) END,%s,%s,%s,%s,%s,%s,%s)',
                        (record,process,valid,lon,lat,txt('geocoding_status') or 'unknown',txt('coordinate_precision'),txt('geocoding_confidence'),review,'assumed',txt('radio'),txt('fraction')))
                    for code in set(issues):cur.execute('INSERT INTO epidemiology.incidencia_validacion(registro_id,codigo) VALUES(%s,%s)',(record,code))
                    if issues:
                        partial+=1
                        cur.execute("UPDATE epidemiology.registro_epidemiologico SET estado_normalizacion='partial' WHERE id=%s",(record,))
                        cur.execute("UPDATE ingestion.fila_staging SET estado='partial' WHERE id=%s",(staging,))
                    processed+=1
                    if fail_after and processed==fail_after:raise ValueError('injected_test_failure')
            # Technical duplicates require identical row payload AND header layout.
            cur.execute('''INSERT INTO epidemiology.relacion_registro(registro_id,otro_id,tipo,evidencia,revision_estado)
                SELECT r.id,min(other.id),'exact_duplicate','same_layout_and_typed_payload','technical_exact'
                FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
                JOIN ingestion.hoja_fuente h ON h.id=s.hoja_id
                JOIN ingestion.fila_staging os ON os.sha256=s.sha256 AND os.id<s.id
                JOIN ingestion.hoja_fuente oh ON oh.id=os.hoja_id AND oh.layout_sha256=h.layout_sha256
                JOIN epidemiology.registro_epidemiologico other ON other.fila_id=os.id
                WHERE s.lote_id=%s GROUP BY r.id ON CONFLICT DO NOTHING''',(batch_id,))
            cur.execute('''INSERT INTO epidemiology.relacion_registro(registro_id,otro_id,tipo,evidencia,revision_estado)
                SELECT r.id,other.id,'same_external_id','external_identifier_not_episode_key','pending'
                FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
                JOIN epidemiology.registro_epidemiologico other ON other.identificador_externo=r.identificador_externo AND other.id<r.id
                WHERE s.lote_id=%s AND r.identificador_externo IS NOT NULL
                ON CONFLICT DO NOTHING''',(batch_id,))
            cur.execute("UPDATE ingestion.lote_importacion SET estado='complete',filas_leidas=%s,filas_normalizadas=%s,filas_parciales=%s,validacion=%s WHERE id=%s",(total,processed,partial,Json(dict(reconciled=total==processed)),batch_id))
            if digest(path)!=book['sha256']:raise ValueError('source_changed_before_commit')
    return dict(name=book['name'],status='imported',read=total,normalized=processed,preserved=total,partial=partial,rejected_or_dropped=0)
