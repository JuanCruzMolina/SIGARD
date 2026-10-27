"""Consulta manual con entradas generadas; sin ajustes, archivos o datos reales."""

from datetime import date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.dataset import FEATURES, build_dataset
from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.prediction import forecast_for_date, resolve_date_query
from sigard_ml.forecasting.training import FittedCounts


AS_OF, CUTOFF = date(2024, 9, 8), date(2024, 9, 7)


def fitted(inputs, cutoff=date(2024, 6, 22)):
    # Doble determinista: comprueba el recorrido sin ejecutar otro entrenamiento.
    model = SimpleNamespace(predict=lambda frame: np.ones(len(frame)))
    return FittedCounts(model, "fictional_model", "fictional_stub", cutoff,
                        inputs.radios, inputs.dataset_version, 20261022)


@pytest.mark.parametrize("value", ["2024-02-30", "08/09/2024", "20240908", "2024-W36-7",
                                  "2024-09-08T00:00:00", " 2024-09-08", "", None,
                                  datetime(2024, 9, 8), True])
def test_manual_date_is_strict(value):
    with pytest.raises(ForecastError):
        resolve_date_query(value, as_of=AS_OF, information_cutoff=CUTOFF)


@pytest.mark.parametrize("value", ["2024-09-08", "2024-09-11", "2024-09-14", date(2024, 9, 8)])
def test_any_day_selects_the_same_next_week(value):
    result = resolve_date_query(value, as_of=AS_OF, information_cutoff=CUTOFF)
    assert result["query_mode"] == "forecast"
    assert result["target_week"] == "2024-09-08"
    assert result["information_cutoff"] == "2024-09-07"
    assert result["target_week_number"] == 37


def test_historical_query_uses_its_own_cutoff_and_never_todays_features():
    inputs = fictional_inputs()
    captured = []
    model = fitted(inputs)
    model.model.predict = lambda frame: captured.append(frame.copy()) or np.ones(len(frame))
    result = forecast_for_date(model, inputs, target_date="2024-07-17",
                               as_of=AS_OF, information_cutoff=CUTOFF)
    expected = build_dataset(inputs, start=date(2024, 7, 7), end=date(2024, 7, 7),
                             evaluation_as_of=date(2024, 7, 13))
    pd.testing.assert_frame_equal(captured[0], expected[list(FEATURES)].astype(float))
    assert result["query_mode"] == "historical_backtest"
    assert result["information_cutoff"] == "2024-07-13"
    assert result["generated_as_of"] == AS_OF.isoformat()
    assert result["expected_capital_count"] == len(inputs.radios)
    assert not result["real_forecast"]
    assert all(item["available_on"] <= "2024-07-13"
               for row in result["radios"] for item in row["provenance"]["counts"])


def test_late_revision_cannot_enter_historical_prediction():
    inputs = fictional_inputs()
    model = fitted(inputs)
    model.model.predict = lambda frame: frame.cases_lag_1.to_numpy()
    kwargs = dict(target_date="2024-07-17", as_of=AS_OF, information_cutoff=CUTOFF)
    before = forecast_for_date(model, inputs, **kwargs)
    revised = inputs.counts.loc[inputs.counts.week_start.eq(date(2024, 6, 30))].copy()
    revised["available_on"], revised["count"] = date(2024, 9, 1), 10000
    inputs.counts = pd.concat([inputs.counts, revised], ignore_index=True)
    assert forecast_for_date(model, inputs, **kwargs) == before


@pytest.mark.parametrize("target", ["2024-09-15", "2024-12-01"])
def test_distant_weeks_are_rejected_before_model_prediction(target):
    with pytest.raises(ForecastError, match="horizontes lejanos"):
        resolve_date_query(target, as_of=AS_OF, information_cutoff=CUTOFF)


def test_stale_information_does_not_license_current_forecast():
    with pytest.raises(ForecastError, match="t\\+1"):
        resolve_date_query("2024-09-08", as_of=AS_OF, information_cutoff=date(2024, 8, 24))


@pytest.mark.parametrize("cutoff", [date(2024, 9, 6), date(2024, 9, 14)])
def test_partial_or_future_cutoff_is_rejected(cutoff):
    with pytest.raises(ForecastError, match="corte"):
        resolve_date_query("2024-09-08", as_of=AS_OF, information_cutoff=cutoff)


@pytest.mark.parametrize("target,cutoff,year,number", [
    ("2021-01-02", date(2020, 12, 26), 2020, 53),
    ("2026-01-03", date(2025, 12, 27), 2025, 53),
    ("2026-01-04", date(2026, 1, 3), 2026, 1),
])
def test_national_calendar_across_year_boundaries(target, cutoff, year, number):
    result = resolve_date_query(target, as_of=date(2026, 10, 22), information_cutoff=cutoff)
    assert (result["target_year"], result["target_week_number"]) == (year, number)


@pytest.mark.parametrize("target", ["2019-12-29", "2027-01-03"])
def test_unverified_target_or_origin_has_comprehensible_error(target):
    with pytest.raises(ForecastError, match="calendario epidemiológico"):
        resolve_date_query(target, as_of=date(2026, 10, 22), information_cutoff=date(2026, 10, 17))


def test_model_must_exist_support_t_plus_one_and_precede_origin():
    inputs = fictional_inputs()
    kwargs = dict(target_date="2024-09-08", as_of=AS_OF, information_cutoff=CUTOFF)
    with pytest.raises(ForecastError, match="no hay modelo"):
        forecast_for_date(None, inputs, **kwargs)
    model = fitted(inputs)
    model.horizon_weeks = 4
    with pytest.raises(ForecastError, match="multihorizonte"):
        forecast_for_date(model, inputs, **kwargs)
    model.horizon_weeks = 1
    model.fit_cutoff = date(2024, 9, 8)
    with pytest.raises(ForecastError, match="después del origen"):
        forecast_for_date(model, inputs, **kwargs)


def test_missing_recent_counts_has_no_prediction_or_fallback_to_old_origin():
    inputs = fictional_inputs()
    model = fitted(inputs)
    model.model.predict = lambda frame: pytest.fail("No debe inferir con historia reciente desconocida")
    inputs.counts.loc[inputs.counts.week_start.eq(date(2024, 8, 25)), "state"] = "unknown"
    with pytest.raises(ForecastError, match="completos y maduros"):
        forecast_for_date(model, inputs, target_date="2024-09-08", as_of=AS_OF, information_cutoff=CUTOFF)


def test_query_never_enables_real_inference_or_opens_sources():
    inputs = fictional_inputs()
    model = fitted(inputs)
    inputs.data_kind, inputs.counts = "epidemiological_accredited", object()
    with pytest.raises(ForecastError, match="Uso real bloqueado"):
        forecast_for_date(model, inputs, target_date="2024-09-08", as_of=AS_OF, information_cutoff=CUTOFF)
