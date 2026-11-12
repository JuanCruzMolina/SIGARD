"""Corrective v2 causal features and top-k decision rules. No fitting, no inference.

Input is the v1 frame from motor_data.build_frame (unchanged). Every new value uses only
the origin week and earlier counts (city) or mature labels before origin - 28 days (propensity).
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_data import load_frame
from sigard_ml.forecasting.motor_protocol_v2 import CITY, PROPENSITY, FEATURES, PROTOCOL, TOPK

SEASON_WINDOW = 4
SEASON_CYCLE = 53


def _known_sum(values):
    return float(values.sum()) if values.notna().all() else np.nan


def city_features(frame):
    """City totals of the origin week and its lags; NaN if any radio count is unknown."""
    weekly = frame.groupby('origin_week').count_origin.agg(_known_sum)
    positive = frame.groupby('origin_week').count_origin.agg(
        lambda s: float(s.gt(0).sum()) if s.notna().all() else np.nan)
    def lag(n):
        return pd.Series(weekly.reindex([d - timedelta(weeks=n) for d in weekly.index]).to_numpy(),
                         index=weekly.index)
    lags = [weekly, lag(1), lag(2), lag(3)]
    table = pd.DataFrame({
        'city_count_origin': weekly,
        'city_mean_2': pd.concat(lags[:2], axis=1).mean(axis=1, skipna=False),
        'city_mean_4': pd.concat(lags, axis=1).mean(axis=1, skipna=False),
        'city_trend_1': weekly - lags[1],
        'city_positive_radios_origin': positive,
        'city_log_growth': np.log1p(weekly) - np.log1p(lags[1]),
    })
    return table.reindex(frame.origin_week).set_axis(frame.index)[list(CITY)]


def _season_distance(a, b):
    d = np.abs(a[:, None] - b[None, :])
    return np.minimum(d, SEASON_CYCLE - d)


def propensity_features(frame):
    """Expanding per-radio propensity from mature labels only (target_end < origin - purge)."""
    purge = timedelta(weeks=PROTOCOL['purge_weeks'])
    result = pd.DataFrame(np.nan, index=frame.index, columns=list(PROPENSITY))
    for _, group in frame.groupby('radio_id', sort=False):
        group = group.sort_values('origin_week')
        if not group.target_end.is_monotonic_increasing:
            raise DatasetBlocked('motor_v2_unsorted_target_end')
        ends = group.target_end.to_numpy()
        cutoffs = np.array([o - purge for o in group.origin_week])
        mature = np.searchsorted(ends, cutoffs, side='left')  # rows [0, mature) satisfy target_end < cutoff
        y = group.target_count.to_numpy(float)
        known = np.isfinite(y)
        positive = known & (np.nan_to_num(y) > 0)
        known_c = np.r_[0, np.cumsum(known)]
        positive_c = np.r_[0, np.cumsum(positive)]
        count_c = np.r_[0, np.cumsum(np.where(known, y, 0.))]
        n_known = known_c[mature]
        with np.errstate(invalid='ignore', divide='ignore'):
            pos_rate = np.where(n_known > 0, positive_c[mature] / n_known, np.nan)
            count_rate = np.where(n_known > 0, count_c[mature] / n_known, np.nan)
        target_ord = np.array([d.toordinal() for d in group.target_week])
        origin_ord = np.array([d.toordinal() for d in group.origin_week])
        last_positive = np.maximum.accumulate(np.where(positive, target_ord, -1))
        last = np.r_[-1, last_positive][mature]
        since = np.where(last >= 0, (origin_ord - last) / 7., np.nan)
        numbers = group.target_number.to_numpy(int)
        years = group.target_year.to_numpy(int)
        index = np.arange(len(group))
        eligible = ((index[None, :] < mature[:, None]) & (years[None, :] < years[:, None])
                    & known[None, :] & (_season_distance(numbers, numbers) <= SEASON_WINDOW))
        season_n = eligible.sum(axis=1)
        season_pos = (eligible & positive[None, :]).sum(axis=1)
        with np.errstate(invalid='ignore', divide='ignore'):
            season = np.where(season_n > 0, season_pos / season_n, np.nan)
        result.loc[group.index] = np.column_stack([pos_rate, count_rate, season, since])
    return result.astype(float)


def build_frame_v2(frame):
    """Append CITY and PROPENSITY to a v1 frame; v1 columns are not altered."""
    overlap = set(frame.columns) & (set(CITY) | set(PROPENSITY))
    if overlap:
        raise DatasetBlocked('motor_v2_feature_already_present')
    out = pd.concat([frame, city_features(frame), propensity_features(frame)], axis=1)
    names = list(dict.fromkeys(x for v in FEATURES.values() for x in v))
    if np.isinf(out[names].to_numpy(float)).any():
        raise DatasetBlocked('motor_v2_nonfinite_feature')
    return out


def matrix_fingerprint(frame):
    names = list(dict.fromkeys(x for v in FEATURES.values() for x in v))
    cols = ['radio_id', 'origin_week', 'target_week', 'target_count', *names]
    return canonical_hash(frame[cols].astype(object).where(frame[cols].notna(), None).to_dict('records'))


def load_frame_v2(conn, version, expected_input_sha256):
    """v1 loader (verifies stage1 hash) + v2 features; returns the v2 matrix hash for pre-fit pinning."""
    frame, meta = load_frame(conn, version, expected_input_sha256)
    frame = build_frame_v2(frame)
    return frame, dict(meta, v1_matrix_sha256=meta['matrix_sha256'], matrix_sha256=matrix_fingerprint(frame),
                       protocol_version=PROTOCOL['version'])


def presence_latest_count(evaluation, territorial):
    """Global score whose order is count_origin desc, then territorial desc (exact pair ties stay tied)."""
    territorial = np.asarray(territorial, float)
    primary = np.where(evaluation.count_origin.notna(), evaluation.count_origin, territorial).astype(float)
    if not (np.isfinite(primary).all() and np.isfinite(territorial).all()):
        raise DatasetBlocked('motor_v2_latest_count_needs_finite_inputs')
    order = np.lexsort((territorial, primary))
    pairs = np.column_stack([primary, territorial])[order]
    change = np.r_[True, np.any(pairs[1:] != pairs[:-1], axis=1)]
    score = np.empty(len(primary))
    score[order] = np.cumsum(change)
    return score


def topk_select(frame, score, k, seed=None):
    """Boolean selection of exactly min(k, radios) rows per target week; deterministic ties."""
    seed = TOPK['tie_seed'] if seed is None else seed
    score = np.asarray(score, float)
    if len(score) != len(frame) or not np.isfinite(score).all():
        raise DatasetBlocked('motor_v2_topk_needs_finite_scores')
    selected = np.zeros(len(frame), dtype=bool)
    positions = pd.Series(np.arange(len(frame)), index=frame.index)
    for week, group in frame.groupby('target_week', sort=True):
        rows = positions[group.sort_values('radio_id', kind='stable').index].to_numpy()
        tie = np.random.default_rng([seed, week.toordinal()]).permutation(len(rows))
        order = np.lexsort((tie, -score[rows]))
        selected[rows[order[:min(k, len(rows))]]] = True
    return selected


def random_score(frame, replicate, seed=None):
    """One reproducible uniform ordering per replicate for the random reference."""
    seed = PROTOCOL['random_reference']['seed'] if seed is None else seed
    ordered = frame.sort_values(['target_week', 'radio_id'], kind='stable').index
    values = np.random.default_rng([seed, replicate]).random(len(frame))
    return pd.Series(values, index=ordered).reindex(frame.index).to_numpy()
