"""Load a versioned local official master; preserve its geometries byte-for-byte upstream."""
import json
from .db import get_id
from .reader import digest

def load_master(conn,path,*,v3_radios=None):
    import geopandas as gpd
    frame=gpd.read_parquet(path)
    if frame.crs is None:raise ValueError('missing_master_crs')
    original_hash=digest(path)
    projected=frame.to_crs(4326)
    if frame.radio_id.duplicated().any() or frame.geometry.isna().any() or not frame.geometry.is_valid.all():raise ValueError('invalid_master')
    with conn:
        with conn.cursor() as cur:
            country=get_id(cur,'territory.pais',dict(nombre='argentina',codigo='AR'),keys=['nombre'])
            province=get_id(cur,'territory.provincia',dict(pais_id=country,nombre='la rioja',codigo='46'),keys=['pais_id','nombre'])
            dept=get_id(cur,'territory.departamento',dict(provincia_id=province,nombre='capital',codigo='014'),keys=['provincia_id','nombre'])
            cur.execute("UPDATE territory.pais SET codigo='AR' WHERE id=%s AND codigo IS NULL",(country,))
            cur.execute("UPDATE territory.provincia SET codigo='46' WHERE id=%s AND codigo IS NULL",(province,))
            cur.execute("UPDATE territory.departamento SET codigo='014' WHERE id=%s AND codigo IS NULL",(dept,))
            gv=get_id(cur,'territory.version_geometria',dict(version='official-master-'+original_hash[:16],fuente_sha256=original_hash,crs='EPSG:4326'))
            universe=get_id(cur,'territory.universo',dict(version='ab-263-master-v1',descripcion='Official master for A/B; no epidemiological validation'))
            cur.execute('SELECT DISTINCT r.version_geometria_id FROM territory.miembro_universo m JOIN territory.radio_censal r ON r.id=m.radio_id WHERE m.universo_id=%s',(universe,))
            old_versions={row[0] for row in cur.fetchall()}
            if old_versions and old_versions!={gv}:raise ValueError('new_geometry_requires_new_universe_version')
            codes={}
            for row,geometry in zip(frame.itertuples(),projected.geometry):
                fraction=get_id(cur,'territory.fraccion_censal',dict(departamento_id=dept,codigo=str(row.fraccion)))
                cur.execute('INSERT INTO territory.radio_censal(fraccion_id,version_geometria_id,codigo,geom) VALUES(%s,%s,%s,ST_Multi(ST_GeomFromText(%s,4326))) ON CONFLICT DO NOTHING RETURNING id',(fraction,gv,str(row.radio_id),geometry.wkt))
                found=cur.fetchone()
                if found:rid=found[0]
                else:
                    cur.execute('SELECT id FROM territory.radio_censal WHERE version_geometria_id=%s AND codigo=%s',(gv,str(row.radio_id)));rid=cur.fetchone()[0]
                codes[str(row.radio_id)]=rid
                cur.execute('INSERT INTO territory.miembro_universo VALUES(%s,%s) ON CONFLICT DO NOTHING',(universe,rid))
                census_version='census-context-'+original_hash[:16]
                cur.execute('INSERT INTO territory.version_contexto_censal VALUES(%s,%s) ON CONFLICT DO NOTHING',(census_version,original_hash))
                cur.execute('INSERT INTO territory.contexto_censal VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(rid,census_version,int(row.poblacion)))
                cur.execute('INSERT INTO analytics.contexto_radio VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(universe,rid,float(row.superficie_km2),int(row.poblacion),len(row.neighbor_ids),original_hash))
            for row in frame.itertuples():
                for neighbor in row.neighbor_ids:
                    if str(neighbor) not in codes:raise ValueError('neighbor_not_in_master')
                    cur.execute('INSERT INTO territory.vecindad VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(codes[str(row.radio_id)],codes[str(neighbor)],'queen-master-1'))
            if v3_radios is not None:
                if len(v3_radios)!=256 or not set(v3_radios)<=set(codes):raise ValueError('incompatible_v3_membership')
                v3=get_id(cur,'territory.universo',dict(version='v3-256-subset-v1',descripcion='Explicit existing operational membership; same canonical geometries, not inferred from codes'))
                for code in sorted(v3_radios):
                    rid=codes[code]
                    cur.execute('INSERT INTO territory.miembro_universo VALUES(%s,%s) ON CONFLICT DO NOTHING',(v3,rid))
                for code in sorted(v3_radios):
                    rid=codes[code]
                    cur.execute('''INSERT INTO analytics.contexto_radio SELECT %s,c.radio_id,c.superficie_km2,c.poblacion,
                        (SELECT count(*) FROM territory.vecindad v JOIN territory.miembro_universo m ON m.radio_id=v.vecino_id AND m.universo_id=%s WHERE v.radio_id=c.radio_id),c.fuente_sha256
                        FROM analytics.contexto_radio c WHERE c.universo_id=%s AND c.radio_id=%s ON CONFLICT DO NOTHING''',(v3,v3,universe,rid))
            if digest(path)!=original_hash:raise ValueError('master_changed')
    return dict(radios=len(codes),v3_radios=len(v3_radios) if v3_radios else 0,source_sha256=original_hash)

def assign_radios(conn):
    """Unique interiors are provisional candidates, never verified domicile/infection locations."""
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM territory.version_geometria ORDER BY id');versions=[r[0] for r in cur.fetchall()]
            for version in versions:
                cur.execute('SELECT id,ST_AsText(geom),requiere_revision FROM territory.geocodificacion g WHERE NOT EXISTS(SELECT 1 FROM territory.asignacion_radio a WHERE a.geocodificacion_id=g.id AND a.version_geometria_id=%s)',(version,))
                rows=cur.fetchall()
                for gid,wkt,review in rows:
                    candidates=[];radio=None
                    if not wkt:state='invalid'
                    else:
                        cur.execute('SELECT id,ST_Contains(geom,ST_GeomFromText(%s,4326)) FROM territory.radio_censal WHERE version_geometria_id=%s AND ST_Intersects(geom,ST_GeomFromText(%s,4326))',(wkt,version,wkt))
                        candidates=cur.fetchall()
                        if len(candidates)>1:state='ambiguous'
                        elif len(candidates)==1 and not candidates[0][1]:state='boundary'
                        elif len(candidates)==1 and review:state='insufficient'
                        elif len(candidates)==1:state='unique_provisional';radio=candidates[0][0]
                        else:
                            cur.execute('SELECT EXISTS(SELECT 1 FROM territory.radio_censal WHERE version_geometria_id=%s AND ST_Intersects(geom,ST_FlipCoordinates(ST_GeomFromText(%s,4326))))',(version,wkt))
                            state='invalid' if cur.fetchone()[0] else 'outside'
                    cur.execute('INSERT INTO territory.asignacion_radio(geocodificacion_id,version_geometria_id,estado,evidencia) VALUES(%s,%s,%s,%s) RETURNING id',(gid,version,state,'exact_PostGIS_predicates; source_crs_assumed; no_automatic_boundary_or_review_resolution'))
                    aid=cur.fetchone()[0]
                    for rid,interior in candidates:cur.execute('INSERT INTO territory.candidato_asignacion VALUES(%s,%s,%s,%s)',(aid,rid,'contains' if interior else 'intersects_boundary',rid==radio))
            cur.execute('SELECT estado,count(*) FROM territory.asignacion_radio GROUP BY estado')
            return dict(cur.fetchall())
