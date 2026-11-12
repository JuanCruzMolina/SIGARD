"""Immutable, offline access to two evaluated h=1 candidates. Never fits models.

The release references existing private artifacts/predictions instead of copying
grids or changing the frozen promotion decision. It is not installed in the API.
"""
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.motor_protocol import FEATURES
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR

VERSION = 'sigard-two-candidates-reused-h1-20261103-v1'
DATASET = 'sigard-consolidated-history-20261102-v1'
POLICY = 'sigard-project-positive-2022-covered-2020-2024-v1'
CAMPAIGN = 'sigard-predictive-motor-h1-20261102-v1'
CANDIDATES = {'presence': 'rf_A_epi_climate', 'quantity': 'residual_h1'}
REFERENCES = {'presence': 'presence_seasonal', 'quantity': 'count_latest'}
STATES = ('experimental_evaluated', 'reference_selected', 'blocked', 'operational_approved')


def require(condition, reason):
    if not condition:
        raise DatasetBlocked(reason)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and not Path(relative).is_absolute(), 'candidate_path_outside_root')
    return path


def verified_bytes(root, entry):
    path = checked_path(root, entry['path'])
    value = path.read_bytes()
    require(hashlib.sha256(value).hexdigest() == entry['sha256'], 'candidate_evidence_hash_mismatch')
    return value


def entry(root, path):
    return {'path': Path(path).resolve().relative_to(Path(root).resolve()).as_posix(), 'sha256': digest(path)}


def validate_predictions(frame, models, radios):
    """Check domain, complete common territory, joins and every temporal cutoff."""
    require(not frame.empty and not frame.duplicated(['radio_id', 'target_week']).any(), 'candidate_duplicate_or_empty_predictions')
    require(frame.target_count.notna().all(), 'candidate_unknown_target')
    columns = [*CANDIDATES.values(), *REFERENCES.values(), 'count_training_mean', 'target_count',
               CANDIDATES['presence'] + '_threshold', REFERENCES['presence'] + '_threshold']
    require(np.isfinite(frame[columns].to_numpy(float)).all(), 'candidate_nonfinite_prediction')
    require((frame[['residual_h1', 'count_latest', 'count_training_mean', 'target_count']] >= 0).all().all(), 'candidate_negative_count')
    require(frame.target_count.mod(1).eq(0).all(), 'candidate_noninteger_observation')
    for name in ('rf_A_epi_climate', 'presence_seasonal', 'rf_A_epi_climate_threshold', 'presence_seasonal_threshold'):
        require(frame[name].between(0, 1).all(), 'candidate_invalid_presence')
    index = {(m['block'], m['method']): m for m in models}
    require(len(index) == len(models), 'candidate_duplicate_model')
    require(set(m['method'] for m in models) == set(CANDIDATES.values()), 'candidate_family_not_allowed')
    for target, group in frame.groupby('target_week'):
        year, _ = DEFAULT_CALENDAR.date_week(target)
        require(target.weekday() == 6 and 2021 <= year <= 2024, 'candidate_target_outside_evaluation')
        require(set(group.radio_id) == set(radios), 'candidate_incompatible_territory')
        require(group.origin_week.eq(target - timedelta(days=7)).all(), 'candidate_horizon_not_one')
        require(group.block.nunique() == 1, 'candidate_mixed_temporal_blocks')
        block = group.block.iloc[0]
        for method in CANDIDATES.values():
            require((block, method) in index, 'candidate_model_not_available')
            model = index[block, method]
            require(model['state'] == 'experimental_evaluated', 'candidate_state_not_evaluated')
            require(model['features'] == list(FEATURES[method]), 'candidate_feature_contract_changed')
            fit_end = date.fromisoformat(model['fit_last_target_end'])
            require(fit_end < target - timedelta(days=35), 'candidate_temporal_leakage')
            if method == CANDIDATES['presence']:
                require(group[method + '_threshold'].eq(model['threshold']).all(), 'candidate_threshold_changed')


def write_release(root, campaign_dir, audit_dir, destination):
    """Add a small pinned manifest, keeping all source artifacts untouched."""
    root, campaign_dir, audit_dir = map(Path, (root, campaign_dir, audit_dir))
    destination = Path(destination)
    require(destination.resolve().is_relative_to(root.resolve() / 'data/interim/official'), 'candidate_private_destination_required')
    require(not destination.exists(), 'candidate_release_refuses_overwrite')
    audit = json.loads((audit_dir / 'verification.private.json').read_text(encoding='utf-8'))
    require(audit['status'] == 'passed' and audit['dataset_version'] == DATASET and audit['policy'] == POLICY,
            'candidate_audit_incompatible')
    recorded = json.loads((audit_dir / 'inputs-before.private.json').read_text(encoding='utf-8'))
    sources = {}
    for name in ('protocol-before-fit.private.json', 'fold-registry.private.json', 'all-predictions.private.parquet',
                 'development-metrics.private.json', 'comparison-metrics.private.json',
                 'development-granular.private.json', 'comparison-granular.private.json', 'decision-before-2024.private.json'):
        ref = entry(root, campaign_dir / name)
        require(recorded.get(ref['path']) == ref['sha256'], 'candidate_changed_since_audit')
        sources[name] = ref
    frozen = json.loads(verified_bytes(root, sources['protocol-before-fit.private.json']))
    require(frozen['input']['dataset_version'] == DATASET and frozen['input']['matrix_sha256'] == audit['matrix_sha256'],
            'candidate_dataset_changed')
    for path, sha in frozen['code_sha256'].items():
        verified_bytes(root, {'path': path, 'sha256': sha})
    folds = json.loads(verified_bytes(root, sources['fold-registry.private.json']))
    models = []
    for fold in folds:
        for model in fold['methods']:
            if model['method'] not in CANDIDATES.values():
                continue
            ref = entry(root, campaign_dir / f"{fold['block']}-{model['method']}.private.joblib")
            require(ref['sha256'] == model['artifact_sha256'] == recorded.get(ref['path']), 'candidate_artifact_changed')
            models.append(dict(block=fold['block'], method=model['method'], artifact=ref,
                model_version=f"{CAMPAIGN}-{fold['block']}-{model['method']}",
                state='experimental_evaluated', fit_last_target_end=model['fit_last_target_end'],
                features=model['metadata']['features'], calibrated=model['metadata'].get('calibrated', False),
                threshold=model['metadata'].get('threshold'), metadata=model['metadata']))
    frame = pd.read_parquet(io.BytesIO(verified_bytes(root, sources['all-predictions.private.parquet'])))
    radios = sorted(int(v) for v in frame.radio_id.unique())
    require(len(models) == 32 and len(radios) == 256 and len(frame) == 53248 and frame.target_week.nunique() == 208,
            'candidate_incomplete_frozen_campaign')
    validate_predictions(frame, models, radios)
    result = dict(version=VERSION, campaign_version=CAMPAIGN, dataset_version=DATASET, data_policy_version=POLICY,
        horizon_weeks=1, input_sha256=frozen['input']['stage1_sha256'], matrix_sha256=audit['matrix_sha256'],
        protocol_sha256=frozen['protocol_sha256'], code_sha256=frozen['code_sha256'],
        training_performed=False, operational_enabled=False, candidates=CANDIDATES, models=models,
        references={name: {'method': method, 'state': 'reference_selected'} for name, method in REFERENCES.items()},
        additional_reference={'method': 'count_training_mean', 'role': 'comparison_only'},
        sources=sources, audit=entry(root, audit_dir / 'verification.private.json'), radio_ids=radios,
        prediction_rows=len(frame), target_weeks=sorted(str(v) for v in frame.target_week.unique()),
        evaluation_type='event_time_retrospective_reconstruction', promotion_approved=False,
        limitations=['uncalibrated_presence_score', 'event_dates_not_historical_arrival',
                    'declared_coverage_zeros', 'approximate_geography', '2024_not_independent',
                    'population_and_density_unavailable', 'count_climate_increment_not_demonstrated'])
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return entry(root, destination)


class CandidateRelease:
    """Explicit private offline reader; never deserializes models or trains."""
    def __init__(self, root, manifest, sha256):
        self.root = Path(root)
        self.pin = {'path': manifest, 'sha256': sha256}

    def _read(self):
        doc = json.loads(verified_bytes(self.root, self.pin))
        require(doc['version'] == VERSION and doc['dataset_version'] == DATASET and doc['data_policy_version'] == POLICY,
                'candidate_release_incompatible')
        require(doc['candidates'] == CANDIDATES and doc['horizon_weeks'] == 1 and not doc['operational_enabled']
                and doc['promotion_approved'] is False, 'candidate_unauthorized_promotion')
        for ref in [doc['audit'], *doc['sources'].values(), *(m['artifact'] for m in doc['models'])]:
            verified_bytes(self.root, ref)
        for path, sha in doc['code_sha256'].items():
            verified_bytes(self.root, {'path': path, 'sha256': sha})
        return doc

    def week(self, target_week, capability):
        require(capability in CANDIDATES, 'candidate_unknown_capability')
        target = date.fromisoformat(target_week)
        require(target.weekday() == 6, 'candidate_expected_epi_week_start')
        doc = self._read()
        year, number = DEFAULT_CALENDAR.date_week(target)
        method = CANDIDATES[capability]
        result = dict(release_version=VERSION, dataset_version=DATASET, data_policy_version=POLICY,
            campaign_version=CAMPAIGN, target_week=target_week, target_year=year, target_epi_week=number,
            horizon_weeks=1, territorial_scope='stage1_common_mask_256',
            origin_week=str(target - timedelta(days=7)), capability=capability, method=method,
            evaluation_type=doc['evaluation_type'], operational_enabled=False, limitations=doc['limitations'])
        if target_week not in doc['target_weeks']:
            return dict(result, state='blocked', availability_status='not_available', rows=[],
                        reason='outside_coverage' if year not in range(2020, 2025) else
                        'insufficient_training_support' if year == 2020 else 'saved_prediction_not_available')
        frame = pd.read_parquet(io.BytesIO(verified_bytes(self.root, doc['sources']['all-predictions.private.parquet'])))
        group = frame.loc[frame.target_week.eq(target)]
        validate_predictions(group, doc['models'], doc['radio_ids'])
        block = group.block.iloc[0]
        model = next(m for m in doc['models'] if m['block'] == block and m['method'] == method)
        rows = []
        reference = REFERENCES[capability]
        for row in group.sort_values('radio_id').to_dict('records'):
            if capability == 'presence':
                values = dict(predicted_score=row[method], predicted_presence=int(row[method] >= row[method + '_threshold']),
                    threshold=row[method + '_threshold'], observed=int(row['target_count'] > 0),
                    baseline_score=row[reference], baseline_presence=int(row[reference] >= row[reference + '_threshold']))
            else:
                values = dict(predicted=row[method], observed=row['target_count'], baseline=row[reference],
                              historical_mean=row['count_training_mean'])
            rows.append(dict(radio_id=int(row['radio_id']), **values))
        return dict(result, state='experimental_evaluated', availability_status='available', reason=None,
            model_version=model['model_version'], artifact_sha256=model['artifact']['sha256'],
            fit_last_target_end=model['fit_last_target_end'], calibrated=model['calibrated'],
            reference_method=reference, reference_state='reference_selected', rows=rows,
            privacy_scope='authorized_local_private_research_not_public_or_http')
