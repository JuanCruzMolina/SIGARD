"""Causal h=1 matrices from stage1 SQL, exact weeks and the common mask."""
from datetime import timedelta
import numpy as np
import pandas as pd

from sigard_ml.data_access import MLRepository,DatasetBlocked
from sigard_ml.forecasting.consolidation import POLICY
from sigard_ml.forecasting.core_data import canonical_hash
from sigard_ml.forecasting.motor_protocol import FEATURES
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR


def build_frame(raw, edges):
    raw=raw.sort_values(['radio_id','inicio']).reset_index(drop=True).copy()
    keys=['radio_id','inicio']
    if raw.duplicated(keys).any() or raw[keys].isna().any().any():
        raise DatasetBlocked('motor_duplicate_or_missing_week_key')
    known=raw.cantidad_sigard.dropna()
    if (known.lt(0)|known.mod(1).ne(0)).any():
        raise DatasetBlocked('motor_invalid_count_labels')
    if not raw.fin.eq(raw.inicio.map(lambda d:d+timedelta(days=6))).all():
        raise DatasetBlocked('motor_invalid_origin_close')
    index=pd.MultiIndex.from_frame(raw[keys])
    source=pd.Series(raw.cantidad_sigard.astype(float).to_numpy(),index=index)
    def lookup(offset):
        key=pd.MultiIndex.from_arrays([raw.radio_id,raw.inicio.map(lambda d:d+timedelta(weeks=offset))])
        return pd.Series(source.reindex(key).to_numpy(),index=raw.index)
    frame=raw.rename(columns={'inicio':'origin_week','fin':'origin_end'}).copy()
    frame['target_week']=frame.origin_week.map(lambda d:d+timedelta(days=7))
    frame['target_end']=frame.origin_week.map(lambda d:d+timedelta(days=13))
    frame['target_year']=frame.target_week.map(lambda d:DEFAULT_CALENDAR.date_week(d)[0])
    frame['target_number']=frame.target_week.map(lambda d:DEFAULT_CALENDAR.date_week(d)[1])
    frame['target_count']=lookup(1)
    frame['target_presence']=frame.target_count.gt(0).astype(float).where(frame.target_count.notna())
    frame['count_origin']=lookup(0)
    frame['presence_origin']=frame.count_origin.gt(0).astype(float).where(frame.count_origin.notna())
    for lag in range(1,5):
        frame[f'count_lag_{lag}']=lookup(-lag)
        values=frame[f'count_lag_{lag}']
        frame[f'presence_lag_{lag}']=values.gt(0).astype(float).where(values.notna())
    for window in (2,4):
        cols=['count_origin',*[f'count_lag_{i}' for i in range(1,window)]]
        frame[f'known_{window}']=frame[cols].notna().sum(axis=1)
        frame[f'mean_{window}']=frame[cols].mean(axis=1).where(frame[f'known_{window}'].eq(window))
    frame['trend_1']=frame.count_origin-frame.count_lag_1
    graph={radio:[] for radio in frame.radio_id.unique()}
    for left,right in edges:
        if left==right or left not in graph or right not in graph:
            raise DatasetBlocked('motor_invalid_common_graph')
        graph[left].append(right)
    if any(len(values)!=len(set(values)) for values in graph.values()):
        raise DatasetBlocked('motor_duplicate_graph_edge')
    for left,values in graph.items():
        if any(left not in graph[right] for right in values):
            raise DatasetBlocked('motor_asymmetric_common_graph')
    additions=[]
    values=source.to_dict()
    for row in frame.itertuples():
        neighbors=graph[row.radio_id]
        obs=np.array([values.get((radio,row.origin_week),np.nan) for radio in neighbors],dtype=float)
        good=np.isfinite(obs)
        additions.append((float(obs[good].mean()) if good.any() else np.nan,
            float((obs[good]>0).mean()) if good.any() else np.nan,float(good.mean()) if len(obs) else np.nan))
    frame[['neighbor_count_mean','neighbor_presence_mean','neighbor_known_fraction']]=pd.DataFrame(additions,index=frame.index)
    frame['poblacion']=frame.poblacion_predictor_asof.astype(float)
    frame['densidad_poblacional']=frame.poblacion/frame.superficie_km2
    frame['cantidad_vecinos']=frame.radio_id.map(lambda radio:len(graph[radio]))
    frame['semana_epidemiologica']=frame.numero
    frame['estacionalidad_seno']=frame.origin_week.map(lambda d:np.sin(2*np.pi*DEFAULT_CALENDAR.date_week(d)[1]/
        next(y.weeks for y in DEFAULT_CALENDAR.years if y.year==DEFAULT_CALENDAR.date_week(d)[0])))
    frame['estacionalidad_coseno']=frame.origin_week.map(lambda d:np.cos(2*np.pi*DEFAULT_CALENDAR.date_week(d)[1]/
        next(y.weeks for y in DEFAULT_CALENDAR.years if y.year==DEFAULT_CALENDAR.date_week(d)[0])))
    mapping={'temperatura':'temperature','humedad':'humidity','precipitacion':'precipitation',
        'temperatura_lag_1':'temperature_lag_1','humedad_lag_1':'humidity_lag_1','precipitacion_lag_1':'precipitation_lag_1',
        'temperatura_media_4':'temperature_mean_4','precipitacion_suma_4':'precipitation_sum_4',
        'temperatura_historia_previa':'temperature_history','humedad_historia_previa':'humidity_history',
        'precipitacion_media_historia_previa':'precipitation_history'}
    for source_name,target_name in mapping.items():frame[target_name]=frame[source_name].astype(float)
    frame['temperature_anomaly']=frame.temperature-frame.temperature_history
    if (frame.clima_historia_hasta.dropna()>=frame.loc[frame.clima_historia_hasta.notna(),'origin_week']).any():
        raise DatasetBlocked('motor_future_weather_history')
    all_features=list(dict.fromkeys(x for names in FEATURES.values() for x in names))
    if np.isinf(frame[all_features].to_numpy(float)).any():
        raise DatasetBlocked('motor_nonfinite_feature')
    return frame


def load_frame(conn, version, expected_input_sha256):
    repo=MLRepository(conn)
    metadata=repo.query('SELECT * FROM analytics.consolidacion_dataset WHERE version=%s',(version,))
    if len(metadata)!=1 or metadata.iloc[0].politica_version!=POLICY or metadata.iloc[0].entrada_sha256!=expected_input_sha256:
        raise DatasetBlocked('verified_stage1_version_and_hash_required')
    raw=repo.query('''SELECT * FROM analytics.consolidacion_radio_semana
        WHERE dataset_version=%s AND mascara_comun AND anio BETWEEN 2020 AND 2024 ORDER BY radio_id,inicio''',(version,))
    if raw.radio_id.nunique()!=256 or raw.groupby('inicio').radio_id.nunique().ne(256).any():
        raise DatasetBlocked('motor_incomplete_common_territory')
    # A withdrawn source must not silently remain an active training snapshot.
    current=repo.query('''SELECT count(*) missing FROM analytics.consolidacion_fuente s
        LEFT JOIN ingestion.lotes_sisa_vigentes b ON b.id=s.lote_id
        LEFT JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id AND a.sha256=s.fuente_sha256
        WHERE s.dataset_version=%s AND a.id IS NULL''',(version,))
    if current.iloc[0,0]:raise DatasetBlocked('motor_source_withdrawn_or_changed')
    edges=repo.query('''SELECT n.radio_id,n.vecino_id FROM territory.vecindad n
        JOIN analytics.consolidacion_territorio a ON a.radio_id=n.radio_id AND a.mascara_comun
        JOIN analytics.consolidacion_territorio b ON b.radio_id=n.vecino_id AND b.dataset_version=a.dataset_version AND b.mascara_comun
        WHERE a.dataset_version=%s ORDER BY 1,2''',(version,))
    frame=build_frame(raw,list(edges.itertuples(index=False,name=None)))
    features=list(dict.fromkeys(x for names in FEATURES.values() for x in names))
    fingerprint=canonical_hash(frame[['radio_id','origin_week','target_week','target_count',*features]].astype(object).where(
        frame[['radio_id','origin_week','target_week','target_count',*features]].notna(),None).to_dict('records'))
    return frame,dict(dataset_version=version,stage1_sha256=expected_input_sha256,matrix_sha256=fingerprint,
        rows=len(frame),known_targets=int(frame.target_count.notna().sum()),radios=int(frame.radio_id.nunique()),
        feature_missing=frame[features].isna().sum().astype(int).to_dict(),
        arrival_verified=False,population_unaccredited_kept_unknown=True)
