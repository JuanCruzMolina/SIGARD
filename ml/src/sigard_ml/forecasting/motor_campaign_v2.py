"""Explicit local corrective v2 campaign. Training never runs on import or API startup.

Every modelling choice comes from motor_protocol_v2.PROTOCOL. The database is only read
(no migrations, no inserts); all outputs are create-only files under the private folder.
Actions:
  prepare   load and verify the v2 matrix and pin its hash (no fitting)
  run       48 fold fits after a pre-fit manifest (16 blocks x 3 models), predictions and artifacts
  evaluate  prespecified criteria and descriptive tables from saved predictions (no fitting)
"""
import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting import v3
from sigard_ml.forecasting.consolidation import ROOT, PRIVATE
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_evaluation import count_summary, paired_interval
from sigard_ml.forecasting.motor_features_v2 import (load_frame_v2, presence_latest_count, topk_select,
    random_score)
from sigard_ml.forecasting.motor_models import baselines
from sigard_ml.forecasting.motor_protocol_v2 import PROTOCOL, CRITERIA_OPERATIONALIZATION

CANDIDATES = PROTOCOL['candidates']
PRINCIPAL = CANDIDATES['principal']['name']
SECONDARY = CANDIDATES['secondary']['name']
COUNT = CANDIDATES['count']['name']
METHODS = (PRINCIPAL, SECONDARY, COUNT)
FROZEN = PRIVATE / 'corrective-v2-20261112-v1/protocol-before-fit.private.json'
CODE = ('ml/src/sigard_ml/forecasting/motor_protocol_v2.py', 'ml/src/sigard_ml/forecasting/motor_features_v2.py',
        'ml/tests/test_motor_v2.py')

# Evaluation thresholds are read from the frozen operationalization text, never chosen here.
P2_TOLERANCE, Q2_BIAS_FRACTION, Q2_HIGH_RATIO = .03, .05, 1.05
assert ('- 0.03' in CRITERIA_OPERATIONALIZATION['P2'] and '0.05 * mean(target)' in CRITERIA_OPERATIONALIZATION['Q2']
        and '1.05 * MAE' in CRITERIA_OPERATIONALIZATION['Q2'])
assert v3.SEED == CANDIDATES['count']['seed']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value, readonly=False):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=1, ensure_ascii=False, default=str))
    if readonly:
        os.chmod(path, stat.S_IREAD)


def verify_frozen():
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if canonical_hash(PROTOCOL) != frozen['protocol_sha256']:
        raise DatasetBlocked('v2_protocol_changed_after_freeze')
    for path in CODE:
        if digest(ROOT / path) != frozen['code_sha256'][path]:
            raise DatasetBlocked('v2_frozen_code_changed')
    return frozen


# ---------------------------------------------------------------- folds and fitting

def purge(frame, first_origin):
    cutoff = first_origin - timedelta(weeks=PROTOCOL['purge_weeks'])
    result = frame.loc[frame.target_count.notna() & frame.target_end.lt(cutoff)].copy()
    if len(result) and not result.target_end.max() < cutoff:
        raise DatasetBlocked('v2_temporal_training_leakage')
    return result


def folds(frame, years):
    for year in years:
        dates = sorted(frame.loc[frame.target_year.eq(year) & frame.target_count.notna(), 'target_week'].unique())
        for left in range(0, len(dates), 13):
            evaluation = frame.loc[frame.target_week.isin(dates[left:left + 13]) & frame.target_count.notna()].copy()
            train = purge(frame, evaluation.origin_week.min())
            if train.target_week.nunique() < PROTOCOL['minimum_training_weeks']:
                raise DatasetBlocked('v2_insufficient_expanding_training_support')
            yield f'{year}-q{left // 13 + 1}', train, evaluation


def matrix(frame, method):
    return frame[list(PROTOCOL['features'][method])].astype(float)


def make_estimator(method):
    if method == PRINCIPAL:
        return RandomForestClassifier(**CANDIDATES['principal']['parameters'])
    if method == SECONDARY:
        return make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler(),
                             LogisticRegression(**CANDIDATES['secondary']['parameters']))
    if method == COUNT:
        return v3._regressor(CANDIDATES['count']['parameters'], CANDIDATES['count']['loss'])
    raise DatasetBlocked('v2_method_not_authorized')


def presence_score(model, frame, method):
    with threadpool_limits(limits=1):
        proba = model.predict_proba(matrix(frame, method))
    classes = list(model.classes_)
    return proba[:, classes.index(1)] if 1 in classes else np.zeros(len(frame))


def count_prediction(model, frame, reference):
    with threadpool_limits(limits=1):
        residual = np.asarray(model.predict(matrix(frame, COUNT)), float)
    return np.maximum(0., np.asarray(reference, float) + CANDIDATES['count']['shrinkage'] * residual)


def fit_fold(train, evaluation):
    y = train.target_count.gt(0).astype(int)
    if y.nunique() < 2:
        raise DatasetBlocked('v2_single_class_training')
    models = {}
    with threadpool_limits(limits=1):
        for method in (PRINCIPAL, SECONDARY):
            models[method] = make_estimator(method).fit(matrix(train, method), y)
        residual = train.target_count.to_numpy(float) - baselines(train, train)['count_latest']
        models[COUNT] = make_estimator(COUNT).fit(matrix(train, COUNT), residual)
    reference = baselines(train, evaluation)
    out = evaluation[['radio_id', 'radio_codigo', 'origin_week', 'target_week', 'target_end', 'target_year',
                      'target_number', 'target_count', 'count_origin']].copy()
    for name, values in reference.items():
        out[name] = values
    out['presence_latest_count'] = presence_latest_count(evaluation, reference['presence_territorial'])
    out[PRINCIPAL] = presence_score(models[PRINCIPAL], evaluation, PRINCIPAL)
    out[SECONDARY] = presence_score(models[SECONDARY], evaluation, SECONDARY)
    out[COUNT] = count_prediction(models[COUNT], evaluation, reference['count_latest'])
    out['tail_limit'] = max(2., float(train.target_count.quantile(.9)))
    out['week_limit'] = max(1., float(train.groupby('target_week').target_count.sum().quantile(.8)))
    names = [PRINCIPAL, SECONDARY, COUNT, 'presence_latest_count', *reference]
    if not np.isfinite(out[names].to_numpy(float)).all():
        raise DatasetBlocked('v2_nonfinite_prediction')
    return out, models


# ---------------------------------------------------------------- actions

def connect_readonly(connection):
    from sigard_ml.ingestion.epidemiology.db import connect
    url = json.loads(Path(connection).read_text(encoding='utf-8-sig'))['url']
    return connect(url)


def prepare(conn, config, output):
    frozen = verify_frozen()
    pins = frozen['input']
    if config['dataset_sha256'] != pins['stage1_sha256'] or config['dataset_version'] != pins['dataset_version']:
        raise DatasetBlocked('v2_config_does_not_match_frozen_input')
    conn.set_session(readonly=True)
    frame, meta = load_frame_v2(conn, pins['dataset_version'], pins['stage1_sha256'])
    if meta['v1_matrix_sha256'] != pins['v1_matrix_sha256']:
        raise DatasetBlocked('v2_v1_matrix_not_reproduced')
    record = dict(protocol_version=PROTOCOL['version'], protocol_sha256=frozen['protocol_sha256'],
                  dataset_version=pins['dataset_version'], stage1_sha256=meta['stage1_sha256'],
                  v1_matrix_sha256_reproduced=meta['v1_matrix_sha256'], v2_matrix_sha256=meta['matrix_sha256'],
                  rows=meta['rows'], known_targets=meta['known_targets'], radios=meta['radios'],
                  v2_feature_missing={k: int(v) for k, v in
                                      frame[list(PROTOCOL['new_features']['city'])
                                            + list(PROTOCOL['new_features']['propensity'])].isna().sum().items()},
                  fits_performed=0)
    write_new(Path(output) / 'matrix-before-fit.private.json', record, readonly=True)
    return record


def run(conn, config, output, progress=print):
    output = Path(output).resolve()
    if not output.is_relative_to(PRIVATE):
        raise DatasetBlocked('v2_private_output_required')
    frozen = verify_frozen()
    pinned = json.loads((output / 'matrix-before-fit.private.json').read_text(encoding='utf-8'))
    conn.set_session(readonly=True)
    frame, meta = load_frame_v2(conn, pinned['dataset_version'], pinned['stage1_sha256'])
    if meta['matrix_sha256'] != pinned['v2_matrix_sha256'] or meta['v1_matrix_sha256'] != frozen['input']['v1_matrix_sha256']:
        raise DatasetBlocked('v2_matrix_changed_after_pin')
    own = Path(__file__).resolve()
    manifest = dict(protocol_sha256=frozen['protocol_sha256'], frozen_code_sha256=frozen['code_sha256'],
                    campaign_module=own.relative_to(ROOT).as_posix(), campaign_module_sha256=digest(own),
                    v2_matrix_sha256=pinned['v2_matrix_sha256'],
                    environment=dict(python=platform.python_version(), sklearn=sklearn.__version__,
                                     numpy=np.__version__, pandas=pd.__version__),
                    authorization_ref=config['authorization_ref'], planned_fits=PROTOCOL['expected_fits'],
                    database_access='read_only_no_inserts')
    write_new(output / 'campaign-manifest-before-fit.private.json', manifest, readonly=True)
    parts, registry, fits = [], [], 0
    years = [*PROTOCOL['development_target_years'], *PROTOCOL['comparison_target_years']]
    for block, train, evaluation in folds(frame, years):
        if digest(own) != manifest['campaign_module_sha256']:
            raise DatasetBlocked('v2_campaign_code_changed_during_run')
        progress(json.dumps(dict(block=block, status='fitting', train_rows=len(train))))
        predicted, models = fit_fold(train, evaluation)
        fits += len(models)
        predicted['block'] = block
        for method, model in models.items():
            path = output / f'{block}-{method}.private.joblib'
            if path.exists():
                raise DatasetBlocked('v2_artifact_exists')
            joblib.dump(model, path)
            restored = joblib.load(path)
            again = (count_prediction(restored, evaluation, predicted.count_latest) if method == COUNT
                     else presence_score(restored, evaluation, method))
            if not np.array_equal(again, predicted[method].to_numpy(float)):
                raise DatasetBlocked('v2_artifact_roundtrip_changed_predictions')
            registry.append(dict(block=block, method=method, artifact=path.name, sha256=digest(path),
                                 training_rows=len(train), training_last_target_end=str(train.target_end.max()),
                                 first_origin=str(evaluation.origin_week.min())))
        predicted.to_parquet(output / f'{block}-predictions.private.parquet', index=False)
        parts.append(predicted)
        progress(json.dumps(dict(block=block, status='saved', fits=fits)))
    if fits != PROTOCOL['expected_fits']['total']:
        raise DatasetBlocked('v2_unexpected_fit_count')
    combined = pd.concat(parts, ignore_index=True)
    combined.to_parquet(output / 'all-predictions.private.parquet', index=False)
    write_new(output / 'artifact-registry.private.json', dict(fits=fits, artifacts=registry,
              predictions_sha256=digest(output / 'all-predictions.private.parquet')))
    return dict(fits=fits, rows=len(combined))


# ---------------------------------------------------------------- evaluation (no fitting)

def week_table(frame, selected):
    y = frame.target_count.gt(0).to_numpy()
    onset = y & frame.count_origin.eq(0).to_numpy()
    sel = np.asarray(selected, float)
    table = pd.DataFrame(dict(target_year=frame.target_year.to_numpy(), target_week=frame.target_week.to_numpy(),
                              hit=sel * y, onset_hit=sel * onset, pos=y.astype(float), onset=onset.astype(float),
                              kk=sel, records=frame.target_count.to_numpy(float)))
    return table.groupby(['target_year', 'target_week'], sort=True).sum().reset_index()


def summary(g):
    def ratio(a, b):
        return float(g[a].sum() / g[b].sum()) if g[b].sum() else None
    return dict(weeks=int(len(g)), positives=int(g.pos.sum()), detected=float(g.hit.sum()),
                recall=ratio('hit', 'pos'), onset_events=int(g.onset.sum()), onset_detected=float(g.onset_hit.sum()),
                onset_recall=ratio('onset_hit', 'onset'), precision=ratio('hit', 'kk'))


def paired_ratio(gm, gr, num, den):
    """v1 paired_interval moving blocks (within epi year) applied to sum(num_m - num_ref) / sum(den)."""
    cfg = PROTOCOL['bootstrap']
    gm, gr = gm.reset_index(drop=True), gr.reset_index(drop=True)
    if not (gm.target_week.values == gr.target_week.values).all():
        raise DatasetBlocked('v2_unpaired_weeks')
    delta = gm[num].to_numpy() - gr[num].to_numpy()
    den_values = gm[den].to_numpy(float)
    blocks = []
    for idx in gm.groupby('target_year', sort=True).indices.values():
        idx = list(idx)
        for start in range(len(idx)):
            block = [idx[start]]
            for nxt in idx[start + 1:start + cfg['block_weeks']]:
                if (pd.Timestamp(gm.loc[nxt, 'target_week']) - pd.Timestamp(gm.loc[block[-1], 'target_week'])).days != 7:
                    break
                block.append(nxt)
            blocks.append(block)
    rng = np.random.default_rng(cfg['seed'])
    draws = []
    for _ in range(cfg['resamples']):
        sample = []
        while len(sample) < len(gm):
            sample.extend(blocks[int(rng.integers(len(blocks)))])
        i = np.asarray(sample[:len(gm)], int)
        d = den_values[i].sum()
        draws.append(delta[i].sum() / d if d else np.nan)
    total = den_values.sum()
    return dict(difference=float(delta.sum() / total) if total else None,
                lower95=float(np.nanquantile(draws, .025)), upper95=float(np.nanquantile(draws, .975)),
                undefined_draws=int(np.isnan(draws).sum()))


def historical_scores(frame):
    """Fase 0 references from saved v1/census predictions, joined by radio and target week."""
    motor = pd.read_parquet(PRIVATE / 'predictive-motor-stage2-20261102-v1/campaign.private/all-predictions.private.parquet',
                            columns=['radio_id', 'target_week', 'rf_A_epi_climate'])
    census = pd.read_parquet(PRIVATE / 'census-maxfeatures6-20261105-v1/development-predictions.private.parquet',
                             columns=['radio_id', 'target_week', 'C']).rename(columns={'C': 'C_census_m6'})
    out = frame[['radio_id', 'target_week']].merge(motor, how='left', on=['radio_id', 'target_week'], validate='one_to_one')
    return out.merge(census, how='left', on=['radio_id', 'target_week'], validate='one_to_one')


def presence_tables(frame, k):
    frame = frame.reset_index(drop=True)
    history = historical_scores(frame)
    methods = {m: frame[m].to_numpy(float) for m in
               (PRINCIPAL, SECONDARY, 'presence_latest_count', 'presence_latest', 'presence_territorial',
                'presence_seasonal')}
    for name in ('rf_A_epi_climate', 'C_census_m6'):
        if history[name].notna().all():
            methods[name] = history[name].to_numpy(float)
    weeks = {m: week_table(frame, topk_select(frame, s, k)) for m, s in methods.items()}
    cfg = PROTOCOL['random_reference']
    random_weeks = [week_table(frame, topk_select(frame, random_score(frame, r), k)) for r in range(cfg['permutations'])]
    mean = random_weeks[0].copy()
    for col in ('hit', 'onset_hit', 'kk'):
        mean[col] = np.mean([w[col].to_numpy() for w in random_weeks], axis=0)
    weeks['random'] = mean
    activity = weeks['presence_latest_count'].records.map(lambda t: '0' if t == 0 else ('1-9' if t < 10 else '>=10'))
    ref = weeks['presence_latest_count']
    years = sorted(frame.target_year.unique())
    result = {}
    for m, g in weeks.items():
        entry = dict(overall=summary(g), by_year={str(y): summary(g.loc[g.target_year == y]) for y in years},
                     by_activity={a: summary(g.loc[activity == a]) for a in ('0', '1-9', '>=10')})
        if m != 'presence_latest_count':
            entry['minus_latest_count'] = dict(recall=paired_ratio(g, ref, 'hit', 'pos'),
                                               onset_recall=paired_ratio(g, ref, 'onset_hit', 'onset'),
                                               precision=paired_ratio(g, ref, 'hit', 'kk'))
        if m != 'presence_territorial':
            entry['minus_territorial_onset'] = paired_ratio(g, weeks['presence_territorial'], 'onset_hit', 'onset')
        result[m] = entry
    return result


def count_tables(frame):
    out = {}
    for name in (COUNT, 'count_latest', 'count_historical_lag1', 'count_training_mean'):
        entry = count_summary(frame, name)
        entry['by_year'] = {str(y): count_summary(g, name)['mae'] for y, g in frame.groupby('target_year')}
        if name != 'count_latest':
            entry['mae_minus_count_latest'] = paired_interval(frame, name, 'count_latest', 'mae')
        out[name] = entry
    for ref in ('count_historical_lag1', 'count_training_mean'):
        out[COUNT]['mae_minus_' + ref] = paired_interval(frame, COUNT, ref, 'mae')
    return out


def criteria(presence10, counts, frame):
    v2, latest, territorial = (presence10[PRINCIPAL], presence10['presence_latest_count'],
                               presence10['presence_territorial'])
    p1 = v2['minus_latest_count']['recall']
    p2 = {y: dict(rf_v2=v2['by_year'][y]['recall'], latest_count=latest['by_year'][y]['recall'],
                  difference=v2['by_year'][y]['recall'] - latest['by_year'][y]['recall']) for y in v2['by_year']}
    p3 = dict(rf_v2=v2['overall']['onset_recall'], territorial=territorial['overall']['onset_recall'],
              interval=v2['minus_territorial_onset'])
    q1 = counts[COUNT]['mae_minus_count_latest']
    mean_y = float(frame.target_count.mean())
    bias_v2, bias_ref = counts[COUNT]['mean_bias'], counts['count_latest']['mean_bias']
    high_v2 = counts[COUNT]['high_count']['mae'] if counts[COUNT]['high_count'] else None
    high_ref = counts['count_latest']['high_count']['mae'] if counts['count_latest']['high_count'] else None
    q2_bias = abs(bias_v2) <= abs(bias_ref) + Q2_BIAS_FRACTION * mean_y
    q2_high = high_v2 is not None and high_ref is not None and high_v2 <= Q2_HIGH_RATIO * high_ref
    result = dict(
        P1=dict(value=p1, passed=bool(p1['lower95'] > 0)),
        P2=dict(value=p2, passed=bool(all(v['difference'] >= -P2_TOLERANCE for v in p2.values()))),
        P3=dict(value=p3, passed=bool(p3['rf_v2'] > p3['territorial'])),
        Q1=dict(value=q1, passed=bool(q1['mean_difference'] < 0 and q1['upper95'] < 0)),
        Q2=dict(value=dict(bias_rf=bias_v2, bias_latest=bias_ref, mean_target=mean_y, high_mae_v2=high_v2,
                           high_mae_latest=high_ref, bias_ok=bool(q2_bias), high_ok=bool(q2_high)),
                passed=bool(q2_bias and q2_high)))
    result['presence_success'] = all(result[c]['passed'] for c in ('P1', 'P2', 'P3'))
    result['count_success'] = all(result[c]['passed'] for c in ('Q1', 'Q2'))
    return result


IMPORTANCE = dict(repeats=10, seed=PROTOCOL['seed'], top_individual=10)


def feature_groups():
    from sigard_ml.forecasting.motor_protocol import STATIC, HISTORY, CLIMATE
    calendar = ['semana_epidemiologica', 'estacionalidad_seno', 'estacionalidad_coseno']
    return dict(CITY=list(PROTOCOL['new_features']['city']),
                PROPENSITY=list(PROTOCOL['new_features']['propensity']), HISTORY=list(HISTORY),
                CLIMATE=list(CLIMATE), STATIC_RADIO=[c for c in STATIC if c not in calendar],
                CALENDAR=[c for c in STATIC if c in calendar])


def variation(part, columns):
    """Whether the columns vary among radios within a week and/or among weeks (NaN-aware)."""
    values = part[columns].astype(float).fillna(-1e300)
    within = bool(values.groupby(part.target_week.to_numpy()).nunique().gt(1).any().any())
    between = bool(values.groupby(part.radio_id.to_numpy()).nunique().gt(1).any().any())
    return within, between


def interpretation(within, between, scheme):
    """Approved reading rule: radio-varying -> within_week; week-only -> between_weeks; structural zero -> n/a."""
    applicable = within if scheme == 'within_week' else between
    if not applicable:
        return 'no_aplica'
    preferred = 'within_week' if within else 'between_weeks'
    return 'interpretado' if scheme == preferred else 'esquema_no_preferido'


def _scores(model, x, part, y):
    from sklearn.metrics import average_precision_score
    with threadpool_limits(limits=1):
        proba = model.predict_proba(x)[:, list(model.classes_).index(1)]
    hits = topk_select(part, proba, PROTOCOL['decision']['k'])
    return float(average_precision_score(y, proba)), float((hits & (y == 1)).sum() / max(int(y.sum()), 1))


def _permute(x, columns, week_index, rng, scheme):
    """within_week: rows of each week shuffled among radios (joint for the group).
    between_weeks: whole week values exchanged among weeks of the block, radio order kept."""
    out = x.copy()
    values = x[columns].to_numpy()
    if scheme == 'within_week':
        new = values.copy()
        for rows in week_index.values():
            new[rows] = values[rng.permutation(rows)]
    else:
        weeks = list(week_index)
        mapping = dict(zip(weeks, [weeks[i] for i in rng.permutation(len(weeks))]))
        new = values.copy()
        for week, rows in week_index.items():
            source = week_index[mapping[week]]
            if len(source) != len(rows):
                raise DatasetBlocked('v2_unbalanced_week_for_permutation')
            new[rows] = values[source]
    out[columns] = new
    return out


def importances(output, frame, blocks):
    """Descriptive out-of-sample importance: each block's own model on its own evaluation rows."""
    output = Path(output)
    names = list(PROTOCOL['features'][PRINCIPAL])
    groups = feature_groups()
    if sorted(sum(groups.values(), [])) != sorted(names):
        raise DatasetBlocked('v2_importance_groups_do_not_cover_features')
    impurity = []
    for block in blocks:
        impurity.append(joblib.load(output / f'{block}-{PRINCIPAL}.private.joblib').feature_importances_)
    impurity = pd.DataFrame(impurity, columns=names, index=blocks)
    top = list(impurity.mean().sort_values(ascending=False).index[:IMPORTANCE['top_individual']])
    rng = np.random.default_rng(IMPORTANCE['seed'])
    targets = [('group', g, cols) for g, cols in groups.items()] + [('feature', f, [f]) for f in top]
    status = {}
    for kind, name, cols in targets:
        within, between = variation(frame, cols)
        for scheme in ('within_week', 'between_weeks'):
            status[(scheme, kind, name)] = dict(varies_within_week=within, varies_between_weeks=between,
                                                status=interpretation(within, between, scheme))
    rows = []
    for block in blocks:
        model = joblib.load(output / f'{block}-{PRINCIPAL}.private.joblib')
        part = frame.loc[frame.block.eq(block)].sort_values(['target_week', 'radio_id']).reset_index(drop=True)
        x, y = matrix(part, PRINCIPAL), part.target_count.gt(0).astype(int).to_numpy()
        base_ap, base_recall = _scores(model, x, part, y)
        week_index = {w: np.asarray(i) for w, i in part.groupby('target_week', sort=True).indices.items()}
        for scheme in ('within_week', 'between_weeks'):
            for kind, name, cols in targets:
                if status[(scheme, kind, name)]['status'] == 'no_aplica':
                    continue
                for repeat in range(IMPORTANCE['repeats']):
                    ap, recall = _scores(model, _permute(x, cols, week_index, rng, scheme), part, y)
                    rows.append(dict(block=block, scheme=scheme, kind=kind, name=name, repeat=repeat,
                                     ap_drop=base_ap - ap, recall10_drop=base_recall - recall,
                                     base_ap=base_ap, base_recall10=base_recall))
    perm = pd.DataFrame(rows)
    per_block = perm.groupby(['scheme', 'kind', 'name', 'block'])[['ap_drop', 'recall10_drop']].mean().reset_index()
    summary_table = per_block.groupby(['scheme', 'kind', 'name']).agg(
        ap_drop_mean=('ap_drop', 'mean'), ap_drop_min=('ap_drop', 'min'), ap_drop_max=('ap_drop', 'max'),
        recall10_drop_mean=('recall10_drop', 'mean'), blocks_ap_drop_positive=('ap_drop', lambda s: int((s > 0).sum())),
        ).reset_index()
    labels = pd.DataFrame([dict(scheme=s, kind=k, name=n, **v) for (s, k, n), v in status.items()])
    summary_table = labels.merge(summary_table, how='left', on=['scheme', 'kind', 'name'])
    summary_table = summary_table.astype(object).where(summary_table.notna(), None)
    coefficients = []
    for block in blocks:
        logit = joblib.load(output / f'{block}-{SECONDARY}.private.joblib')
        coefficients.append(pd.Series(logit[-1].coef_[0], index=logit[:-1].get_feature_names_out(),
                                      name=block))
    coef = pd.concat(coefficients, axis=1)
    return dict(
        note='descriptive only; out-of-sample per block (own model, own evaluation rows); never training rows',
        settings=dict(IMPORTANCE, metric_primary='drop in average precision per block',
                      metric_secondary='drop in recall@10 (exact top-k rule of the protocol)',
                      schemes=dict(within_week='rows of each target week permuted among radios, joint per group',
                                   between_weeks='week-level values exchanged among the 13 weeks of the block, '
                                                 'radio order kept'),
                      reading_rule='approved: radio-varying groups read with within_week; week-only groups '
                                   'with between_weeks; structurally constant cells reported as no_aplica '
                                   '(not computed, never "no importance")'),
        groups=groups, top_impurity_features=top,
        impurity=dict(mean=impurity.mean().to_dict(), std=impurity.std(ddof=1).to_dict(),
                      min=impurity.min().to_dict(), max=impurity.max().to_dict(), blocks=len(blocks)),
        permutation=summary_table.to_dict('records'), permutation_per_block=per_block.to_dict('records'),
        logit_standardized_coefficients=dict(mean=coef.mean(axis=1).to_dict(), min=coef.min(axis=1).to_dict(),
                                             max=coef.max(axis=1).to_dict(), blocks=int(coef.shape[1])))


def load_verified_matrix(connection, expected_sha256):
    """Read-only reload of the pinned v2 matrix; blocks on any hash mismatch."""
    pinned = json.loads((PRIVATE / 'corrective-v2-20261112-v1/matrix-before-fit.private.json').read_text(encoding='utf-8'))
    if pinned['v2_matrix_sha256'] != expected_sha256:
        raise DatasetBlocked('v2_unexpected_pinned_hash')
    with connect_readonly(connection) as conn:
        conn.set_session(readonly=True)
        frame, meta = load_frame_v2(conn, pinned['dataset_version'], pinned['stage1_sha256'])
    if meta['matrix_sha256'] != expected_sha256:
        raise DatasetBlocked('v2_matrix_changed_after_pin')
    return frame


def importance_from_matrix(output, frame):
    """Attach feature rows to saved development predictions by key, then compute importances."""
    output = Path(output)
    saved = pd.read_parquet(output / 'all-predictions.private.parquet', columns=['radio_id', 'target_week', 'block',
                                                                                 'target_year'])
    saved = saved.loc[saved.target_year.isin(PROTOCOL['development_target_years'])]
    names = list(PROTOCOL['features'][PRINCIPAL])
    keyed = frame[list(dict.fromkeys(['radio_id', 'target_week', 'target_count', 'count_origin', *names]))].copy()
    keyed['target_week'] = pd.to_datetime(keyed.target_week)
    saved['target_week'] = pd.to_datetime(saved.target_week)
    joined = saved.merge(keyed, how='left', on=['radio_id', 'target_week'], validate='one_to_one')
    if joined.target_count.isna().any():
        raise DatasetBlocked('v2_importance_rows_not_found')
    result = importances(output, joined, sorted(joined.block.unique()))
    write_new(output / 'importance.private.json', result)
    return result


def evaluate(output):
    output = Path(output)
    frame = pd.read_parquet(output / 'all-predictions.private.parquet')
    dev = frame.loc[frame.target_year.isin(PROTOCOL['development_target_years'])].reset_index(drop=True)
    cmp = frame.loc[frame.target_year.isin(PROTOCOL['comparison_target_years'])].reset_index(drop=True)
    ks = [PROTOCOL['decision']['k'], *PROTOCOL['decision']['sensitivity']]
    result = dict(protocol_sha256=canonical_hash(PROTOCOL), training_performed_in_evaluation=False,
                  development=dict(presence={str(k): presence_tables(dev, k) for k in ks}, counts=count_tables(dev)),
                  comparison_2024=dict(label='comparación ya observada, no validación',
                                       presence={str(k): presence_tables(cmp, k) for k in ks},
                                       counts=count_tables(cmp)))
    result['criteria'] = criteria(result['development']['presence'][str(ks[0])], result['development']['counts'], dev)
    result['incident'] = ('evaluation split after a KeyError: saved predictions do not store features; '
                          'importance moved to importance.private.json before any metric was seen; '
                          'training code sha256 recorded in campaign-manifest-before-fit')
    write_new(output / 'metrics.private.json', result)
    return result['criteria']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'evaluate'])
    parser.add_argument('--connection', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(PRIVATE):
        raise DatasetBlocked('v2_private_output_required')
    if subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() != 'entrenamiento-ML':
        raise DatasetBlocked('wrong_branch')
    if args.action == 'evaluate':
        print(json.dumps({k: v['passed'] if isinstance(v, dict) else v for k, v in evaluate(args.output).items()}))
        return 0
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    if (config.get('research_training_authorized') is not True
            or config.get('authorization_basis') != 'project_owner_declared_provision'):
        raise DatasetBlocked('explicit_v2_research_training_authorization_required')
    with connect_readonly(args.connection) as conn:
        result = prepare(conn, config, args.output) if args.action == 'prepare' else run(conn, config, args.output)
    print(json.dumps({k: v for k, v in result.items() if k in ('v2_matrix_sha256', 'rows', 'radios', 'fits')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
