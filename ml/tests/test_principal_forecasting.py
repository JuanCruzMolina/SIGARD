"""Sólo fixtures generadas: no abre datos, cartografía, A/B ni servicios."""

from copy import deepcopy
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.dataset import FEATURES, build_dataset
from sigard_ml.forecasting.evaluation import count_metrics, evaluate, poisson_presence_diagnostic
from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.prediction import forecast_next_week
from sigard_ml.forecasting.training import (
    baseline_predictions, estimator, matrix, partition, predict, run_experiment, training_labels,
)

START, END = date(2024, 1, 28), date(2024, 8, 11)
VALIDATION, TEST = date(2024, 4, 21), date(2024, 6, 16)
FREEZE = date(2024, 9, 1)


def panel(inputs=None, start=START, end=END):
    return build_dataset(inputs or fictional_inputs(), start=start, end=end, evaluation_as_of=FREEZE)


def experiment(inputs=None, **kwargs):
    return run_experiment(inputs or fictional_inputs(), start=START, end=END,
                          validation_start=VALIDATION, test_start=TEST,
                          evaluation_as_of=FREEZE, **kwargs)


@pytest.fixture(scope="module")
def trained():
    return experiment()


def source_mask(inputs, radio=None, source_week=None):
    return inputs.counts.radio_id.eq(radio or inputs.radios[0]) & inputs.counts.week_start.eq(source_week or START - timedelta(weeks=1))


def test_real_kind_blocked_before_inspecting_any_frame():
    inputs = fictional_inputs()
    inputs.data_kind = "official_observed"
    inputs.counts = object()
    with pytest.raises(ForecastError, match="Uso real bloqueado"):
        panel(inputs)
    with pytest.raises(ForecastError, match="Uso real bloqueado"):
        experiment(inputs)


@pytest.mark.parametrize("change", ["count_negative", "count_fraction", "count_bool", "count_infinite", "count_text", "duplicate", "foreign_radio", "coordinate", "unknown_state", "flag_null", "missing_ref", "real_ref", "invalid_day", "empty_universe", "duplicate_radio", "zero_area", "humidity", "graph_asymmetry", "graph_self", "graph_duplicate", "early_mature", "early_climate"])
def test_input_contract_rejects_invalid_snapshots(change):
    inputs = fictional_inputs()
    if change.startswith("count_"):
        inputs.counts["count"] = inputs.counts["count"].astype(object)
        inputs.counts.loc[0, "count"] = {"count_negative": -1, "count_fraction": 1.5, "count_bool": True, "count_infinite": np.inf, "count_text": "0"}[change]
    elif change == "duplicate":
        inputs.counts = pd.concat([inputs.counts, inputs.counts.iloc[:1]])
    elif change == "foreign_radio":
        inputs.counts.loc[0, "radio_id"] = "fictional_other"
    elif change == "coordinate":
        inputs.counts["latitude"] = 0
    elif change == "unknown_state":
        inputs.counts.loc[0, "state"] = "invented"
    elif change == "flag_null":
        inputs.counts["pending"] = inputs.counts.pending.astype(object)
        inputs.counts.loc[0, "pending"] = None
    elif change in ("missing_ref", "real_ref"):
        inputs.counts.loc[0, "source_ref"] = None if change == "missing_ref" else "real_source"
    elif change == "invalid_day":
        inputs.counts.loc[0, "week_start"] += timedelta(days=1)
    elif change == "empty_universe":
        inputs.radios = ()
    elif change == "duplicate_radio":
        inputs.radios = inputs.radios + inputs.radios[:1]
    elif change == "zero_area":
        inputs.territory.loc[0, "area_km2"] = 0
    elif change == "humidity":
        inputs.climate.loc[0, "humidity"] = 110.0
    elif change == "graph_asymmetry":
        inputs.edges = inputs.edges[:1]
    elif change == "graph_self":
        inputs.edges = ((inputs.radios[0], inputs.radios[0]),)
    elif change == "graph_duplicate":
        inputs.edges += inputs.edges[:1]
    elif change == "early_mature":
        inputs.counts.loc[0, "available_on"] = inputs.counts.loc[0, "week_start"]
    else:
        inputs.climate.loc[0, "available_on"] = inputs.climate.loc[0, "week_start"]
    with pytest.raises(ValueError):
        inputs.validate()


def test_full_grid_exact_horizon_and_no_patient_features():
    inputs = fictional_inputs()
    frame = panel(inputs)
    assert len(frame) == len(inputs.radios) * ((END - START).days // 7 + 1)
    assert not frame.duplicated(["radio_id", "origin_week"]).any()
    assert all(target == origin + timedelta(days=7) for origin, target in zip(frame.origin_week, frame.target_week))
    assert set(matrix(frame)) == set(FEATURES)
    assert not set(FEATURES) & {"radio_id", "target_count", "target_presence", "latitude", "longitude", "target_available_on"}
    assert frame.target_presence.eq(frame.target_count.gt(0).astype(int)).all()


def test_lags_are_exact_and_windows_exclude_origin():
    inputs = fictional_inputs()
    radio = inputs.radios[0]
    mask = inputs.counts.radio_id.eq(radio)
    inputs.counts.loc[mask, "count"] = np.arange(mask.sum())
    row = panel(inputs, START, START).query("radio_id == @radio").iloc[0]
    assert [row[f"cases_lag_{lag}"] for lag in range(1, 5)] == [3, 2, 1, 0]
    assert row.cases_mean_4 == 1.5 and row.cases_trend_1 == 1
    assert row.target_count == 5


@pytest.mark.parametrize("reason", ["missing_row", "unknown", "provisional", "uncovered", "pending", "immature", "late"])
def test_missing_weeks_are_never_shifted_or_imputed_to_zero(reason):
    inputs = fictional_inputs()
    mask = source_mask(inputs)
    if reason == "missing_row":
        inputs.counts = inputs.counts.loc[~mask].copy()
    elif reason in ("unknown", "provisional"):
        inputs.counts.loc[mask, "state"] = reason
    elif reason == "uncovered":
        inputs.counts.loc[mask, "coverage_complete"] = False
    elif reason == "pending":
        inputs.counts.loc[mask, "pending"] = True
    elif reason == "immature":
        inputs.counts.loc[mask, "mature"] = False
    else:
        inputs.counts.loc[mask, "available_on"] = START + timedelta(days=7)
    row = panel(inputs, START, START).iloc[0]
    assert np.isnan(row.cases_lag_1) and np.isnan(row.cases_mean_4)
    assert not row.cases_lag_1_available and np.isfinite(row.cases_lag_2)


def test_observed_zero_is_available_but_unknown_zero_is_not():
    inputs = fictional_inputs()
    mask = source_mask(inputs)
    inputs.counts.loc[mask, "count"] = 0
    row = panel(inputs, START, START).iloc[0]
    assert row.cases_lag_1 == 0 and row.cases_lag_1_available
    inputs.counts.loc[mask, "state"] = "unknown"
    assert np.isnan(panel(inputs, START, START).iloc[0].cases_lag_1)


def test_latest_revision_masks_prior_complete_instead_of_falling_back():
    inputs = fictional_inputs()
    revised = inputs.counts.loc[source_mask(inputs)].copy()
    revised["available_on"] = START + timedelta(days=1)
    revised["state"] = "unknown"
    inputs.counts = pd.concat([inputs.counts, revised], ignore_index=True)
    assert np.isnan(panel(inputs, START, START).iloc[0].cases_lag_1)


def test_future_revision_cannot_change_features_but_can_change_final_outcome():
    inputs = fictional_inputs()
    before = panel(inputs, START, START)
    revision = inputs.counts.loc[inputs.counts.week_start.isin([START - timedelta(weeks=1), START + timedelta(weeks=1)])].copy()
    revision["available_on"] = date(2024, 7, 1)
    revision["count"] = 900
    inputs.counts = pd.concat([inputs.counts, revision], ignore_index=True)
    after = panel(inputs, START, START)
    pd.testing.assert_frame_equal(matrix(before), matrix(after))
    assert after.target_count.eq(900).all()
    assert before.target_count.ne(after.target_count).any()


def test_training_labels_use_historical_version_not_the_final_revision():
    inputs = fictional_inputs()
    frame = panel(inputs, START, START)
    revision = inputs.counts.loc[inputs.counts.week_start.eq(START + timedelta(weeks=1))].copy()
    revision["available_on"] = date(2024, 7, 1)
    revision["count"] = 999
    inputs.counts = pd.concat([inputs.counts, revision], ignore_index=True)
    final = panel(inputs, START, START)
    assert final.target_count.eq(999).all()
    historical = training_labels(final, inputs, date(2024, 3, 1))
    assert historical.target_count.tolist() == frame.target_count.tolist()


def test_target_unknown_preserves_grid_and_blocks_capital_total():
    inputs = fictional_inputs()
    inputs.counts.loc[source_mask(inputs, source_week=START + timedelta(weeks=1)), "coverage_complete"] = False
    frame = panel(inputs, START, START)
    assert len(frame) == 3 and frame.target_count.isna().sum() == 1
    row = frame.loc[frame.target_count.isna()].iloc[0]
    assert row.target_state == "unknown" and pd.isna(row.target_presence)
    assert not row.target_coverage_complete and row.target_snapshot_available_on is not None
    scored = frame.loc[frame.target_count.notna()]
    metrics = evaluate(scored, np.ones(len(scored)), inputs.radios)
    assert metrics["capital"] is None
    assert metrics["weekly"][0]["actual_total"] is None
    assert metrics["weekly"][0]["eligible_radios"] == 2


@pytest.mark.parametrize("unit", ["notifications", "records", "presence", "outbreak_risk"])
def test_other_targets_are_not_silently_accepted(unit):
    inputs = fictional_inputs()
    inputs.count_unit = unit
    with pytest.raises(ForecastError, match="No confundir"):
        inputs.validate()


def test_climate_excludes_future_and_unavailable_or_partial_weeks():
    inputs = fictional_inputs()
    before = panel(inputs, START, START)
    inputs.climate.loc[inputs.climate.week_start.ge(START), "temperature"] = 999.0
    pd.testing.assert_frame_equal(matrix(before), matrix(panel(inputs, START, START)))
    inputs.climate.loc[inputs.climate.week_start.eq(START - timedelta(weeks=1)), "available_on"] = START + timedelta(days=7)
    row = panel(inputs, START, START).iloc[0]
    assert np.isnan(row.temperature_lag_1) and np.isnan(row.temperature_mean_4)
    inputs.climate.loc[inputs.climate.week_start.eq(START - timedelta(weeks=2)), "complete"] = False
    assert np.isnan(panel(inputs, START, START).iloc[0].precipitation_sum_4)


def test_context_and_graph_require_historical_availability():
    inputs = fictional_inputs()
    inputs.territory["available_on"] = START + timedelta(weeks=1)
    inputs.graph_available_on = START + timedelta(weeks=1)
    frame = panel(inputs, START, START)
    assert frame[["population", "area_km2", "population_density", "neighbor_count", "neighbor_cases_mean_lag_1"]].isna().all().all()
    assert all(row["territory"] is None and row["graph"] is None for row in frame.provenance)


def test_neighbor_aggregation_requires_all_neighbors_known():
    inputs = fictional_inputs()
    inputs.counts.loc[source_mask(inputs, inputs.radios[2]), "state"] = "unknown"
    frame = panel(inputs, START, START).set_index("radio_id")
    assert np.isnan(frame.loc[inputs.radios[1], "neighbor_cases_mean_lag_1"])
    assert np.isfinite(frame.loc[inputs.radios[0], "neighbor_cases_mean_lag_1"])


def test_calendar_2025_week53_to_2026_week1():
    inputs = fictional_inputs(weeks=5)
    delta = date(2025, 12, 7) - date(2023, 12, 31)
    for frame in (inputs.counts, inputs.climate):
        for column in ("week_start", "available_on"):
            frame[column] = frame[column].map(lambda value: value + delta)
    frame = build_dataset(inputs, start=date(2025, 12, 28), end=date(2026, 1, 4), evaluation_as_of=date(2026, 2, 1))
    first = frame.iloc[0]
    assert first.origin_year == 2025 and first.origin_week_number == 53
    assert first.target_year == 2026 and first.target_week_number == 1
    assert first.target_week == date(2026, 1, 4)
    assert frame.iloc[-1].origin_week_number == 1


def test_temporal_partitions_purge_crossings_and_keep_radios_together():
    frame = panel()
    frame["partition"] = partition(frame, VALIDATION, TEST)
    assert frame.groupby("origin_week").partition.nunique().eq(1).all()
    assert frame.loc[frame.partition.eq("train"), "target_end"].max() < VALIDATION
    validation = frame.loc[frame.partition.eq("validation")]
    assert validation.origin_week.min() == VALIDATION and validation.target_end.max() < TEST
    assert frame.loc[frame.partition.eq("test"), "origin_week"].min() == TEST
    assert frame.loc[frame.partition.eq("purged"), "origin_week"].unique().tolist() == [VALIDATION - timedelta(weeks=1), TEST - timedelta(weeks=1)]


@pytest.mark.parametrize("validation,test", [(TEST, VALIDATION), (VALIDATION, VALIDATION), (date(2023, 1, 1), TEST), (VALIDATION + timedelta(days=1), TEST)])
def test_invalid_or_empty_temporal_splits_are_rejected(validation, test):
    with pytest.raises(ValueError):
        partition(panel(), validation, test)


def test_unknown_only_outcomes_cannot_train():
    inputs = fictional_inputs()
    inputs.counts["state"] = "unknown"
    with pytest.raises(ForecastError, match="Sin observaciones elegibles"):
        experiment(inputs)


def test_outcome_freeze_cannot_precede_origin_cutoff():
    with pytest.raises(ForecastError, match="Congelamiento"):
        build_dataset(fictional_inputs(), start=START, end=END, evaluation_as_of=START)


def test_outcome_unavailable_at_fit_is_excluded():
    inputs = fictional_inputs()
    inputs.counts.loc[inputs.counts.week_start.eq(date(2024, 2, 4)), "available_on"] = FREEZE
    fitted_rows = training_labels(panel(inputs), inputs, VALIDATION + timedelta(days=6))
    assert not fitted_rows.target_week.eq(date(2024, 2, 4)).any()


def test_preprocessing_fits_training_only_and_boosting_has_no_random_validation():
    train = pd.DataFrame({feature: [0., 1., 2.] for feature in FEATURES})
    model = estimator("poisson_glm")
    model.fit(train, [0, 1, 2])
    means = model.named_steps["standardscaler"].mean_.copy()
    model.predict(train + 1)
    np.testing.assert_array_equal(model.named_steps["standardscaler"].mean_, means)
    assert estimator("poisson_boosting").steps[-1][1].early_stopping is False


def test_end_to_end_baselines_use_identical_eligible_test_rows(trained):
    report = trained.report
    n = report["rows"]["test"]
    assert n > 0 and not report["real_training_enabled"] and not report["scientific_performance"]
    for comparison in report["test"].values():
        assert comparison["territorial"]["n"] == n
        assert sum(row["n"] for row in comparison["per_radio"].values()) == n
        assert comparison["territorial"]["mae"] >= 0
        for row in comparison["weekly"]:
            assert row["complete"] and row["eligible_radios"] == 3
    json.dumps(report, allow_nan=False)


def test_reproducibility_without_reusing_any_trained_artifact(trained):
    repeated = experiment()
    assert repeated.report == trained.report
    np.testing.assert_array_equal(predict(repeated.fitted.model, repeated.panel), predict(trained.fitted.model, trained.panel))


def test_test_outcomes_cannot_select_or_fit_model(trained):
    inputs = fictional_inputs()
    inputs.counts.loc[inputs.counts.week_start.ge(TEST + timedelta(weeks=1)), "count"] = 100
    changed = experiment(inputs)
    assert changed.fitted.model_id == trained.fitted.model_id
    assert changed.report["selected"] == trained.report["selected"]
    assert changed.report["candidates"] == trained.report["candidates"]
    assert changed.report["test"]["model"]["territorial"]["mae"] != trained.report["test"]["model"]["territorial"]["mae"]


def test_zero_only_training_has_explicit_safe_null_model():
    inputs = fictional_inputs()
    inputs.counts["count"] = 0
    result = experiment(inputs)
    assert result.report["test"]["model"]["territorial"]["mae"] == 0
    assert result.report["test"]["model"]["territorial"]["mae_positive"] is None
    assert result.report["test"]["model"]["territorial"]["poisson_deviance"] is None
    assert np.equal(predict(result.fitted.model, result.panel), 0).all()


def test_persistence_fallback_does_not_fill_unknown_labels(trained):
    train = trained.panel.loc[trained.panel.partition.eq("train")].copy()
    frame = trained.panel.iloc[:3].copy()
    frame["cases_lag_1"] = np.nan
    frame["target_count"] = np.nan
    predictions = baseline_predictions(train, frame)
    np.testing.assert_array_equal(predictions["training_radio_mean"], predictions["lag_1_or_training_mean"])
    assert frame.target_count.isna().all()


def test_metrics_have_known_answers_and_probability_is_only_a_diagnostic():
    result = count_metrics([0, 2], [1, 1])
    assert result["mae"] == 1 and result["rmse"] == 1 and result["mean_bias"] == 0
    assert result["mae_positive"] == 1
    assert count_metrics([0, 0], [0, 0])["mae_positive"] is None
    diagnostic = poisson_presence_diagnostic([0, 1], [0, np.log(2)])
    assert diagnostic["brier"] == pytest.approx(0.125)
    assert not diagnostic["probabilities_accredited"]


@pytest.mark.parametrize("actual,predicted", [([1], [-1]), ([1], [np.nan]), ([1], [np.inf]), ([np.nan], [1]), ([], []), ([1.5], [1])])
def test_metrics_reject_invalid_values(actual, predicted):
    with pytest.raises(ValueError):
        count_metrics(actual, predicted)


def test_forecast_output_contract_and_capital_coherence(trained):
    output = forecast_next_week(trained.fitted, fictional_inputs(), as_of=date(2024, 9, 8))
    assert output["status"] == "available_simulation_only"
    assert output["origin_week"] == "2024-09-01" and output["target_week"] == "2024-09-08"
    assert output["horizon_weeks"] == 1 and not output["real_forecast"]
    assert output["expected_capital_count"] == sum(row["expected_count"] for row in output["radios"])
    assert all(row["expected_count"] >= 0 and row["presence_probability"] is None and row["prediction_interval"] is None for row in output["radios"])
    means = [row["expected_count"] for row in output["radios"]]
    assert means == sorted(means, reverse=True)
    assert output["uncertainty"]["interval"] is None
    json.dumps(output, allow_nan=False)


def test_forecast_missing_latest_history_blocks_instead_of_dating_old_origin_as_current(trained):
    inputs = fictional_inputs()
    inputs.counts.loc[source_mask(inputs, source_week=date(2024, 8, 25)), "state"] = "unknown"
    output = forecast_next_week(trained.fitted, inputs, as_of=date(2024, 9, 8))
    assert output["status"] == "blocked_missing_recent_counts"
    assert output["origin_week"] == "2024-09-01"
    assert output["expected_capital_count"] is None
    assert all(row["expected_count"] is None for row in output["radios"])


def test_forecast_far_future_blocks_and_cannot_look_back_before_model_fit(trained):
    output = forecast_next_week(trained.fitted, fictional_inputs(), as_of=date(2026, 10, 21))
    assert output["status"] == "blocked_missing_recent_counts"
    with pytest.raises(ForecastError, match="después del origen"):
        forecast_next_week(trained.fitted, fictional_inputs(), as_of=date(2024, 3, 1))


def test_forecast_rejects_other_version_or_territorial_order(trained):
    inputs = fictional_inputs()
    inputs.dataset_version = "fictional_other_v2"
    with pytest.raises(ForecastError, match="incompatible"):
        forecast_next_week(trained.fitted, inputs, as_of=date(2024, 9, 8))


def test_inputs_not_mutated_and_no_source_or_model_io(monkeypatch):
    inputs = fictional_inputs()
    original = deepcopy(inputs)

    def forbidden(*args, **kwargs):
        pytest.fail("Se intentó IO sobre fuentes o modelos")

    monkeypatch.setattr(pd, "read_parquet", forbidden)
    monkeypatch.setattr(pd, "read_excel", forbidden)
    monkeypatch.setattr(pd, "read_csv", forbidden)
    import joblib
    monkeypatch.setattr(joblib, "load", forbidden)
    monkeypatch.setattr(joblib, "dump", forbidden)
    experiment(inputs)
    for name in ("counts", "climate", "territory"):
        pd.testing.assert_frame_equal(getattr(inputs, name), getattr(original, name))


def test_input_row_order_cannot_change_snapshot_features_or_labels():
    inputs = fictional_inputs()
    original = panel(inputs)
    for name in ("counts", "climate", "territory"):
        setattr(inputs, name, getattr(inputs, name).sample(frac=1, random_state=123).reset_index(drop=True))
    pd.testing.assert_frame_equal(panel(inputs), original)


def test_cli_requires_explicit_fictional_mode_and_accepts_no_input_paths(monkeypatch):
    from sigard_ml.forecasting.__main__ import main
    for arguments in ([], ["--fictional-demo", "--input", "forbidden"]):
        monkeypatch.setattr("sys.argv", ["forecasting", *arguments])
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
