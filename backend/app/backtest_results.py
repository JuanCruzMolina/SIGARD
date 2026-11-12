"""Pinned, aggregate-only historical results. No DB, estimator or training runtime."""
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .experimental_results import ROOT, ArtifactBlocked, InvalidDate, NotAvailable, local_bytes, require

SCHEMA = 'sigard-historical-backtest/1'
EVALUATION = 'event_time_retrospective_reconstruction'
METHODS = {'presence': 'presence_seasonal', 'quantity': 'count_latest'}
CONTEXT = ('schema_version', 'dataset_version', 'campaign_version', 'data_policy_version', 'territory_version')
WEEK = ('target_year', 'target_epi_week', 'target_week', 'target_end', 'origin_week', 'origin_end',
        'availability_status', 'unavailable_reason')
STATUSES = {'available', 'outside_coverage', 'insufficient_training_support', 'territorial_uncertainty', 'outside_common_territory'}


def finite(value, *, binary=False, signed=False):
    require(value is None or (type(value) in (int, float) and math.isfinite(value)
                             and (signed or value >= 0) and (not binary or value in (0, 1))))
    return value


def metrics(rows):
    """Same unrounded cells used by the maps and tables; unknowns are excluded."""
    valid = [r for r in rows if r['availability_status'] == 'available']
    counts = [(r['predicted']['quantity'], r['observed']['quantity'], r['baseline']['quantity']) for r in valid]
    counts = [r for r in counts if all(v is not None for v in r)]
    confusion = Counter(r['confusion'] for r in valid)
    tp, fp, fn, tn = (confusion[k] for k in ('TP', 'FP', 'FN', 'TN'))
    ratio = lambda a, b: a / b if b else None
    pairs = [(r['predicted']['presence_score'], r['observed']['presence']) for r in valid
             if r['predicted']['presence_score'] is not None and r['observed']['presence'] is not None]
    groups = {}
    for score, label in pairs:
        groups.setdefault(score, [0, 0])[label] += 1
    positives = sum(y for _, y in pairs); negatives = len(pairs) - positives
    seen_pos = seen = 0; ap = auc = 0.0; lower_neg = negatives
    for score in sorted(groups, reverse=True):
        neg, pos = groups[score]; seen += neg + pos; seen_pos += pos; lower_neg -= neg
        ap += pos * seen_pos / seen
        auc += pos * (lower_neg + neg / 2)
    calibration = []
    for low in range(10):
        bucket = [(p, y) for p, y in pairs if low / 10 <= p < (low + 1) / 10 or low == 9 and p == 1]
        if bucket:
            calibration.append({'lower': low / 10, 'upper': (low + 1) / 10, 'n': len(bucket),
                                'score_mean': sum(p for p, _ in bucket) / len(bucket),
                                'observed_fraction': sum(y for _, y in bucket) / len(bucket)})
    def error(items, baseline=False):
        if not items: return {'n': 0, 'mae': None, 'rmse': None, 'bias': None}
        errors = [(b if baseline else p) - y for p, y, b in items]
        return {'n': len(errors), 'mae': sum(abs(e) for e in errors) / len(errors),
                'rmse': math.sqrt(sum(e * e for e in errors) / len(errors)), 'bias': sum(errors) / len(errors)}
    return {'n_comparable': len(valid), 'quantity': error(counts), 'baseline': error(counts, True),
            'quantity_zero': error([r for r in counts if r[1] == 0]),
            'quantity_positive': error([r for r in counts if r[1] > 0]),
            'presence': {'n': len(pairs), 'brier': ratio(sum((p - y) ** 2 for p, y in pairs), len(pairs)),
                         'average_precision': ratio(ap, positives), 'roc_auc': ratio(auc, positives * negatives),
                         'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn), 'f1': ratio(2 * tp, 2 * tp + fp + fn),
                         'confusion': {'TP': tp, 'FP': fp, 'FN': fn, 'TN': tn}, 'calibration': calibration},
            'totals': {name: sum(r[i] for r in counts) if counts else None
                       for i, name in enumerate(('predicted', 'observed', 'baseline'))}}


class BacktestResults:
    def __init__(self, registry_path, registry_sha256, *, root=ROOT):
        self.root = Path(root).resolve(); self.registry_path = Path(registry_path); self.registry_sha256 = registry_sha256

    def _bundle(self):
        registry = json.loads(local_bytes(self.root, self.registry_path, self.registry_sha256))
        require(registry.get('local_read_authorized') is True)
        path = Path(registry['manifest_path'])
        require(str(path).replace('\\', '/').startswith('data/interim/official/'))
        manifest = json.loads(local_bytes(self.root, path, registry['manifest_sha256']))
        require(manifest['schema_version'] == SCHEMA and manifest['local_read_authorized'] is True
                and manifest['selected_methods'] == METHODS and manifest['training_performed'] is False)
        return path.parent, manifest

    def _read(self, name):
        folder, manifest = self._bundle()
        require(name in manifest['files'])
        value = json.loads(local_bytes(self.root, folder / name, manifest['files'][name]))
        if name != 'geometry.private.json':
            require(value.get('schema_version') == SCHEMA)
            require(all(value[k] == manifest[k] for k in CONTEXT))
        return value

    def catalog(self):
        value = self._read('calendar.private.json')
        require(value['calendar_version'] == 'ar-snvs-2020-2026-v1')
        weeks = [{k: w[k] for k in WEEK} for w in value['weeks']]
        previous = None
        for w in weeks:
            start = date.fromisoformat(w['target_week']); end = date.fromisoformat(w['target_end'])
            require(start.weekday() == 6 and end == start + timedelta(days=6)
                    and w['availability_status'] in STATUSES
                    and date.fromisoformat(w['origin_week']) == start - timedelta(days=7)
                    and date.fromisoformat(w['origin_end']) == start - timedelta(days=1))
            require(previous is None or start == previous + timedelta(days=7)); previous = start
            require(1 <= w['target_epi_week'] <= 53 and 2020 <= w['target_year'] <= 2026)
        require(len(value['radio_ids']) == 263 and len(set(value['radio_ids'])) == 263)
        require(all(re.fullmatch(r'\d{9}', radio) for radio in value['radio_ids']))
        return {**{k: value[k] for k in CONTEXT}, 'calendar_version': value['calendar_version'],
                'weeks': weeks, 'radio_ids': value['radio_ids']}

    def metadata(self):
        value = self._read('metadata.private.json')
        require(value['selected_methods'] == METHODS and value['operational_enabled'] is False
                and value['alerts_enabled'] is False and value['evaluation_type'] == EVALUATION)
        keys = (*CONTEXT, 'evaluation_type', 'selected_methods', 'method_kinds', 'method_labels',
                'arrival_availability', 'scores', 'operational_enabled', 'alerts_enabled', 'coverage_basis',
                'included_2022_policy', 'territory_radios', 'common_radios', 'dataset_sha256', 'protocol_sha256',
                'horizon_weeks', 'purge_weeks', 'reference_is_not_trained_ml')
        # Nested objects also have fixed keys. No arbitrary source metadata is exposed.
        result = {k: value[k] for k in keys}
        for key in ('selected_methods', 'method_kinds', 'method_labels'):
            result[key] = {k: value[key][k] for k in METHODS}
        return result

    def geometry(self):
        value = self._read('geometry.private.json'); radios = set(self.catalog()['radio_ids'])
        require(value['type'] == 'FeatureCollection' and len(value['features']) == 263)
        features = []
        for f in value['features']:
            p, g = f['properties'], f['geometry']
            require(p['radio_id'] in radios and type(p['common_mask']) is bool)
            require(g['type'] in ('Polygon', 'MultiPolygon'))
            polygons = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            for polygon in polygons:
                for ring in polygon:
                    require(len(ring) >= 4 and ring[0] == ring[-1])
                    for point in ring:
                        require(len(point) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in point)
                                and -180 <= point[0] <= 180 and -90 <= point[1] <= 90)
            features.append({'type': 'Feature', 'properties': {k: p[k] for k in ('radio_id', 'common_mask')},
                             'geometry': {'type': g['type'], 'coordinates': g['coordinates']}})
        require({f['properties']['radio_id'] for f in features} == radios
                and sum(f['properties']['common_mask'] for f in features) == 256)
        return {'type': 'FeatureCollection', 'features': features}

    def week(self, year, week, radio=None):
        try:
            if not re.fullmatch(r'\d{4}', str(year)) or not re.fullmatch(r'\d{1,2}', str(week)): raise ValueError
            year, week = int(year), int(week)
        except ValueError: raise InvalidDate() from None
        catalog = self.catalog()
        selected = next((w for w in catalog['weeks'] if w['target_year'] == year and w['target_epi_week'] == week), None)
        if selected is None: raise InvalidDate()
        if radio is not None and radio not in catalog['radio_ids']: raise NotAvailable()
        value = self._read(f"weeks/{selected['target_week']}.private.json")
        require(all(value[k] == selected[k] for k in WEEK) and value['evaluation_type'] == EVALUATION)
        if value['availability_status'] == 'available':
            require(date.fromisoformat(value['fit_last_target_end']) < date.fromisoformat(value['origin_week']) - timedelta(days=28))
        projected = []
        for row in value['rows']:
            require(row['availability_status'] in STATUSES and type(row['common_mask']) is bool)
            r = {k: row[k] for k in ('radio_id', 'availability_status', 'unavailable_reason', 'common_mask',
                                     'territorial_quality', 'coverage_status', 'zero_provenance', 'confusion')}
            r['predicted'] = {k: finite(row['predicted'][k], binary=k == 'presence') for k in ('presence_score', 'presence', 'quantity')}
            r['observed'] = {k: finite(row['observed'][k], binary=k == 'presence') for k in ('quantity', 'presence', 'assigned_records')}
            r['observed']['quality_counts'] = {k: finite(row['observed']['quality_counts'][k]) for k in ('approximate', 'provisional', 'verified')}
            r['baseline'] = {'quantity': finite(row['baseline']['quantity'])}
            r['presence_threshold'] = finite(row['presence_threshold'])
            r['difference'] = finite(row['difference'], signed=True); r['absolute_error'] = finite(row['absolute_error'])
            require(r['confusion'] in (None, 'TP', 'FP', 'FN', 'TN'))
            if r['availability_status'] != 'available':
                require(all(v is None for v in r['predicted'].values()) and r['baseline']['quantity'] is None)
            else:
                require(r['common_mask'] and all(v is not None for v in r['predicted'].values())
                        and r['predicted']['presence_score'] <= 1 and r['presence_threshold'] <= 1)
                p, y = r['predicted']['presence'], r['observed']['presence']
                require(p == int(r['predicted']['presence_score'] >= r['presence_threshold']))
                require(r['confusion'] == ('TP' if p and y else 'FP' if p else 'FN' if y else 'TN'))
                require(r['difference'] == r['predicted']['quantity'] - r['observed']['quantity']
                        and r['absolute_error'] == abs(r['difference']))
            projected.append(r)
        require(len(projected) == 263 and {r['radio_id'] for r in projected} == set(catalog['radio_ids']))
        require(sum(r['common_mask'] for r in projected) == 256)
        department = {k: value['department'][k] for k in ('observed_total', 'assigned_common_total', 'assigned_masked_total', 'unassigned_total', 'reconciled')}
        if department['observed_total'] is not None:
            common = sum(r['observed']['assigned_records'] or 0 for r in projected if r['common_mask'])
            masked = sum(r['observed']['assigned_records'] or 0 for r in projected if not r['common_mask'])
            require(department['reconciled'] is True and department['assigned_common_total'] == common
                    and department['assigned_masked_total'] == masked
                    and department['observed_total'] == common + masked + department['unassigned_total'])
        rows = [r for r in projected if radio is None or r['radio_id'] == radio]
        result = {k: value[k] for k in (*CONTEXT, *WEEK, 'evaluation_type', 'fit_last_target_end')}
        result['model_version'] = {k: value['model_version'][k] for k in METHODS}
        result['period_availability_status'] = result['availability_status']
        if radio and rows[0]['availability_status'] != 'available':
            result['availability_status'] = rows[0]['availability_status']
            result['unavailable_reason'] = rows[0]['unavailable_reason']
        return {**result, 'scope': 'selected_territory' if radio else 'common_territories', 'selected_radio': radio,
                'department': department, 'rows': rows, 'metrics': metrics(rows)}

    def history(self, start, end, radio=None):
        catalog = self.catalog()
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except (ValueError, TypeError): raise InvalidDate() from None
        keys = {w['target_week'] for w in catalog['weeks']}
        if start not in keys or end not in keys or first > last: raise InvalidDate()
        if radio is not None and radio not in catalog['radio_ids']: raise NotAvailable()
        series = []; all_rows = []; years = {}
        for w in catalog['weeks']:
            if start <= w['target_week'] <= end:
                result = self.week(w['target_year'], w['target_epi_week'], radio)
                totals = result['metrics']['totals']; valid = result['availability_status'] == 'available'
                observed = [r['observed']['quantity'] for r in result['rows'] if r['common_mask']]
                observed_total = sum(observed) if observed and all(v is not None for v in observed) else None
                series.append({**{k: result[k] for k in WEEK}, 'observed': observed_total,
                               'predicted': totals['predicted'] if valid else None, 'baseline': totals['baseline'] if valid else None,
                               'n_comparable': result['metrics']['n_comparable'], 'metrics': result['metrics']})
                all_rows.extend(result['rows']); years.setdefault(str(w['target_year']), []).extend(result['rows'])
        return {**{k: catalog[k] for k in CONTEXT}, 'evaluation_type': EVALUATION, 'selected_radio': radio,
                'start': start, 'end': end, 'series': series, 'metrics': metrics(all_rows),
                'by_year': {year: metrics(rows) for year, rows in years.items()}}
