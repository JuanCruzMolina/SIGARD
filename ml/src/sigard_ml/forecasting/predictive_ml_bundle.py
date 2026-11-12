"""Project frozen ML2 predictions into hash-pinned JSON for the local API.

No fitting, model deserialization, inference, SQL or source-data changes.
The caller supplies the existing reference reader; outputs are create-only.
"""
import io
import json
from pathlib import Path

import pandas as pd

from .candidate_release import CandidateRelease, CANDIDATES, entry, require, verified_bytes, validate_predictions


def compile_bundle(root, release_pin, reference, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    require(destination.is_relative_to(root / 'data/interim/official') and not destination.exists(),
            'ml_projection_requires_new_private_destination')
    release = CandidateRelease(root, release_pin['path'], release_pin['sha256'])._read()
    frame = pd.read_parquet(io.BytesIO(verified_bytes(root, release['sources']['all-predictions.private.parquet'])))
    validate_predictions(frame, release['models'], release['radio_ids'])
    catalog = reference.catalog()
    common = {f['properties']['radio_id'] for f in reference.geometry()['features'] if f['properties']['common_mask']}
    require(set(frame.radio_codigo.astype(str)) == common, 'ml_projection_territory_mismatch')
    require(all(release[k] == catalog[k] for k in ('dataset_version', 'data_policy_version', 'campaign_version')),
            'ml_projection_context_mismatch')
    models = {(m['block'], m['method']): m for m in release['models']}
    documents = {}
    for target, group in frame.groupby('target_week'):
        w = next(w for w in catalog['weeks'] if w['target_week'] == str(target))
        base = reference.week(w['target_year'], w['target_epi_week'])
        baseline = {r['radio_id']: r for r in base['rows']}
        rows = []
        for r in group.to_dict('records'):
            b = baseline[str(r['radio_codigo'])]
            require(r['target_count'] == b['observed']['quantity'] and r['count_latest'] == b['baseline']['quantity']
                    and r['presence_seasonal'] == b['predicted']['presence_score'], 'ml_projection_unpaired_results')
            rows.append(dict(radio_id=str(r['radio_codigo']), observed=r['target_count'], baseline=r['count_latest'],
                baseline_score=r['presence_seasonal'], presence_score=r['rf_A_epi_climate'],
                presence_threshold=r['rf_A_epi_climate_threshold'], quantity=r['residual_h1']))
        selected = {}
        for capability, method in CANDIDATES.items():
            m = models[group.block.iloc[0], method]
            selected[capability] = {k: m[k] for k in ('method', 'state', 'model_version', 'fit_last_target_end',
                                                     'features', 'calibrated', 'artifact')}
            selected[capability]['artifact_sha256'] = m['artifact']['sha256']
        documents[str(target)] = dict(target_week=str(target), origin_week=base['origin_week'], models=selected, rows=rows)
    destination.mkdir(parents=True)
    def write(path, value):
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return entry(root, path)
    weeks = {target: write(destination / f'{target}.private.json', value) for target, value in documents.items()}
    manifest = {k: catalog[k] for k in ('dataset_version', 'campaign_version', 'data_policy_version', 'territory_version')}
    manifest.update(schema_version='sigard-predictive-ml-overlay/1', release=release_pin, candidates=CANDIDATES,
        horizon_weeks=1, operational_enabled=False, training_performed=False, inference_performed=False,
        radio_ids=sorted(common), weeks=weeks,
        features={c: next(m['features'] for m in release['models'] if m['method'] == method) for c, method in CANDIDATES.items()})
    return write(destination / 'manifest.private.json', manifest)
