"""Fictional data only; regression of label preservation, exact lags and purging."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.spatial_ml.features import calendar_predictors
from sigard_ml.official.spatial_ml.historical_expansion import (
    BASE, FEATURES, KEYS, LAGS, ab_matrix, prepare_ab, temporal_split, fit_ab, positive_score,
)


def fictional():
    rows=[]
    for radio in ['fictional-1','fictional-2']:
        for i in range(10):
            origin=date(2023,12,31)+timedelta(weeks=i)
            rows.append(dict(radio_censal=radio,fecha_inicio_semana=origin,
                fecha_inicio_semana_objetivo=origin+timedelta(weeks=1),
                objetivo_semana_siguiente=pd.NA if i==3 else (i%2),
                tipo_etiqueta='desconocida' if i==3 else ('positivo_provisional' if i%2 else 'cero_asumido_experimental'),
                en_intervalo_autorizado=True,pendientes_semana_objetivo=0,semana_objetivo_parcial=False,
                apto_entrenamiento=False))
    labels=pd.DataFrame(rows)
    labels.objetivo_semana_siguiente=labels.objetivo_semana_siguiente.astype('Int8')
    context=labels[KEYS].copy()
    for name in BASE[:4]:context[name]=1.
    yw=context.fecha_inicio_semana.map(DEFAULT_CALENDAR.date_week)
    context['anio_epidemiologico']=yw.map(lambda x:x[0])
    context['semana_epidemiologica']=yw.map(lambda x:x[1])
    seasonal=calendar_predictors(context)
    for name in BASE[4:]:context[name]=seasonal[name]
    return labels,context[KEYS+BASE]


def test_exact_binary_lags_preserve_unknown_and_target():
    labels,features=fictional()
    frame=prepare_ab(labels,features)
    assert frame.objetivo_semana_siguiente.isna().sum()==2
    assert not frame.apto_entrenamiento.any()
    row=frame.loc[frame.radio_censal.eq('fictional-1') & frame.fecha_inicio_semana.eq(date(2024,2,4))].iloc[0]
    assert pd.isna(row[LAGS[0]])  # source Jan 28 is unknown, not previous observed row
    assert row[LAGS[1]]==0 and row[LAGS[0]+'_missing']==1
    assert ab_matrix(frame,'B')[LAGS[0]].isna().any()


def test_future_target_mutation_does_not_affect_earlier_features():
    labels,features=fictional()
    original=prepare_ab(labels,features)
    changed=labels.copy()
    changed.loc[changed.fecha_inicio_semana_objetivo.eq(date(2024,3,10)),'objetivo_semana_siguiente']=1
    changed.loc[changed.fecha_inicio_semana_objetivo.eq(date(2024,3,10)),'tipo_etiqueta']='positivo_provisional'
    new=prepare_ab(changed,features)
    pd.testing.assert_frame_equal(original[KEYS+FEATURES['B']],new[KEYS+FEATURES['B']])


@pytest.mark.parametrize('bad',['duplicate','negative','target','context','calendar'])
def test_invalid_or_incompatible_rows_rejected(bad):
    labels,features=fictional()
    if bad=='duplicate':labels=pd.concat([labels,labels.iloc[:1]],ignore_index=True)
    elif bad=='negative':labels.loc[0,'en_intervalo_autorizado']=False
    elif bad=='target':labels.loc[0,'fecha_inicio_semana_objetivo']+=timedelta(weeks=1)
    elif bad=='context':features.loc[0,BASE[0]]=2.
    else:features.loc[0,'estacionalidad_seno']=.75
    with pytest.raises(ValueError):prepare_ab(labels,features)


def test_temporal_split_purges_outcome_crossing_origin():
    labels,features=fictional();frame=prepare_ab(labels,features)
    train,evaluation=temporal_split(frame,date(2024,2,11),date(2024,2,25))
    assert max(train.target_end)<min(evaluation.fecha_inicio_semana)
    assert not train.fecha_inicio_semana_objetivo.eq(date(2024,2,4)).any()
    assert not train.objetivo_semana_siguiente.isna().any()


def test_fit_rejects_single_class_or_unknown():
    labels,features=fictional();frame=prepare_ab(labels,features)
    with pytest.raises(ValueError):fit_ab(frame,'A')
    with pytest.raises(ValueError):fit_ab(frame.loc[frame.objetivo_semana_siguiente.eq(1)],'B')


def test_fixed_estimator_nan_and_serialization(tmp_path):
    import joblib
    labels,features=fictional();frame=prepare_ab(labels,features)
    fit=frame.loc[frame.objetivo_semana_siguiente.notna()]
    model=fit_ab(fit,'B')
    path=tmp_path/'fictional.joblib';joblib.dump(model,path)
    assert model.n_estimators==400 and model.n_features_in_==15
    np.testing.assert_array_equal(positive_score(model,ab_matrix(frame,'B')),
        positive_score(joblib.load(path),ab_matrix(frame,'B')))
