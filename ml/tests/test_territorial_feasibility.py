"""Pure fictional arithmetic fixtures; no private reads or fitting."""
from datetime import date,timedelta
import numpy as np
import pandas as pd
import pytest

import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('territorial_feasibility',Path(__file__).resolve().parents[2]/'tools'/'analyze_territorial_feasibility.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
coverage,concentration,variation,error_decomposition,adjacent_pairs,trend_summary=(getattr(module,name) for name in
    ('coverage','concentration','variation','error_decomposition','adjacent_pairs','trend_summary'))


def test_unknown_radio_cannot_count_as_city_total():
    frame=pd.DataFrame([[1.,np.nan],[0.,0.]],columns=['fictional_a','fictional_b'])
    report=coverage(frame)
    assert report['completely_known_weeks']==1
    assert report['unknown_cells']==1
    assert report['radios_known_every_week']==1
    assert report['weeks_at_maximum_observable']==1
    assert pd.isna(frame.iloc[0,1])


def test_l1_decomposition_distinguishes_level_and_allocation():
    level=error_decomposition([1,2],[2,4])
    assert level['total_absolute_error']==level['absolute_subset_total_error']==3
    assert level['cancelling_error']==0
    assert level['share_tv']==0
    spatial=error_decomposition([1,0],[0,1])
    assert spatial['absolute_subset_total_error']==0
    assert spatial['cancelling_error']==spatial['total_absolute_error']==2
    assert spatial['share_tv']==1


def test_total_variation_is_scale_invariant_and_zero_totals_undefined():
    assert variation([1,3],[2,6])==0
    assert variation([0,0],[2,6]) is None
    assert concentration([0,0]) is None
    assert concentration([0,5])['effective_radios']==1


def test_missing_calendar_week_is_not_adjacent():
    first=date(2020,1,5)
    dates=[first,first+timedelta(weeks=1),first+timedelta(weeks=3)]
    assert adjacent_pairs(dates)==[(0,1)]


def test_aggregation_can_hide_spatial_turnover_without_a_trend():
    first=date(2020,1,5)
    frame=pd.DataFrame([[1.,0.],[0.,1.]],index=[first,first+timedelta(weeks=1)])
    report=trend_summary(frame)
    assert report['aggregate_change_divided_by_sum_radio_changes']==0
    assert report['zero_total_fraction']==0
    assert report['zero_cell_fraction']==.5
    assert report['weekly_total_cv']==0
    with pytest.raises(AssertionError):
        trend_summary(frame.mask(frame==0))
