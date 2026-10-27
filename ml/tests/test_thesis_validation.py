"""Fictional paired errors and quarantined future packages; no fitting or real IO."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import json

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn

from sigard_ml.forecasting import independent_evaluation as future
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.thesis_validation import (
    FrozenArtifact, METHODS, block_interval, compare, digest, paired_frame, week_statistics,
)
from sigard_ml.forecasting.v3 import CANDIDATES, FEATURES, VERSION


def paired():
    rows = []
    for w in range(12):
        target = date(2025, 2, 2) + timedelta(weeks=w)
        for radio in ("fictional_a", "fictional_b"):
            rows.append(dict(radio_id=radio, origin_week=target-timedelta(weeks=1), target_week=target,
                             target_count=float(w % 3), ml=float(w % 3)+.2, ref=float(w % 3)+.8))
    return pd.DataFrame(rows)


def test_week_cluster_bootstrap_exact_constant_gain_and_rmse():
    frame = paired()
    weekly = week_statistics(frame, "ml", "ref")
    ci = block_interval(weekly, 3, resamples=400)
    assert np.allclose(ci["intervals"]["mae"], [-.6, -.6])
    assert np.allclose(ci["intervals"]["rmse"], [-.6, -.6])
    duplicated = pd.concat([frame, frame.assign(radio_id=frame.radio_id+"_duplicate")])
    assert block_interval(week_statistics(duplicated, "ml", "ref"), 3, resamples=400) == ci


def test_gaps_and_folds_define_runs_and_seed_is_reproducible():
    frame = paired()
    frame["fold"] = np.repeat([0, 1], 12)
    frame = frame.loc[frame.target_week != date(2025, 2, 16)]
    weekly = week_statistics(frame, "ml", "ref")
    a = block_interval(weekly, 4, resamples=200)
    assert a == block_interval(weekly, 4, resamples=200)
    assert a["run_weeks"] == [2, 3, 6]


def test_unknowns_excluded_identically_but_missing_predictions_rejected():
    frame = paired()
    frame.loc[0, "target_count"] = np.nan
    result = paired_frame(frame, 1, ("ml", "ref"))
    assert len(result) == len(frame)-1 and not result.target_count.isna().any()
    frame.loc[1, "ml"] = np.nan
    with pytest.raises(ForecastError):
        paired_frame(frame, 1, ("ml", "ref"))
    with pytest.raises(ForecastError):
        paired_frame(pd.concat([result, result.head(1)]), 1, ("ml", "ref"))


def test_outlier_sensitivity_and_rmse_use_squared_error_totals():
    frame = paired()
    frame.loc[frame.target_week == frame.target_week.max(), "ml"] = 20.
    report = compare(frame, "ml", "ref", high_threshold=1., horizon=1, resamples=200)
    assert report["delta_mae"] > 0 and report["delta_rmse"] > 0
    assert report["wins_ml"] == 11 and report["wins_persistence"] == 1


def incoming():
    radios = ["fictional_a", "fictional_b"]
    rows = []
    for h in (1, 2, 4):
        for w in range(8):
            origin = date(2025, 2, 2) + timedelta(weeks=w)
            cutoff = origin + timedelta(days=6)
            for radio in radios:
                features = dict.fromkeys(FEATURES, None)
                features["count_origin"] = 1.
                lineage = dict.fromkeys(FEATURES, None)
                lineage["count_origin"] = dict(max_event_week=origin.isoformat(), available_on=cutoff.isoformat(),
                                                source_ref="fictional_closed_snapshot")
                rows.append(dict(radio_id=radio, horizon=h, origin_week=origin.isoformat(),
                    target_week=(origin+timedelta(weeks=h)).isoformat(), cutoff_date=cutoff.isoformat(),
                    features=features, lineage=lineage))
    return dict(schema=future.SCHEMA, unit="snapshot_record_count", territory_version=future.TERRITORY,
                target_definition=future.DEFINITION, feature_rule=future.FEATURE_RULE, model_version=VERSION,
                source_version="fictional_authorized_delivery", feature_order=list(FEATURES), radios=radios, rows=rows,
                zero_meaning="no_record_in_filtered_snapshot_not_epidemiological_absence",
                availability_evidence_ref="fictional_availability", preparation_review_ref="fictional_preparer")


@pytest.mark.parametrize("defect", ["future_event", "late_availability", "territory", "target", "duplicate", "lag", "infinity"])
def test_future_panel_rejects_leakage_and_incompatibility(defect):
    payload = incoming()
    row = payload["rows"][0]
    if defect == "future_event":
        row["lineage"]["count_origin"]["max_event_week"] = row["target_week"]
    elif defect == "late_availability":
        row["lineage"]["count_origin"]["available_on"] = row["target_week"]
    elif defect == "territory":
        payload["territory_version"] = "fictional_wrong_version"
    elif defect == "target":
        row["target_week"] = "2025-02-10"
    elif defect == "duplicate":
        payload["rows"].append(deepcopy(row))
    elif defect == "lag":
        row["features"]["cases_lag_1"] = 1.
        row["lineage"]["cases_lag_1"] = deepcopy(row["lineage"]["count_origin"])
    else:
        row["features"]["count_origin"] = float("inf")
    with pytest.raises(ForecastError):
        future.validate_panel(payload, radios=payload["radios"], last_seen=date(2024, 12, 29))


@dataclass
class FrozenFictionalModel:
    horizon_weeks: int
    fit_cutoff: date = date(2024, 12, 28)

    def predict_frame(self, frame):
        return frame.count_origin.to_numpy(float) * .5


def write(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def authorized(path, payload, purpose):
    write(path, dict(status="approved", purpose=purpose, payload_sha256=digest(payload),
        source_version="fictional_authorized_delivery", authorization_basis="project_owner_declared_provision",
        reviewer_ref="fictional_custodian", authorization_ref="fictional_permission", limits="fictional_test_only",
        decided_on="2025-01-01", training_embargo=True, previously_used_or_reviewed=False, local_only=True))


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(future, "ROOT", tmp_path)
    directory = tmp_path / "ml/artifacts/official" / VERSION
    monkeypatch.setattr(future, "DEFAULT_ARTIFACT", directory)
    directory.mkdir(parents=True)
    (directory / "implementation").mkdir()
    for name in ("v3.py", "v2.py", "contracts.py"):
        (directory / "implementation" / name).write_bytes(future.Path(future.__file__).with_name(name).read_bytes())
    write(directory / "configuration.private.json", dict(versions=dict(sklearn=sklearn.__version__,
        numpy=np.__version__, pandas=pd.__version__, joblib=joblib.__version__)))
    write(directory / "provenance.private.json", dict(source_input_evidence=dict(snapshot_scenario=dict(covered_weeks=["2024-12-29"]))))
    write(directory / "selection.private.json", dict(horizons={str(h): dict(best_ml=CANDIDATES[0]) for h in (1,2,4)}))
    panel = paired().rename(columns={"ml":"count_origin"})
    panel["target_week"], panel["partition"], panel["predictor_admissible"] = date(2024, 12, 29), "train", True
    for h in (1,2,4):
        folder = directory / f"horizon_{h}"
        folder.mkdir()
        panel.to_parquet(folder / "modeling_panel.private.parquet", index=False)
        joblib.dump(dict(counts={name:FrozenFictionalModel(h) for name in METHODS}), folder / "models.private.joblib")
    write(directory / "manifest.private.json", dict(artifact_version=VERSION, outputs_sha256={
        p.relative_to(directory).as_posix():digest(p) for p in directory.rglob("*") if p.is_file()}))
    private = tmp_path / "data/interim/fictional"
    private.mkdir(parents=True)
    return directory, private


def prepared_score(frozen):
    directory, private = frozen
    features, auth, output = private / "features.json", private / "permission.json", private / "sealed"
    payload = incoming()
    write(features, payload)
    authorized(auth, features, "independent_features")
    before = {p: digest(p) for p in directory.rglob("*") if p.is_file()}
    receipt = future.seal(features, auth, output, directory)
    assert receipt["phase"] == "sealed_without_labels" and receipt["training_embargo"]
    predictions = pd.read_parquet(output / "predictions.private.parquet")
    rows = [dict(radio_id=r, target_week=str(t), target_count=0., state="usable_snapshot",
                 available_on=str(t+timedelta(days=6)), source_ref="fictional_label")
            for r,t in sorted(set(predictions[["radio_id","target_week"]].itertuples(index=False,name=None)))]
    rows[0].update(target_count=None, state="unknown", available_on=None)
    labels, label_auth = private / "labels.json", private / "labels-permission.json"
    write(labels, dict(schema=future.SCHEMA, unit="snapshot_record_count", target_definition=future.DEFINITION,
                       territory_version=future.TERRITORY, source_version="fictional_authorized_delivery",
                       seal_sha256=digest(output / "seal.private.json"), rows=rows))
    authorized(label_auth, labels, "independent_labels")
    return directory, output, labels, label_auth, before


def test_future_end_to_end_seals_without_labels_then_scores_no_training(frozen):
    directory, output, labels, label_auth, before = prepared_score(frozen)
    report = future.score(labels, label_auth, output)
    assert not report["retrained"] and report["training_embargo"]
    assert report["horizons"]["1"]["excluded_unknown"] == 1
    assert {p:digest(p) for p in before} == before
    assert (output / "report.private.md").exists() and (output / "completion.private.json").exists()
    with pytest.raises(ForecastError, match="ya terminada"):
        future.score(labels, label_auth, output)


@pytest.mark.parametrize("defect", ["unknown_as_zero", "missing_keys", "fractional", "future_label", "seal", "predictions"])
def test_scoring_fails_closed_without_releasing_training_embargo(frozen, defect):
    _, output, labels, label_auth, _ = prepared_score(frozen)
    payload = json.loads(labels.read_text(encoding="utf-8"))
    if defect == "unknown_as_zero":
        payload["rows"][0]["target_count"] = 0
    elif defect == "missing_keys":
        payload["rows"].pop()
    elif defect == "fractional":
        payload["rows"][1]["target_count"] = .5
    elif defect == "future_label":
        payload["rows"][1]["available_on"] = "2099-01-01"
    elif defect == "seal":
        payload["seal_sha256"] = "0"*64
    else:
        with (output / "predictions.private.parquet").open("ab") as stream:
            stream.write(b"fictional_tamper")
    write(labels, payload)
    authorized(label_auth, labels, "independent_labels")
    with pytest.raises(ForecastError):
        future.score(labels, label_auth, output)
    assert not (output / "completion.private.json").exists()
    assert json.loads((output / "seal.private.json").read_text())["training_embargo"] is True


def test_permissions_and_integrity_fail_before_loading_models(frozen):
    directory, private = frozen
    features, auth = private / "features.json", private / "permission.json"
    write(features, incoming())
    authorized(auth, features, "independent_features")
    record = json.loads(auth.read_text())
    record["previously_used_or_reviewed"] = True
    write(auth, record)
    with pytest.raises(ForecastError, match="exposición"):
        future.seal(features, auth, private / "denied", directory)
    assert not (private / "denied").exists()
    artifact = FrozenArtifact(directory)
    (directory / "horizon_1/models.private.joblib").write_bytes(b"fictional_tampered_not_a_pickle")
    with pytest.raises(ForecastError, match="Integridad"):
        artifact.path("horizon_1/models.private.joblib")


def test_feature_mutation_during_prediction_cannot_be_sealed(frozen, monkeypatch):
    directory, private = frozen
    features, auth = private / "features.json", private / "permission.json"
    write(features, incoming())
    authorized(auth, features, "independent_features")

    def mutating_predict(self, frame):
        write(features, {"fictional_unapproved_change": True})
        return frame.count_origin.to_numpy(float) * .5

    monkeypatch.setattr(FrozenFictionalModel, "predict_frame", mutating_predict)
    with pytest.raises(ForecastError, match="durante la inferencia"):
        future.seal(features, auth, private / "must_not_seal", directory)
    assert not (private / "must_not_seal").exists()
