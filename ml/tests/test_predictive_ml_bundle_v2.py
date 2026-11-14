"""Fictitious v2 bundle contracts: no fits, estimators, database or private files."""
import hashlib
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting import predictive_ml_bundle_v2 as bundle
from sigard_ml.forecasting.motor_features_v2 import topk_select
from sigard_ml.forecasting.motor_protocol_v2 import COUNT, PRINCIPAL, PROTOCOL, SECONDARY

RADIOS = [f'9990{n:05d}' for n in range(12)]
BLOCKS = {'2021-q1': date(2021, 1, 3), '2024-q1': date(2024, 1, 7)}
WEEKS_PER_BLOCK = 4


def fictitious_frame(seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for block, first in BLOCKS.items():
        for w in range(WEEKS_PER_BLOCK):
            target = first + timedelta(days=7 * w)
            for i, radio in enumerate(RADIOS):
                count = float(rng.integers(0, 3) if i % 3 == 0 else 0)
                origin = float(rng.integers(0, 2))
                rows.append(dict(radio_id=i + 1, radio_codigo=radio, origin_week=target - timedelta(days=7),
                    target_week=target, target_end=target + timedelta(days=6), target_year=target.year, target_number=w + 1,
                    target_count=count, count_origin=origin, count_latest=origin,
                    # Deliberate ties: several radios share the same score.
                    **{PRINCIPAL: float(round(rng.random(), 1)), SECONDARY: float(rng.random()), COUNT: float(rng.random() * 2)},
                    block=block))
    return pd.DataFrame(rows)


def frozen_metrics(frame):
    k = bundle.TOPK['k']
    selected = topk_select(frame, frame[PRINCIPAL].to_numpy(float), k)
    positive = frame.target_count.gt(0).to_numpy(); onset = positive & frame.count_origin.eq(0).to_numpy()

    def summary(mask):
        return dict(positives=int(positive[mask].sum()), detected=float((selected & positive)[mask].sum()),
                    onset_detected=float((selected & onset)[mask].sum()))

    result = {'protocol_sha256': bundle.PROTOCOL_SHA256}
    for scope, years in (('development', PROTOCOL['development_target_years']), ('comparison_2024', PROTOCOL['comparison_target_years'])):
        mask = frame.target_year.isin(years).to_numpy()
        result[scope] = {'presence': {str(k): {PRINCIPAL: {'overall': summary(mask),
            'by_year': {str(y): summary(frame.target_year.eq(y).to_numpy()) for y in years}}}}}
    dev = frame.target_year.isin(PROTOCOL['development_target_years'])
    result['development']['counts'] = {COUNT: {'mae': float((frame.loc[dev, COUNT] - frame.loc[dev, 'target_count']).abs().mean())}}
    return result


class FictitiousReference:
    def __init__(self, frame):
        self.frame = frame

    def catalog(self):
        weeks = sorted(set(self.frame.target_week))
        return dict(dataset_version='FICTIONAL-dataset', campaign_version='FICTIONAL-campaign',
                    data_policy_version='FICTIONAL-policy', territory_version='FICTIONAL-territory',
                    weeks=[dict(target_week=str(w), target_year=w.year, target_epi_week=i + 1) for i, w in enumerate(weeks)])

    def geometry(self):
        return {'features': [{'properties': {'radio_id': r, 'common_mask': True}} for r in RADIOS]
                + [{'properties': {'radio_id': '999099999', 'common_mask': False}}]}

    def week(self, year, epi_week):
        target = next(w for w in self.catalog()['weeks'] if w['target_epi_week'] == epi_week)['target_week']
        group = self.frame[self.frame.target_week.astype(str) == target]
        return dict(origin_week=str(date.fromisoformat(target) - timedelta(days=7)), rows=[
            dict(radio_id=r.radio_codigo, observed={'quantity': r.target_count}, baseline={'quantity': r.count_latest})
            for r in group.itertuples()])


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, 'EXPECTED', dict(rows=len(BLOCKS) * WEEKS_PER_BLOCK * len(RADIOS),
        weeks=len(BLOCKS) * WEEKS_PER_BLOCK, radios=len(RADIOS), artifacts=len(BLOCKS) * 3, blocks=len(BLOCKS)))
    root = tmp_path
    folder = root / 'data/interim/official/FICTIONAL-corrective-v2'
    folder.mkdir(parents=True)
    frame = fictitious_frame()
    frame.to_parquet(folder / 'all-predictions.private.parquet', index=False)
    artifacts = []
    for block, first in BLOCKS.items():
        for method in (PRINCIPAL, SECONDARY, COUNT):
            name = f'{block}-{method}.private.joblib'
            (folder / name).write_bytes(f'FICTIONAL artifact {block} {method}'.encode())
            artifacts.append(dict(block=block, method=method, artifact=name,
                sha256=hashlib.sha256((folder / name).read_bytes()).hexdigest(),
                training_last_target_end=str(first - timedelta(days=7 + 29)), first_origin=str(first - timedelta(days=7))))
    write = lambda name, value: (folder / name).write_text(json.dumps(value, default=str), encoding='utf-8')
    write('artifact-registry.private.json', dict(fits=len(artifacts), artifacts=artifacts,
        predictions_sha256=hashlib.sha256((folder / 'all-predictions.private.parquet').read_bytes()).hexdigest()))
    write('protocol-before-fit.private.json', dict(protocol=PROTOCOL, protocol_sha256=bundle.PROTOCOL_SHA256,
        input=dict(dataset_version='FICTIONAL-dataset')))
    pins = dict(protocol_sha256=bundle.PROTOCOL_SHA256, v2_matrix_sha256=bundle.MATRIX_SHA256)
    write('matrix-before-fit.private.json', pins)
    write('campaign-manifest-before-fit.private.json', pins)
    write('metrics.private.json', frozen_metrics(frame))
    return root, folder, frame


def compile_into(campaign, name='bundle'):
    root, folder, frame = campaign
    destination = root / 'data/interim/official/FICTIONAL-integration' / name
    result = bundle.compile_bundle(root, folder, FictitiousReference(frame), destination)
    return root, destination, result


def test_bundle_pins_hashes_candidates_and_resolved_topk(campaign):
    root, destination, pin = compile_into(campaign)
    manifest = json.loads((root / pin['path']).read_text(encoding='utf-8'))
    assert hashlib.sha256((root / pin['path']).read_bytes()).hexdigest() == pin['sha256']
    assert manifest['schema_version'] == 'sigard-predictive-ml-overlay/2'
    assert manifest['protocol_sha256'].startswith('a7dc47f9') and manifest['v2_matrix_sha256'].startswith('2c09895c')
    assert manifest['training_performed'] is False and manifest['inference_performed'] is False
    assert manifest['operational_enabled'] is False and manifest['artifacts_verified'] == 6
    assert [(c['id'], c['capability'], c['decision_rule']['type'], c['state']) for c in manifest['candidates']] == [
        (PRINCIPAL, 'presence', 'top_k', 'experimental_not_promoted'), (COUNT, 'quantity', 'count_estimate', 'experimental_not_promoted')]
    assert manifest['candidates'][0]['decision_rule']['k'] == 10
    assert manifest['candidates'][0]['promotion']['decision'] == 'not_promoted'
    assert set(manifest['evidence']) == set(bundle.EVIDENCE)
    for target, entry in manifest['weeks'].items():
        week = json.loads((root / entry['path']).read_text(encoding='utf-8'))
        ranks = sorted(r['topk_rank'] for r in week['rows'])
        assert ranks == list(range(1, len(RADIOS) + 1)) and len(week['rows']) == len(RADIOS)
        assert set(week['models']) == {PRINCIPAL, COUNT} and all(m['calibrated'] is False for m in week['models'].values())
        scores = {r['radio_id']: r['presence_score'] for r in week['rows']}
        top = [r for r in week['rows'] if r['topk_rank'] <= 10]
        assert min(scores[r['radio_id']] for r in top) >= max(r['presence_score'] for r in week['rows'] if r['topk_rank'] > 10)


def test_topk_ranks_match_prespecified_selection_and_are_order_independent():
    frame = fictitious_frame(3)
    ranks = bundle.topk_ranks(frame, frame[PRINCIPAL].to_numpy(float))
    assert np.array_equal(ranks <= 10, topk_select(frame, frame[PRINCIPAL].to_numpy(float), 10))
    shuffled = frame.sample(frac=1, random_state=1)
    again = pd.Series(bundle.topk_ranks(shuffled, shuffled[PRINCIPAL].to_numpy(float)), index=shuffled.index).sort_index()
    assert np.array_equal(again.to_numpy(), ranks)


@pytest.mark.parametrize('target,reason', [
    ('2021-q1-rf_v2_city_propensity.private.joblib', 'v2_artifact_hash_mismatch'),
    ('2024-q1-logit_v2_factors.private.joblib', 'v2_artifact_hash_mismatch'),
    ('all-predictions.private.parquet', 'v2_predictions_hash_mismatch'),
])
def test_altered_artifact_or_predictions_block_compilation(campaign, target, reason):
    root, folder, _ = campaign
    path = folder / target
    path.write_bytes(path.read_bytes() + b'FICTIONAL tamper')
    with pytest.raises(DatasetBlocked, match=reason):
        compile_into(campaign)
    assert not (root / 'data/interim/official/FICTIONAL-integration/bundle').exists()


@pytest.mark.parametrize('name,field,value,reason', [
    ('protocol-before-fit.private.json', 'protocol_sha256', '0' * 64, 'v2_frozen_protocol_mismatch'),
    ('matrix-before-fit.private.json', 'v2_matrix_sha256', '0' * 64, 'v2_matrix_hash_mismatch'),
])
def test_changed_protocol_or_matrix_pin_blocks(campaign, name, field, value, reason):
    _, folder, _ = campaign
    data = json.loads((folder / name).read_text(encoding='utf-8')); data[field] = value
    (folder / name).write_text(json.dumps(data, default=str), encoding='utf-8')
    with pytest.raises(DatasetBlocked, match=reason):
        compile_into(campaign)


def test_topk_that_does_not_reproduce_frozen_metrics_blocks(campaign):
    _, folder, _ = campaign
    data = json.loads((folder / 'metrics.private.json').read_text(encoding='utf-8'))
    data['development']['presence']['10'][PRINCIPAL]['overall']['detected'] += 1
    (folder / 'metrics.private.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(DatasetBlocked, match='v2_topk_does_not_reproduce_frozen_metrics'):
        compile_into(campaign)


def test_temporal_leakage_and_overwrite_are_refused(campaign):
    root, folder, _ = campaign
    compile_into(campaign, 'first')
    with pytest.raises(DatasetBlocked, match='v2_bundle_requires_new_private_destination'):
        compile_into(campaign, 'first')
    registry = json.loads((folder / 'artifact-registry.private.json').read_text(encoding='utf-8'))
    registry['artifacts'][0]['training_last_target_end'] = registry['artifacts'][0]['first_origin']
    (folder / 'artifact-registry.private.json').write_text(json.dumps(registry), encoding='utf-8')
    with pytest.raises(DatasetBlocked, match='v2_temporal_leakage'):
        compile_into(campaign, 'second')


def test_destination_outside_private_root_is_refused(campaign, tmp_path):
    root, folder, frame = campaign
    with pytest.raises(DatasetBlocked):
        bundle.compile_bundle(root, folder, FictitiousReference(frame), tmp_path / 'public-output')
