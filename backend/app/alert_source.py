"""Prediction sources for internal alerts. Read-only; no training, inference or files.

`LocalResearchSource` reads the already integrated predictions from the local
predictive API (127.0.0.1:8765) over HTTP, so the administrative API never opens
private artifacts. It is attached only by `alerts_local` (never in deployments).
`FictionalSource` is a generated, clearly fictitious grid for tests and browser
checks: unrelated to real cartography, predictions or sources.

Exact values stay in this process memory; every response/persisted value goes
through `alert_rules.disclose` first.
"""
from datetime import date, timedelta
import random
import threading

REFERENCE_QUANTITY = 'count_latest'
YEARS = (2021, 2024)


class SourceUnavailable(Exception):
    pass


def _check(condition):
    if not condition:
        raise SourceUnavailable('Respuesta de predicciones inválida')


class _Store:
    """Compact per-week cache: {target_week: {radio: {'observed': q, model: {'rank', 'quantity'}}}}."""

    kind = 'base'

    def __init__(self):
        self._weeks = {}
        self._lock = threading.Lock()
        self._status = None

    def status(self):
        with self._lock:
            if self._status is None:
                self._status = self._load_status()
            return self._status

    def week(self, target_week):
        status = self.status()
        entry = next((w for w in status['weeks'] if w['target_week'] == target_week), None)
        if entry is None:
            return None
        with self._lock:
            if target_week not in self._weeks:
                self._weeks[target_week] = self._load_week(entry, status)
            return self._weeks[target_week]

    def preload(self):
        for entry in self.status()['weeks']:
            self.week(entry['target_week'])


class LocalResearchSource(_Store):
    kind = 'local_research_api'
    BASE = 'http://127.0.0.1:8765/api/v1/research/predictive'
    # The research API admits only its loopback frontend origin plus the read header.
    HEADERS = {'Origin': 'http://127.0.0.1:5173', 'X-Sigard-Research': 'local-read'}

    def __init__(self, client=None):
        super().__init__()
        import httpx
        self._client = client or httpx.Client(base_url=self.BASE, headers=self.HEADERS, follow_redirects=False,
                                              timeout=20, trust_env=False)

    def _get(self, path, **params):
        try:
            response = self._client.get(path, params=params or None)
        except Exception:
            raise SourceUnavailable('API predictiva local no disponible') from None
        if response.status_code != 200:
            raise SourceUnavailable('API predictiva local no disponible')
        return response.json()

    def _load_status(self):
        calendar = self._get('/calendar')
        _check(calendar.get('training_enabled') is False and calendar.get('operational_enabled') is False)
        models = []
        for c in calendar['experimental_candidates']:
            rule = c['decision_rule']
            _check(c['promotion']['decision'] == 'not_promoted')
            if c['capability'] == 'presence' and rule['type'] == 'top_k':
                models.append(dict(id=c['id'], capability='presence', rule=dict(type='top_k', k=int(rule['k'])),
                                   state=c['state'], reference=False))
            elif c['capability'] == 'quantity' and rule['type'] == 'count_estimate':
                models.append(dict(id=c['id'], capability='quantity', rule=dict(type='count_estimate'),
                                   state=c['state'], reference=False))
        defaults = set((calendar.get('default_candidates') or {}).values())
        for model in models:
            model['default'] = model['id'] in defaults
        _check(calendar['active_methods']['quantity'] == REFERENCE_QUANTITY)
        models.append(dict(id=REFERENCE_QUANTITY, capability='quantity', rule=dict(type='count_estimate'),
                           state='selected_statistical_reference', reference=True, default=False))
        weeks = []
        for w in calendar['weeks']:
            if YEARS[0] <= w['target_year'] <= YEARS[1] and w['availability_status'] == 'available':
                available = [m['id'] for m in models if m['reference'] or w['ml_availability'].get(m['id']) == 'available']
                weeks.append(dict(target_week=w['target_week'], target_year=w['target_year'],
                                  target_epi_week=w['target_epi_week'], models=available))
        context = {k: calendar[k] for k in ('dataset_version', 'data_policy_version', 'campaign_version',
                                            'territory_version', 'calendar_version', 'module_version')}
        return dict(kind=self.kind, fictional=False, context=context, models=models, weeks=weeks, radio_ids=None)

    def _load_week(self, entry, status):
        doc = self._get('/comparison', year=entry['target_year'], week=entry['target_epi_week'], disclosure='private')
        _check(doc['target_week'] == entry['target_week'] and doc['dataset_version'] == status['context']['dataset_version'])
        rows = {}
        for row in doc['rows']:
            if not row['common_mask']:
                continue
            values = {'observed': row['observed']['quantity'],
                      REFERENCE_QUANTITY: dict(rank=None, quantity=row['predicted']['quantity'])}
            for model in status['models']:
                if model['reference']:
                    continue
                ml = row.get('ml', {}).get(model['id'], {})
                ok = row.get('ml_availability', {}).get(model['id']) == 'available'
                values[model['id']] = dict(rank=ml.get('topk_rank') if ok else None, quantity=ml.get('quantity') if ok else None)
            rows[row['radio_id']] = values
        _check(len(rows) > 0)
        if status['radio_ids'] is None:
            status['radio_ids'] = sorted(rows)
        return rows


class FictionalSource(_Store):
    """Generated fixture: 12 fictitious radios FX0000001.., 30 synthetic weeks, top-3."""

    kind = 'generated_fictional_fixture'
    RADIOS = tuple(f'FX{i:07d}' for i in range(1, 13))
    START = date(2021, 1, 3)
    WEEKS = 30
    ML_GAP = 12  # week index without ML predictions (only the reference)

    def _load_status(self):
        models = [dict(id='rf_v2_city_propensity', capability='presence', rule=dict(type='top_k', k=3),
                       state='experimental_not_promoted', reference=False, default=True),
                  dict(id='residual_v2', capability='quantity', rule=dict(type='count_estimate'),
                       state='experimental_not_promoted', reference=False, default=True),
                  dict(id=REFERENCE_QUANTITY, capability='quantity', rule=dict(type='count_estimate'),
                       state='selected_statistical_reference', reference=True, default=False)]
        weeks = [dict(target_week=(self.START + timedelta(weeks=i)).isoformat(), target_year=2021, target_epi_week=i + 1,
                      models=[m['id'] for m in models if m['reference'] or i != self.ML_GAP]) for i in range(self.WEEKS)]
        return dict(kind=self.kind, fictional=True, models=models, weeks=weeks, radio_ids=list(self.RADIOS),
                    context=dict(dataset_version='FICTIONAL-alerts-fixture-v1', module_version='FICTIONAL'))

    def observed(self, i, radio):
        if i < 0:
            return None
        if radio == 'FX0000001':
            return 2 if i % 2 == 0 else 7  # small cells alternate with disclosable ones
        return random.Random(f'{i}:{radio}').randint(0, 4) if radio != 'FX0000003' else 6

    def _load_week(self, entry, status):
        i = entry['target_epi_week'] - 1
        order = list(self.RADIOS[3:])
        random.Random(20261114 + i).shuffle(order)
        # FX0000001 always first; FX0000003 enters the top-3 only on weeks 5..8.
        inside = 5 <= i <= 8
        ranking = ['FX0000001', 'FX0000002', *(['FX0000003'] if inside else []), *order,
                   *([] if inside else ['FX0000003'])]
        rows = {}
        for radio in self.RADIOS:
            if radio == 'FX0000001':
                quantity = 8.0 + i % 3
            elif radio == 'FX0000002':
                quantity = 6.0 if i % 2 == 0 else 1.0
            else:
                quantity = round(random.Random(f'q{i}:{radio}').uniform(0, 4.5), 2)
            gap = i == self.ML_GAP
            rows[radio] = {'observed': self.observed(i, radio),
                           REFERENCE_QUANTITY: dict(rank=None, quantity=self.observed(i - 1, radio)),
                           'rf_v2_city_propensity': dict(rank=None if gap else ranking.index(radio) + 1, quantity=None),
                           'residual_v2': dict(rank=None, quantity=None if gap else quantity)}
        return rows
