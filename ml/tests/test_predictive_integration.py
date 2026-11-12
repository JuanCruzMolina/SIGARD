"""Synthetic final integration contracts: no fits, database connections or private files."""
from datetime import date,timedelta
import importlib
import sys
import pytest
from sigard_ml.forecasting.predictive_context import project_context,USAGE
from sigard_ml.forecasting.lifecycle import REGISTRY
from sigard_ml.data_access import DatasetBlocked


def weather(**extra):
    row=dict(inicio=date(2024,1,7),fin=date(2024,1,13),dias=7,temperatura=20.,humedad=50.,precipitacion=2.)
    return dict(row,**extra)


def test_climate_joins_only_origin_period_with_known_values_not_arrival_claims():
    weeks=[dict(inicio=date(2024,1,14)),dict(inicio=date(2025,1,5))]
    result=project_context(weeks,[weather()])
    first=result['2024-01-14'];missing=result['2025-01-05']
    assert first['origin_week']=='2024-01-07' and first['period_end']=='2024-01-13'
    assert first['temperature_mean']==20 and first['humidity_mean']==50 and first['precipitation_total']==2
    assert first['availability_basis']=='event_dates_only_arrival_not_accredited' and first['usage']==USAGE
    assert missing['precipitation_total'] is None and missing['availability_status']=='not_available'
    assert result==project_context(weeks,[weather()])


@pytest.mark.parametrize('extra',[{'humedad':None},{'dias':6},{'temperatura':None},{'precipitacion':None}])
def test_missing_climate_never_becomes_zero(extra):
    row=weather();row.update(extra)
    result=project_context([dict(inicio=date(2024,1,14))],[row])['2024-01-14']
    assert result['availability_status']=='not_available' and result['precipitation_total'] is None


def test_future_climate_context_blocks_and_lifecycle_has_only_two_h1_references():
    with pytest.raises(DatasetBlocked):project_context([dict(inicio=date(2024,1,14))],[weather(fin=date(2024,1,14))])
    assert REGISTRY['active_references']==['presence_seasonal','count_latest']
    assert REGISTRY['horizon_weeks']==1 and REGISTRY['training_enabled'] is False


@pytest.mark.parametrize('family',['A','B','V3'])
def test_archived_default_never_dispatches_database_or_training(monkeypatch,capsys,family):
    from sigard_ml.data_access.historical import database_default
    monkeypatch.setattr(sys,'argv',['FICTIONAL'])
    assert database_default(family)==2 and 'archived' in capsys.readouterr().out
    monkeypatch.setattr(sys,'argv',['FICTIONAL','--historical-reproduction'])
    assert database_default(family) is None
