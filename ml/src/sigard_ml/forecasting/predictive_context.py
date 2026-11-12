"""Read-only projection of stage1 climate at the permitted historical origin."""
from datetime import timedelta
import hashlib
import json

from sigard_ml.data_access import DatasetBlocked,MLRepository
from sigard_ml.forecasting.consolidation import POLICY
from sigard_ml.forecasting.option_b_data import json_dump

USAGE='context_only_not_used_by_selected_methods'


def project_context(weeks,weather):
    by_origin={r['inicio']:r for r in weather};output={}
    for week in weeks:
        target=week['inicio'];origin=target-timedelta(days=7);end=target-timedelta(days=1)
        row=by_origin.get(origin)
        if row and row['fin']>end:raise DatasetBlocked('future_climate_context')
        available=bool(row and row['dias']==7 and all(row[k] is not None for k in ('temperatura','humedad','precipitacion')))
        output[str(target)]=dict(availability_status='available' if available else 'not_available',
            origin_week=str(origin),origin_end=str(end),period_end=str(row['fin']) if row else None,
            temperature_mean=float(row['temperatura']) if available else None,
            humidity_mean=float(row['humedad']) if available else None,
            precipitation_total=float(row['precipitacion']) if available else None,days=int(row['dias']) if row else None,
            availability_basis='event_dates_only_arrival_not_accredited',usage=USAGE,
            spatial_support='single_open_meteo_reference_point_la_rioja_capital_not_per_radio')
    return output


def compile_context(conn,dataset,output):
    repo=MLRepository(conn)
    meta=repo.query('SELECT politica_version,entrada_sha256 FROM analytics.consolidacion_dataset WHERE version=%s',(dataset,))
    if len(meta)!=1 or meta.iloc[0].politica_version!=POLICY:raise DatasetBlocked('verified_stage1_policy_required')
    weather=repo.query('SELECT * FROM analytics.consolidacion_clima WHERE dataset_version=%s ORDER BY inicio',(dataset,))
    weather=weather.astype(object).where(weather.notna(),None).to_dict('records')
    weeks=repo.query('SELECT inicio FROM analytics.consolidacion_departamento WHERE dataset_version=%s ORDER BY inicio',(dataset,)).to_dict('records')
    doc=dict(dataset_version=dataset,policy_version=POLICY,stage1_sha256=meta.iloc[0].entrada_sha256,usage=USAGE,
             weeks=project_context(weeks,weather))
    if output.exists():raise DatasetBlocked('new_private_context_output_required')
    output.parent.mkdir(parents=True,exist_ok=True);body=json_dump(doc).encode('utf-8');output.write_bytes(body)
    return dict(dataset_version=dataset,sha256=hashlib.sha256(body).hexdigest(),weeks=len(weeks),training_performed=False)
