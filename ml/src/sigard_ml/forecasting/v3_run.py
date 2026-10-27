"""Una ejecución V3 autorizada sobre el pipeline principal y derivados existentes.

No ingiere originales ni repite auditorías. Todas las selecciones se sellan
antes de evaluar el período V1/V2 ya observado. Repetir exige un destino nuevo.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import sklearn

from sigard_ml.forecasting.adapter import AdapterRequest, EvidenceDocument, adapt_derived
from sigard_ml.forecasting.contracts import PROVISIONAL_EXPERIMENT
from sigard_ml.forecasting.v3 import (VERSION,PROTOCOL,FEATURES,CANDIDATES,BASELINES,METHOD_LABELS,
    validate_development,fit_final,count_summary,presence_summary,precision_recall_rows)
from sigard_ml.official.access import SourceAuthorization,SourceRegistry,AuthorizedUse
from sigard_ml.official.epidemiological_preflight.evidence import canonical_bytes

def snapshot_provenance(grid, bundle):
    """Validate the authorized grid without embedding private dataset totals."""
    keys = ["radio_id", "week_start"]
    expected = pd.MultiIndex.from_product([
        bundle["radios"],
        [date.fromisoformat(value) for value in bundle["snapshot_scenario"]["covered_weeks"]],
    ], names=keys)
    actual = pd.MultiIndex.from_frame(grid[keys])
    assert actual.is_unique and len(actual) == len(expected)
    assert set(actual) == set(expected)
    assert grid.snapshot_count.notna().equals(grid.label_usable)
    assert grid.loc[~grid.label_usable, "snapshot_count"].isna().all()
    return dict(source_grid_cells=len(grid), usable_labels=int(grid.snapshot_count.notna().sum()),
        unknown_labels=int(grid.snapshot_count.isna().sum()),
        source_positive_records=int(grid.recorded_positive_count.sum()))


def main():
    ROOT=Path(__file__).resolve().parents[4]
    V2=ROOT/"ml/artifacts/official/sigard-principal-v2-experimental"
    DATA=ROOT/"data/processed/official/principal_snapshot_20261026_v2"
    HERE=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description="V3 local autorizada; sin sobrescrituras")
    parser.add_argument("--output",type=Path,default=ROOT/"ml/artifacts/official"/VERSION)
    args=parser.parse_args()
    OUT=args.output.resolve()
    assert OUT.parent==ROOT/"ml/artifacts/official" and OUT.name.startswith("sigard-principal-v3-")
    assert not OUT.exists(),"No sobrescribir una ejecución"
    assert subprocess.check_output(["git","branch","--show-current"],text=True).strip()=="entrenamiento-ML"
    OUT.mkdir()
    dig=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    inputs_sha={}


    def read(path):
        inputs_sha[path.relative_to(ROOT).as_posix()]=dig(path)
        return json.loads(path.read_text(encoding="utf-8"))


    def write(path,value):
        with path.open("x",encoding="utf-8") as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)


    protected={p.relative_to(ROOT).as_posix():dig(p) for name in ("sigard-principal-v1-experimental","sigard-principal-v2-experimental")
        for p in (ROOT/"ml/artifacts/official"/name).rglob("*") if p.is_file()}
    protocol=dict(PROTOCOL,source_dataset="principal_snapshot_20261026_v2",authorization_basis="project_owner_declared_provision",
        execution_authorization="Explicit project-owner V3 request, 2026-10-26, local experimental aggregates; V1/V2 preserved",
        configuration_frozen_before_fit=True,versions=dict(python=sys.version,sklearn=sklearn.__version__,pandas=pd.__version__,numpy=np.__version__,joblib=joblib.__version__))
    write(OUT/"configuration.private.json",protocol)
    write(OUT/"protected_before.private.json",protected)
    manifest=read(DATA/"manifest.private.json")


    def verified(name):
        path=DATA/name
        assert dig(path)==manifest["outputs_sha256"][name]
        inputs_sha[path.relative_to(ROOT).as_posix()]=dig(path)
        return path


    bundle=read(verified("derived_bundle.private.json"))
    access=read(verified("access.private.json"))
    documents=read(verified("documents.private.json"))
    registry=SourceRegistry(tuple(SourceAuthorization(**dict(row,path=Path(row["path"]),sheets=tuple(row["sheets"]),
        uses=frozenset(AuthorizedUse(use) for use in row["uses"]))) for row in access["sources"]))
    docs={ref:EvidenceDocument(canonical_bytes(value["content"]),value["sha256"]) for ref,value in documents.items()}
    prep_ref=next(ref for ref,value in documents.items() if value["content"]["role"]=="provisional_experiment_preparation")
    use_ref=next(ref for ref,value in documents.items() if value["content"]["role"]=="provisional_experiment_use")
    prep=documents[prep_ref]["content"]
    request=AdapterRequest(prep["source_id"],bundle["dataset_version"],prep["subset_ref"],
        hashlib.sha256(canonical_bytes(bundle)).hexdigest(),prep_ref,use_ref,date(2026,10,26),mode=PROVISIONAL_EXPERIMENT)
    inputs=adapt_derived(canonical_bytes(bundle),registry,request,documents=docs)
    v2_manifest=read(V2/"manifest.private.json")
    grid=pd.read_parquet(verified("covered_grid.private.parquet"))
    source_summary=snapshot_provenance(grid,bundle)
    validations,finals,selections,unsupported={},{},{},{}
    print(json.dumps(dict(protocol_frozen=True,candidates=list(CANDIDATES),destination=str(OUT.relative_to(ROOT)))),flush=True)

    # Exclusivamente desarrollo: no se evalúa comparación hasta sellar los 3 horizontes.
    for h in PROTOCOL["horizons"]:
        folder=OUT/f"horizon_{h}"
        folder.mkdir()
        name=f"horizon_{h}/modeling_panel.private.parquet"
        path=V2/name
        assert dig(path)==v2_manifest["outputs_sha256"][name]
        inputs_sha[path.relative_to(ROOT).as_posix()]=dig(path)
        cached=pd.read_parquet(path)
        result=validate_development(inputs,cached,h)
        old_oof=pd.read_parquet(V2/f"horizon_{h}/development_predictions.private.parquet")
        assert set(result["oof"][["radio_id","target_week"]].itertuples(index=False,name=None))==set(old_oof[["radio_id","target_week"]].itertuples(index=False,name=None))
        result["oof"].to_parquet(folder/"development_predictions.private.parquet",index=False)
        result["frame"][["radio_id","origin_week","cutoff_date","target_week","target_end","partition","target_count","predictor_admissible",*FEATURES]].to_parquet(folder/"modeling_panel.private.parquet",index=False)
        write(folder/"development_metrics.private.json",result["report"])
        joblib.dump(result["fold_models"],folder/"fold_models.private.joblib",compress=3)
        final=fit_final(result,h)
        joblib.dump(final,folder/"models.private.joblib",compress=3)
        validations[h],finals[h],selections[str(h)]=result,final,result["report"]["selection"]
        print(json.dumps(dict(horizon=h,development_rows=len(result["development"]),validation_rows=len(result["oof"]),
            best_ml=selections[str(h)]["best_ml"],selected=selections[str(h)]["selected"],
            validation={name:{key:value[key] for key in ("mae","rmse","mean_bias")} for name,value in result["report"]["validation"].items()})),flush=True)
    write(OUT/"selection.private.json",dict(horizons=selections,selection_uses_development_only=True,
        previous_comparison_used=False,default_query_version_unchanged=True))

    reports,active_rows,reference_rows,weekly_all,pr_rows={},[],[],[],[]
    for h,result in validations.items():
        folder=OUT/f"horizon_{h}"
        frame,development=result["frame"],result["development"]
        comparison=frame.loc[frame.partition.eq("test") & frame.predictor_admissible & frame.target_count.notna()]
        assert comparison.target_week.nunique()>=4
        fitted=finals[h]
        tail=max(2.,float(development.target_count.quantile(.9)))
        high=float(development.groupby("target_week").target_count.sum().quantile(.8))
        predictions=comparison[["radio_id","origin_week","target_week","target_count"]].copy()
        comparisons={}
        for name,model in fitted["counts"].items():
            predictions[name]=model.predict_frame(comparison)
            comparisons[name]=count_summary(comparison,predictions[name],tail,high)
            shift=comparison.target_count.gt(float(development.target_count.max()))
            comparisons[name]["above_development_max"]=(count_summary(comparison.loc[shift],predictions.loc[shift,name],tail,high) if shift.any() else None)
        predictions.to_parquet(folder/"comparison_predictions.private.parquet",index=False)
        pres=fitted["presence"]
        scores=comparison[["radio_id","origin_week","target_week","target_count"]].copy()
        scores["presence_score"],scores["presence_raw"]=pres.score(comparison),pres.score(comparison,raw=True)
        scores["threshold"]=pres.threshold
        scores["training_prevalence"]=float(development.target_count.gt(0).mean())
        scores["presence_persistence"]=np.where(comparison.cases_lag_1.notna(),comparison.cases_lag_1.gt(0),float(development.target_count.gt(0).mean()))
        presence_metrics={name:presence_summary(comparison,scores[name],[pres.threshold]*len(scores) if name=="presence_score" else [.5 if pres.threshold is not None else None]*len(scores))
            for name in ("presence_score","presence_raw","training_prevalence","presence_persistence")}
        scores.to_parquet(folder/"presence_comparison.private.parquet",index=False)
        for part,pframe,values in (("development_oof",result["oof"],result["oof"].presence_score),("comparison_previously_observed",comparison,scores.presence_score)):
            for row in precision_recall_rows(pframe,values):pr_rows.append(dict(horizon=h,partition=part,**row))
        presence_weekly=[]
        for part,pframe in (("development_oof",result["oof"]),("comparison_previously_observed",scores)):
            for target,group in pframe.groupby("target_week"):
                thresholds=group.presence_threshold if "presence_threshold" in group else group.threshold
                value=presence_summary(group,group.presence_score,thresholds)
                presence_weekly.append(dict(partition=part,target_week=str(target),**{k:value[k] for k in ("n","positive","prevalence","brier","log_loss","precision","recall","f1","binary_supported_rows")}))
        write(folder/"presence_weekly.private.json",presence_weekly)
        write(folder/"comparison_metrics.private.json",dict(counts=comparisons,presence=presence_metrics,
            presence_fit_metadata=pres.metadata,threshold_learned_in_development=pres.threshold,
            comparison_independent=False,used_for_selection=False,external_validation_pending=True))
        reports[str(h)]=dict(development=result["report"],comparison_previously_observed=comparisons,
            presence_comparison_previously_observed=presence_metrics,
            development_rows=len(development),development_weeks=int(development.target_week.nunique()),
            comparison_rows=len(comparison),comparison_weeks=int(comparison.target_week.nunique()),selection=selections[str(h)])
        territory=frame.loc[frame.partition.eq("test") & frame.predictor_admissible].copy()
        base_fields=["radio_id","origin_week","cutoff_date","target_week","target_end"]
        old_territory=pd.read_parquet(V2/"territorial_predictions.private.parquet")
        observed=old_territory.loc[old_territory.horizon_weeks.eq(h),["radio_id","target_week","observed_snapshot_count","observed_quality_state","recorded_positive_count"]]
        for name,collector in ((selections[str(h)]["selected"],active_rows),(BASELINES[0],reference_rows)):
            output=territory[base_fields].copy()
            output["expected_count"]=fitted["counts"][name].predict_frame(territory)
            output["selected_method"]=name
            output["model_version"],output["horizon_weeks"],output["retrospective"]=VERSION,h,True
            output["fit_cutoff"]=fitted["counts"][name].fit_cutoff
            output["available_features"]=territory[list(FEATURES)].notna().sum(axis=1)
            output["missing_features"]=territory[list(FEATURES)].apply(lambda row:[key for key,value in row.items() if pd.isna(value)],axis=1)
            partial=(territory.cases_lag_1.isna() if name==BASELINES[0] else territory.count_origin.isna())
            output["predictor_status"]=np.where(partial,"partial_missing_recent_radio_counts","recent_radio_counts_available")
            output["estimate_status"]=np.where(partial,"available_with_historical_mean_fallback" if name in BASELINES else "available_with_partial_predictors","available")
            output["quality_warning"]="experimental_snapshot_unknown_masks_retrospective_availability_approximate_geography_not_epidemiological_incidence"
            output=output.merge(observed,on=["radio_id","target_week"],how="left",validate="one_to_one")
            collector.append(output)
        selected_output=active_rows[-1]
        for target,group in selected_output.groupby("target_week"):
            known=group.observed_snapshot_count.notna()
            weekly_all.append(dict(horizon=h,target_week=str(target),selected_method=selections[str(h)]["selected"],
                predicted_256_total=float(group.expected_count.sum()),observed_256_total=float(group.observed_snapshot_count.sum()) if known.all() else None,
                eligible_labels=int(known.sum()),observed_known_subset_total=float(group.loc[known,"observed_snapshot_count"].sum()),
                predicted_known_subset_total=float(group.loc[known,"expected_count"].sum())))
        print(json.dumps(dict(horizon=h,comparison_is_independent=False,selected=selections[str(h)]["selected"],
            reference=comparisons[BASELINES[0]]["mae"],selected_mae=comparisons[selections[str(h)]["selected"]]["mae"],
            presence_brier=presence_metrics["presence_score"]["brier"],presence_recall=presence_metrics["presence_score"]["recall"])),flush=True)

    pd.concat(active_rows,ignore_index=True).to_parquet(OUT/"territorial_predictions.private.parquet",index=False)
    pd.concat(reference_rows,ignore_index=True).to_parquet(OUT/"persistence_predictions.private.parquet",index=False)
    pd.DataFrame(weekly_all).to_parquet(OUT/"territorial_weekly_totals.private.parquet",index=False)
    pd.DataFrame(pr_rows).to_parquet(OUT/"precision_recall_curves.private.parquet",index=False)
    write(OUT/"metrics.private.json",reports)
    write(OUT/"features.private.json",dict(ordered_features=list(FEATURES),historical_availability_accredited=False,
        new_origin_information_compared_to_V2=True,strong_latest_persistence_included=True,labels_unchanged=True))
    write(OUT/"quality_status.private.json",dict(territorial_selected={h:value["selected"] for h,value in selections.items()},
        method_labels=METHOD_LABELS,promotion_approved={h:value["promotion_approved"] for h,value in selections.items()},
        explicit_version_selection_required=True,artifact_version=VERSION,
        presence_quality="experimental_presence_development_thresholds_no_calibrated_epidemiological_probability",
        probability_available=False,alerts_enabled=False,external_validation_pending=True))
    write(OUT/"provenance.private.json",dict(input_sha256=inputs_sha,protected_V1_V2_sha256=protected,
        source_dataset_version=bundle["dataset_version"],source_input_evidence=inputs.input_evidence,
        base_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        original_SISA_opened=False,AB_artifacts_opened=False,prior_scientific_audits_repeated=False,
        unknown_labels_zero_filled=False,**source_summary,
        unit="snapshot_record_count",historical_availability_accredited=False))
    shutil.copyfile(__file__,OUT/"execute_private.py")
    implementation=OUT/"implementation"
    implementation.mkdir()
    for path in (ROOT/"ml/src/sigard_ml/forecasting").glob("*.py"):shutil.copyfile(path,implementation/path.name)
    for path,sha in {**protected,**inputs_sha}.items():assert dig(ROOT/path)==sha,"Entrada protegida modificada"
    write(OUT/"manifest.private.json",dict(artifact_version=VERSION,private_local_only=True,
        outputs_sha256={p.relative_to(OUT).as_posix():dig(p) for p in OUT.rglob("*") if p.is_file()}))
    print(json.dumps(dict(completed=True,selected={h:s["selected"] for h,s in selections.items()},
        promoted_horizons=[h for h,s in selections.items() if s["promotion_approved"]],protected_files_unchanged=len(protected))),flush=True)


if __name__ == "__main__":
    main()
