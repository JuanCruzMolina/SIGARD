"""Generated abstract weekly fixtures only; no real sources or estimators."""
from datetime import date,timedelta
import copy

import numpy as np
import pandas as pd
import pytest

from sigard_ml.forecasting.core_data import eligibility,proposed_coverage,canonical_hash
from sigard_ml.forecasting.core_model import feature_panel,PROTOCOL,FEATURES,uncertainty
from sigard_ml.ingestion.epidemiology.complementary import OpenMeteoCSV,PublicDengueCSV,CensusCSV


def series():
    start=date(2024,2,4)
    rows=[]
    for i in range(12):
        w=start+timedelta(weeks=i)
        rows.append(dict(inicio=w,fin=w+timedelta(days=6),anio=2024,numero=6+i,semanas_anio=52,
            conteo_experimental=float(2+i%4),cobertura='experimental_assumed',dias=7,
            temperatura=20.,humedad=45.,precipitacion=1.,disponible_desde=None,
            disponibilidad_verificada=False,clima_disponible_desde=None))
    return pd.DataFrame(rows)


def record(**changes):
    return dict(exact_duplicate=False,pending_identity=False,classes=['confirmado'],
        reference_date=date(2024,2,4),date_type='symptom_onset',province='la rioja',
        department='capital',locality='la rioja',geography_state='point_only',**changes)


def test_eligibility_does_not_use_uncertain_radio_or_force_unknown_class():
    row=record()
    assert eligibility(row)=='included'
    row['classes']=[None];assert eligibility(row)=='classification_not_unambiguously_confirmed'
    row=record();row['pending_identity']=True
    assert eligibility(row)=='unresolved_identifier_or_revision'
    row=record();row['reference_date']=None
    assert eligibility(row)=='missing_clinical_reference_date'
    row=record();row['reference_date']=date(2022,2,6)
    assert eligibility(row)=='2022_classification_policy_separate'


def test_coverage_only_bounded_explicit_years():
    rows=[record(),record()]
    rows[1]['reference_date']=date(2024,2,25)
    weeks=proposed_coverage(rows)
    assert weeks==[date(2024,2,4)+timedelta(weeks=i) for i in range(4)]
    rows.append(record());rows[-1]['reference_date']=date(2023,2,5)
    assert len(proposed_coverage(rows))==5


def test_future_target_and_weather_never_change_origin_features():
    original=series();before=feature_panel(original)
    changed=original.copy()
    changed.loc[changed.index>=5,['conteo_experimental','temperatura','humedad','precipitacion']]=999.
    after=feature_panel(changed)
    pd.testing.assert_frame_equal(before.loc[:4,list(FEATURES)],after.loc[:4,list(FEATURES)])
    assert before.iloc[4].target_count!=after.iloc[4].target_count


def test_gap_and_unknown_counts_never_become_zero_or_previous_season():
    rows=series();rows.loc[4,'conteo_experimental']=np.nan;rows.loc[4,'cobertura']='unknown'
    panel=feature_panel(rows)
    assert not panel.iloc[4:7].admissible.any()
    assert np.isnan(panel.iloc[3].target_count)
    without=feature_panel(rows.drop(index=4))
    assert not without.loc[without.origin_week.eq(rows.iloc[5].inicio)].iloc[0].admissible
    rows=series();rows.loc[1:,'anio']=2025
    assert not feature_panel(rows).iloc[1].admissible


def test_missing_weather_and_optional_four_week_windows():
    rows=series();rows.loc[4,'dias']=6
    panel=feature_panel(rows)
    assert not panel.iloc[4].admissible
    assert np.isnan(panel.iloc[5].temperature_mean_4_origin)
    assert panel.iloc[5].admissible


def test_protocol_frozen_and_no_mass_search():
    assert PROTOCOL['primary_metric']=='MAE'
    assert PROTOCOL['provisional_minimum_relative_mae_improvement']==.05
    assert PROTOCOL['no_hyperparameter_search']
    assert canonical_hash(PROTOCOL)==canonical_hash(copy.deepcopy(PROTOCOL))
    assert not any(s in FEATURES for s in ('target_count','radio_id','latitude','longitude'))


def test_temporal_uncertainty_is_paired_deterministic():
    f=pd.DataFrame(dict(target_week=[date(2024,2,4)+timedelta(weeks=i) for i in range(15)],year=2024,
        target_count=[3]*15,model=[2]*15,persistence=[1]*15))
    a=uncertainty(f);b=uncertainty(f)
    assert a==b and a['mean_mae_difference']==-1 and a['upper95']==-1


def climate_bytes():
    return ('latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation\n'
        '10,10,0,0,UTC,UTC\n\n'
        'time,temperature_2m_max (C),temperature_2m_min (C),temperature_2m_mean (C),relative_humidity_2m_mean (%),precipitation_sum (mm)\n'
        '2024-02-04,25,15,20,45,1\n').encode()


def test_climate_adapter_preserves_unknown_arrival_and_checks_domains():
    adapted=OpenMeteoCSV().read(climate_bytes())
    assert len(adapted.frame)==1 and adapted.contract['available_on'] is None
    with pytest.raises(ValueError):OpenMeteoCSV().read(climate_bytes().replace(b'20,45,1',b'20,145,1'))
    with pytest.raises(ValueError):OpenMeteoCSV().read(climate_bytes()+b'2024-02-04,25,15,20,45,1\n')


def test_public_aggregate_adapter_canonical_codes_and_overlap_not_addition():
    header='id_depto_indec_residencia;id_prov_indec_residencia;anio_min;sepi_min;evento;grupo_etario;cantidad\n'
    data=(header+'014;46;2024;6;FICTIONAL EVENT;FICTIONAL AGE;5\n007;46;2024;6;FICTIONAL EVENT;FICTIONAL AGE;8\n').encode()
    adapted=PublicDengueCSV().read(data)
    assert adapted.source_rows==2 and len(adapted.frame)==1 and adapted.contract['not_additive_to_sisa']
    with pytest.raises(ValueError):PublicDengueCSV().read(data+data.splitlines(keepends=True)[1])


def test_census_adapter_uses_exact_keys_and_no_join_by_position():
    data=('codigo,cod_prov,cod_dep,fraccion,radio,cod_variable,cod_categoria,categoria,cantidad\n'
        '460149999,46,014,99,99,FICTIONAL_VARIABLE,1,FICTIONAL_CATEGORY,5\n').encode()
    adapted=CensusCSV().read(data)
    assert adapted.frame.iloc[0].codigo=='460149999'
