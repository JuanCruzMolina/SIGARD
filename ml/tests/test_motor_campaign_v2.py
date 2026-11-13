"""Corrective v2 campaign helpers on fictional grids only; no database, no private files."""
from datetime import timedelta

import numpy as np
import pandas as pd

from sigard_ml.forecasting import motor_campaign_v2 as campaign
from sigard_ml.forecasting.motor_data import build_frame
from sigard_ml.forecasting.motor_features_v2 import build_frame_v2
from sigard_ml.forecasting.motor_protocol_v2 import PROTOCOL
from test_motor_v2 import raw_grid


def fictional_frame():
    raw, edges = raw_grid(radios=6, weeks=150, count=lambda radio, i: float((radio * 7 + i) % 5 == 0) * (radio % 3 + 1))
    return build_frame_v2(build_frame(raw, edges))


def test_campaign_takes_models_from_frozen_protocol():
    assert campaign.make_estimator(campaign.PRINCIPAL).get_params()['max_features'] == .5
    assert campaign.make_estimator(campaign.PRINCIPAL).get_params()['class_weight'] is None
    assert campaign.make_estimator(campaign.SECONDARY)[-1].C == PROTOCOL['candidates']['secondary']['parameters']['C']
    assert campaign.make_estimator(campaign.COUNT)[-1].loss == 'absolute_error'
    assert campaign.METHODS == ('rf_v2_city_propensity', 'logit_v2_factors', 'residual_v2')


def test_folds_purge_and_fit_fold_outputs(monkeypatch):
    frame = fictional_frame()
    year = int(frame.target_year.max()) - 1
    block, train, evaluation = next(campaign.folds(frame, [year]))
    assert train.target_end.max() < evaluation.origin_week.min() - timedelta(days=28)
    small = dict(PROTOCOL['candidates']['principal']['parameters'], n_estimators=5)
    monkeypatch.setitem(campaign.CANDIDATES['principal'], 'parameters', small)
    predicted, models = campaign.fit_fold(train, evaluation)
    assert set(models) == set(campaign.METHODS)
    assert np.isfinite(predicted[[*campaign.METHODS, 'presence_latest_count']].to_numpy(float)).all()
    assert predicted[campaign.COUNT].ge(0).all() and len(predicted) == len(evaluation)


def test_paired_ratio_and_week_table():
    frame = fictional_frame().loc[lambda f: f.target_count.notna()].reset_index(drop=True)
    selected = np.zeros(len(frame), bool)
    g = campaign.week_table(frame, selected)
    assert g.hit.sum() == 0 and g.pos.sum() == frame.target_count.gt(0).sum()
    same = campaign.paired_ratio(g, g, 'hit', 'pos')
    assert same['difference'] == 0 and same['lower95'] == 0 and same['upper95'] == 0
