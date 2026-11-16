"""Public activity package: generated fictional aggregates built to attempt re-identification."""
from datetime import date
import hashlib
import json

import pytest

from sigard_ml.publication import activity_package as ap
from sigard_ml.publication.activity_package import PROTECTED, PackageBlocked, build_package, disclosure, epi_weeks, write_package

SOURCE = dict(kind='fixture', dataset_version='fictional', input_sha256=None)
TODAY = date(2026, 11, 16)


def inputs(cells=None, extra=None, radios=('FICT-A', 'FICT-B', 'FICT-C'), years=(2020, 2021, 2022, 2023, 2024), drop=()):
    """Zero everywhere except ``cells[(radio, year, week)]``; ``extra[(year, week)]`` adds outside records."""
    cells, extra = cells or {}, extra or {}
    radio_weeks, city_weeks = [], []
    for year in years:
        for week, start, end in epi_weeks(year):
            total = 0
            for radio in radios:
                count = None if (radio, year, week) in drop else cells.get((radio, year, week), 0)
                total += count or 0
                radio_weeks.append(dict(radio_id=radio, year=year, week=week, start=start, end=end, count=count))
            city_weeks.append(dict(year=year, week=week, start=start, end=end, count=total + extra.get((year, week), 0)))
    return radio_weeks, city_weeks


def build(cells=None, extra=None, populations=None, outside=('FICT-Z',), **kw):
    radio_weeks, city_weeks = inputs(cells, extra, **kw)
    pops = {r: 500 for r in {w['radio_id'] for w in radio_weeks}} | (populations or {})
    return build_package(radio_weeks, city_weeks, list(outside), source=SOURCE, generated_at=TODAY, populations=pops)


def block(package, block_id):
    return next(b for b in package['activity']['blocks'] if b['id'] == block_id)


def report(package, block_id):
    return next(b for b in package['risk']['blocks'] if b['block'] == block_id)


def test_single_protected_radio_is_not_deducible_from_city_total():
    # A=9, B=9 (bajo, upper bound 9), C=4 (primary). City week exact 22, nothing outside:
    # without complementary suppression C >= 22 - 9 - 9 = 4 is provable.
    levels = {'FICT-A': 'bajo', 'FICT-B': 'bajo', 'FICT-C': PROTECTED}
    city = [dict(value=22, display=None)] + [dict(value=None, display='<5')] * 3
    assert disclosure(levels, city, outside=0) == 4
    package = build({('FICT-A', 2021, 1): 9, ('FICT-B', 2021, 1): 9, ('FICT-C', 2021, 1): 4})
    out = block(package, '2021-B01')
    assert list(out['radios'].values()).count(PROTECTED) == 2
    assert report(package, '2021-B01')['complementary'] == 1
    assert package['risk']['status'] == 'passed' and package['risk']['disclosures'] == 0


def test_all_published_except_one_with_medio_bound_triggers_complementary():
    # Two radios only: A=19 (medio, upper 19), C=3. City exact 22 -> C >= 3 provable.
    two = dict(radios=('FICT-A', 'FICT-C'))
    package = build({('FICT-A', 2023, 5): 19, ('FICT-C', 2023, 5): 3}, **two)
    assert block(package, '2023-B02')['radios'] == {'FICT-A': PROTECTED, 'FICT-C': PROTECTED}
    assert report(package, '2023-B02')['complementary'] == 1
    # A second protected radio (0..4) already hides which one holds the remainder of 3.
    package = build({('FICT-A', 2023, 5): 19, ('FICT-C', 2023, 5): 3})
    assert block(package, '2023-B02')['radios'] == {'FICT-A': 'medio', 'FICT-B': PROTECTED, 'FICT-C': PROTECTED}
    assert report(package, '2023-B02')['complementary'] == 0
    # Known outside records are subtracted by the attacker (worst case) and still caught.
    package = build({('FICT-A', 2023, 5): 19, ('FICT-C', 2023, 5): 3}, extra={(2023, 5): 6}, **two)
    assert report(package, '2023-B02')['complementary'] == 1


def test_alto_level_has_no_upper_bound_so_no_complementary_is_needed():
    cells = {('FICT-A', 2020, 9): 25, ('FICT-C', 2020, 9): 2}
    package = build(cells)
    out = block(package, '2020-B03')
    assert out['radios'] == {'FICT-A': 'alto', 'FICT-B': PROTECTED, 'FICT-C': PROTECTED}
    assert report(package, '2020-B03')['complementary'] == 0


def test_population_protected_radio_value_is_not_deducible():
    # B has 7 records but population 60: protected; with A bajo and city exact, B >= 13 - 9.
    cells = {('FICT-A', 2024, 1): 6, ('FICT-B', 2024, 1): 7}
    package = build(cells, populations={'FICT-B': 60}, radios=('FICT-A', 'FICT-B'))
    out = block(package, '2024-B01')
    assert out['radios']['FICT-B'] == PROTECTED
    assert out['radios']['FICT-A'] == PROTECTED  # complementary: A's bajo bound would pin B
    assert report(package, '2024-B01')['primary_population'] == 1
    assert report(package, '2024-B01')['complementary'] == 1


def test_population_threshold_is_strict_and_unknown_population_protects():
    cells = {('FICT-A', 2021, 13): 30, ('FICT-B', 2021, 13): 30, ('FICT-C', 2021, 13): 30}
    package = build(cells, populations={'FICT-A': 99, 'FICT-B': 100, 'FICT-C': None})
    radios = block(package, '2021-B04')['radios']
    assert radios == {'FICT-A': PROTECTED, 'FICT-B': 'alto', 'FICT-C': PROTECTED}


def test_city_weeks_below_minimum_are_never_published_exactly():
    package = build({('FICT-A', 2020, 2): 3, ('FICT-A', 2020, 3): 6})
    weeks = {e['week']: e for e in block(package, '2020-B01')['city_weeks']}
    assert weeks[2] == {**weeks[2], 'value': None, 'display': '<5'}
    assert weeks[3]['value'] == 6
    assert all(e['value'] is None or e['value'] >= 5 for b in package['activity']['blocks'] for e in b['city_weeks'])


def test_only_levels_are_published_never_exact_radio_counts():
    package = build({('FICT-A', 2023, 20): 7, ('FICT-B', 2023, 20): 14, ('FICT-C', 2023, 20): 33})
    allowed = {PROTECTED, 'bajo', 'medio', 'alto'}
    assert {lvl for b in package['activity']['blocks'] for lvl in b['radios'].values()} <= allowed
    assert block(package, '2023-B05')['radios'] == {'FICT-A': 'bajo', 'FICT-B': 'medio', 'FICT-C': 'alto'}
    text = json.dumps(package['activity'])
    assert '"counts"' not in text and '"outside"' not in text


def test_blocks_are_fixed_disjoint_and_week_53_joins_last_block():
    years_with_53 = [y for y in range(2020, 2025) if len(epi_weeks(y)) == 53]
    assert years_with_53, 'the generated calendar must exercise week 53'
    year = years_with_53[0]
    package = build()
    seen = set()
    for b in package['activity']['blocks']:
        keys = {(b['year'], w) for w in b['weeks']}
        assert not keys & seen
        seen |= keys
        assert b['weeks'] == list(range(b['block'] * 4 - 3, b['block'] * 4 + 1)) + ([53] if b['block'] == 13 and year == b['year'] else [])
    assert block(package, f'{year}-B13')['weeks'][-1] == 53
    assert package['risk']['checks']['blocks_disjoint'] is True


def test_2022_and_weeks_after_se24_2024_are_excluded():
    package = build({('FICT-A', 2022, 10): 50, ('FICT-A', 2024, 30): 50})
    ids = [b['id'] for b in package['activity']['blocks']]
    assert not any(i.startswith('2022') for i in ids)
    assert ids[-1] == '2024-B06' and ids[0] == '2020-B01'
    period = package['activity']['period']
    assert period['last_week'] == {'year': 2024, 'week': 24} and period['first_block'] == '2020-B01'
    assert package['activity']['policy']['excluded_years'][0]['year'] == 2022


def test_masked_radio_is_never_published_and_its_records_stay_outside():
    with pytest.raises(PackageBlocked, match='masked_radio_in_published_universe'):
        build(outside=('FICT-A',))
    package = build({('FICT-A', 2021, 1): 6}, extra={(2021, 1): 9})
    assert 'FICT-Z' not in block(package, '2021-B01')['radios']
    assert package['activity']['outside_radios'] == ['FICT-Z']


def test_incomplete_block_is_skipped_not_imputed():
    package = build(drop={('FICT-B', 2023, 6)})
    assert '2023-B02' in package['risk']['skipped_incomplete_blocks']
    assert '2023-B02' not in [b['id'] for b in package['activity']['blocks']]


def test_audit_detects_tampered_small_cell_and_presence():
    package = build({('FICT-A', 2021, 1): 3})
    activity = package['activity']
    private = [dict(block=b['id'], counts={r: 0 for r in b['radios']}, outside=0, complementary=[]) for b in activity['blocks']]
    private[0]['counts']['FICT-A'] = 3
    activity['blocks'][0]['radios']['FICT-A'] = 'bajo'
    result = ap.audit(activity, private, {r: 500 for r in ('FICT-A', 'FICT-B', 'FICT-C')})
    assert result['status'] == 'failed'
    assert {d['kind'] for d in result['disclosure_details']} >= {'small_cell_published', 'level_inconsistent_with_count'}


def test_write_package_guards_and_manifest_hashes(tmp_path):
    package = build({('FICT-A', 2021, 1): 6})
    with pytest.raises(PackageBlocked, match='frontend_output_forbidden'):
        write_package(package, ap.ROOT / 'frontend/public/data/activity', package_version='x')
    real = dict(package, source=dict(SOURCE, kind='real'))
    with pytest.raises(PackageBlocked, match='real_package_must_stay'):
        write_package(real, tmp_path / 'real', package_version='x')
    result = write_package(package, tmp_path / 'pkg', package_version='fictional-v1')
    manifest_bytes = (tmp_path / 'pkg/manifest.json').read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == result['manifest_sha256']
    manifest = json.loads(manifest_bytes)
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((tmp_path / 'pkg' / name).read_bytes()).hexdigest() == digest
    assert manifest['risk'] == {'status': 'passed', 'disclosures': 0}
    with pytest.raises(PackageBlocked, match='output_exists_never_overwrite'):
        write_package(package, tmp_path / 'pkg', package_version='fictional-v1')


def test_fixture_cli_is_deterministic_and_passes_audit(tmp_path, capsys):
    assert ap.main(['fixture', '--output', str(tmp_path / 'one')]) == 0
    first = json.loads(capsys.readouterr().out)
    assert ap.main(['fixture', '--output', str(tmp_path / 'two')]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first['manifest_sha256'] == second['manifest_sha256'] and first['risk'] == 'passed'
    risk = json.loads((tmp_path / 'one/risk-report.json').read_text(encoding='utf-8'))
    assert risk['disclosures'] == 0 and risk['protected_cells'] > 0 and risk['published_cells'] > 0
    activity = json.loads((tmp_path / 'one/activity.json').read_text(encoding='utf-8'))
    assert activity['source'] == {'kind': 'fixture', 'fictional': True}


def test_real_build_requires_private_configuration(tmp_path, capsys):
    code = ap.main(['build', '--connection', str(tmp_path / 'c.json'), '--config', str(tmp_path / 'k.json'),
                    '--output', str(tmp_path / 'out')])
    assert code == 1 and json.loads(capsys.readouterr().out)['reason'] == 'private_configuration_required'


def test_load_inputs_reads_only_analytics_views_available_to_the_reader(monkeypatch):
    import pandas as pd
    from sigard_ml.data_access import postgres
    statements = []
    start, end = date(2021, 1, 3), date(2021, 1, 9)

    def query(self, statement, parameters=()):
        statements.append(statement)
        if 'consolidacion_dataset' in statement:
            return pd.DataFrame([{'entrada_sha256': 'f' * 64}])
        if 'NOT mascara_comun' in statement:
            return pd.DataFrame([{'codigo': 'FICT-900'}])
        if 'consolidacion_radio_semana' in statement:
            return pd.DataFrame([dict(radio_codigo='FICT-001', anio=2021, numero=1, inicio=start, fin=end, registros_asignados=2,
                                      cobertura_estado='covered_observed', poblacion_contexto_2022=float('nan'))])
        return pd.DataFrame([dict(anio=2021, numero=1, inicio=start, fin=end, cantidad_sigard=3)])
    monkeypatch.setattr(postgres.MLRepository, 'query', query)
    radio_weeks, city_weeks, outside, populations = ap.load_inputs(object(), 'fictional', 'f' * 64)
    assert all('territory.' not in s and 'epidemiology.' not in s for s in statements)
    assert all('analytics.' in s for s in statements)
    assert outside == ['FICT-900'] and populations == {'FICT-001': None}
    assert radio_weeks[0]['count'] == 2 and city_weeks[0]['count'] == 3
    with pytest.raises(PackageBlocked, match='verified_stage1'):
        ap.load_inputs(object(), 'fictional', '0' * 64)
