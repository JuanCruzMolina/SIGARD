"""Regresiones V2 con radios, permisos y conteos generados ficticios en memoria."""

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.adapter import SNAPSHOT_SCHEMA, EvidenceDocument, adapt_derived
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.dataset import FEATURES, build_dataset
from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.local_query import query_predictions
from sigard_ml.forecasting import local_query
from sigard_ml.forecasting.v2 import snapshot_grid, select_candidate, run_counts, run_presence, fit_count, EmptyFeatureFallback
from sigard_ml.official.epidemiological_preflight.evidence import canonical_bytes
from test_provisional_aggregate_experiment import bundle, seal


START, END = date(2024, 1, 28), date(2024, 12, 1)
VALIDATION, TEST, REVIEW = date(2024, 6, 2), date(2024, 9, 1), date(2026, 10, 24)


def snapshot_bundle():
    data = bundle()
    original = fictional_inputs(weeks=50)
    data.update(schema_version=SNAPSHOT_SCHEMA, data_kind="epidemiological_snapshot_scenario",
        count_unit="snapshot_record_count", target_definition="principal-confirmed-snapshot-2",
        period_end="2024-12-08")
    counts = {(r.radio_id, r.week_start): r.count for r in original.counts.itertuples()}
    dates = sorted(original.climate.week_start.unique())
    data["counts"] = [dict(radio_id=radio, week_start=str(target), available_on=None,
        count=counts.get((radio, target), 0) if radio != "fictional_empty_0" else None,
        state="provisional" if radio != "fictional_empty_0" else "unknown",
        pending=radio == "fictional_empty_0", mature=False, coverage_complete=False,
        source_ref="fictional_counts", label_kind="snapshot_record_count" if radio != "fictional_empty_0" else "unknown",
        partial_week=False) for radio in data["radios"] for target in dates]
    data["climate"] = [dict(week_start=str(r.week_start), available_on=None, temperature=r.temperature,
        humidity=r.humidity, precipitation=r.precipitation, complete=True, partial_week=False,
        source_ref="fictional_climate") for r in original.climate.itertuples()]
    data["snapshot_scenario"] = dict(scenario_id="confirmed-snapshot-observed-weeks-2", covered_weeks=[str(w) for w in dates],
        zero_meaning="no_record_in_filtered_snapshot_not_epidemiological_absence", quality_masks_sha256="a"*64,
        declaration_ref="fictional_snapshot_declaration", special_2022_policy="excluded_separate_not_confirmed_or_negative")
    return data


def adapt_snapshot(data=None):
    data = data or snapshot_bundle()
    raw, registry, request, documents = seal(data)
    for reference, artifact in list(documents.items()):
        document = json.loads(artifact.content)
        document["scope"]["snapshot_scenario"] = data["snapshot_scenario"]
        if reference == request.decision_ref:
            document.update(conditional_on_observed_cells=False, snapshot_zero_assumption_accepted=True,
                            local_retrospective_query_authorized=True)
        content = canonical_bytes(document)
        documents[reference] = EvidenceDocument(content, hashlib.sha256(content).hexdigest())
    return adapt_derived(raw, registry, request, documents=documents)


def test_snapshot_retains_zero_assumption_unknowns_and_no_future_feature_leakage():
    data = snapshot_bundle()
    inputs = adapt_snapshot(data)
    before = build_dataset(inputs, start=START, end=TEST, evaluation_as_of=REVIEW, horizon_weeks=4,
                           origin_weeks=[START, TEST])
    assert before.target_count.eq(0).any() and before.target_count.isna().any()
    assert before.target_state.eq("snapshot_record_count").any()
    assert before.target_week.iloc[0] == START + timedelta(weeks=4)
    for row in data["counts"]:
        if date.fromisoformat(row["week_start"]) > TEST and row["count"] is not None:
            row["count"] += 100
    after = build_dataset(adapt_snapshot(data), start=START, end=TEST, evaluation_as_of=REVIEW, horizon_weeks=4,
                          origin_weeks=[START, TEST])
    assert np.allclose(before[list(FEATURES)], after[list(FEATURES)], equal_nan=True)
    assert not inputs.counts.coverage_complete.any() and not inputs.counts.mature.any()


@pytest.mark.parametrize("change", ["pending_zero", "unknown_value", "outside_coverage", "2022", "absence_claim"])
def test_snapshot_controls_reject_fabricated_labels_or_coverage(change):
    data = snapshot_bundle()
    if change == "pending_zero": data["counts"][0].update(count=0, pending=True)
    elif change == "unknown_value": data["counts"][0].update(state="unknown", label_kind="unknown", count=3)
    elif change == "outside_coverage": data["snapshot_scenario"]["covered_weeks"].pop()
    elif change == "2022": data["snapshot_scenario"]["covered_weeks"][0] = "2022-01-02"
    elif change == "absence_claim": data["snapshot_scenario"]["zero_meaning"] = "verified_no_dengue"
    with pytest.raises(ForecastError):
        adapt_snapshot(data)


def test_grid_masks_preserve_recorded_counts_and_do_not_fill_unknown():
    radios = [f"fictional_{i}" for i in range(256)]
    target = date(2024, 3, 3)
    positive = pd.DataFrame([dict(radio_id=radios[0], week_start=target, provisional_positive_records=5,
                                 source_id="fictional_source", source_version="fictional_v1")])
    quality = pd.DataFrame([dict(radio_id=r, week_start=target, pending_mentions=int(i in (0, 1)),
                                approximate_date_records=int(i == 2), partial_week=False) for i, r in enumerate(radios)])
    frame = snapshot_grid(positive, quality, radios, [target]).set_index("radio_id")
    assert len(frame) == 256 and frame.recorded_positive_count.sum() == 5
    assert pd.isna(frame.loc[radios[0], "snapshot_count"])
    assert pd.isna(frame.loc[radios[1], "snapshot_count"])
    assert pd.isna(frame.loc[radios[2], "snapshot_count"])
    assert frame.loc[radios[3], "snapshot_count"] == 0
    assert not frame.zero_is_epidemiological_absence.any()
    quality.loc[0, "pending_mentions"] = -1
    with pytest.raises(ForecastError):
        snapshot_grid(positive, quality, radios, [target])


def test_selection_does_not_promote_lower_mae_with_much_worse_rmse_or_bias():
    baseline = dict(mae=1., rmse=2., mean_bias=.1, high_count={"mae": 2.}, weekly_known_subset_rmse=10.)
    misleading = dict(baseline, mae=.5, rmse=3., mean_bias=-1.)
    selected, scores = select_candidate({"poisson_boosting": misleading, "lag_1_or_training_mean": baseline}, 2.)
    assert selected == "lag_1_or_training_mean" and not scores["poisson_boosting"]["guardrails_passed"]


def test_native_count_variant_handles_training_columns_entirely_unknown():
    frame = pd.DataFrame({feature: np.arange(40, dtype=float) for feature in FEATURES})
    frame["neighbor_cases_mean_lag_1"] = np.nan
    frame["radio_id"] = "fictional_0"
    frame["target_count"] = np.tile([1, 2], 20)
    frame["target_end"] = date(2024, 3, 2)
    fitted = fit_count("poisson_native", frame)
    assert np.isfinite(fitted.predict_frame(frame)).all()
    transformer = EmptyFeatureFallback().fit(frame[list(FEATURES)])
    after = frame[list(FEATURES)].copy()
    after["cases_lag_1"] = np.nan
    transformed = transformer.transform(after)
    assert transformed.cases_lag_1.isna().all()
    assert transformed.neighbor_cases_mean_lag_1.eq(0).all()


def run(data):
    return run_counts(adapt_snapshot(data), start=START, end=END, validation_start=VALIDATION,
        test_start=TEST, evaluation_as_of=REVIEW)


def test_temporal_selection_calibration_and_private_date_query():
    result = run(snapshot_bundle())
    assert all(f["training_target_end"] < f["validation_first_origin"] for f in result["report"]["folds"])
    assert not result["report"]["comparison_is_independent_test"]
    presence = run_presence(result)
    assert presence["report"]["calibration_cutoff"] < min(result["comparison"].origin_week).isoformat()
    assert not presence["report"]["probability_calibrated_claim"]
    frame = presence["territory"]
    target = min(frame.target_week)
    query = query_predictions(frame, target_date=target, as_of=REVIEW)
    assert len(query["radios"]) == 256 and query["retrospective"]
    assert query["expected_territorial_total"] == pytest.approx(frame.loc[frame.target_week.eq(target), "expected_count"].sum())
    assert query_predictions(frame, target_date="2026-10-26", as_of=REVIEW)["status"] == "insufficient_origin_data"
    assert query_predictions(frame, target_date=target, horizon_weeks=4, as_of=REVIEW)["status"] == "unavailable_horizon"


def test_comparison_labels_do_not_select_or_fit_v2():
    data = snapshot_bundle()
    before = run(data)
    changed = deepcopy(data)
    for row in changed["counts"]:
        if date.fromisoformat(row["week_start"]) >= TEST and row["count"] is not None:
            row["count"] += 10
    after = run(changed)
    assert before["report"]["selected"] == after["report"]["selected"]
    assert before["report"]["validation"] == after["report"]["validation"]
    assert np.array_equal(before["fitted"].predict_frame(before["development"]), after["fitted"].predict_frame(before["development"]))


def test_private_reader_checks_integrity_without_loading_executable_models(tmp_path, monkeypatch):
    monkeypatch.setattr(local_query, "__file__", str(tmp_path / "ml/src/sigard_ml/forecasting/local_query.py"))
    directory = tmp_path / "ml/artifacts/official/sigard-principal-v2-experimental"
    directory.mkdir(parents=True)
    path = directory / "territorial_predictions.private.parquet"
    pd.DataFrame({"fictional": [1]}).to_parquet(path)
    manifest = {"outputs_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}}
    (directory / "manifest.private.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert local_query.load_predictions(directory).fictional.tolist() == [1]
    path.write_bytes(path.read_bytes() + b"fictional_tamper")
    with pytest.raises(ForecastError, match="Integridad"):
        local_query.load_predictions(directory)
    with pytest.raises(ForecastError, match="privados"):
        local_query.load_predictions(tmp_path / "frontend/public")
