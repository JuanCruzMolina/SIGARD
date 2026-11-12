"""Verified offline ML projections. No estimator loading, inference or fitting."""
import json
from datetime import date, timedelta

from .backtest_results import CONTEXT, finite, metrics
from .experimental_results import local_bytes, require

SCHEMA = 'sigard-predictive-ml-overlay/1'
CANDIDATES = {'presence': 'rf_A_epi_climate', 'quantity': 'residual_h1'}


class MLProjection:
    """A new instance per request; hash all referenced bytes before use."""
    def __init__(self, root, pointer, sha256):
        self.root = root
        pin = json.loads(local_bytes(root, pointer, sha256))
        self.path = pin['path']
        self.doc = json.loads(local_bytes(root, self.path, pin['sha256']))
        require(self.doc['schema_version'] == SCHEMA and self.doc['candidates'] == CANDIDATES)
        require(self.doc['horizon_weeks'] == 1 and self.doc['operational_enabled'] is False)
        self.checked = set()

    def compatible(self, base):
        require(all(self.doc[k] == base[k] for k in CONTEXT if k != 'schema_version'))

    def week(self, base):
        self.compatible(base)
        pin = self.doc['weeks'].get(base['target_week'])
        if pin is None: return None
        value = json.loads(local_bytes(self.root, pin['path'], pin['sha256']))
        require(value['target_week'] == base['target_week'] and value['origin_week'] == base['origin_week'])
        require(date.fromisoformat(value['target_week']) - date.fromisoformat(value['origin_week']) == timedelta(days=7))
        require(len(value['rows']) == 256 and len({r['radio_id'] for r in value['rows']}) == 256)
        require(set(r['radio_id'] for r in value['rows']) == set(self.doc['radio_ids']))
        for capability, model in value['models'].items():
            require(capability in CANDIDATES and model['method'] == CANDIDATES[capability])
            require(model['state'] == 'experimental_evaluated' and model['calibrated'] is False)
            require(date.fromisoformat(model['fit_last_target_end']) < date.fromisoformat(base['origin_week']) - timedelta(days=28))
            require(model['features'] == self.doc['features'][capability])
            artifact = model['artifact']
            require(artifact['sha256'] == model['artifact_sha256'])
            if artifact['sha256'] not in self.checked:
                local_bytes(self.root, artifact['path'], artifact['sha256'])
                self.checked.add(artifact['sha256'])
        return value

    def availability(self, target):
        pin = self.doc['weeks'].get(target)
        if pin is None: return {c: 'not_available' for c in CANDIDATES}
        value = json.loads(local_bytes(self.root, pin['path'], pin['sha256']))
        require(value['target_week'] == target)
        return {c: 'available' if c in value['models'] else 'not_available' for c in CANDIDATES}


def attach_ml(base, reader):
    """Keep the reference contract unchanged; add independent experimental outputs."""
    value = reader.week(base) if reader else None
    lookup = {r['radio_id']: r for r in value['rows']} if value else {}
    models = value['models'] if value else {}
    base['ml'] = {c: {'availability_status': 'available' if c in models else 'not_available',
                     'reason': None if c in models else 'saved_compatible_prediction_not_available',
                     **({k: models[c][k] for k in ('method', 'state', 'model_version', 'fit_last_target_end',
                                                   'features', 'calibrated', 'artifact_sha256')} if c in models else {})}
                  for c in CANDIDATES}
    for row in base['rows']:
        raw = lookup.get(row['radio_id'])
        row['ml'] = dict(presence_score=None, presence=None, quantity=None, presence_threshold=None,
                         confusion=None, difference=None, absolute_error=None)
        row['ml_availability'] = {c: 'not_available' for c in CANDIDATES}
        if raw is None: continue
        require(row['common_mask'] and row['availability_status'] == 'available')
        require(raw['observed'] == row['observed']['quantity'] and raw['baseline'] == row['baseline']['quantity']
                and raw['baseline_score'] == row['predicted']['presence_score'])
        if 'presence' in models:
            score, threshold = finite(raw['presence_score']), finite(raw['presence_threshold'])
            require(score is not None and threshold is not None and score <= 1 and threshold <= 1)
            p, y = int(score >= threshold), row['observed']['presence']
            row['ml'].update(presence_score=score, presence=p, presence_threshold=threshold,
                             confusion='TP' if p and y else 'FP' if p else 'FN' if y else 'TN')
            row['ml_availability']['presence'] = 'available'
        if 'quantity' in models:
            quantity = finite(raw['quantity']); require(quantity is not None)
            difference = quantity - row['observed']['quantity']
            row['ml'].update(quantity=quantity, difference=difference, absolute_error=abs(difference))
            row['ml_availability']['quantity'] = 'available'
    return base


def ml_metrics(rows):
    projected = []
    for row in rows:
        ml = row.get('ml', {})
        if row['availability_status'] != 'available' or all(ml.get(k) is None for k in ('presence_score', 'quantity')): continue
        projected.append({**row, 'predicted': {k: ml.get(k) for k in ('presence_score', 'presence', 'quantity')},
                          'confusion': ml.get('confusion')})
    return metrics(projected)
