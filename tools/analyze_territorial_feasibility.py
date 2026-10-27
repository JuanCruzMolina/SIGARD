"""Read-only feasibility analysis: existing derived counts and frozen predictions.

No estimators, fit, model loading, new forecasts, parameter selection, original
sources or writes. Only aggregate JSON goes to stdout. Missing labels stay null.
"""
import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

METHODS=('v3_direct_poisson','v3_hurdle','v3_residual_boosting',
         'lag_1_or_training_mean','latest_closed_or_training_mean')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def description(values):
    array=np.asarray(values,dtype=float)
    array=array[np.isfinite(array)]
    if not len(array):
        return dict(n=0)
    return dict(n=len(array),mean=float(array.mean()),median=float(np.median(array)),
                p25=float(np.quantile(array,.25)),p75=float(np.quantile(array,.75)),
                minimum=float(array.min()),maximum=float(array.max()))


def adjacent_pairs(index):
    return [(i-1,i) for i in range(1,len(index)) if index[i]-index[i-1]==timedelta(weeks=1)]


def coverage(pivot):
    known=pivot.notna().sum(axis=1)
    return dict(weeks=len(pivot),radios=pivot.shape[1],known_cells=int(pivot.notna().sum().sum()),
                unknown_cells=int(pivot.isna().sum().sum()),known_per_week=description(known),
                completely_known_weeks=int(known.eq(pivot.shape[1]).sum()),
                weeks_at_least_90_percent=int(known.ge(.90*pivot.shape[1]).sum()),
                weeks_at_least_95_percent=int(known.ge(.95*pivot.shape[1]).sum()),
                weeks_at_maximum_observable=int(known.eq(pivot.notna().any(axis=0).sum()).sum()),
                radios_known_every_week=int(pivot.notna().all(axis=0).sum()),
                radios_never_known=int(pivot.isna().all(axis=0).sum()))


def concentration(values):
    values=np.asarray(values,float)
    assert np.isfinite(values).all() and (values>=0).all()
    total=values.sum()
    if total==0:
        return None
    shares=values/total
    ordered=np.sort(shares)[::-1]
    return dict(active_radios=int((values>0).sum()),largest_share=float(ordered[0]),
                top10_share=float(ordered[:min(10,len(ordered))].sum()),
                hhi=float((shares**2).sum()),effective_radios=float(1/(shares**2).sum()))


def variation(p,q):
    p,q=np.asarray(p,float),np.asarray(q,float)
    assert p.shape==q.shape and np.isfinite(p).all() and np.isfinite(q).all()
    if p.sum()<=0 or q.sum()<=0:
        return None
    return float(abs(p/p.sum()-q/q.sum()).sum()/2)


def distribution_summary(pivot):
    # A changing-support subtotal is never labelled city total.
    rows=[]
    for _,row in pivot.iterrows():
        value=concentration(row.dropna().to_numpy())
        if value is not None:
            rows.append(value)
    summary={key:description([r[key] for r in rows]) for key in
             ('active_radios','largest_share','top10_share','hhi','effective_radios')}
    pairs=[]
    for left,right in adjacent_pairs(pivot.index):
        a,b=pivot.iloc[left],pivot.iloc[right]
        mask=a.notna() & b.notna()
        x,y=a.loc[mask].to_numpy(float),b.loc[mask].to_numpy(float)
        tv=variation(x,y)
        if tv is None:
            continue
        active_a,active_b=x>0,y>0
        union=int((active_a|active_b).sum())
        pairs.append(dict(total_variation=tv,
            active_jaccard=float((active_a&active_b).sum()/union),
            record_share_in_newly_active_radios=float(y[(x==0)&(y>0)].sum()/y.sum()),
            common_radios=int(mask.sum()),left_total=float(x.sum()),right_total=float(y.sum())))
    summary['positive_consecutive_pairs']=len(pairs)
    summary['consecutive_pairs']={key:description([r[key] for r in pairs]) for key in
        ('total_variation','active_jaccard','record_share_in_newly_active_radios','common_radios')}
    return summary


def trend_summary(complete):
    # Required complete and fixed support; excludes missing weeks, never fills gaps.
    assert complete.notna().all().all()
    values=complete.to_numpy(float)
    total=values.sum(axis=1)
    pairs=adjacent_pairs(complete.index)
    cell_change=sum(float(abs(values[b]-values[a]).sum()) for a,b in pairs)
    total_change=sum(float(abs(total[b]-total[a])) for a,b in pairs)
    past=np.array([total[a] for a,b in pairs])
    future=np.array([total[b] for a,b in pairs])
    autocorrelation=float(np.corrcoef(past,future)[0,1]) if len(pairs)>=3 and past.std()>0 and future.std()>0 else None
    return dict(weeks=len(complete),fixed_radios=complete.shape[1],consecutive_pairs=len(pairs),
                mean_weekly_subset_total=float(total.mean()) if len(total) else None,
                zero_cell_fraction=float((values==0).mean()) if values.size else None,
                zero_total_fraction=float((total==0).mean()) if len(total) else None,
                pooled_cell_cv=float(values.std()/values.mean()) if values.mean()>0 else None,
                weekly_total_cv=float(total.std()/total.mean()) if total.mean()>0 else None,
                lag1_correlation_consecutive_only=autocorrelation,
                aggregate_change_divided_by_sum_radio_changes=float(total_change/cell_change) if cell_change>0 else None)


def error_decomposition(y,p):
    """Exact weekly L1 identity: sum|e| = |sum e| + cancelling error.

    The first term is a lower bound due to total mismatch; neither term is a
    causal attribution. TV of normalized shares isolates composition descriptively.
    """
    y,p=np.asarray(y,float),np.asarray(p,float)
    assert y.shape==p.shape and np.isfinite(y).all() and np.isfinite(p).all()
    assert (y>=0).all() and (p>=0).all()
    error=p-y
    l1=float(abs(error).sum())
    total_error=float(error.sum())
    unmatched=abs(total_error)
    cancelling=max(0.,l1-unmatched)
    assert np.isclose(l1,unmatched+cancelling)
    return dict(cells=len(y),total_absolute_error=l1,total_squared_error=float((error**2).sum()),
                absolute_subset_total_error=unmatched,signed_subset_total_error=total_error,
                cancelling_error=cancelling,actual_total=float(y.sum()),predicted_total=float(p.sum()),
                share_tv=variation(y,p),predicted_mass_on_observed_zero=float(p[y==0].sum()/p.sum()) if p.sum()>0 else None)


def errors_summary(frame,method):
    rows=[error_decomposition(group.target_count,group[method]) for _,group in frame.groupby('target_week')]
    l1=sum(r['total_absolute_error'] for r in rows)
    total=sum(r['actual_total'] for r in rows)
    return dict(weeks=len(rows),cells=len(frame),
        subset_total_mismatch_fraction_of_l1=sum(r['absolute_subset_total_error'] for r in rows)/l1 if l1>0 else None,
        complementary_cancelling_fraction_of_l1=sum(r['cancelling_error'] for r in rows)/l1 if l1>0 else None,
        weekly_subset_total_mae=float(np.mean([r['absolute_subset_total_error'] for r in rows])),
        weekly_subset_total_rmse=float(np.sqrt(np.mean([r['signed_subset_total_error']**2 for r in rows]))),
        mean_composition_tv=description([r['share_tv'] for r in rows if r['share_tv'] is not None]),
        mean_predicted_mass_on_observed_zero=description([r['predicted_mass_on_observed_zero'] for r in rows if r['predicted_mass_on_observed_zero'] is not None]),
        captured_total_ratio=sum(r['predicted_total'] for r in rows)/total if total>0 else None,
        diagnostic_only=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    snapshot=root/'data/processed/official/principal_snapshot_20261026_v2'
    artifact=root/'ml/artifacts/official/sigard-principal-v3-experimental'
    inputs={}
    def read_frame(folder,name,columns=None):
        manifest_path=folder/'manifest.private.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        path=(folder/name).resolve()
        assert path.is_relative_to(folder) and path.is_file() and not path.is_symlink()
        assert path.stat().st_nlink==1 and path.stat().st_size<64*1024**2
        assert digest(path)==manifest['outputs_sha256'][name]
        metadata=pq.ParquetFile(path)
        assert metadata.metadata.num_rows<=100000 and len(metadata.schema_arrow.names)<=50
        inputs[str(path.relative_to(root))]=digest(path)
        inputs[str(manifest_path.relative_to(root))]=digest(manifest_path)
        return pd.read_parquet(path,columns=columns)
    protected={str(p.relative_to(root)):digest(p)
        for version in ('v1','v2','v3')
        for p in (root/f'ml/artifacts/official/sigard-principal-{version}-experimental').rglob('*') if p.is_file()}
    grid=read_frame(snapshot,'covered_grid.private.parquet',
        ['radio_id','week_start','snapshot_count','label_usable','pending_mask','temporal_mask'])
    assert not grid.duplicated(['radio_id','week_start']).any()
    assert grid.snapshot_count.notna().equals(grid.label_usable)
    assert grid.loc[~grid.label_usable,'snapshot_count'].isna().all()
    assert grid.week_start.map(lambda d:d.year!=2022).all()
    pivot=grid.pivot(index='week_start',columns='radio_id',values='snapshot_count').sort_index()
    assert pivot.shape[1]==256 and len(grid)==pivot.size
    common=pivot.loc[:,pivot.notna().all(axis=0)]
    ever_known=pivot.loc[:,pivot.notna().any(axis=0)]
    maximum_observable_complete=ever_known.loc[ever_known.notna().all(axis=1)]
    panel=read_frame(artifact,'horizon_1/modeling_panel.private.parquet',
        ['radio_id','origin_week','target_week','partition','target_count','count_origin'])
    development_weeks=set(panel.loc[panel.partition.isin(['train','validation']),'target_week'])
    comparison_weeks=set(panel.loc[panel.partition.eq('test'),'target_week'])
    scopes={'all_covered':pivot.index,'development':pivot.index[pivot.index.isin(development_weeks)],
            'observed_2024_comparison':pivot.index[pivot.index.isin(comparison_weeks)]}
    for year in sorted({d.year for d in pivot.index}):
        scopes[f'year_{year}']=pivot.index[pivot.index.map(lambda d:d.year==year)]
    result=dict(unit='filtered_snapshot_records_per_radio_week',city_total_requires_256_known_labels=True,
        unknowns_imputed=False,models_loaded=False,trained=False,new_forecasts=False,
        coverage={},global_fixed_radios=common.shape[1],trends_fixed_support={},
        concentration_variable_support={},concentration_fixed_support={},errors_t1={})
    for scope,index in scopes.items():
        part=pivot.loc[index]
        result['coverage'][scope]=coverage(part)
        result['trends_fixed_support'][scope]=trend_summary(common.loc[index])
        result['concentration_variable_support'][scope]=distribution_summary(part)
        result['concentration_fixed_support'][scope]=distribution_summary(common.loc[index])
    result['complete_maximum_observable_subset']={}
    for scope,index in scopes.items():
        subset=maximum_observable_complete.loc[maximum_observable_complete.index.isin(index)]
        result['complete_maximum_observable_subset'][scope]=dict(weeks=len(subset),radios=subset.shape[1],
            trends=trend_summary(subset),concentration=distribution_summary(subset))
    result['mask_counts']={
        'pending':int(grid.pending_mask.sum()),'temporal':int(grid.temporal_mask.sum()),
        'both':int((grid.pending_mask & grid.temporal_mask).sum())}
    for period,file in [('development_oof','development_predictions'),('observed_2024_comparison','comparison_predictions')]:
        predictions=read_frame(artifact,f'horizon_1/{file}.private.parquet')
        keys=['radio_id','origin_week','target_week']
        assert not predictions.duplicated(keys).any()
        joined=predictions.merge(panel,on=keys,how='left',validate='one_to_one',suffixes=('','_panel'))
        assert joined.target_count.equals(joined.target_count_panel)
        result['errors_t1'][period]={method:errors_summary(joined,method) for method in METHODS}
        result['errors_t1'][period]['by_fold']={
            str(fold):{method:errors_summary(part,method) for method in METHODS}
            for fold,part in joined.groupby('fold')} if 'fold' in joined else {}
        # Restrict origin/target trend comparison to exactly paired known cells.
        matched=joined.loc[joined.count_origin.notna()]
        actual=float(matched.target_count.sum())
        result['errors_t1'][period]['paired_origin_description']=dict(cells=len(matched),
            fraction_records_at_radios_zero_at_origin=float(matched.loc[matched.count_origin.eq(0),'target_count'].sum()/actual) if actual>0 else None,
            rising_week_fraction=float(matched.groupby('target_week').apply(lambda p:p.target_count.sum()>p.count_origin.sum(),include_groups=False).mean()))
    assert all(digest(root/name)==sha for name,sha in inputs.items())
    assert all(digest(root/name)==sha for name,sha in protected.items())
    result['integrity']=dict(verified_inputs=len(inputs),protected_files=len(protected),protected_unchanged=True,
        inputs_sha256=inputs,script_sha256=digest(Path(__file__)))
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    main()
