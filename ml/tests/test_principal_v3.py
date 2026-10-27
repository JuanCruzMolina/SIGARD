"""V3: fixtures totalmente ficticias y selección aislada de la comparación."""
from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pytest

from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.dataset import build_dataset
from sigard_ml.forecasting.training import partition
from sigard_ml.forecasting.v3 import (CANDIDATES, FEATURES, choose_threshold, feature_frame,
    fit_models, fit_final, presence_summary, validate_development)
from test_principal_v2 import adapt_snapshot, snapshot_bundle

START, END, VALIDATION, TEST, REVIEW = date(2024,1,28), date(2024,12,1), date(2024,6,2), date(2024,9,1), date(2026,10,24)


def prepared(data=None,horizon=1):
    inputs=adapt_snapshot(data or snapshot_bundle())
    end=END-timedelta(weeks=horizon-1)
    frame=build_dataset(inputs,start=START,end=end,evaluation_as_of=REVIEW,horizon_weeks=horizon)
    frame["partition"]=partition(frame,VALIDATION,TEST)
    frame["predictor_admissible"]=True
    return inputs,frame


@pytest.mark.parametrize("horizon",[1,2,4])
def test_features_use_only_origin_or_earlier_and_preserve_unknown_labels(horizon):
    data=snapshot_bundle()
    inputs,frame=prepared(data,horizon)
    before=feature_frame(inputs,frame,horizon)
    changed=deepcopy(data)
    for row in changed["counts"]:
        if date.fromisoformat(row["week_start"])>TEST and row["count"] is not None: row["count"]+=100
    after=feature_frame(adapt_snapshot(changed),frame,horizon)
    past=before.origin_week.le(TEST)
    assert np.allclose(before.loc[past,list(FEATURES)],after.loc[past,list(FEATURES)],equal_nan=True)
    assert before.target_count.equals(frame.target_count)
    assert before.target_count.isna().any() and before.target_count.eq(0).any()
    assert all(before.target_week-before.origin_week==timedelta(weeks=horizon))
    assert not set(FEATURES)&{"target_count","target_week","radio_id","target_presence"}


def test_threshold_comes_from_training_data_instead_of_default_half():
    y=np.array([0,0,0,0,1,1])
    scores=np.array([.01,.02,.03,.04,.10,.15])
    threshold,rows=choose_threshold(y,scores)
    assert threshold is not None and threshold!=.5
    assert max(row["f1"] for row in rows)>0
    assert choose_threshold(np.zeros(6),scores)[0] is None


def test_walk_forward_calibration_and_all_three_candidates_are_reproducible(tmp_path):
    inputs,frame=prepared()
    result=validate_development(inputs,frame,1)
    assert set(CANDIDATES)<=set(result["report"]["validation"])
    for fold in result["report"]["folds"]:
        assert fold["train_target_end"]<fold["validation_first_origin"]
        calibration=fold["presence"]
        if calibration["calibrated_on_development_only"]:
            assert calibration["base_target_end"]<calibration["calibration_first_origin"]
            assert calibration["calibration_target_end"]<=fold["train_target_end"]
    final=fit_final(result,1)
    import joblib
    path=tmp_path/"fictional_v3.joblib"
    joblib.dump(final,path)
    reopened=joblib.load(path)
    for name,model in final["counts"].items():
        predictions=model.predict_frame(result["development"])
        assert np.isfinite(predictions).all() and (predictions>=0).all()
        assert np.array_equal(predictions,reopened["counts"][name].predict_frame(result["development"]))
    assert result["report"]["external_validation_pending"] and not result["report"]["alerts_enabled"]


def test_observed_comparison_outcomes_cannot_select_or_fit_v3():
    data=snapshot_bundle()
    inputs,frame=prepared(data)
    before=validate_development(inputs,frame,1)
    changed=deepcopy(data)
    for row in changed["counts"]:
        if date.fromisoformat(row["week_start"])>=TEST and row["count"] is not None: row["count"]+=25
    new_inputs,new_frame=prepared(changed)
    after=validate_development(new_inputs,new_frame,1)
    assert before["report"]==after["report"]
    assert before["oof"].equals(after["oof"])


def test_unknown_targets_are_never_accepted_by_fit_and_unavailable_threshold_is_visible():
    inputs,frame=prepared()
    with pytest.raises(ForecastError): fit_models(feature_frame(inputs,frame,1),1)
    known=frame.loc[frame.target_count.notna()].head(20)
    values=np.full(len(known),.1)
    report=presence_summary(known,values,[None]*len(known))
    assert report["precision"] is None and report["recall"] is None and report["binary_supported_rows"]==0


def test_v3_explicit_query_preserves_reference_and_rejects_unpromoted_ml(tmp_path, monkeypatch):
    import hashlib
    import json
    from sigard_ml.forecasting import local_query
    from sigard_ml.forecasting.local_map import build_map_payload
    from test_predictive_closure import fictional_frame, geometry

    monkeypatch.setattr(local_query, "__file__", str(tmp_path / "ml/src/sigard_ml/forecasting/local_query.py"))
    directory = tmp_path / "ml/artifacts/official/sigard-principal-v3-experimental"
    directory.mkdir(parents=True)
    frame = fictional_frame()
    frame["model_version"] = "fictional_v3"
    for name in ("territorial_predictions.private.parquet", "persistence_predictions.private.parquet"):
        frame.to_parquet(directory / name, index=False)
    quality = dict(presence_quality="fictional_research_only", promotion_approved=dict.fromkeys(("1","2","4"),False),
                   territorial_selected=dict.fromkeys(("1","2","4"),"lag_1_or_training_mean"))
    fictional_metric = dict(n=3,mae=1.,rmse=1.,mean_bias=0.)
    fictional_report = {"1":dict(development_rows=10,development_weeks=5,
        development=dict(validation_rows=3,validation_weeks=1,validation={"fictional":fictional_metric},
                         presence_validation=dict(presence_score=dict(brier=.1,recall=0.))),
        selection=dict(selected="lag_1_or_training_mean",best_ml="fictional",promotion_approved=False))}
    (directory / "metrics.private.json").write_text(json.dumps(fictional_report),encoding="utf-8")

    def seal():
        (directory / "quality_status.private.json").write_text(json.dumps(quality), encoding="utf-8")
        hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.name != "manifest.private.json"}
        (directory / "manifest.private.json").write_text(json.dumps(dict(outputs_sha256=hashes)),encoding="utf-8")

    seal()
    selected = local_query.load_predictions(directory)
    reference = local_query.load_predictions(directory, method="persistence")
    assert selected.equals(reference)
    summary = local_query.research_summary(directory)
    assert summary["horizons"]["1"]["counts"]["fictional"] == fictional_metric
    assert not summary["alerts_enabled"] and summary["external_validation_pending"]
    payload = build_map_payload(selected,geometry(),[])
    assert not payload["probability_available"] and not payload["alerts_enabled"]
    assert payload["queries"]["1"][0]["model_version"] == "fictional_v3"
    assert local_query.query_predictions(selected,target_date="2026-10-26")["expected_eligible_total"] is None
    frame["selected_method"] = "v3_direct_poisson"
    frame.to_parquet(directory / "territorial_predictions.private.parquet",index=False)
    quality["territorial_selected"] = dict.fromkeys(("1","2","4"),"v3_direct_poisson")
    seal()
    with pytest.raises(ForecastError,match="promoción explícitas"):
        local_query.load_predictions(directory)
    assert local_query.load_predictions(directory,method="persistence").selected_method.eq("lag_1_or_training_mean").all()
    (directory / "persistence_predictions.private.parquet").write_bytes(b"tampered fictional data")
    with pytest.raises(ForecastError,match="Integridad"):
        local_query.load_predictions(directory,method="persistence")


def test_presence_decisions_use_the_same_supported_cohort():
    import pandas as pd
    frame = pd.DataFrame(dict(target_count=[0.,1.,0.,1.]))
    values = np.array([.1,.2,.9,.9])
    report = presence_summary(frame,values,[.15,.15,None,np.nan])
    assert report["n"]==4 and report["binary_supported_rows"]==2
    assert report["true_positives"]==1 and report["false_positives"]==0
    assert report["precision"]==report["recall"]==1.


def test_runner_can_be_imported_without_io_or_training():
    from sigard_ml.forecasting import v3_run
    assert callable(v3_run.main)
