"""Corrective v2 features and decision rules on fictional weekly grids only. No fitting."""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.motor_data import build_frame
from sigard_ml.forecasting.motor_features_v2 import (build_frame_v2, city_features, propensity_features,
    presence_latest_count, topk_select, random_score)
from sigard_ml.forecasting.motor_protocol_v2 import PROTOCOL, CITY, PROPENSITY, FEATURES, SUCCESS_CRITERIA
from sigard_ml.forecasting.motor_protocol import PROTOCOL as V1
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR

START = DEFAULT_CALENDAR.week_bounds(2020, 1)[0]


def raw_grid(radios=4, weeks=130, count=None):
    count = count or (lambda radio, i: float((radio + i) % 3 == 0) * 2)
    rows = []
    for radio in range(1, radios + 1):
        for i in range(weeks):
            day = START + timedelta(weeks=i)
            year, number = DEFAULT_CALENDAR.date_week(day)
            rows.append(dict(radio_id=radio, radio_codigo=f'FICTIONAL-Z{radio:03}', inicio=day,
                fin=day + timedelta(days=6), anio=year, numero=number, cantidad_sigard=count(radio, i),
                poblacion_predictor_asof=np.nan, poblacion_contexto_2022=99999, superficie_km2=float(radio),
                clima_historia_hasta=day - timedelta(days=1), temperatura=20. + i % 4, humedad=50.,
                precipitacion=2., temperatura_lag_1=19., humedad_lag_1=49., precipitacion_lag_1=1.,
                temperatura_media_4=20., precipitacion_suma_4=8., temperatura_historia_previa=18.,
                humedad_historia_previa=45., precipitacion_media_historia_previa=1.))
    edges = [(i, j) for i in range(1, radios + 1) for j in range(1, radios + 1) if abs(i - j) == 1]
    return pd.DataFrame(rows), edges


def frame_from(raw, edges):
    return build_frame_v2(build_frame(raw, edges))


def test_protocol_reuses_v1_and_records_criteria():
    assert PROTOCOL['purge_weeks'] == V1['purge_weeks'] == 4
    assert PROTOCOL['bootstrap'] == V1['bootstrap']
    assert PROTOCOL['development_target_years'] == [2021, 2022, 2023]
    assert PROTOCOL['candidates']['principal']['parameters']['class_weight'] is None
    assert PROTOCOL['candidates']['principal']['parameters']['max_features'] == .5
    assert PROTOCOL['candidates']['principal']['parameters']['random_state'] == 20261112
    assert PROTOCOL['candidates']['count']['loss'] == 'absolute_error'
    assert set(SUCCESS_CRITERIA) >= {'P1', 'P2', 'P3', 'Q1', 'Q2'}
    assert PROTOCOL['expected_fits']['total'] == 48
    assert set(CITY) | set(PROPENSITY) <= set(FEATURES['rf_v2_city_propensity'])
    assert FEATURES['logit_v2_factors'] == CITY + PROPENSITY


def test_city_features_sum_origin_and_lags_only():
    raw, edges = raw_grid()
    base = frame_from(raw, edges)
    row = base.loc[base.origin_week.eq(START + timedelta(weeks=10))].iloc[0]
    week = raw.loc[raw.inicio.eq(START + timedelta(weeks=10)), 'cantidad_sigard'].sum()
    prior = raw.loc[raw.inicio.eq(START + timedelta(weeks=9)), 'cantidad_sigard'].sum()
    assert row.city_count_origin == week
    assert row.city_trend_1 == week - prior
    assert row.city_log_growth == pytest.approx(np.log1p(week) - np.log1p(prior))
    assert row.city_positive_radios_origin == raw.loc[raw.inicio.eq(START + timedelta(weeks=10))
                                                      ].cantidad_sigard.gt(0).sum()
    cut = START + timedelta(weeks=60)
    changed = raw.copy()
    changed.loc[changed.inicio > cut, 'cantidad_sigard'] = 7.
    other = frame_from(changed, edges)
    early = base.origin_week <= cut
    pd.testing.assert_frame_equal(base.loc[early, list(CITY)], other.loc[early, list(CITY)])
    assert not base.loc[~early, list(CITY)].equals(other.loc[~early, list(CITY)])


def test_city_features_unknown_radio_week_is_nan_not_zero():
    raw, edges = raw_grid()
    raw.loc[(raw.radio_id == 2) & raw.inicio.eq(START + timedelta(weeks=20)), 'cantidad_sigard'] = np.nan
    frame = frame_from(raw, edges)
    at = frame.origin_week.eq(START + timedelta(weeks=20))
    assert frame.loc[at, 'city_count_origin'].isna().all()
    nxt = frame.origin_week.eq(START + timedelta(weeks=21))
    assert frame.loc[nxt, 'city_mean_2'].isna().all() and frame.loc[nxt, 'city_count_origin'].notna().all()


def test_propensity_ignores_labels_after_origin_minus_28_days():
    raw, edges = raw_grid()
    base = frame_from(raw, edges)
    origin = START + timedelta(weeks=70)
    up_to = base.origin_week <= origin
    immature = raw.copy()
    immature.loc[immature.inicio >= origin - timedelta(weeks=4), 'cantidad_sigard'] = 9.
    other = frame_from(immature, edges)
    pd.testing.assert_frame_equal(base.loc[up_to, list(PROPENSITY)], other.loc[up_to, list(PROPENSITY)])
    mature = raw.copy()
    boundary = mature.inicio.eq(origin - timedelta(weeks=5)) & mature.radio_id.eq(1)
    mature.loc[boundary, 'cantidad_sigard'] = 9.
    changed = frame_from(mature, edges)
    row = (changed.origin_week == origin) & (changed.radio_id == 1)
    assert changed.loc[row, 'radio_hist_count_rate'].item() != base.loc[row, 'radio_hist_count_rate'].item()
    before = (changed.origin_week == origin - timedelta(weeks=1)) & (changed.radio_id == 1)
    assert changed.loc[before, 'radio_hist_count_rate'].item() == base.loc[before, 'radio_hist_count_rate'].item()


def test_propensity_rates_match_manual_mature_labels():
    raw, edges = raw_grid()
    frame = frame_from(raw, edges)
    row = frame.loc[(frame.radio_id == 3) & (frame.origin_week == START + timedelta(weeks=40))].iloc[0]
    ref = frame.loc[(frame.radio_id == 3) & frame.target_count.notna()
                    & (frame.target_end < row.origin_week - timedelta(days=28))]
    assert row.radio_hist_count_rate == pytest.approx(ref.target_count.mean())
    assert row.radio_hist_positive_rate == pytest.approx(ref.target_count.gt(0).mean())
    first = frame.loc[frame.radio_id == 3].sort_values('origin_week').iloc[0]
    assert np.isnan(first.radio_hist_positive_rate) and np.isnan(first.weeks_since_last_positive)


def single_positive_grid():
    week53 = START + timedelta(weeks=52)
    assert DEFAULT_CALENDAR.date_week(week53) == (2020, 53)
    return raw_grid(radios=2, weeks=160, count=lambda radio, i: 3. if (radio == 1 and i == 52) else 0.)


def test_weeks_since_last_positive_crosses_epi_week_53():
    raw, edges = single_positive_grid()
    frame = frame_from(raw, edges).sort_values('origin_week')
    radio = frame.loc[frame.radio_id == 1].set_index('origin_week')
    positive_week = START + timedelta(weeks=52)
    assert np.isnan(radio.loc[positive_week + timedelta(weeks=4), 'weeks_since_last_positive'])
    assert radio.loc[positive_week + timedelta(weeks=5), 'weeks_since_last_positive'] == 5.
    assert radio.loc[positive_week + timedelta(weeks=20), 'weeks_since_last_positive'] == 20.
    assert frame.loc[frame.radio_id == 2, 'weeks_since_last_positive'].isna().all()


def test_season_window_crosses_year_boundary_with_week_53():
    raw, edges = single_positive_grid()
    frame = frame_from(raw, edges)
    radio = frame.loc[frame.radio_id == 1]
    def season(year, number):
        return radio.loc[radio.target_year.eq(year) & radio.target_number.eq(number),
                         'radio_hist_season_positive_rate'].item()
    for number in (1, 2, 3, 4, 49, 50, 51, 52):
        assert season(2022, number) > 0, number
    for number in (5, 48):
        assert season(2022, number) == 0, number
    assert season(2021, 49) > 0 and season(2021, 48) == 0
    assert np.isnan(season(2020, 10))


def test_topk_selects_exactly_k_with_deterministic_ties():
    raw, edges = raw_grid(radios=6, weeks=40)
    frame = build_frame(raw, edges)
    ties = np.zeros(len(frame))
    chosen = topk_select(frame, ties, 3)
    assert pd.Series(chosen).groupby(frame.target_week.to_numpy()).sum().eq(3).all()
    shuffled = frame.sample(frac=1, random_state=1)
    again = pd.Series(topk_select(shuffled, np.zeros(len(shuffled)), 3), index=shuffled.index)
    assert (again.reindex(frame.index).to_numpy() == chosen).all()
    assert (topk_select(frame, ties, 3) == chosen).all()
    score = frame.radio_id.to_numpy(float)
    best = topk_select(frame, score, 2)
    assert set(frame.loc[best, 'radio_id']) == {5, 6}
    assert pd.Series(topk_select(frame, score, 25)).groupby(frame.target_week.to_numpy()).sum().eq(6).all()


def test_presence_latest_count_orders_by_count_then_territorial():
    evaluation = pd.DataFrame(dict(count_origin=[3., 1., 1., 0., np.nan, 0.]))
    territorial = np.array([.01, .02, .30, .40, .50, .10])
    score = presence_latest_count(evaluation, territorial)
    order = list(np.argsort(-score, kind='stable'))
    assert order == [0, 2, 1, 4, 3, 5]


def test_random_reference_is_reproducible_and_order_independent():
    raw, edges = raw_grid(radios=3, weeks=20)
    frame = build_frame(raw, edges)
    a = random_score(frame, 0)
    shuffled = frame.sample(frac=1, random_state=2)
    b = pd.Series(random_score(shuffled, 0), index=shuffled.index).reindex(frame.index).to_numpy()
    assert np.allclose(a, b) and not np.allclose(a, random_score(frame, 1))


def test_build_frame_v2_keeps_v1_columns_unchanged():
    raw, edges = raw_grid()
    v1 = build_frame(raw, edges)
    v2 = build_frame_v2(v1)
    pd.testing.assert_frame_equal(v1, v2[v1.columns])
    assert city_features(v1).index.equals(v1.index) and propensity_features(v1).index.equals(v1.index)
