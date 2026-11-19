"""Protected public package of registered activity: radio levels in 4-week blocks + city weekly series.

The package aggregates already consolidated counts. It never contains individual records,
exact radio counts, single-record dates or masked radios. Building it does not publish
anything: the public API serves it only with a private authorization bound to the manifest
hash. Real builds require an explicit request; tests use generated fictional inputs only.

Protection policy (``POLICY_VERSION``):
- fixed, non-overlapping blocks of 4 epidemiological weeks; week 53 joins block 13;
- primary suppression: radios with 0-4 records in the block, or Census 2022 population
  below ``MIN_POPULATION`` (or unknown), are shown as ``protegido``;
- published radios show a level (5-9 / 10-19 / >=20), never the exact count;
- city weekly series: exact value only when >= 5, otherwise ``<5``;
- complementary suppression: an attacker who knows the published city weeks, the published
  levels and (worst case) the exact number of records outside the published radios must not
  be able to prove that a primary-protected radio has at least one record. Otherwise the
  published radio with the smallest count is also protected (its value then has no known
  upper bound); if no published radio is left, the city weeks of that block are hidden.
"""

import argparse
import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

SCHEMA = 'sigard-public-activity/1'
MANIFEST_SCHEMA = 'sigard-public-activity-manifest/1'
POLICY_VERSION = 'sigard-public-activity-minimum5-blocks4-v1'
MINIMUM = 5
MIN_POPULATION = 100
BLOCK_WEEKS = 4
LAST_BLOCK = 13
LEVELS = (('bajo', 5, 9), ('medio', 10, 19), ('alto', 20, None))
PROTECTED = 'protegido'
DECLARED_YEARS = (2020, 2021, 2022, 2023, 2024)
EXCLUDED_YEARS = {2022: 'classification_differs_suspected_probable_discarded_counted'}
LAST_WEEK = (2024, 24)

ROOT = Path(__file__).resolve().parents[4]
REAL_OUTPUT = ROOT / 'data/processed/official'
PRIVATE_CONFIG = ROOT / 'data/interim/official'
FORBIDDEN_OUTPUT = (ROOT / 'frontend',)


class PackageBlocked(ValueError):
    """Stable, non-sensitive reason; the package is not written."""


def policy():
    return dict(version=POLICY_VERSION, minimum_count=MINIMUM, min_population=MIN_POPULATION,
                block_weeks=BLOCK_WEEKS, week_53='joins_block_13', overlapping_blocks=False,
                levels=[dict(level=name, min=low, max=high) for name, low, high in LEVELS],
                protected_label='Menos de 5 registros (protegido)', zero_merged_with_protected=True,
                years=[y for y in DECLARED_YEARS if y not in EXCLUDED_YEARS],
                excluded_years=[dict(year=y, reason=r) for y, r in EXCLUDED_YEARS.items()],
                last_week=dict(year=LAST_WEEK[0], week=LAST_WEEK[1]),
                radio_count_source='records_with_assigned_radio_in_common_territory',
                city_count_source='all_eligible_records_of_the_department',
                complementary_rule='known_outside_records_and_complementary_cells_v1')


def level_for(count):
    for name, low, high in LEVELS:
        if count >= low and (high is None or count <= high):
            return name
    return PROTECTED


def level_interval(level):
    for name, low, high in LEVELS:
        if name == level:
            return low, math.inf if high is None else high
    raise PackageBlocked('unknown_level')


def city_interval(entry):
    if entry['value'] is not None:
        return entry['value'], entry['value']
    return (0, MINIMUM - 1) if entry['display'] == '<5' else (0, math.inf)


def disclosure(levels, city, outside, unbounded=(), complementary=()):
    """Largest lower bound an attacker can prove for a sensitive protected radio of one block.

    Worst case: the attacker knows the published city weeks, the published levels, the exact
    number of block records outside the published radios, the Census population (so which
    radios are protected for population) and which radios are complementary. Protected radios
    are 0..4, except population-protected and complementary ones, which have no upper bound.
    Complementary radios (>= 5 by construction) are not sensitive. Inverting the selection
    algorithm itself is not modelled (documented limitation).
    """
    protected = [r for r, level in levels.items() if level == PROTECTED]
    sensitive = [r for r in protected if r not in complementary]
    if not sensitive:
        return 0
    low_total = sum(city_interval(e)[0] for e in city)
    published = [level_interval(level) for level in levels.values() if level != PROTECTED]
    low_sum = max(0, low_total - outside - sum(high for _, high in published))
    open_ended = {r for r in protected if r in unbounded or r in complementary}
    bounded = len(protected) - len(open_ended)
    best = 0
    for radio in sensitive:
        if open_ended - {radio}:
            continue  # another protected radio may absorb the whole remainder
        others = (MINIMUM - 1) * (bounded - (radio not in open_ended))
        best = max(best, low_sum - others)
    return best


def _blocks(radio_weeks, city_weeks):
    years = [y for y in DECLARED_YEARS if y not in EXCLUDED_YEARS and y <= LAST_WEEK[0]]
    city = {(r['year'], r['week']): r for r in city_weeks if r['year'] in years and (r['year'], r['week']) <= LAST_WEEK}
    radios = {}
    for row in radio_weeks:
        if (row['year'], row['week']) in city:
            radios.setdefault(row['radio_id'], {})[(row['year'], row['week'])] = row
    blocks, skipped = [], []
    for year in years:
        for number in range(1, LAST_BLOCK + 1):
            expected = list(range(number * BLOCK_WEEKS - BLOCK_WEEKS + 1, number * BLOCK_WEEKS + 1))
            if (year, expected[-1]) > LAST_WEEK:
                continue
            weeks = expected + ([53] if number == LAST_BLOCK and (year, 53) in city else [])
            keys = [(year, w) for w in weeks]
            complete = bool(radios) and all(k in city and city[k]['count'] is not None for k in keys) and all(
                k in series and series[k]['count'] is not None for series in radios.values() for k in keys)
            if not complete:
                skipped.append(f'{year}-B{number:02d}')
                continue
            blocks.append(dict(id=f'{year}-B{number:02d}', year=year, block=number, weeks=weeks,
                               start=city[keys[0]]['start'], end=city[keys[-1]]['end'], city=[city[k] for k in keys],
                               counts={r: sum(series[k]['count'] for k in keys) for r, series in radios.items()}))
    return blocks, skipped


def protect_block(block, populations):
    counts = block['counts']
    primary_count = {r for r, c in counts.items() if c < MINIMUM}
    primary_population = {r for r in counts if r not in primary_count
                          and (populations.get(r) is None or populations[r] < MIN_POPULATION)}
    levels = {r: PROTECTED if r in primary_count or r in primary_population else level_for(c) for r, c in counts.items()}
    city = [dict(year=w['year'], week=w['week'], start=w['start'], end=w['end'],
                 value=w['count'] if w['count'] >= MINIMUM else None,
                 display=None if w['count'] >= MINIMUM else '<5') for w in block['city']]
    outside = sum(w['count'] for w in block['city']) - sum(counts.values())
    if outside < 0:
        raise PackageBlocked('city_total_below_radio_sum')
    complementary, hidden_city = [], False
    if disclosure(levels, city, outside, unbounded=primary_population) >= 1:
        candidates = sorted((counts[r], r) for r, level in levels.items() if level != PROTECTED)
        if candidates:
            # Smallest published count: least information lost for the citizen view.
            complementary.append(candidates[0][1])
            levels[candidates[0][1]] = PROTECTED
        else:
            for entry in city:
                entry.update(value=None, display='oculto')
            hidden_city = True
    published = [counts[r] for r, level in levels.items() if level != PROTECTED]
    summary = dict(block=block['id'], radios=len(levels), published=len(published),
                   primary_count=len(primary_count), primary_population=len(primary_population),
                   complementary=len(complementary), city_weeks_hidden=hidden_city,
                   city_weeks_below_minimum=sum(1 for e in city if e['display'] == '<5'),
                   min_published_count=min(published) if published else None)
    return levels, city, outside, complementary, summary


def build_package(radio_weeks, city_weeks, outside_radios, *, source, generated_at, populations):
    """Pure function over generated or consolidated aggregates; returns the package dict."""
    radio_weeks, city_weeks = list(radio_weeks), list(city_weeks)
    if {r['radio_id'] for r in radio_weeks} & set(outside_radios):
        raise PackageBlocked('masked_radio_in_published_universe')
    raw_blocks, skipped = _blocks(radio_weeks, city_weeks)
    if not raw_blocks:
        raise PackageBlocked('no_complete_block')
    blocks, report, private = [], [], []
    for block in raw_blocks:
        levels, city, outside, complementary, summary = protect_block(block, populations)
        blocks.append(dict(id=block['id'], year=block['year'], block=block['block'], weeks=block['weeks'],
                           start=block['start'].isoformat(), end=block['end'].isoformat(),
                           radios=dict(sorted(levels.items())),
                           city_weeks=[dict(year=e['year'], week=e['week'], start=e['start'].isoformat(),
                                            end=e['end'].isoformat(), value=e['value'], display=e['display']) for e in city]))
        report.append(summary)
        private.append(dict(block=block['id'], counts=block['counts'], outside=outside, complementary=complementary))
    period = dict(first_block=blocks[0]['id'], last_block=blocks[-1]['id'], start=blocks[0]['start'], end=blocks[-1]['end'],
                  first_week=dict(year=blocks[0]['year'], week=blocks[0]['weeks'][0]),
                  last_week=dict(year=blocks[-1]['year'], week=blocks[-1]['weeks'][-1]))
    activity = dict(schema=SCHEMA, policy=policy(), period=period, generated_at=generated_at.isoformat(),
                    source=dict(kind=source['kind'], fictional=source['kind'] == 'fixture'),
                    outside_radios=sorted(outside_radios), blocks=blocks)
    risk = audit(activity, private, populations)
    risk.update(skipped_incomplete_blocks=skipped, blocks=report)
    if risk['status'] != 'passed':
        raise PackageBlocked('risk_audit_failed')
    return dict(activity=activity, risk=risk, source=source)


def audit(activity, private, populations):
    """Independent re-check of the produced package against the private block counts."""
    disclosures, weeks_seen, overlap = [], set(), 0
    for block, raw in zip(activity['blocks'], private, strict=True):
        keys = {(block['year'], w) for w in block['weeks']}
        overlap += len(keys & weeks_seen)
        weeks_seen |= keys
        city = [dict(value=e['value'], display=e['display']) for e in block['city_weeks']]
        unbounded = {r for r in block["radios"] if populations.get(r) is None or populations[r] < MIN_POPULATION}
        if disclosure(block["radios"], city, raw["outside"], unbounded, raw["complementary"]) >= 1:
            disclosures.append(dict(block=block['id'], kind='protected_radio_presence_provable'))
        for radio, level in block['radios'].items():
            if level == PROTECTED:
                continue
            count = raw['counts'][radio]
            low, high = level_interval(level)
            if not low <= count <= high:
                disclosures.append(dict(block=block['id'], kind='level_inconsistent_with_count'))
            if count < MINIMUM or (populations.get(radio) or 0) < MIN_POPULATION:
                disclosures.append(dict(block=block['id'], kind='small_cell_published'))
        if any(e['value'] is not None and e['value'] < MINIMUM for e in block['city_weeks']):
            disclosures.append(dict(block=block['id'], kind='city_week_below_minimum_published'))
    if overlap:
        disclosures.append(dict(block=None, kind='overlapping_blocks'))
    years = {b['year'] for b in activity['blocks']}
    if years & set(EXCLUDED_YEARS) or not years <= set(DECLARED_YEARS):
        disclosures.append(dict(block=None, kind='excluded_or_uncovered_year_present'))
    if set(activity['outside_radios']) & {r for b in activity['blocks'] for r in b['radios']}:
        disclosures.append(dict(block=None, kind='masked_radio_published'))
    kinds = {d['kind'] for d in disclosures}
    published = [raw['counts'][r] for b, raw in zip(activity['blocks'], private) for r, l in b['radios'].items() if l != PROTECTED]
    cells = sum(len(b['radios']) for b in activity['blocks'])
    checks = dict(blocks_disjoint=not overlap, consecutive_block_differences_share_no_week=not overlap,
                  no_city_week_below_minimum='city_week_below_minimum_published' not in kinds,
                  no_protected_presence_provable_from_totals='protected_radio_presence_provable' not in kinds,
                  no_small_cell_published='small_cell_published' not in kinds,
                  levels_consistent='level_inconsistent_with_count' not in kinds,
                  excluded_years_absent='excluded_or_uncovered_year_present' not in kinds,
                  masked_radios_absent='masked_radio_published' not in kinds)
    return dict(policy_version=POLICY_VERSION, status='passed' if not disclosures else 'failed', disclosures=len(disclosures),
                disclosure_details=disclosures, checks=checks, cells=cells, published_cells=len(published),
                protected_cells=cells - len(published), minimum_published_lower_bound=MINIMUM,
                min_published_count=min(published) if published else None,
                complementary_cells=sum(len(raw['complementary']) for raw in private),
                city_weeks=sum(len(b['city_weeks']) for b in activity['blocks']),
                city_weeks_published=sum(1 for b in activity['blocks'] for e in b['city_weeks'] if e['value'] is not None),
                limitations=['selection_algorithm_inversion_not_modelled', 'outside_records_assumed_known_worst_case',
                             'radio_assignment_mostly_approximate_geocoding'])


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')


def risk_markdown(risk):
    lines = ['# Informe de riesgo de reidentificación', '', f"Política: `{risk['policy_version']}`", '',
             f"- Estado: **{risk['status']}** · revelaciones: {risk['disclosures']}",
             f"- Celdas radio-bloque: {risk['cells']} · publicadas: {risk['published_cells']} · protegidas: {risk['protected_cells']}"
             f" (complementarias: {risk['complementary_cells']})",
             f"- Mínimo publicable: {risk['minimum_published_lower_bound']} · mínimo publicado (privado): {risk['min_published_count']}",
             f"- Semanas de ciudad: {risk['city_weeks']} · con valor publicado: {risk['city_weeks_published']}",
             f"- Bloques incompletos omitidos: {', '.join(risk['skipped_incomplete_blocks']) or 'ninguno'}",
             f"- Limitaciones: {', '.join(risk['limitations'])}", '',
             '| Bloque | Publicados | Prim. conteo | Prim. población | Complementarios | Ciudad <5 | Ciudad oculta |',
             '|---|---|---|---|---|---|---|']
    lines += [f"| {b['block']} | {b['published']} | {b['primary_count']} | {b['primary_population']} | {b['complementary']} | "
              f"{b['city_weeks_below_minimum']} | {'sí' if b['city_weeks_hidden'] else 'no'} |" for b in risk['blocks']]
    lines += ['', 'Comprobaciones: ' + ', '.join(f'{k}={v}' for k, v in risk['checks'].items()), '']
    return '\n'.join(lines).encode('utf-8')


def write_package(package, output, *, package_version):
    output = Path(output).resolve()
    if any(output.is_relative_to(p) for p in FORBIDDEN_OUTPUT):
        raise PackageBlocked('frontend_output_forbidden')
    if package['source']['kind'] != 'fixture' and not output.is_relative_to(REAL_OUTPUT):
        raise PackageBlocked('real_package_must_stay_in_private_processed_folder')
    if output.exists() and any(output.iterdir()):
        raise PackageBlocked('output_exists_never_overwrite')
    output.mkdir(parents=True, exist_ok=True)
    contents = {'activity.json': _canonical(package['activity']), 'risk-report.json': _canonical(package['risk']),
                'risk-report.md': risk_markdown(package['risk'])}
    for name, data in contents.items():
        (output / name).write_bytes(data)
    activity = package['activity']
    manifest = dict(schema=MANIFEST_SCHEMA, package_version=package_version, policy_version=POLICY_VERSION,
                    generated_at=activity['generated_at'], period=activity['period'], source=package['source'],
                    risk=dict(status=package['risk']['status'], disclosures=package['risk']['disclosures']),
                    files={name: hashlib.sha256(data).hexdigest() for name, data in contents.items()})
    data = _canonical(manifest)
    (output / 'manifest.json').write_bytes(data)
    return dict(manifest_sha256=hashlib.sha256(data).hexdigest(), output=str(output))


def epi_weeks(year):
    """Generated calendar for fixtures only: Sunday-start weeks, week 1 contains Jan 4."""
    def first_sunday(y):
        jan4 = date(y, 1, 4)
        return jan4 - timedelta(days=(jan4.weekday() + 1) % 7)
    start, end = first_sunday(year), first_sunday(year + 1)
    return [(n + 1, start + timedelta(weeks=n), start + timedelta(weeks=n, days=6)) for n in range((end - start).days // 7)]


def fictional_inputs(seed=20261116, radios=30):
    """Clearly fictional radios and counts; unrelated to cartography or official sources."""
    rng = random.Random(seed)
    codes = [f'FICT-{i:03d}' for i in range(1, radios + 1)]
    populations = {c: rng.choice([60, 250, 400, 800, 1200]) for c in codes}
    radio_weeks, city_weeks = [], []
    for year in DECLARED_YEARS:
        peak = rng.randint(8, 16)
        for week, start, end in epi_weeks(year):
            intensity = max(0.0, 3.0 - abs(week - peak) / 2.0)
            total = 0
            for code in codes:
                count = sum(rng.random() < intensity / 6 for _ in range(3))
                total += count
                radio_weeks.append(dict(radio_id=code, year=year, week=week, start=start, end=end, count=count))
            city_weeks.append(dict(year=year, week=week, start=start, end=end, count=total + rng.randint(0, 2)))
    return radio_weeks, city_weeks, ['FICT-900'], populations


def load_inputs(conn, version, input_sha256):
    from sigard_ml.data_access import MLRepository
    repo = MLRepository(conn)
    meta = repo.query('SELECT entrada_sha256 FROM analytics.consolidacion_dataset WHERE version=%s', (version,))
    if len(meta) != 1 or meta.iloc[0].entrada_sha256 != input_sha256:
        raise PackageBlocked('verified_stage1_version_and_hash_required')
    rows = repo.query('''SELECT radio_codigo,anio,numero,inicio,fin,registros_asignados,cobertura_estado,poblacion_contexto_2022
        FROM analytics.consolidacion_radio_semana WHERE dataset_version=%s AND mascara_comun AND anio BETWEEN 2020 AND 2024
        ORDER BY radio_codigo,inicio''', (version,))
    city = repo.query('''SELECT anio,numero,inicio,fin,cantidad_sigard FROM analytics.consolidacion_departamento
        WHERE dataset_version=%s AND anio BETWEEN 2020 AND 2024 ORDER BY inicio''', (version,))
    # Only analytics views: the read-only analytics role has no access to the territory schema.
    outside = repo.query('''SELECT DISTINCT radio_codigo AS codigo FROM analytics.consolidacion_radio_semana
        WHERE dataset_version=%s AND NOT mascara_comun ORDER BY 1''', (version,))
    known = lambda value: value is not None and value == value  # noqa: E731 - NaN from pandas is unknown
    radio_weeks = [dict(radio_id=str(r.radio_codigo), year=int(r.anio), week=int(r.numero), start=r.inicio, end=r.fin,
                        count=None if r.cobertura_estado == 'out_of_coverage' else int(r.registros_asignados))
                   for r in rows.itertuples()]
    populations = {str(r.radio_codigo): int(r.poblacion_contexto_2022) if known(r.poblacion_contexto_2022) else None
                   for r in rows.itertuples()}
    city_weeks = [dict(year=int(r.anio), week=int(r.numero), start=r.inicio, end=r.fin,
                       count=int(r.cantidad_sigard) if known(r.cantidad_sigard) else None) for r in city.itertuples()]
    return radio_weeks, city_weeks, [str(c) for c in outside.codigo], populations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='action', required=True)
    real = sub.add_parser('build', help='real aggregates; only on explicit request of the project owner')
    real.add_argument('--connection', type=Path, required=True)
    real.add_argument('--config', type=Path, required=True, help='JSON with dataset_version, input_sha256, package_version')
    real.add_argument('--output', type=Path, required=True)
    fixture = sub.add_parser('fixture', help='generated fictional package for local tests')
    fixture.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'fixture':
            radio_weeks, city_weeks, outside, populations = fictional_inputs()
            package = build_package(radio_weeks, city_weeks, outside, populations=populations,
                                    source=dict(kind='fixture', dataset_version='fictional', input_sha256=None),
                                    generated_at=date(2026, 11, 16))
            result = write_package(package, args.output, package_version='fictional-public-activity-v1')
        else:
            if any(not p.resolve().is_relative_to(PRIVATE_CONFIG) for p in (args.connection, args.config)):
                raise PackageBlocked('private_configuration_required')
            from sigard_ml.ingestion.epidemiology.db import connect
            cfg = json.loads(args.config.read_text(encoding='utf-8-sig'))
            url = json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
            with connect(url) as conn:
                radio_weeks, city_weeks, outside, populations = load_inputs(conn, cfg['dataset_version'], cfg['input_sha256'])
            package = build_package(radio_weeks, city_weeks, outside, populations=populations,
                                    source=dict(kind='real', dataset_version=cfg['dataset_version'], input_sha256=cfg['input_sha256']),
                                    generated_at=date.today())
            result = write_package(package, args.output, package_version=cfg['package_version'])
        print(json.dumps(dict(status='complete', action=args.action, risk=package['risk']['status'], **result)))
        return 0
    except PackageBlocked as error:
        print(json.dumps(dict(status='blocked', reason=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
