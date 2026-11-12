"""Fictional features/estimators only. No training and no private artifact reads."""

from datetime import date, datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from sigard_ml.official.spatial_ml import date_inference as d
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS

NOW = datetime(2026, 10, 28, 1, tzinfo=timezone.utc)  # Oct 27 in Argentina.
POLICY = {"static_available_at": "2026-10-28T00:00:00+00:00", "model_available_at": "2026-10-28T00:00:00+00:00"}


@pytest.mark.parametrize("requested", ["2026-11-01", "2026-11-04", "2026-11-07"])
def test_prospective_a_uses_current_origin_and_observed_input_cutoff(requested):
    value = d.plan(requested, POLICY, NOW)
    assert value["origin_week_start"] == "2026-10-25" and value["origin_week_end"] == "2026-10-31"
    assert value["target_week_start"] == "2026-11-01" and value["target_week_end"] == "2026-11-07"
    assert value["information_cutoff"] == NOW.isoformat()


@pytest.mark.parametrize("requested,code", [("2024-03-03", "historical_input_availability_unverified"),
    ("2026-10-27", "historical_input_availability_unverified"), ("2026-11-08", "horizon_not_supported"),
    ("2026-12-15", "horizon_not_supported")])
def test_only_t_plus_one_from_current_origin_is_permitted(requested, code):
    with pytest.raises(d.InferenceBlocked, match=code):
        d.plan(requested, POLICY, NOW)


def test_no_backdating_and_no_inputs_after_cutoff():
    with pytest.raises(d.InferenceBlocked, match="inputs_not_available_at_cutoff"):
        d.plan("2026-11-01", {**POLICY, "static_available_at": "2026-10-29T00:00:00+00:00"}, NOW)
    with pytest.raises(d.InferenceBlocked):
        d.timestamp("2026-10-27")


def test_incompatible_python_is_blocked_before_deserialization(monkeypatch):
    import joblib
    monkeypatch.setattr(d, 'load_policy', lambda *args: (POLICY, {}, {'python': '0.0.0'}))
    monkeypatch.setattr(joblib, 'load', lambda *args: pytest.fail('must not deserialize'))
    with pytest.raises(d.InferenceBlocked, match='inference_runtime_incompatible'):
        d.infer_historical('2026-11-01', 'fictional-policy', now=NOW)


def test_original_calendar_transform_and_exact_feature_order_without_target_inputs():
    static = pd.DataFrame({"radio_censal": ["fictional-a", "fictional-b"],
        "superficie_km2": [1.25, 2.0], "poblacion": [100, 200], "densidad_poblacional": [80, 100], "cantidad_vecinos": [2, 1]})
    before = static.copy(deep=True)
    origin = date(2026, 10, 25)
    matrix = d.feature_matrix(static, origin)
    assert list(matrix.columns) == BASE
    assert matrix.iloc[0, :4].tolist() == [1.25, 100, 80, 2]
    year, week = d.DEFAULT_CALENDAR.date_week(origin)
    length = next(y.weeks for y in d.DEFAULT_CALENDAR.years if y.year == year)
    assert matrix.semana_epidemiologica.eq(week).all()
    assert np.allclose(matrix.estacionalidad_seno, np.sin(2 * np.pi * (week - 1) / length))
    assert np.allclose(matrix.estacionalidad_coseno, np.cos(2 * np.pi * (week - 1) / length))
    pd.testing.assert_frame_equal(static, before)


def fictional_forest():
    # Construct an unfitted test double; predict_proba is patched below. No fit.
    forest = RandomForestClassifier(**RF_PARAMETERS)
    forest.feature_names_in_ = np.array(BASE, dtype=object)
    forest.n_features_in_ = 7
    forest.estimators_ = ["fictional-tree"] * 400
    forest.classes_ = np.array([0, 1])
    return forest


def test_predict_only_no_fit_no_learned_state_mutation(monkeypatch):
    forest = fictional_forest()
    matrix = pd.DataFrame(np.ones((3, 7)), columns=BASE)
    def forbidden(*args, **kwargs):
        pytest.fail("fit must never be called")
    monkeypatch.setattr(RandomForestClassifier, "fit", forbidden)
    monkeypatch.setattr(RandomForestClassifier, "predict_proba", lambda self, x: np.tile([.75, .25], (len(x), 1)))
    assert np.array_equal(d.predict_existing(forest, matrix, RF_PARAMETERS), [.25, .25, .25])
    def mutate(self, x):
        self.estimators_[0] = 'modified'
        return np.tile([.75, .25], (len(x), 1))
    monkeypatch.setattr(RandomForestClassifier, "predict_proba", mutate)
    with pytest.raises(d.InferenceBlocked, match="estimator_mutated"):
        d.predict_existing(forest, matrix, RF_PARAMETERS)


@pytest.mark.parametrize('field', ['features', 'parameters', 'classes', 'tree_count'])
def test_incompatible_estimator_blocked_before_predict(monkeypatch, field):
    forest = fictional_forest()
    if field == 'features': forest.feature_names_in_[0] = 'target_label'
    if field == 'parameters': forest.max_depth = 11
    if field == 'classes': forest.classes_ = np.array([1, 0])
    if field == 'tree_count': forest.estimators_.pop()
    monkeypatch.setattr(RandomForestClassifier, 'predict_proba', lambda *args: pytest.fail('must not predict'))
    with pytest.raises(d.InferenceBlocked):
        d.predict_existing(forest, pd.DataFrame(np.ones((1, 7)), columns=BASE), RF_PARAMETERS)


def test_private_reader_rejects_hash_changes_traversal_and_links(tmp_path):
    file = tmp_path / 'fictional.bin'
    file.write_bytes(b'fictional')
    expected = hashlib.sha256(file.read_bytes()).hexdigest()
    assert d.content(tmp_path, 'fictional.bin', expected) == b'fictional'
    file.write_bytes(b'altered')
    with pytest.raises(d.InferenceBlocked): d.content(tmp_path, 'fictional.bin', expected)
    with pytest.raises(d.InferenceBlocked): d.content(tmp_path, '../fictional.bin')


def test_capture_uses_real_observation_time_never_file_mtime_or_user_backdate(tmp_path, monkeypatch):
    monkeypatch.setattr(d, 'trusted_inputs', lambda root: ({'fictional': 'hash'}, {}, {}))
    monkeypatch.setattr(d, 'static_context', lambda *args: None)
    monkeypatch.setattr(d, 'utc_now', lambda: NOW)
    result = d.capture(tmp_path)
    stored = json.loads((tmp_path / d.POLICY).read_text())
    assert result['static_available_at'] == NOW.isoformat()
    assert stored['historical_availability_accredited'] is False
    assert stored['authorized_models'] == ['A']
    with pytest.raises(d.InferenceBlocked, match='inference_policy_already_exists'): d.capture(tmp_path)
