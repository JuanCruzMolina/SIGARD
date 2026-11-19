"""Final h=1 service: frozen results, request-scoped integrity and disclosure."""
from datetime import date, timedelta
import json

from .backtest_results import BacktestResults, CONTEXT, METHODS, WEEK, metrics
from .experimental_results import ArtifactBlocked, InvalidDate, local_bytes, require
from .predictive_ml import MLProjection, CANDIDATES, attach_ml, ml_metrics

MODULE = 'sigard-predictive-experimental/1'
DISCLOSURE = 'sigard-local-presentation-minimum5-v1'
MINIMUM = 5
LIMITATIONS = [
    'experimental_ml_not_operationally_approved', 'event_time_not_arrival_time_reconstruction',
    'project_owner_declared_coverage_not_institutionally_certified', 'approximate_territorial_assignments',
    'uncalibrated_scores_not_health_risk', '2024_previously_examined_not_external_validation',
    'climate_single_reference_point', 'not_for_operational_use_no_official_alerts',
]
LIFECYCLE = [
    {'component': 'presence_seasonal', 'state': 'reference_selected', 'capability': 'presence', 'horizon_weeks': 1},
    {'component': 'count_latest', 'state': 'reference_selected', 'capability': 'quantity', 'horizon_weeks': 1},
    {'component': 'A_original_and_B', 'state': 'archived', 'reason': 'frozen_earlier_policy'},
    {'component': 'Poisson_V1_V2_core', 'state': 'archived', 'reason': 'not_promoted'},
    {'component': 'V3_h2_h4_and_discarded_variants', 'state': 'archived', 'reason': 'outside_final_h1_scope'},
    {'component': 'rf_A_epi_climate', 'state': 'experimental_evaluated', 'reason': 'not_promoted'},
    {'component': 'residual_h1', 'state': 'experimental_evaluated', 'reason': 'not_promoted'},
    {'component': 'stage2_RF_A_reference_no_climate', 'state': 'archived', 'reason': 'comparison_evidence'},
    {'component': 'current_2025_2026_and_official_alerts', 'state': 'blocked', 'reason': 'no_accredited_epidemiological_coverage_or_operational_authorization'},
]


class SnapshotReader(BacktestResults):
    """Check registry/manifest/catalog once per request; every week still hashes bytes.

    No cache survives the request. An altered file or pointer blocks the next read.
    This avoids revalidating the same 366-week catalog for each history row.
    """
    def _bundle(self):
        if not hasattr(self, '_manifest_snapshot'):
            self._manifest_snapshot = super()._bundle()
        return self._manifest_snapshot

    def catalog(self):
        if not hasattr(self, '_catalog_snapshot'):
            self._catalog_snapshot = super().catalog()
        return self._catalog_snapshot


def protect_week(document, mode):
    result = dict(document)
    result['disclosure'] = {'policy_version': DISCLOSURE, 'mode': mode, 'minimum_count': MINIMUM,
                            'metrics_scope': 'all_comparable' if mode == 'private' else 'disclosable_subset_not_full_study'}
    if mode == 'private':
        result['ml_metrics'] = ml_metrics(result['rows'])
        return result
    # Copy only the aggregate contract objects we change. No model or source object
    # is deserialized; avoiding recursive copies matters for the full calendar.
    result['rows'] = [{**row, 'predicted': dict(row['predicted']), 'baseline': dict(row['baseline']),
                      'observed': {**row['observed'], 'quality_counts': dict(row['observed']['quality_counts'])}}
                     for row in document['rows']]
    for row in result['rows']:
        # Includes zero: masking only 1..4 would reveal the presence of small cells.
        # Protect persistence too: it exposes an observed count at the previous origin.
        values = (row['observed']['quantity'], row['observed']['assigned_records'],
                  row['predicted']['quantity'], row['baseline']['quantity'], row.get('ml', {}).get('quantity'))
        mask = any(value is not None and 0 <= value < MINIMUM for value in values)
        if mask:
            if row['availability_status'] not in ('outside_common_territory', 'outside_coverage'):
                row['availability_status'] = 'privacy_suppressed'
                row['unavailable_reason'] = 'protected_cell_no_presence_or_small_count_disclosure'
            row['territorial_quality'] = 'withheld'; row['coverage_status'] = 'withheld'; row['zero_provenance'] = None
            row['predicted'] = {k: None for k in row['predicted']}
            row['baseline'] = {'quantity': None}
            row['observed'] = {'quantity': None, 'presence': None, 'assigned_records': None,
                               'quality_counts': {k: None for k in ('approximate', 'provisional', 'verified')}}
            for key in ('confusion', 'presence_threshold', 'difference', 'absolute_error'): row[key] = None
            if 'ml' in row:
                row['ml'] = {k: None for k in row['ml']}
                row['ml_availability'] = {k: 'privacy_suppressed' for k in row['ml_availability']}
        else:
            # Quality sub-counts could themselves disclose small cells.
            row['observed']['assigned_records'] = None
            row['observed']['quality_counts'] = {k: None for k in ('approximate', 'provisional', 'verified')}
            row['territorial_quality'] = 'withheld'; row['coverage_status'] = 'withheld'; row['zero_provenance'] = None
    # Exact complementary totals and metrics would allow subtraction attacks.
    result['department'] = {key: None for key in result['department']}
    result['metrics'] = metrics(result['rows'])
    result['ml_metrics'] = ml_metrics(result['rows'])
    result['disclosure']['suppressed_units'] = sum(r['availability_status'] == 'privacy_suppressed' for r in result['rows'])
    return result


class PredictiveService:
    def __init__(self, reader, *, context_registry=None, context_sha256=None, ml_registry=None, ml_sha256=None):
        self.reader = reader
        self.context_registry = context_registry; self.context_sha256 = context_sha256
        self.ml_registry = ml_registry; self.ml_sha256 = ml_sha256

    def _ml(self):
        return MLProjection(self.reader.root, self.ml_registry, self.ml_sha256) if self.ml_registry else None

    @staticmethod
    def _attach(base, ml):
        try:
            return attach_ml(base, ml)
        except (ArtifactBlocked, KeyError, ValueError, TypeError, OSError):
            result = attach_ml(base, None)
            for model in result['ml'].values():
                model['reason'] = 'ml_integrity_or_compatibility_blocked'
            return result

    def _snapshot(self):
        if self.reader is None: raise ArtifactBlocked('predictive_bundle_unavailable')
        return SnapshotReader(self.reader.registry_path, self.reader.registry_sha256, root=self.reader.root)

    @staticmethod
    def mode(mode):
        if mode not in ('presentation', 'private'): raise InvalidDate('invalid_disclosure_mode')
        return mode

    def catalog(self):
        catalog = dict(self._snapshot().catalog()); ml = self._ml()
        if ml: ml.compatible(catalog)
        catalog['weeks'] = [{**w, 'ml_availability': ml.availability(w['target_week']) if ml else
                            {c: 'not_available' for c in CANDIDATES}} for w in catalog['weeks']]
        return {**catalog, 'module_version': MODULE, 'active_methods': METHODS, 'experimental_methods': CANDIDATES,
                'training_enabled': False, 'operational_enabled': False}

    def geometry(self): return self._snapshot().geometry()

    def metadata(self):
        return {**self._snapshot().metadata(), 'module_version': MODULE, 'result_type': 'historical_h1_statistical_reference',
                'limitations': LIMITATIONS, 'lifecycle': LIFECYCLE, 'training_enabled': False,
                'disclosure_policy': {'version': DISCLOSURE, 'default_mode': 'presentation', 'minimum_count': MINIMUM,
                                     'exact_values_scope': 'authorized_loopback_private_research_only'},
                'climate_usage': 'context_only_not_used_by_selected_methods',
                'experimental_methods': CANDIDATES,
                'ml_climate_usage': 'origin_and_prior_weeks_temperature_humidity_precipitation',
                'ml_climate_evidence': 'presence_brier_improved_vs_no_climate_not_vs_reference_in_development;quantity_increment_not_demonstrated'}

    def _climate(self, week):
        absent = {'availability_status': 'not_available', 'reason': 'verified_climate_context_not_installed',
                  'usage': 'context_only_not_used_by_selected_methods'}
        if self.context_registry is None: return absent
        registry = json.loads(local_bytes(self.reader.root, self.context_registry, self.context_sha256))
        require(registry['dataset_version'] == week['dataset_version'])
        value = json.loads(local_bytes(self.reader.root, registry['path'], registry['sha256']))
        require(value['dataset_version'] == week['dataset_version'] and value['usage'] == absent['usage'])
        context = value['weeks'].get(week['target_week'])
        if context is None: return absent
        require(context['origin_week'] == week['origin_week'] and context['origin_end'] == week['origin_end'])
        require(context['period_end'] is None or context['period_end'] <= week['origin_end'])
        # The compiler writes only these fields; no arbitrary source metadata is exposed.
        return {key: context[key] for key in ('availability_status', 'origin_week', 'origin_end', 'period_end',
            'temperature_mean', 'humidity_mean', 'precipitation_total', 'days', 'availability_basis', 'usage', 'spatial_support')}

    def week(self, year, week, radio=None, mode='presentation'):
        self.mode(mode)
        result = protect_week(self._attach(self._snapshot().week(year, week, radio), self._ml()), mode)
        return {**result, 'module_version': MODULE, 'result_type': 'historical_h1_statistical_reference',
                'limitations': LIMITATIONS, 'climate': self._climate(result)}

    def history(self, start, end, radio=None, mode='presentation'):
        self.mode(mode); reader = self._snapshot(); catalog = reader.catalog(); ml = self._ml()
        try: first, last = date.fromisoformat(start), date.fromisoformat(end)
        except (ValueError, TypeError): raise InvalidDate() from None
        keys = {w['target_week'] for w in catalog['weeks']}
        if start not in keys or end not in keys or first > last: raise InvalidDate()
        series = []; all_rows = []; years = {}
        for week in catalog['weeks']:
            if start <= week['target_week'] <= end:
                doc = protect_week(self._attach(reader.week(week['target_year'], week['target_epi_week'], radio), ml), mode)
                observed = [r['observed']['quantity'] for r in doc['rows'] if r['common_mask']]
                complete = bool(observed) and all(v is not None for v in observed)
                totals = doc['metrics']['totals']
                comparable = doc['metrics']['n_comparable'] > 0 and doc['availability_status'] == 'available'
                observed_total = sum(observed) if complete else totals['observed'] if mode == 'presentation' else None
                series.append({**{k: doc[k] for k in WEEK}, 'observed': observed_total,
                    'predicted': totals['predicted'] if comparable else None, 'baseline': totals['baseline'] if comparable else None,
                    'n_comparable': doc['metrics']['n_comparable'], 'metrics': doc['metrics'],
                    'ml_predicted': doc['ml_metrics']['totals']['predicted'], 'ml_metrics': doc['ml_metrics'], 'ml': doc['ml'],
                    'disclosure_status': 'complete' if complete else 'disclosable_subset' if comparable else 'protected_or_unavailable'})
                all_rows.extend(doc['rows']); years.setdefault(str(week['target_year']), []).extend(doc['rows'])
        if radio is not None and radio not in catalog['radio_ids']: raise InvalidDate()
        return {**{k: catalog[k] for k in CONTEXT}, 'module_version': MODULE, 'result_type': 'historical_h1_statistical_reference',
                'evaluation_type': 'event_time_retrospective_reconstruction', 'selected_radio': radio, 'start': start, 'end': end,
                'series': series, 'metrics': metrics(all_rows), 'ml_metrics': ml_metrics(all_rows),
                'by_year': {y: metrics(rows) for y, rows in years.items()},
                'ml_by_year': {y: ml_metrics(rows) for y, rows in years.items()},
                'disclosure': {'policy_version': DISCLOSURE, 'mode': mode, 'minimum_count': MINIMUM,
                               'metrics_scope': 'all_comparable' if mode == 'private' else 'disclosable_subset_not_full_study'},
                'limitations': LIMITATIONS}
