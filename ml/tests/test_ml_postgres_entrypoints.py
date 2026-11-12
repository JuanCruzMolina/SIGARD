"""No source reads, no models fitted; default entry points cannot fall back."""
import importlib
import sys

import pytest


@pytest.mark.parametrize('module,family',[
    ('sigard_ml.official.spatial_ml.research_training','A'),
    ('sigard_ml.official.spatial_ml.research_model_b','B'),
    ('sigard_ml.forecasting.v3_run','V3')])
def test_archived_training_command_is_blocked_before_database_by_default(monkeypatch,module,family,capsys):
    from sigard_ml.forecasting import database_pipeline
    called=[]
    monkeypatch.setattr(sys,'argv',['FICTIONAL-command'])
    monkeypatch.setattr(database_pipeline,'main',lambda **kw:called.append(kw) or 17)
    assert importlib.import_module(module).main()==2
    assert called==[] and 'archived' in capsys.readouterr().out


@pytest.mark.parametrize('module',[
    'sigard_ml.official.spatial_ml.pipeline',
    'sigard_ml.official.spatial_ml.experiment_pipeline',
    'sigard_ml.official.spatial_ml.assumed_scenario_pipeline',
    'sigard_ml.features.pipeline',
    'sigard_ml.evaluation.pipeline',
    'sigard_ml.evaluation.random_forest_pipeline',
    'sigard_ml.evaluation.random_forest_variants_pipeline',
    'sigard_ml.evaluation.department_temporal_pipeline',
    'sigard_ml.evaluation.department_temporal_variants',
    'sigard_ml.evaluation.department_temporal_delta'])
def test_file_preparation_requires_historical_opt_in_before_configuration(monkeypatch,module):
    monkeypatch.setattr(sys,'argv',['FICTIONAL-command','--config','FICTIONAL-not-opened.json'])
    with pytest.raises(SystemExit) as error:
        importlib.import_module(module).main()
    assert error.value.code==2


def test_file_inference_and_snapshot_query_are_not_operational_fallbacks(monkeypatch,tmp_path):
    from sigard_ml.official.spatial_ml import date_inference
    from sigard_ml.forecasting import local_query
    def forbidden(*args,**kwargs):raise AssertionError('must not read a legacy file')
    monkeypatch.setattr(date_inference,'load_policy',forbidden)
    with pytest.raises(date_inference.InferenceBlocked,match='postgres_legacy_contract_unverified'):
        date_inference.infer('2026-11-01','FICTIONAL')
    with pytest.raises(ValueError,match='historical_reproduction_only'):
        local_query.load_predictions(tmp_path)
