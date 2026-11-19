"""Project the saved corrective v2 predictions into hash-pinned JSON for the local API.

No fitting, estimator deserialization, inference, SQL or source-data changes. Every
input is hashed before use: frozen protocol (canonical hash), pinned v2 matrix, the
48 artifacts of the artifact registry and the saved predictions. The prespecified
top-k rule (k=10, seeded per-week tie-break) is resolved offline and stored per row.
Outputs are create-only below data/interim/official. The scientific decision is not
changed: both candidates stay ``experimental_not_promoted``.
"""
import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_features_v2 import topk_select
from sigard_ml.forecasting.motor_protocol_v2 import COUNT, FEATURES, PRINCIPAL, PROTOCOL, SECONDARY, TOPK

SCHEMA = 'sigard-predictive-ml-overlay/2'
CAMPAIGN = PROTOCOL['version']
PROTOCOL_SHA256 = 'a7dc47f971db7a8c01418209f7443cefb64de919b6834f8f61f5c4fbbc276cd1'
MATRIX_SHA256 = '2c09895cacd59a77f2af7f3ffd2890d2a858e4ec32899db635a6e15034edf677'
STATE = 'experimental_not_promoted'
EXPECTED = dict(rows=53248, weeks=208, radios=256, artifacts=48, blocks=16)
EVIDENCE = ('protocol-before-fit.private.json', 'matrix-before-fit.private.json',
            'campaign-manifest-before-fit.private.json', 'artifact-registry.private.json',
            'all-predictions.private.parquet', 'metrics.private.json')
CANDIDATES = [
    dict(id=PRINCIPAL, capability='presence', score_column=PRINCIPAL,
         decision_rule=dict(type='top_k', k=TOPK['k'], scope='per_target_week_common_territory',
                            tie_break=TOPK['tie_break'], tie_seed=TOPK['tie_seed']),
         promotion=dict(decision='not_promoted', criteria={'P1': False, 'P2': False, 'P3': False})),
    dict(id=COUNT, capability='quantity', score_column=COUNT,
         decision_rule=dict(type='count_estimate'),
         promotion=dict(decision='not_promoted', criteria={'Q1': True, 'Q2': False})),
]


def require(condition, reason):
    if not condition:
        raise DatasetBlocked(reason)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def checked(root, path):
    path = Path(path).resolve()
    require(path.is_relative_to(Path(root).resolve() / 'data/interim/official'), 'v2_bundle_path_outside_private_root')
    return path


def entry(root, path):
    path = checked(root, path)
    return {'path': path.relative_to(Path(root).resolve()).as_posix(), 'sha256': digest_bytes(path.read_bytes())}


def topk_ranks(frame, score, seed=None):
    """1-based rank per target week with the same order as topk_select (prespecified tie-break)."""
    seed = TOPK['tie_seed'] if seed is None else seed
    score = np.asarray(score, float)
    require(len(score) == len(frame) and np.isfinite(score).all(), 'v2_topk_needs_finite_scores')
    ranks = np.zeros(len(frame), dtype=int)
    positions = pd.Series(np.arange(len(frame)), index=frame.index)
    for week, group in frame.groupby('target_week', sort=True):
        rows = positions[group.sort_values('radio_id', kind='stable').index].to_numpy()
        tie = np.random.default_rng([seed, week.toordinal()]).permutation(len(rows))
        order = np.lexsort((tie, -score[rows]))
        ranks[rows[order]] = np.arange(1, len(rows) + 1)
    return ranks


def verify_campaign(root, folder):
    """Hash-check frozen protocol, matrix, artifact registry and predictions. Returns verified inputs."""
    root, folder = Path(root).resolve(), checked(root, folder)
    evidence = {name: entry(root, folder / name) for name in EVIDENCE}
    read = lambda name: (folder / name).read_bytes()
    require(canonical_hash(PROTOCOL) == PROTOCOL_SHA256, 'v2_protocol_code_changed')
    frozen = json.loads(read('protocol-before-fit.private.json'))
    require(frozen['protocol_sha256'] == PROTOCOL_SHA256 and frozen['protocol'] == json.loads(json.dumps(PROTOCOL, default=str)),
            'v2_frozen_protocol_mismatch')
    matrix = json.loads(read('matrix-before-fit.private.json'))
    manifest = json.loads(read('campaign-manifest-before-fit.private.json'))
    require(matrix['protocol_sha256'] == PROTOCOL_SHA256 and matrix['v2_matrix_sha256'] == MATRIX_SHA256
            and manifest['v2_matrix_sha256'] == MATRIX_SHA256 and manifest['protocol_sha256'] == PROTOCOL_SHA256,
            'v2_matrix_hash_mismatch')
    registry = json.loads(read('artifact-registry.private.json'))
    predictions = read('all-predictions.private.parquet')
    require(registry['predictions_sha256'] == digest_bytes(predictions), 'v2_predictions_hash_mismatch')
    artifacts = registry['artifacts']
    require(registry['fits'] == len(artifacts) == EXPECTED['artifacts'], 'v2_artifact_count_mismatch')
    index = {}
    for item in artifacts:
        path = checked(root, folder / item['artifact'])
        require(path.parent == folder and item['artifact'] == f"{item['block']}-{item['method']}.private.joblib",
                'v2_artifact_name_mismatch')
        # Hash only: estimators are never deserialized.
        require(digest_bytes(path.read_bytes()) == item['sha256'], 'v2_artifact_hash_mismatch')
        require((item['block'], item['method']) not in index, 'v2_duplicate_artifact')
        index[item['block'], item['method']] = item
    require({m for _, m in index} == {PRINCIPAL, SECONDARY, COUNT}
            and len({b for b, _ in index}) == EXPECTED['blocks'], 'v2_artifact_family_mismatch')
    frame = pd.read_parquet(io.BytesIO(predictions))
    metrics = json.loads(read('metrics.private.json'))
    require(metrics['protocol_sha256'] == PROTOCOL_SHA256, 'v2_metrics_protocol_mismatch')
    return dict(evidence=evidence, frame=frame, models=index, metrics=metrics, frozen=frozen)


def validate_frame(frame, models):
    require(len(frame) == EXPECTED['rows'] and frame.target_week.nunique() == EXPECTED['weeks']
            and frame.radio_codigo.nunique() == EXPECTED['radios'], 'v2_incomplete_predictions')
    require(not frame.duplicated(['radio_codigo', 'target_week']).any(), 'v2_duplicate_predictions')
    columns = [PRINCIPAL, COUNT, 'target_count', 'count_latest']
    require(np.isfinite(frame[columns].to_numpy(float)).all(), 'v2_nonfinite_prediction')
    require(frame[PRINCIPAL].between(0, 1).all() and (frame[[COUNT, 'count_latest', 'target_count']] >= 0).all().all(),
            'v2_invalid_prediction_domain')
    require(frame.target_count.mod(1).eq(0).all(), 'v2_noninteger_observation')
    radios = set(frame.radio_codigo)
    for target, group in frame.groupby('target_week'):
        require(set(group.radio_codigo) == radios and group.block.nunique() == 1, 'v2_incomplete_week')
        require(group.origin_week.eq(target - timedelta(days=7)).all(), 'v2_horizon_not_one')
        block = group.block.iloc[0]
        for method in (PRINCIPAL, COUNT):
            model = models.get((block, method))
            require(model is not None, 'v2_model_missing_for_week')
            # Same purge rule as the protocol: training target_end < first origin - 28 days.
            require(date.fromisoformat(model['training_last_target_end'])
                    < date.fromisoformat(model['first_origin']) - timedelta(days=28)
                    and date.fromisoformat(model['first_origin']) <= group.origin_week.iloc[0], 'v2_temporal_leakage')


def check_frozen_metrics(frame, metrics):
    """The offline top-10 must reproduce the frozen evaluation exactly (detected and onset counts)."""
    k = TOPK['k']
    selected = topk_select(frame, frame[PRINCIPAL].to_numpy(float), k)
    ranks = topk_ranks(frame, frame[PRINCIPAL].to_numpy(float))
    require(np.array_equal(selected, ranks <= k), 'v2_rank_selection_mismatch')
    positive = frame.target_count.gt(0).to_numpy()
    onset = positive & frame.count_origin.eq(0).to_numpy()
    for scope, years in (('development', PROTOCOL['development_target_years']), ('comparison_2024', PROTOCOL['comparison_target_years'])):
        frozen = metrics[scope]['presence'][str(k)][PRINCIPAL]
        for label, mask in [('overall', frame.target_year.isin(years).to_numpy())] + [
                (str(y), frame.target_year.eq(y).to_numpy()) for y in years]:
            expected = frozen['overall'] if label == 'overall' else frozen['by_year'][label]
            require(int(positive[mask].sum()) == expected['positives']
                    and float((selected & positive)[mask].sum()) == expected['detected']
                    and float((selected & onset)[mask].sum()) == expected['onset_detected'], 'v2_topk_does_not_reproduce_frozen_metrics')
    dev = frame.target_year.isin(PROTOCOL['development_target_years'])
    mae = float((frame.loc[dev, COUNT] - frame.loc[dev, 'target_count']).abs().mean())
    require(abs(mae - metrics['development']['counts'][COUNT]['mae']) < 1e-12, 'v2_count_does_not_reproduce_frozen_metrics')
    return ranks


def compile_bundle(root, campaign_folder, reference, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    require(checked(root, destination) and not destination.exists(), 'v2_bundle_requires_new_private_destination')
    verified = verify_campaign(root, campaign_folder)
    frame, models = verified['frame'], verified['models']
    validate_frame(frame, models)
    ranks = check_frozen_metrics(frame, verified['metrics'])
    frame = frame.assign(topk_rank=ranks)
    catalog = reference.catalog()
    common = {f['properties']['radio_id'] for f in reference.geometry()['features'] if f['properties']['common_mask']}
    require(set(frame.radio_codigo.astype(str)) == common, 'v2_territory_mismatch')
    require(verified['frozen']['input']['dataset_version'] == catalog['dataset_version'], 'v2_dataset_mismatch')
    folder = checked(root, campaign_folder)
    documents = {}
    for target, group in frame.groupby('target_week', sort=True):
        week = next(w for w in catalog['weeks'] if w['target_week'] == str(target))
        base = reference.week(week['target_year'], week['target_epi_week'])
        require(base['origin_week'] == str(target - timedelta(days=7)), 'v2_reference_origin_mismatch')
        baseline = {r['radio_id']: r for r in base['rows']}
        rows = []
        for r in group.sort_values('radio_codigo').to_dict('records'):
            b = baseline[str(r['radio_codigo'])]
            # Paired with the installed reference: same observation and persistence for each radio.
            require(r['target_count'] == b['observed']['quantity'] and r['count_latest'] == b['baseline']['quantity'],
                    'v2_unpaired_with_reference')
            origin = r['count_origin']
            rows.append(dict(radio_id=str(r['radio_codigo']), observed=r['target_count'], baseline=r['count_latest'],
                             onset_eligible=bool(origin == 0) if origin == origin else False,
                             presence_score=float(r[PRINCIPAL]), topk_rank=int(r['topk_rank']),
                             quantity=float(r[COUNT])))
        block = group.block.iloc[0]
        selected = {}
        for candidate in CANDIDATES:
            model = models[block, candidate['id']]
            artifact = entry(root, folder / model['artifact'])
            require(artifact['sha256'] == model['sha256'], 'v2_artifact_hash_mismatch')
            selected[candidate['id']] = dict(method=candidate['id'], capability=candidate['capability'], state=STATE,
                block=block, model_version=f"{CAMPAIGN}-{block}-{candidate['id']}",
                fit_last_target_end=model['training_last_target_end'], features=list(FEATURES[candidate['id']]),
                calibrated=False, artifact=artifact, artifact_sha256=artifact['sha256'])
        documents[str(target)] = dict(target_week=str(target), origin_week=base['origin_week'], models=selected, rows=rows)
    destination.mkdir(parents=True)

    def write(path, value):
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return entry(root, path)

    weeks = {target: write(destination / f'{target}.private.json', value) for target, value in documents.items()}
    manifest = {k: catalog[k] for k in ('dataset_version', 'campaign_version', 'data_policy_version', 'territory_version')}
    manifest.update(
        schema_version=SCHEMA, ml_campaign_version=CAMPAIGN, protocol_sha256=PROTOCOL_SHA256, v2_matrix_sha256=MATRIX_SHA256,
        evidence=verified['evidence'], artifacts_verified=EXPECTED['artifacts'],
        candidates=[{**{k: v for k, v in c.items() if k != 'score_column'}, 'state': STATE,
                     'features': list(FEATURES[c['id']]), 'calibrated': False} for c in CANDIDATES],
        horizon_weeks=1, operational_enabled=False, training_performed=False, inference_performed=False,
        radio_ids=sorted(common), weeks=weeks, prediction_rows=len(frame))
    return write(destination / 'manifest.private.json', manifest)
