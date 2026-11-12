"""Generated abstract values; no private files, historical models or DB."""
import numpy as np
import pandas as pd
import pytest
from sigard_ml.forecasting.census_campaign import scenarios, CENSUS
from sigard_ml.forecasting.motor_models import matrix
from sigard_ml.forecasting.motor_protocol import FEATURES
from sigard_ml.data_access import DatasetBlocked


def test_scenarios_preserve_inputs_and_only_b_replaces_census():
    frame=pd.DataFrame(dict(radio_codigo=['FICT-A','FICT-B'],superficie_km2=[2.,4.],
        poblacion=[np.nan,np.nan],densidad_poblacional=[np.nan,np.nan],target_count=[1.,0.]))
    before=frame.copy(deep=True)
    context=pd.DataFrame(dict(radio_id=['FICT-B','FICT-A'],poblacion_2022=[40.,10.],
        hogares_2022=[12,3],viviendas_2022=[15,4]))
    master=pd.DataFrame(dict(radio_id=['FICT-A','FICT-B'],superficie_km2=[2.,4.]))
    versions,_=scenarios(frame,context,master)
    pd.testing.assert_frame_equal(frame,before)
    assert versions['A'][list(CENSUS)].isna().all().all()
    assert versions['B'].poblacion.tolist()==[10.,40.]
    assert versions['B'].densidad_poblacional.tolist()==[5.,10.]
    assert versions['B'].target_count.equals(versions['A'].target_count)
    master.loc[0,'superficie_km2']=3.
    with pytest.raises(ValueError,match='area_mismatch'):scenarios(frame,context,master)


def test_ablation_matrices_really_remove_columns_and_reject_targets():
    names=FEATURES['rf_A_epi_climate']
    frame=pd.DataFrame({name:[1.,2.] for name in names})
    without=tuple(n for n in names if n not in CENSUS)
    assert set(matrix(frame,'rf_A_epi_climate',without))==set(names)-set(CENSUS)
    assert set(CENSUS)<=set(matrix(frame,'rf_A_epi_climate'))
    with pytest.raises(DatasetBlocked):matrix(frame,'rf_A_epi_climate',['target_count'])
    assert FEATURES['rf_A_epi_climate']==names
