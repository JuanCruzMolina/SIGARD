"""Fictional geometries and records only; real PostGIS through the guarded test DB."""
from datetime import date, datetime, timedelta, timezone

import pytest
from openpyxl import load_workbook

from test_epidemiology_database import db, seed_geometry, workbook
from sigard_ml.ingestion.epidemiology.importer import import_book
from sigard_ml.ingestion.epidemiology.resolution import resolve, review_point, original_fingerprint
from sigard_ml.ingestion.epidemiology.territory import assign_radios
from sigard_ml.ingestion.epidemiology.analytics import materialize


def fictional_source(tmp_path, *, precision='altura_interpolada', review=False,
                     when=date(2024, 2, 4), identifier='FICTIONAL-REVIEW', **kwargs):
    path = workbook(tmp_path / (identifier + '.xlsx'), identifier_value=identifier,
                    when=when, **kwargs)
    book = load_workbook(path)
    sheet = book.active
    sheet.cell(2, 6, review)
    extra = [('geocod_precision', precision), ('geocod_confianza', 'media'),
             ('geocod_metodo_resolucion', 'exacto'), ('geocod_radio_censal', 'F000')]
    for col, (header, value) in enumerate(extra, 8):
        sheet.cell(1, col, header)
        sheet.cell(2, col, value)
    book.save(path)
    return path


@pytest.mark.parametrize('change,state,reason', [
    ({'needs_review': True, 'precision': 'calle'}, 'point_only', 'insufficient_calle'),
    ({'needs_review': False, 'precision': 'barrio'}, 'point_only', 'insufficient_barrio'),
    ({'matches': 2}, 'ambiguous', 'multiple'),
    ({'interior': False}, 'boundary', 'point_on'),
    ({'matches': 0}, 'outside', 'outside'),
    ({'matches': 0, 'flipped_inside': True}, 'invalid', 'possible_swapped'),
    ({'has_point': False}, 'invalid', 'missing_or_invalid'),
    ({'declared_compatible': False}, 'point_only', 'declared_radio'),
    ({}, 'unique_provisional', 'compatible_interpolated'),
])
def test_spatial_evidence_does_not_invent_precision(change, state, reason):
    values = dict(matches=1, interior=True, declared_compatible=True,
                  precision='altura_interpolada', confidence='media', method='exacto',
                  needs_review=False, has_point=True)
    actual, why = review_point(**(values | change))
    assert actual == state and why.startswith(reason)


def test_reviews_preserve_originals_are_idempotent_and_immutable(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path, when='*sin dato*'))
    assign_radios(db)
    before = original_fingerprint(db)
    evidence = {'reference': 'FICTIONAL deterministic review'}
    first = resolve(db, version='fictional-r1', evidence=evidence)
    second = resolve(db, version='fictional-r1', evidence=evidence)
    assert first['missing_markers_reclassified'] == 1
    assert second['idempotent_reuse'] and before == original_fingerprint(db)
    with db.cursor() as cur:
        cur.execute('SELECT estado FROM epidemiology.fecha_registro')
        assert cur.fetchone()[0] == 'invalid_format'
        cur.execute('SELECT estado,valor FROM epidemiology.revision_fecha')
        assert cur.fetchone() == ('missing', None)
    with pytest.raises(ValueError, match='conflict'):
        resolve(db, version='fictional-r1', evidence={'reference': 'changed'})
    with pytest.raises(Exception):
        with db:
            with db.cursor() as cur:
                cur.execute("UPDATE territory.revision_asignacion SET motivo='changed'")


def test_missing_reference_keeps_all_possible_weeks_unknown(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path, when='*sin dato*'))
    assign_radios(db)
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    weeks = {date(2024, 1, 21) + timedelta(weeks=i) for i in range(6)}
    result = materialize(db, version='fictional-reviewed', universe_version='ab-263-master-v1',
        start=min(weeks), end=max(weeks)+timedelta(days=6), scenario='experimental_assumed',
        coverage_weeks=weeks, coverage_ref='FICTIONAL assumed scope', accept_provisional=True,
        resolution_version='fictional-r1')
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM analytics.conteos_radio_semana c JOIN territory.radio_censal r ON r.id=c.radio_id WHERE c.ejecucion_id=%s AND r.codigo='F000' AND cantidad_registros IS NOT NULL", (result['run_id'],))
        assert cur.fetchone()[0] == 0


def test_street_point_not_promoted_and_complete_weeks_not_discarded(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path, precision='calle', review=True))
    assign_radios(db)
    result = resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    assert result['geography'] == {'point_only': 1}
    weeks = {date(2024, 1, 21) + timedelta(weeks=i) for i in range(6)}
    run = materialize(db, version='fictional-street', universe_version='ab-263-master-v1',
        start=min(weeks), end=max(weeks)+timedelta(days=6), scenario='experimental_assumed',
        coverage_weeks=weeks, coverage_ref='FICTIONAL assumed scope', accept_provisional=True,
        resolution_version='fictional-r1')
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM analytics.conteos_con_procedencia WHERE ejecucion_id=%s AND semana_inicio='2024-02-04' AND cantidad_registros IS NOT NULL", (run['run_id'],))
        assert cur.fetchone()[0] == 0  # Unbounded street uncertainty affects all possible radios.
        cur.execute("SELECT count(*) FROM analytics.conteos_con_procedencia WHERE ejecucion_id=%s AND semana_inicio='2024-01-28' AND cantidad_registros=0", (run['run_id'],))
        assert cur.fetchone()[0] == 263


def test_reviewed_counts_b_four_exact_lags_and_old_versions_preserved(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path))
    assign_radios(db)
    weeks = {date(2024, 1, 21) + timedelta(weeks=i) for i in range(8)}
    args = dict(universe_version='ab-263-master-v1', start=min(weeks),
        end=max(weeks)+timedelta(days=6), scenario='experimental_assumed',
        coverage_weeks=weeks, coverage_ref='FICTIONAL assumed scope', accept_provisional=True)
    old = materialize(db, version='fictional-before', **args)
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    reviewed = materialize(db, version='fictional-after', resolution_version='fictional-r1', **args)
    assert old['known_counts'] == reviewed['known_counts'] == 263*8
    with db.cursor() as cur:
        cur.execute("SELECT local_presencia_exp_rezago_1,local_presencia_exp_rezago_2,local_presencia_exp_rezago_3,local_presencia_exp_rezago_4,local_presencia_exp_rezago_4_missing FROM analytics.ml_b WHERE ejecucion_id=%s AND radio_censal='F000' AND fecha_inicio_semana='2024-02-25'", (reviewed['run_id'],))
        assert cur.fetchone() == (0, 0, 1, 0, 0)
        cur.execute('SELECT version_resolucion_geografica,version_territorial,clasificacion_epidemiologica,array_length(fuentes_sha256,1) FROM analytics.conteos_con_procedencia WHERE ejecucion_id=%s LIMIT 1', (reviewed['run_id'],))
        assert cur.fetchone() == ('fictional-r1', 'fictional-geometry-1', 'confirmado', 1)
        cur.execute('SELECT count(*) FROM analytics.conteos_radio_semana WHERE ejecucion_id=%s', (old['run_id'],))
        assert cur.fetchone()[0] == 263*8
    with pytest.raises(ValueError, match='overwrite'):
        materialize(db, version='fictional-after', resolution_version='fictional-r1', **args)


def test_reviews_cannot_claim_wrong_geometry_or_expose_private_fields(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path))
    assign_radios(db)
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    with pytest.raises(Exception):
        with db:
            with db.cursor() as cur:
                cur.execute("INSERT INTO territory.revision_asignacion SELECT version,asignacion_id,(SELECT id FROM territory.radio_censal WHERE codigo='F001'),estado,motivo,comprobaciones FROM territory.revision_asignacion")
    with db.cursor() as cur:
        cur.execute("SELECT has_table_privilege('sigard_epi_analytics_reader','territory.revision_asignacion','SELECT')")
        assert cur.fetchone()[0] is False


def test_source_edits_require_new_review_version(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path))
    assign_radios(db)
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    with db:
        with db.cursor() as cur:
            cur.execute("UPDATE territory.geocodificacion SET precision_literal='barrio'")
    with pytest.raises(ValueError, match='stale'):
        materialize(db, version='fictional-stale', universe_version='ab-263-master-v1',
                    start=date(2024, 1, 21), end=date(2024, 3, 9), resolution_version='fictional-r1')


def test_unmapped_class_and_repeated_identifiers_are_never_resolved_by_assumption(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path, classification='FICTIONAL LAB POSITIVE UNMAPPED'))
    other = fictional_source(tmp_path, identifier='FICTIONAL-OTHER')
    # Two distinct rows remain two records even with the same identifier.
    book = load_workbook(other)
    book.active.cell(2, 1, 'FICTIONAL-REVIEW')
    book.save(other)
    import_book(db, other)
    assign_radios(db)
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    with db.cursor() as cur:
        cur.execute('SELECT count(*) FROM epidemiology.registro_epidemiologico')
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM epidemiology.relacion_registro WHERE revision_estado='pending'")
        assert cur.fetchone()[0] == 1
        cur.execute('SELECT count(*) FROM epidemiology.revision_clasificacion WHERE catalogo_id IS NULL')
        assert cur.fetchone()[0] == 1


def test_review_availability_cannot_leak_into_earlier_origin(db, tmp_path):
    seed_geometry(db)
    import_book(db, fictional_source(tmp_path))
    assign_radios(db)
    with db:
        with db.cursor() as cur:
            cur.execute("UPDATE epidemiology.registro_epidemiologico SET disponible_desde='2024-02-05T00:00:00Z'")
    resolve(db, version='fictional-r1', evidence={'reference': 'FICTIONAL'})
    args = dict(universe_version='ab-263-master-v1', start=date(2024, 1, 21),
                end=date(2024, 3, 9), resolution_version='fictional-r1',
                accept_provisional=True, mode='as_of')
    with pytest.raises(ValueError, match='review_not_available'):
        materialize(db, version='fictional-early-cutoff', cutoff=datetime(2024, 4, 1, tzinfo=timezone.utc), **args)
    result = materialize(db, version='fictional-review-asof', cutoff=datetime(2100, 1, 1, tzinfo=timezone.utc), **args)
    with db.cursor() as cur:
        cur.execute("SELECT local_presencia_exp_rezago_1 FROM analytics.ml_b WHERE ejecucion_id=%s AND radio_censal='F000' AND fecha_inicio_semana='2024-02-11'", (result['run_id'],))
        assert cur.fetchone()[0] is None
