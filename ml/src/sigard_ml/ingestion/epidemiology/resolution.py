"""Local deterministic reviews, independent of source import and model artifacts.

A unique point is evidence about the stored point, not an error bound on an
address. Street/neighborhood precision never becomes a usable radio merely
because its representative point lies in one polygon.
"""
import hashlib
import json

from psycopg2.extras import Json, execute_values

POLICY = 'deterministic-source-review-1'
MISSING_MARKERS = {'*sin dato*'}


def original_fingerprint(conn):
    """Hash original operational inputs, including geometry, without logging rows."""
    tables = [
        'ingestion.archivo_fuente', 'ingestion.hoja_fuente', 'ingestion.columna_fuente',
        'ingestion.lote_importacion', 'ingestion.fila_staging',
        'epidemiology.registro_epidemiologico', 'epidemiology.fecha_registro',
        'epidemiology.clasificacion_registro', 'epidemiology.normalizacion_clasificacion',
        'epidemiology.regla_normalizacion_clasificacion', 'epidemiology.relacion_registro',
        'epidemiology.incidencia_validacion', 'territory.geocodificacion',
        'territory.proceso_geocodificacion', 'territory.asignacion_radio',
        'territory.candidato_asignacion', 'territory.version_geometria',
        'territory.radio_censal', 'territory.miembro_universo',
    ]
    digest = hashlib.sha256()
    with conn.cursor() as cur:
        for table in tables:
            # Table names are internal constants. Hashes avoid retaining BYTEA copies.
            cur.execute(f'SELECT md5(row_to_json(t)::text) FROM {table} t ORDER BY 1')
            digest.update(table.encode())
            for row in cur:
                digest.update(row[0].encode())
    return digest.hexdigest()


def review_point(*, matches, interior, declared_compatible, precision, confidence,
                 method, needs_review, has_point, flipped_inside=False):
    if not has_point:
        return 'invalid', 'missing_or_invalid_coordinate_pair'
    if matches == 0:
        return ('invalid', 'possible_swapped_axes_not_corrected') if flipped_inside else ('outside', 'outside_versioned_territory')
    if matches > 1:
        return 'ambiguous', 'multiple_intersecting_radios'
    if not interior:
        return 'boundary', 'point_on_boundary'
    if not declared_compatible:
        return 'point_only', 'declared_radio_missing_or_incompatible'
    if precision in ('calle', 'barrio'):
        return 'point_only', 'insufficient_' + precision + '_precision_no_documented_error_bound'
    if method == 'ambiguo':
        return 'point_only', 'ambiguous_geocoding_method'
    if (precision == 'altura_interpolada' and confidence in ('media', 'alta')
            and method in ('exacto', 'difuso') and not needs_review):
        return 'unique_provisional', 'compatible_interpolated_height_not_verified_residence'
    return 'point_only', 'unresolved_precision_or_source_review'


def resolve(conn, *, version, evidence, extraction_declarations=None):
    if not version or not evidence or not isinstance(evidence, dict):
        raise ValueError('review_version_and_evidence_required')
    declarations = extraction_declarations or {}
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734827193)')
            fingerprint = original_fingerprint(conn)
            payload = dict(evidence=evidence, extraction_declarations=declarations)
            # JSON storage normalizes integer dictionary keys, too.
            payload = json.loads(json.dumps(payload, sort_keys=True))
            cur.execute('SELECT politica,entrada_sha256,evidencia FROM epidemiology.version_resolucion WHERE version=%s', (version,))
            existing = cur.fetchone()
            if existing and existing != (POLICY, fingerprint, payload):
                raise ValueError('immutable_review_version_conflict')
            if not existing:
                cur.execute('INSERT INTO epidemiology.version_resolucion(version,politica,entrada_sha256,evidencia) VALUES(%s,%s,%s,%s)',
                            (version, POLICY, fingerprint, Json(payload)))
                cur.execute('''SELECT a.id,g.geom IS NOT NULL,g.precision_literal,g.confianza,p.metodo,
                    g.requiere_revision,g.radio_declarado,g.fraccion_declarada,g.crs_estado,vg.version,
                    ARRAY(SELECT r.id FROM territory.radio_censal r WHERE r.version_geometria_id=a.version_geometria_id AND ST_Intersects(r.geom,g.geom) ORDER BY r.id),
                    ARRAY(SELECT r.id FROM territory.radio_censal r WHERE r.version_geometria_id=a.version_geometria_id AND ST_Contains(r.geom,g.geom) ORDER BY r.id),
                    ARRAY(SELECT r.codigo FROM territory.radio_censal r WHERE r.version_geometria_id=a.version_geometria_id AND ST_Intersects(r.geom,g.geom) ORDER BY r.id),
                    EXISTS(SELECT 1 FROM territory.radio_censal r WHERE r.version_geometria_id=a.version_geometria_id AND ST_Intersects(r.geom,ST_FlipCoordinates(g.geom)))
                    FROM territory.asignacion_radio a JOIN territory.geocodificacion g ON g.id=a.geocodificacion_id
                    JOIN territory.proceso_geocodificacion p ON p.id=g.proceso_id
                    JOIN territory.version_geometria vg ON vg.id=a.version_geometria_id ORDER BY a.id''')
                reviews = []
                for aid, has_point, precision, confidence, method, flag, declared, fraction, crs, gv, matches, interiors, codes, flipped in cur.fetchall():
                    # No suffix/fuzzy inference: imported declared codes are canonical keys.
                    compatible = len(codes) == 1 and declared == codes[0]
                    state, reason = review_point(matches=len(matches), interior=len(interiors) == 1,
                        declared_compatible=compatible, precision=precision, confidence=confidence,
                        method=method, needs_review=flag, has_point=has_point, flipped_inside=flipped)
                    radio = matches[0] if state in ('point_only', 'unique_provisional') else None
                    checks = dict(valid_point=has_point, intersecting_radios=len(matches),
                        interior_radios=len(interiors), declared_compatible=compatible,
                        territorial_version=gv, crs_state=crs, source_review_flag=flag,
                        precision=precision, coordinate_changed=False, residence_verified=False)
                    reviews.append((version, aid, radio, state, reason, Json(checks)))
                if reviews:
                    execute_values(cur, 'INSERT INTO territory.revision_asignacion VALUES %s', reviews)
                cur.execute('''SELECT f.id,f.valor,f.estado,s.contenido->(col.ordinal-1)->>'value'
                    FROM epidemiology.fecha_registro f JOIN ingestion.columna_fuente col ON col.id=f.columna_id
                    JOIN epidemiology.registro_epidemiologico r ON r.id=f.registro_id
                    JOIN ingestion.fila_staging s ON s.id=r.fila_id ORDER BY f.id''')
                dates = []
                for fid, value, state, literal in cur.fetchall():
                    missing = state != 'valid' and isinstance(literal, str) and literal.strip().casefold() in MISSING_MARKERS
                    dates.append((version, fid, value, 'missing' if missing else state,
                                  'explicit_source_missing_marker' if missing else 'original_interpretation_preserved'))
                if dates:
                    execute_values(cur, 'INSERT INTO epidemiology.revision_fecha VALUES %s', dates)
                cur.execute('''INSERT INTO epidemiology.revision_clasificacion
                    SELECT %s,obs.id,CASE WHEN count(DISTINCT rule.catalogo_id)=1 THEN min(rule.catalogo_id) END,
                    CASE WHEN count(DISTINCT rule.catalogo_id)=1 THEN 'existing_explicit_mapping_preserved'
                         ELSE 'no_unambiguous_validated_equivalence_do_not_infer' END
                    FROM epidemiology.clasificacion_registro obs
                    LEFT JOIN epidemiology.normalizacion_clasificacion n ON n.observacion_id=obs.id
                    LEFT JOIN epidemiology.regla_normalizacion_clasificacion rule ON rule.id=n.regla_id
                    GROUP BY obs.id''', (version,))
                for file_id, declaration in declarations.items():
                    cur.execute('SELECT sha256 FROM ingestion.archivo_fuente WHERE id=%s', (int(file_id),))
                    source = cur.fetchone()
                    if not source or declaration.get('source_sha256') != source[0]:
                        raise ValueError('extraction_declaration_source_mismatch')
                    cur.execute('INSERT INTO epidemiology.revision_extraccion VALUES(%s,%s,%s)',
                                (version, int(file_id), Json(declaration)))
                if original_fingerprint(conn) != fingerprint:
                    raise ValueError('originals_changed_during_review')
            cur.execute('SELECT estado,count(*) FROM territory.revision_asignacion WHERE version=%s GROUP BY estado', (version,))
            states = dict(cur.fetchall())
            cur.execute("SELECT count(*) FROM epidemiology.revision_fecha WHERE version=%s AND motivo='explicit_source_missing_marker'", (version,))
            return dict(version=version, original_sha256=fingerprint, geography=states,
                        missing_markers_reclassified=cur.fetchone()[0], idempotent_reuse=bool(existing))
