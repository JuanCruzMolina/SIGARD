"""Consulta/demostración con fixtures ficticias; nunca ajusta modelos."""
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.local_map import build_map_payload, export_private_map
from sigard_ml.forecasting.local_query import query_predictions


def fictional_frame():
    target = date(2024, 4, 7)
    rows = []
    for h in (1, 2, 4):
        for i in range(256):
            origin = target - timedelta(weeks=h)
            rows.append(dict(radio_id=f"fictional_{i:03}", horizon_weeks=h, target_week=target,
                origin_week=origin, cutoff_date=origin+timedelta(days=6), fit_cutoff=date(2024,1,7),
                expected_count=float(i % 4) if i != 255 else np.nan,
                predictor_status="recent_radio_counts_available" if i < 200 else "partial_missing_recent_radio_counts" if i < 255 else "insufficient_data",
                available_features=21 if i < 200 else 8, missing_features=[] if i < 200 else ["cases_lag_1"],
                experimental_presence_score=.987654321, presence_output_kind="fictional_score",
                model_version="fictional_v2", selected_method="lag_1_or_training_mean",
                observed_snapshot_count=1. if i < 10 else np.nan, observed_quality_state="unknown_pending"))
    return pd.DataFrame(rows)


def geometry():
    return dict(type="FeatureCollection", features=[dict(type="Feature", properties=dict(radio_id=f"fictional_{i:03}"),
        geometry=dict(type="Polygon", coordinates=[[[i,0],[i+.5,0],[i+.5,.5],[i,.5],[i,0]]])) for i in range(256)])


@pytest.mark.parametrize("horizon", [1, 2, 4])
def test_dates_horizons_eligibility_and_total_do_not_invent_missing_values(horizon):
    frame = fictional_frame()
    result = query_predictions(frame, target_date="2024-04-08", horizon_weeks=horizon, as_of=date(2026,10,26))
    assert len(result["radios"]) == 256 and result["eligible_radios"] == 255
    assert result["radios_without_estimate"] == 1 and result["radios_with_incomplete_predictors"] == 55
    assert result["expected_territorial_total"] is None
    assert result["expected_eligible_total"] == sum(i % 4 for i in range(255))
    assert result["radios"][-1]["expected_count"] is None
    assert result["radios"][-1]["estimate_status"] == "insufficient_data"
    assert not result["probability_available"]
    assert all("experimental_presence_score" not in row for row in result["radios"])
    assert result["selected_method"] == "lag_1_or_training_mean"
    single = query_predictions(frame, target_date="2024-04-07", horizon_weeks=horizon,
        radio_id="fictional_201", as_of=date(2026,10,26))
    assert len(single["radios"]) == 1 and single["expected_eligible_total"] == result["expected_eligible_total"]
    assert single["radios"][0]["estimate_status"] == "available_with_historical_mean_fallback"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("target", ["2026-10-26", "2022-01-02", "2024-04-21"])
def test_unavailable_dates_remove_estimates(target):
    result = query_predictions(fictional_frame(), target_date=target, as_of=date(2026,10,26))
    assert result["status"] == "insufficient_origin_data"
    assert not result["radios"] and result["expected_eligible_total"] is None


def test_excluded_radio_and_invalid_or_missing_counts_are_rejected():
    frame = fictional_frame()
    with pytest.raises(ForecastError, match="Radio ajeno"):
        query_predictions(frame, target_date="2024-04-07", radio_id="fictional_excluded")
    frame.loc[0, "expected_count"] = np.inf
    with pytest.raises(ForecastError, match="inválidos"):
        query_predictions(frame, target_date="2024-04-07")
    frame.loc[0, "expected_count"] = np.nan
    with pytest.raises(ForecastError, match="sin estado"):
        query_predictions(frame, target_date="2024-04-07")


def test_map_payload_suppresses_numeric_presence_and_discarded_model():
    payload = build_map_payload(fictional_frame(), geometry(), [])
    assert set(payload["queries"]) == {"1", "2", "4"}
    raw = json.dumps(payload, allow_nan=False)
    assert "0.987654321" not in raw and "experimental_presence_score" not in raw
    assert not payload["alerts_enabled"] and not payload["probability_available"]
    wrong = fictional_frame()
    wrong["selected_method"] = "poisson_glm"
    with pytest.raises(ForecastError, match="referencia territorial"):
        build_map_payload(wrong, geometry(), [])


def test_map_cannot_export_into_public_or_models(tmp_path):
    for output in (tmp_path / "frontend/public/map.private.html", tmp_path / "model.private.html"):
        with pytest.raises(ForecastError, match="data/interim/official"):
            export_private_map(fictional_frame(), output)
        assert not output.exists()
