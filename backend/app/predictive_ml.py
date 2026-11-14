"""Verified offline ML projections. No estimator loading, inference or fitting.

Candidates come from each installed manifest (overlay/1: stage-2 candidates with a
threshold; overlay/2: corrective v2 candidates with a prespecified top-k rule). The
week contract is keyed by candidate id so several candidates per capability coexist
with the selected statistical reference. No candidate is promoted here.
"""
import json
from datetime import date, timedelta

from .backtest_results import CONTEXT, finite, metrics
from .experimental_results import ArtifactBlocked, local_bytes, require

SCHEMA_V1 = 'sigard-predictive-ml-overlay/1'
SCHEMA_V2 = 'sigard-predictive-ml-overlay/2'
V1_CANDIDATES = {'presence': 'rf_A_epi_climate', 'quantity': 'residual_h1'}
STATES = {SCHEMA_V1: 'experimental_evaluated', SCHEMA_V2: 'experimental_not_promoted'}
# Preferred defaults when installed; otherwise the first candidate of the capability.
DEFAULTS = {'presence': 'rf_v2_city_propensity', 'quantity': 'residual_v2'}
CAPABILITIES = ('presence', 'quantity')
VALUE_KEYS = ('presence_score', 'presence', 'presence_threshold', 'topk_rank', 'onset_eligible',
              'quantity', 'confusion', 'difference', 'absolute_error')
BLOCKED = (ArtifactBlocked, KeyError, ValueError, TypeError, OSError)
TOPK_PRIVATE_ONLY = 'private_only_selection_bias'
# Artifacts are only hashed, never decoded; RF artifacts of later blocks exceed the JSON limit.
ARTIFACT_LIMIT = 64 * 1024 * 1024


class MLProjection:
    """A new instance per request; hash all referenced bytes before use."""
    def __init__(self, root, pointer, sha256):
        self.root = root
        pin = json.loads(local_bytes(root, pointer, sha256))
        self.path = pin['path']
        self.doc = json.loads(local_bytes(root, self.path, pin['sha256']))
        self.schema = self.doc['schema_version']
        require(self.schema in STATES and self.doc['horizon_weeks'] == 1 and self.doc['operational_enabled'] is False)
        if self.schema == SCHEMA_V1:
            require(self.doc['candidates'] == V1_CANDIDATES)
            self.candidates = [dict(id=method, capability=capability, state=STATES[SCHEMA_V1],
                decision_rule={'type': 'threshold'} if capability == 'presence' else {'type': 'count_estimate'},
                campaign=self.doc['campaign_version'], features=self.doc['features'][capability], calibrated=False,
                promotion={'decision': 'not_promoted'}) for capability, method in V1_CANDIDATES.items()]
        else:
            require(self.doc['training_performed'] is False and self.doc['inference_performed'] is False)
            self.candidates = []
            for c in self.doc['candidates']:
                rule = c['decision_rule']
                require(c['capability'] in CAPABILITIES and c['state'] == STATES[SCHEMA_V2] and c['calibrated'] is False)
                require(c['promotion']['decision'] == 'not_promoted')
                require(rule['type'] == 'top_k' and type(rule['k']) is int and 1 <= rule['k'] <= 256
                        if c['capability'] == 'presence' else rule['type'] == 'count_estimate')
                self.candidates.append(dict(id=c['id'], capability=c['capability'], state=c['state'], decision_rule=rule,
                    campaign=self.doc['ml_campaign_version'], features=c['features'], calibrated=False,
                    promotion=c['promotion']))
        require(len({c['id'] for c in self.candidates}) == len(self.candidates))
        self.by_id = {c['id']: c for c in self.candidates}
        self.checked = set()

    def compatible(self, base):
        require(all(self.doc[k] == base[k] for k in CONTEXT if k != 'schema_version'))

    def _models(self, value):
        if self.schema == SCHEMA_V1:
            # overlay/1 keys models by capability; normalize to candidate ids.
            require(all(c in V1_CANDIDATES and m['method'] == V1_CANDIDATES[c] for c, m in value['models'].items()))
            return {m['method']: m for m in value['models'].values()}
        require(all(k in self.by_id and m['method'] == k for k, m in value['models'].items()))
        return value['models']

    def week(self, base):
        self.compatible(base)
        pin = self.doc['weeks'].get(base['target_week'])
        if pin is None: return None
        value = json.loads(local_bytes(self.root, pin['path'], pin['sha256']))
        require(value['target_week'] == base['target_week'] and value['origin_week'] == base['origin_week'])
        require(date.fromisoformat(value['target_week']) - date.fromisoformat(value['origin_week']) == timedelta(days=7))
        require(len(value['rows']) == 256 and len({r['radio_id'] for r in value['rows']}) == 256)
        require(set(r['radio_id'] for r in value['rows']) == set(self.doc['radio_ids']))
        models = self._models(value)
        for method, model in models.items():
            candidate = self.by_id[method]
            require(model['state'] == candidate['state'] and model['calibrated'] is False)
            require(date.fromisoformat(model['fit_last_target_end']) < date.fromisoformat(base['origin_week']) - timedelta(days=28))
            require(model['features'] == candidate['features'])
            artifact = model['artifact']
            require(artifact['sha256'] == model['artifact_sha256'])
            if artifact['sha256'] not in self.checked:
                local_bytes(self.root, artifact['path'], artifact['sha256'], limit=ARTIFACT_LIMIT)
                self.checked.add(artifact['sha256'])
        if self.schema == SCHEMA_V2:
            # The offline top-k resolution must be a complete per-week ranking.
            require(sorted(r['topk_rank'] for r in value['rows']) == list(range(1, 257)))
        return {'models': models, 'rows': {r['radio_id']: r for r in value['rows']}}

    def availability(self, target):
        """Calendar availability from the hashed manifest only (no per-week reads).

        Both compilers write a week only with every candidate; the week document itself is
        hashed and validated when requested, and a missing model there stays not_available.
        Reading 208 week files per calendar request dominated the cold start.
        """
        status = 'available' if target in self.doc['weeks'] else 'not_available'
        return {c['id']: status for c in self.candidates}


def candidate_list(projections):
    candidates = [c for p in projections for c in p.candidates]
    require(len({c['id'] for c in candidates}) == len(candidates))
    return candidates


def default_candidates(candidates):
    result = {}
    for capability in CAPABILITIES:
        ids = [c['id'] for c in candidates if c['capability'] == capability]
        if ids: result[capability] = DEFAULTS[capability] if DEFAULTS[capability] in ids else ids[0]
    return result


def describe(candidate):
    return {k: candidate[k] for k in ('id', 'capability', 'state', 'decision_rule', 'campaign', 'calibrated', 'promotion')}


def empty_values():
    return dict.fromkeys(VALUE_KEYS)


def project_row(candidate, raw, row):
    """One candidate's values for one radio; raises if inconsistent with the reference row."""
    require(raw['observed'] == row['observed']['quantity'] and raw['baseline'] == row['baseline']['quantity'])
    if 'baseline_score' in raw: require(raw['baseline_score'] == row['predicted']['presence_score'])
    values = empty_values()
    if candidate['capability'] == 'presence':
        score = finite(raw['presence_score']); require(score is not None and score <= 1)
        rule = candidate['decision_rule']
        if rule['type'] == 'top_k':
            rank = raw['topk_rank']; require(type(rank) is int and 1 <= rank <= 256)
            presence = int(rank <= rule['k'])
            values.update(topk_rank=rank, onset_eligible=bool(raw['onset_eligible']))
        else:
            threshold = finite(raw['presence_threshold']); require(threshold is not None and threshold <= 1)
            presence = int(score >= threshold)
            values.update(presence_threshold=threshold)
        y = row['observed']['presence']
        values.update(presence_score=score, presence=presence,
                      confusion='TP' if presence and y else 'FP' if presence else 'FN' if y else 'TN')
    else:
        quantity = finite(raw['quantity']); require(quantity is not None)
        difference = quantity - row['observed']['quantity']
        values.update(quantity=quantity, difference=difference, absolute_error=abs(difference))
    return values


def attach_ml(base, projections):
    """Keep the reference contract unchanged; add independent experimental outputs per candidate."""
    projections = projections or []
    candidates = candidate_list(projections)
    base['ml'] = {c['id']: {**describe(c), 'availability_status': 'not_available',
                            'reason': 'saved_compatible_prediction_not_available'} for c in candidates}
    projected = {}
    for projection in projections:
        try:
            value = projection.week(base)
            if value is None: continue
            # Validate every row before changing the response (all-or-nothing per projection).
            rows = {}
            for row in base['rows']:
                raw = value['rows'].get(row['radio_id'])
                if raw is None: continue
                require(row['common_mask'] and row['availability_status'] == 'available')
                rows[row['radio_id']] = {method: project_row(projection.by_id[method], raw, row) for method in value['models']}
            require(len(rows) == len(value['rows']))
        except BLOCKED:
            for c in projection.candidates:
                base['ml'][c['id']]['reason'] = 'ml_integrity_or_compatibility_blocked'
            continue
        for method, model in value['models'].items():
            base['ml'][method].update(availability_status='available', reason=None, model_version=model['model_version'],
                fit_last_target_end=model['fit_last_target_end'], features=model['features'],
                artifact_sha256=model['artifact_sha256'])
        for radio, by_method in rows.items():
            projected.setdefault(radio, {}).update(by_method)
    for row in base['rows']:
        values = projected.get(row['radio_id'], {})
        row['ml'] = {c['id']: values.get(c['id'], empty_values()) for c in candidates}
        row['ml_availability'] = {c['id']: 'available' if c['id'] in values else 'not_available' for c in candidates}
    return base


def topk_metrics(rows, candidate, mode):
    k = candidate['decision_rule']['k']
    if mode != 'private':
        # Protected mode only shows radios with 5+ records: every false alarm and every onset
        # (origin 0) is hidden, so a recall@k there would be a biased, selected subset.
        return {'k': k, 'status': TOPK_PRIVATE_ONLY, 'positives': None, 'hits': None, 'recall': None,
                'onset_events': None, 'onset_hits': None, 'onset_recall': None, 'flagged': None, 'precision': None}
    values = [(r['ml'][candidate['id']], r['observed']['presence']) for r in rows
              if r['availability_status'] == 'available' and r.get('ml', {}).get(candidate['id'], {}).get('presence') is not None]
    positives = sum(y for _, y in values); hits = sum(v['presence'] * y for v, y in values)
    onset = sum(y for v, y in values if v['onset_eligible']); onset_hits = sum(v['presence'] * y for v, y in values if v['onset_eligible'])
    flagged = sum(v['presence'] for v, _ in values)
    ratio = lambda a, b: a / b if b else None
    return {'k': k, 'status': 'all_comparable', 'positives': positives, 'hits': hits, 'recall': ratio(hits, positives),
            'onset_events': onset, 'onset_hits': onset_hits, 'onset_recall': ratio(onset_hits, onset),
            'flagged': flagged, 'precision': ratio(hits, flagged)}


def ml_metrics(rows, candidates, mode):
    result = {}
    for c in candidates:
        projected = []
        for row in rows:
            values = row.get('ml', {}).get(c['id'])
            if row['availability_status'] != 'available' or not values or all(values[k] is None for k in ('presence_score', 'quantity')):
                continue
            projected.append({**row, 'predicted': {k: values[k] for k in ('presence_score', 'presence', 'quantity')},
                              'confusion': values['confusion']})
        result[c['id']] = metrics(projected)
        if c['decision_rule']['type'] == 'top_k':
            result[c['id']]['topk'] = topk_metrics(rows, c, mode)
    return result
