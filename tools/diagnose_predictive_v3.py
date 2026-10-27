"""One bounded, local diagnosis of frozen V3; never fits an estimator.

EDA reads only manifest-verified derived panels. The separate sklearn inspection
loads only the trusted frozen fold estimators, verifies their saved predictions,
and permutes feature groups on development. No original or reserved input is read.
"""
import argparse
from datetime import date
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import warnings

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from sigard_ml.forecasting.thesis_validation import FrozenArtifact, digest, write_json
from sigard_ml.forecasting.v3 import BASELINES, CANDIDATES, FEATURES, VERSION

SEED = 20261026
GROUPS = {
    'count_history': list(FEATURES[:6]),
    'climate': list(FEATURES[8:13]),
    'season': list(FEATURES[13:15]),
    'spatial_context': [FEATURES[6], FEATURES[7], *FEATURES[15:]],
}
METHODS = (*CANDIDATES, *BASELINES[:2])


def describe(values):
    values = pd.Series(values, dtype=float)
    known = values.dropna()
    if known.empty:
        return dict(n=len(values), known=0, missing=len(values))
    return dict(n=len(values), known=len(known), missing=int(values.isna().sum()),
                zero_fraction=float(known.eq(0).mean()), mean=float(known.mean()),
                sd=float(known.std(ddof=0)), median=float(known.median()),
                p90=float(known.quantile(.9)), p99=float(known.quantile(.99)),
                maximum=float(known.max()), minimum=float(known.min()),
                iqr=float(known.quantile(.75)-known.quantile(.25)),
                mad=float((known-known.median()).abs().median()))


def errors(y, prediction):
    y, prediction = np.asarray(y, float), np.asarray(prediction, float)
    if len(y) == 0:
        return None
    assert y.shape == prediction.shape and np.isfinite(y).all() and np.isfinite(prediction).all()
    residual = prediction-y
    return dict(n=len(y), mae=float(abs(residual).mean()),
                rmse=float(np.sqrt(np.mean(residual**2))), bias=float(residual.mean()),
                observed_mean=float(y.mean()), predicted_mean=float(prediction.mean()))


def panel_profile(frame):
    weekly = frame.groupby('target_week').target_count.agg(['sum', 'size'])
    return dict(target=describe(frame.target_count), weeks=len(weekly),
                weekly_known_subset=describe(weekly['sum']),
                cells_per_week=describe(weekly['size']),
                features={name: describe(frame[name]) for name in FEATURES},
                target_histogram={str(label): int(mask.sum()) for label, mask in {
                    '0': frame.target_count.eq(0), '1': frame.target_count.eq(1),
                    '2_to_4': frame.target_count.between(2, 4),
                    '5_plus': frame.target_count.ge(5)}.items()})


def join_panel(predictions, panel):
    keys = ['radio_id', 'origin_week', 'target_week']
    assert not panel.duplicated(keys).any() and not predictions.duplicated(keys).any()
    joined = predictions.merge(panel[keys+list(FEATURES)+['target_count', 'partition', 'predictor_admissible']],
                               on=keys, validate='one_to_one', how='left', suffixes=('', '_panel'))
    assert joined.target_count.equals(joined.target_count_panel)
    assert joined.predictor_admissible.all()
    return joined


def error_profile(frame):
    groups = {'all': np.ones(len(frame), bool), 'zero': frame.target_count.eq(0),
              'positive': frame.target_count.gt(0), '2_plus': frame.target_count.ge(2)}
    if 'training_max_count' in frame:
        groups['above_training_max'] = frame.target_count.gt(frame.training_max_count)
    if 'high_week_threshold' in frame:
        total = frame.groupby('target_week').target_count.transform('sum')
        groups['high_weeks'] = total.ge(frame.high_week_threshold)
    # These phase strata are outcome-conditioned descriptions, never predictors.
    delta = frame.target_count-frame.count_origin
    groups.update(rising=delta.gt(0), falling=delta.lt(0), flat=delta.eq(0))
    result = {}
    for label, mask in groups.items():
        part = frame.loc[mask]
        if len(part):
            result[label] = {name: errors(part.target_count, part[name]) for name in METHODS}
    if 'high_week_threshold' in frame:
        weekly = frame.groupby('target_week').agg(actual=('target_count', 'sum'),
                    threshold=('high_week_threshold', 'first'), **{m:(m,'sum') for m in METHODS})
        high = weekly.actual.ge(weekly.threshold)
        result['high_week_subtotals'] = {m:errors(weekly.loc[high,'actual'], weekly.loc[high,m]) for m in METHODS}
    return result


def development(frame, oof):
    dev = frame.loc[frame.partition.isin(['train', 'validation']) & frame.predictor_admissible & frame.target_count.notna()]
    assert oof.partition.isin(['train','validation']).all()
    fold_details = []
    for fold, val in oof.groupby('fold', sort=True):
        train = dev.loc[dev.target_end.lt(val.origin_week.min())]
        assert train.target_end.max() < val.origin_week.min()
        fold_details.append(dict(fold=int(fold), train=panel_profile(train), validation=panel_profile(val),
                                 errors=error_profile(val),
                                 validation_above_training_max=float(val.target_count.gt(train.target_count.max()).mean())))
    return dict(profile=panel_profile(dev), oof_profile=panel_profile(oof),
                errors=error_profile(oof), folds=fold_details)


def shift_profile(development_frame, comparison):
    result = {}
    for name in FEATURES:
        a, b = development_frame[name].dropna(), comparison[name].dropna()
        result[name] = dict(development_missing=float(development_frame[name].isna().mean()),
                           comparison_missing=float(comparison[name].isna().mean()),
                           outside_development_range=float(((b<a.min()) | (b>a.max())).mean()) if len(a) and len(b) else None,
                           standardized_mean_difference=float((b.mean()-a.mean())/a.std(ddof=0)) if len(a) and len(b) and a.std(ddof=0)>0 else None)
    return result


def permute_group(frame, columns, group, rng):
    altered = frame.copy(deep=True)
    if group in ('climate', 'season'):
        # Joint weekly circular shift; all radios share the same donor week.
        weekly = frame.groupby('target_week')[columns].first().sort_index()
        assert len(weekly)>1
        shifted = np.roll(weekly.to_numpy(), int(rng.integers(1,len(weekly))), axis=0)
        donor = pd.DataFrame(shifted, index=weekly.index, columns=columns)
        for col in columns:
            altered[col] = frame.target_week.map(donor[col])
    else:
        # Joint within-week shuffle preserves weekly distributions and missingness.
        for _, indices in frame.groupby('target_week').groups.items():
            altered.loc[indices,columns] = frame.loc[rng.permutation(indices),columns].to_numpy()
    return altered


def frozen_group_importance(artifact, oof):
    import joblib  # Trusted sklearn artifact inspection, outside EDA deserialization.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        models = joblib.load(artifact.path('horizon_1/fold_models.private.joblib'))
    rows = []
    for fold, val in oof.groupby('fold', sort=True):
        val = val.reset_index(drop=True)
        fitted = models[int(fold)]['counts']
        # Fixed methods, no ranking or new model selection by importance.
        for name in (CANDIDATES[0], CANDIDATES[2]):
            model = fitted[name]
            original = model.predict_frame(val)
            np.testing.assert_allclose(original, val[name], rtol=1e-12, atol=1e-12)
            for group, columns in GROUPS.items():
                differences = []
                for repeat in range(3):
                    altered = permute_group(val, columns, group, np.random.default_rng(SEED+100*int(fold)+repeat))
                    permuted = errors(val.target_count, model.predict_frame(altered))
                    base = errors(val.target_count, original)
                    differences.append({key:permuted[key]-base[key] for key in ('mae','rmse','bias')})
                rows.append(dict(fold=int(fold), method=name, group=group, repeats=differences))
    return rows


def protected_hashes(root):
    return {p.relative_to(root).as_posix():digest(p)
            for version in ('v1','v2','v3')
            for p in (root/f'ml/artifacts/official/sigard-principal-{version}-experimental').rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    assert out.parent == root/'data/interim/official' and out.name.startswith('predictive_diagnosis_')
    assert not out.exists(), 'Never overwrite a diagnosis'
    assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip() == 'entrenamiento-ML'
    before = protected_hashes(root)
    artifact = FrozenArtifact(root/'ml/artifacts/official'/VERSION)
    panels, oofs = {}, {}
    result = dict(schema='sigard-predictive-diagnosis-1', seed=SEED, training_performed=False,
                  scope='Existing derived snapshot; exploratory, no new outcomes',
                  unit='filtered_snapshot_records_per_radio_week',
                  zero_meaning='No record in explicitly covered snapshot; not epidemiological absence',
                  shap='Unavailable: package and skill not installed; no installation requested',
                  historical_availability_accredited=False,
                  versions={p:metadata.version(p) for p in ('numpy','pandas','scikit-learn','pyarrow')},
                  development={})
    # All development diagnostics are saved before any historical comparison is opened.
    for h in (1,2,4):
        for name in ('modeling_panel','development_predictions'):
            path = artifact.path(f'horizon_{h}/{name}.private.parquet')
            assert not path.is_symlink() and path.stat().st_nlink == 1 and path.stat().st_size < 64*1024**2
            meta = pq.ParquetFile(path)
            assert meta.metadata.num_rows <= 100000 and len(meta.schema_arrow.names)<=50
        panel = artifact.frame(f'horizon_{h}/modeling_panel.private.parquet')
        oof = join_panel(artifact.frame(f'horizon_{h}/development_predictions.private.parquet'),panel)
        panels[h], oofs[h] = panel, oof
        result['development'][str(h)] = development(panel,oof)
    result['group_importance_development_t1'] = frozen_group_importance(artifact,oofs[1])
    out.mkdir()
    write_json(out/'development.private.json',result)
    print(json.dumps(dict(development_complete=True, training_performed=False)),flush=True)
    # Comparison is descriptive and physically separated from development output.
    comparison = {}
    for h in (1,2,4):
        test = join_panel(artifact.frame(f'horizon_{h}/comparison_predictions.private.parquet'), panels[h])
        assert test.partition.eq('test').all()
        dev = panels[h].loc[panels[h].partition.isin(['train','validation']) & panels[h].predictor_admissible & panels[h].target_count.notna()]
        comparison[str(h)] = dict(profile=panel_profile(test), errors=error_profile(test),
                                  predictor_shift=shift_profile(dev,test),
                                  above_development_max=float(test.target_count.gt(dev.target_count.max()).mean()))
    write_json(out/'comparison_diagnostic.private.json',comparison)
    artifact.unchanged()
    assert protected_hashes(root)==before
    write_json(out/'manifest.private.json',dict(inputs_sha256=artifact.inputs,
               script_sha256=digest(Path(__file__)), protected_files=len(before), protected_unchanged=True,
               protected_before=before, rows_truncated=False, new_outcomes_read=False,
               output_sha256={p.name:digest(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(completed=True, protected_files=len(before), protected_unchanged=True)),flush=True)


if __name__ == '__main__':
    main()
