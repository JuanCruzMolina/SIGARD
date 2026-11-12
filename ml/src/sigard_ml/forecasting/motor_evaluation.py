"""Paired temporal evaluation, prespecified decisions and no model fitting."""
import numpy as np
from sklearn.metrics import confusion_matrix,precision_score,recall_score,f1_score

from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.motor_protocol import PROTOCOL,PRESENCE,PRESENCE_BASELINES,COUNT_BASELINES
from sigard_ml.official.spatial_ml.research_training import classification_metrics,reliability_bins
from sigard_ml.data_access import DatasetBlocked


def presence_metrics(frame, method):
    y=frame.target_count.gt(0).to_numpy(int)
    score=frame[method].to_numpy(float)
    result=classification_metrics(y,score,.5)
    decision=score>=frame[method+'_threshold'].to_numpy(float)
    cm=confusion_matrix(y,decision,labels=[0,1])
    result.update(threshold='inner_development_or_fixed_0.5',precision=float(precision_score(y,decision,zero_division=0)),
        recall=float(recall_score(y,decision,zero_division=0)),f1=float(f1_score(y,decision,zero_division=0)),
        confusion_matrix_true_rows_predicted_columns_0_1=cm.tolist(),
        false_positives=int(cm[0,1]),false_negatives=int(cm[1,0]),true_positives=int(cm[1,1]),
        true_negatives=int(cm[0,0]),predicted_positive=int(decision.sum()),
        reliability=reliability_bins(y,score))
    return result


def top_zones(frame, method):
    k=PROTOCOL['top_zones']['k'];rows=[]
    for week,group in frame.groupby('target_week',sort=True):
        score=group[method].to_numpy(float);y=group.target_count.gt(0).to_numpy()
        onset=y & group.count_origin.eq(0).to_numpy()
        n=min(k,len(score));cut=np.sort(score)[-n]
        above=score>cut;tied=score==cut
        weights=above.astype(float)
        weights[tied]=(n-int(above.sum()))/max(int(tied.sum()),1)
        rows.append(dict(target_week=str(week),positive_zones=int(y.sum()),new_activation_zones=int(onset.sum()),
            top_k=n,positive_hits=float(weights[y].sum()),new_activation_hits=float(weights[onset].sum()),
            top_k_precision=float(weights[y].sum()/n),
            new_activation_recall=float(weights[onset].sum()/onset.sum()) if onset.any() else None))
    events=sum(r['new_activation_zones'] for r in rows)
    return dict(k=k,tie_policy='fractional',new_activation_zones=events,
        new_activation_recall=sum(r['new_activation_hits'] for r in rows)/events if events else None,
        mean_top_k_precision=float(np.mean([r['top_k_precision'] for r in rows])),weekly=rows)


def count_summary(frame, method):
    result=count_metrics(frame.target_count,frame[method])
    def subset(mask):return count_metrics(frame.loc[mask,'target_count'],frame.loc[mask,method]) if mask.any() else None
    result['zero']=subset(frame.target_count.eq(0))
    result['positive']=subset(frame.target_count.gt(0))
    result['high_count']=subset(frame.target_count.ge(frame.tail_limit))
    weekly=frame.groupby('target_week').agg(actual=('target_count','sum'),predicted=(method,'sum'),limit=('week_limit','first'))
    result['weekly_total']=count_metrics(weekly.actual,weekly.predicted)
    high=weekly.actual.ge(weekly.limit)
    result['high_week']=count_metrics(weekly.loc[high,'actual'],weekly.loc[high,'predicted']) if high.any() else None
    result['known_subset_only']=True
    return result


def summarize(frame):
    presence_names=(*PRESENCE,*PRESENCE_BASELINES)
    count_names=('residual_h1',*COUNT_BASELINES)
    result=dict(rows=len(frame),weeks=int(frame.target_week.nunique()),
        first_target=str(frame.target_week.min()),last_target=str(frame.target_week.max()),
        observed_records=int(frame.target_count.sum()),positive_cells=int(frame.target_count.gt(0).sum()),
        presence={name:presence_metrics(frame,name) for name in presence_names},
        counts={name:count_summary(frame,name) for name in count_names},
        early_zones={name:top_zones(frame,name) for name in presence_names},by_year={})
    for year,group in frame.groupby('target_year',sort=True):
        result['by_year'][str(year)]=dict(rows=len(group),weeks=int(group.target_week.nunique()),
            records=int(group.target_count.sum()),positive_cells=int(group.target_count.gt(0).sum()),
            presence={name:presence_metrics(group,name) for name in presence_names},
            counts={name:count_summary(group,name) for name in count_names},
            early_zones={name:top_zones(group,name) for name in presence_names})
    return result


def granular_metrics(frame):
    """Period/zone diagnostics kept separate from compact decision summaries."""
    presence_names=(*PRESENCE,*PRESENCE_BASELINES)
    count_names=('residual_h1',*COUNT_BASELINES)
    weekly=[];zones=[]
    for week,group in frame.groupby('target_week',sort=True):
        weekly.append(dict(target_week=str(week),year=int(group.target_year.iloc[0]),
            records=int(group.target_count.sum()),radios=len(group),positive_cells=int(group.target_count.gt(0).sum()),
            presence={name:presence_metrics(group,name) for name in presence_names},
            counts={name:count_summary(group,name) for name in count_names}))
    for radio,group in frame.groupby('radio_id',sort=True):
        zones.append(dict(radio_id=int(radio),radio_codigo=str(group.radio_codigo.iloc[0]),rows=len(group),
            observed_records=int(group.target_count.sum()),
            presence={name:presence_metrics(group,name) for name in presence_names},
            counts={name:count_summary(group,name) for name in count_names}))
    return dict(weekly=weekly,zones=zones)


def paired_interval(frame, method, reference, loss):
    actual=frame.target_count.to_numpy(float)
    if loss=='brier':
        actual=(actual>0).astype(float)
        delta=(frame[method].to_numpy(float)-actual)**2-(frame[reference].to_numpy(float)-actual)**2
    else:
        delta=np.abs(frame[method].to_numpy(float)-actual)-np.abs(frame[reference].to_numpy(float)-actual)
    copy=frame[['target_week','target_year']].copy();copy['delta']=delta
    grouped=copy.groupby(['target_year','target_week']).delta.agg(['sum','size']).reset_index()
    blocks=[]
    for indices in grouped.groupby('target_year',sort=True).indices.values():
        indices=list(indices)
        for start in range(len(indices)):
            block=[indices[start]]
            for nxt in indices[start+1:start+PROTOCOL['bootstrap']['block_weeks']]:
                if (grouped.loc[nxt,'target_week']-grouped.loc[block[-1],'target_week']).days!=7:break
                block.append(nxt)
            blocks.append(block)
    rng=np.random.default_rng(PROTOCOL['bootstrap']['seed'])
    sums=grouped['sum'].to_numpy();sizes=grouped['size'].to_numpy();draws=[]
    for _ in range(PROTOCOL['bootstrap']['resamples']):
        sample=[]
        while len(sample)<len(grouped):sample.extend(blocks[int(rng.integers(len(blocks)))])
        idx=np.asarray(sample[:len(grouped)],int)
        draws.append(float(sums[idx].sum()/sizes[idx].sum()))
    return dict(mean_difference=float(delta.mean()),lower95=float(np.quantile(draws,.025)),
        upper95=float(np.quantile(draws,.975)),method=method,reference=reference,
        loss=loss,unit='paired whole-week moving blocks within epi year',descriptive_not_external=True)


def select_presence(frame, metrics):
    if not set(frame.target_year.unique())<=set(PROTOCOL['development_target_years']):
        raise DatasetBlocked('motor_selection_cannot_use_2024_or_future_years')
    cfg=PROTOCOL['presence_selection'];all_metrics=metrics['presence'];years=metrics['by_year']
    best_baseline=min(PRESENCE_BASELINES,key=lambda n:(all_metrics[n]['brier'],PRESENCE_BASELINES.index(n)))
    candidates={}
    for method in PRESENCE:
        refs=list(PRESENCE_BASELINES)+(list(PRESENCE[:1]) if method!=PRESENCE[0] else [])
        gates=[]
        for ref in refs:
            value,base=all_metrics[method],all_metrics[ref]
            yearly=[(m['presence'][method],m['presence'][ref]) for m in years.values()]
            wins=sum(a['brier']<b['brier'] for a,b in yearly)
            stable=all(a['brier']<=cfg['year_max_brier_ratio']*b['brier']+cfg['year_absolute_tolerance'] for a,b in yearly)
            ap_ok=(value['average_precision_pr_auc'] is not None and base['average_precision_pr_auc'] is not None
                and value['average_precision_pr_auc']>=base['average_precision_pr_auc']-cfg['average_precision_max_loss'])
            interval=paired_interval(frame,method,ref,'brier')
            gates.append(dict(reference=ref,brier=value['brier']<=(1-cfg['brier_relative_improvement'])*base['brier'],
                discriminative=ap_ok,decision_errors=value['f1']>=base['f1']-cfg['f1_max_loss'],
                year_wins=wins,stable=stable,interval=interval))
        approved=all(g['brier'] and g['discriminative'] and g['decision_errors'] and g['stable']
            and g['year_wins']>=cfg['minimum_year_wins'] and g['interval']['upper95']<0 for g in gates)
        candidates[method]=dict(approved=bool(approved),gates=gates)
    enhanced=[m for m in PRESENCE[1:] if candidates[m]['approved']]
    if enhanced:
        chosen=min(enhanced,key=lambda n:(all_metrics[n]['brier'],n!=PRESENCE[2]))
    elif candidates[PRESENCE[0]]['approved']:chosen=PRESENCE[0]
    else:chosen=best_baseline
    return dict(selected=chosen,is_trained_ml=chosen in PRESENCE,promotion_approved=chosen in PRESENCE,
        candidates=candidates,strongest_simple_reference=best_baseline,selected_using=[2021,2022,2023],operational_enabled=False)


def select_counts(frame, metrics):
    if not set(frame.target_year.unique())<=set(PROTOCOL['development_target_years']):
        raise DatasetBlocked('motor_selection_cannot_use_2024_or_future_years')
    cfg=PROTOCOL['count_selection'];value=metrics['counts']['residual_h1'];gates=[]
    for ref in COUNT_BASELINES:
        baseline=metrics['counts'][ref]
        yearly=[(m['counts']['residual_h1'],m['counts'][ref]) for m in metrics['by_year'].values()]
        ratio=lambda key,mult: value[key] is None or baseline[key] is None or value[key]['mae']<=mult*baseline[key]['mae']
        high_week=(value['high_week'] is None or baseline['high_week'] is None
                   or value['high_week']['rmse']<=cfg['high_week_rmse_max_ratio']*baseline['high_week']['rmse'])
        zero=(value['zero'] is None or baseline['zero'] is None or value['zero']['mae']<=
              cfg['zero_mae_max_ratio']*baseline['zero']['mae']+cfg['zero_mae_absolute_tolerance'])
        gates.append(dict(reference=ref,
            mae=value['mae']<=(1-cfg['mae_relative_improvement'])*baseline['mae'],
            rmse=value['rmse']<=cfg['rmse_max_ratio']*baseline['rmse'],
            bias=abs(value['mean_bias'])<=abs(baseline['mean_bias'])+cfg['bias_mean_y_tolerance']*float(frame.target_count.mean()),
            positive=ratio('positive',cfg['positive_mae_max_ratio']),high_count=ratio('high_count',cfg['high_count_mae_max_ratio']),
            high_week=high_week,zero=zero,year_wins=sum(a['mae']<b['mae'] for a,b in yearly),
            stable=all(a['mae']<=cfg['year_max_mae_ratio']*b['mae']+1e-12 for a,b in yearly),
            interval=paired_interval(frame,'residual_h1',ref,'mae')))
    approved=all(all(g[k] for k in ('mae','rmse','bias','positive','high_count','high_week','zero','stable'))
        and g['year_wins']>=cfg['minimum_year_wins'] and g['interval']['upper95']<0 for g in gates)
    return dict(selected='residual_h1' if approved else 'count_latest',is_trained_ml=bool(approved),
        promotion_approved=bool(approved),gates=gates,selected_using=[2021,2022,2023],operational_enabled=False)
