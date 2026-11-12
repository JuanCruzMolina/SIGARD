"""Generated software fixtures only; no project files, fitting or clinical sources."""
from datetime import date, timedelta
import pytest
from sigard_ml.data_access import DatasetBlocked
from sigard_ml.forecasting.backtest_bundle import project_week
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR


def fixture(year=2022, week=6, count=1):
    start, end = DEFAULT_CALENDAR.week_bounds(year, week)
    w = dict(anio=year, numero=week, inicio=start, fin=end, department_count=count)
    row = dict(radio_id=1,radio_codigo='999999999',mascara_comun=True,cantidad_sigard=count,
        presencia_sigard=int(count>0),registros_asignados=count,registros_sin_radio=0,
        registros_aproximados=count,registros_provisionales=0,registros_verificados=0,
        calidad_geografica='approximate',cobertura_estado='covered_observed' if count else 'covered_assumed_zero',
        procedencia_cero=None if count else 'project_owner_declared_coverage_2020_2024')
    p = {1:dict(presencia={'presence_seasonal':.2},umbrales={'presence_seasonal':.1},cantidad={'count_latest':.75})}
    training = dict(block='FICTIONAL',fit_end=start-timedelta(days=42))
    context = dict(dataset_version='FICTIONAL',campaign_version='FICTIONAL',data_policy_version='FICTIONAL',territory_version='FICTIONAL')
    return w,[row],p,training,context


def test_projection_preserves_exact_decimals_and_omits_private_fields():
    args=fixture();args[1][0]['FICTIONAL_PRIVATE_NAME']='DO NOT EXPOSE'
    result=project_week(*args);r=result['rows'][0]
    assert r['predicted']['quantity']==.75 and r['difference']==-.25 and r['absolute_error']==.25
    assert r['confusion']=='TP' and r['observed']['quantity']==1
    assert 'DO NOT EXPOSE' not in str(result)
    assert result==project_week(*args) and result['department']['reconciled']


def test_zero_unknown_warmup_and_mask_are_different():
    args=fixture(count=0);r=project_week(*args)['rows'][0]
    assert r['observed']['quantity']==0 and r['zero_provenance'] and r['confusion']=='FP'
    args=list(fixture(2025));r=project_week(*args)['rows'][0]
    assert r['availability_status']=='outside_coverage' and r['observed']['quantity'] is None and r['predicted']['quantity'] is None
    args=list(fixture(2020));args[3]=None;r=project_week(*args)['rows'][0]
    assert r['availability_status']=='insufficient_training_support' and r['observed']['quantity']==1
    args=list(fixture());args[1][0]['mascara_comun']=False;args[1][0]['cantidad_sigard']=None;args[1][0]['presencia_sigard']=None
    r=project_week(*args)['rows'][0]
    assert r['availability_status']=='outside_common_territory' and r['observed']['quantity'] is None
    assert r['observed']['assigned_records']==1 and r['predicted']['quantity'] is None
    args=list(fixture());args[1][0]['cantidad_sigard']=None;args[1][0]['registros_sin_radio']=1;args[0]['department_count']=2
    assert project_week(*args)['availability_status']=='territorial_uncertainty'


@pytest.mark.parametrize('days',[0,7,28,35])
def test_temporal_purge_rejects_future_or_insufficiently_separated_fits(days):
    args=fixture();args[3]['fit_end']=args[0]['inicio']-timedelta(days=days)
    with pytest.raises(DatasetBlocked):project_week(*args)


def test_2020_week53_origin_and_2021_transition_are_argentine():
    a=project_week(*fixture(2020,53));b=project_week(*fixture(2021,1))
    assert a['target_week']=='2020-12-27' and b['origin_week']==a['target_week']
    assert a['target_end']=='2021-01-02' and b['target_week']=='2021-01-03'


def test_reconciliation_and_missing_saved_prediction_fail_closed():
    args=fixture();args[0]['department_count']=2
    with pytest.raises(DatasetBlocked):project_week(*args)
    args=list(fixture());args[2]={}
    with pytest.raises(DatasetBlocked):project_week(*args)
