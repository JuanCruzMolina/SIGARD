"""Fase 5E: viabilidad temporal y auditoría de A, sin entrenamiento."""

import argparse
from contextlib import ExitStack
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, require_preserved
from sigard_ml.official.spatial_ml.experiment_selection import BASE, SUPPORT_RULE
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.research_diagnostics import workspace_snapshot, git_state
from sigard_ml.official.spatial_ml.temporal_history import (
    PARTS, TRACKS, LAGS, WINDOWS, source_history, history_matrix, availability_report, pending_report,
)

VERSION = "official-spatial-temporal-feasibility-0.5e.0"
SCENARIO = "data/processed/official/spatial_assumed_2024_v1"
MODEL_A = "data/processed/official/spatial_rf_05c_v1"
OUTPUT = "data/processed/official/spatial_temporal_feasibility_05e_v1"
NO_FIT = ("sklearn.ensemble.RandomForestClassifier.fit", "sklearn.ensemble.RandomForestRegressor.fit",
    "sklearn.dummy.DummyClassifier.fit", "sklearn.calibration.CalibratedClassifierCV.fit",
    "sklearn.linear_model.LogisticRegression.fit", "sklearn.pipeline.Pipeline.fit")


def read_json(path):
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("JSON fuera del límite local")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Clave JSON duplicada")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("JSON con constante no finita")
    def finite_float(value):
        number = float(value)
        if not np.isfinite(number):
            raise ValueError("Número JSON fuera del rango finito")
        return number
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite_float)


def bounded_frame(path, root, columns=None, filters=None):
    path, root = Path(path), root.resolve()
    if (path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file()
            or path.suffix != ".parquet" or path.stat().st_size > 64 * 1024 * 1024):
        raise ValueError("Parquet fuera del límite de datos autorizado")
    metadata = pq.ParquetFile(path)
    planned_split_filter = filters == [("plan", "=", "authorized_2024_only")]
    row_bound = 250_000 if planned_split_filter else 100_000
    if metadata.metadata.num_rows > row_bound or len(metadata.schema.names) > 180:
        raise ValueError("Esquema o filas exceden la revisión acotada")
    frame = pd.read_parquet(path, columns=columns, filters=filters)
    if len(frame) > 100_000:
        raise ValueError("La selección autorizada excede el límite de revisión")
    return frame


def verify_hashes(mapping):
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_file() or digest_path(path) != expected:
            raise ValueError("Se alteró una fuente o artefacto protegido")


def verify_manifest(path):
    entry = read_json(path / "integrity_manifest.private.json")
    for name, expected in entry["outputs_sha256"].items():
        file = (path / name).resolve()
        if not file.is_relative_to(path.resolve()) or digest_path(file) != expected:
            raise ValueError("Entrada distinta de su manifiesto congelado")
    return entry


def checked_output(root, output_name):
    root = root.resolve()
    output = (root / output_name).resolve()
    private = (root / "data/processed/official").resolve()
    if (not private.is_relative_to(root) or output.parent != private or output.exists()
            or output == (root / SCENARIO).resolve() or output == (root / MODEL_A).resolve()):
        raise ValueError("Se exige un destino privado nuevo independiente")
    if subprocess.run(["git", "check-ignore", "--quiet", "--", str(output.relative_to(root))],
                      cwd=root, capture_output=True).returncode != 0:
        raise ValueError("Destino no excluido de Git")
    return output


def protected_snapshot(root, inherited):
    result = dict(inherited)
    for name in ("data/processed/official", "data/interim/official", "ml/artifacts", "ml/models"):
        folder = root / name
        if folder.exists():
            result.update({str(path.resolve()): digest_path(path) for path in folder.rglob("*") if path.is_file()})
    return result


def training_support(availability):
    rows = []
    for row in availability[availability.partition.eq("train")].to_dict("records"):
        fraction = row["rows_feature_and_target_known"] / row["known_targets"] if row["known_targets"] else 0
        supported = (min(row["target_positive_when_feature_known"], row["target_negative_when_feature_known"])
            >= SUPPORT_RULE["minimum_known_training_values_per_class"]
            and fraction >= SUPPORT_RULE["minimum_known_training_fraction"])
        rows.append({"feature_or_set": row["feature_or_set"], "scope": row["scope"], "track": row["track"],
            "known_training_values": row["rows_feature_and_target_known"], "known_training_fraction": fraction,
            "positive_training_targets": row["target_positive_when_feature_known"],
            "negative_training_targets": row["target_negative_when_feature_known"],
            "distinct_training_weeks": row["distinct_target_weeks_feature_known"],
            "legacy_technical_support_rule_met": bool(supported),
            "sample_size_scientifically_validated": False, "selection_by_validation_or_test": False})
    return pd.DataFrame(rows)


def write_outputs(root, output, source, labels, splits, a_features, history, operational, catalog,
                  availability, by_week, pending, states, support, model_report, model_tables,
                  protected, before_workspace, initial_git, extra):
    output.mkdir(parents=True, exist_ok=False)
    key_scope = labels[labels.en_intervalo_autorizado.eq(True)][KEYS]
    a_scope = key_scope.merge(a_features, on=KEYS, validate="one_to_one")
    full = a_scope.merge(history, on=KEYS, validate="one_to_one")
    op_a = a_scope.copy()
    for name in BASE[:4]:
        op_a[name] = np.nan
    op = op_a.merge(operational, on=KEYS, validate="one_to_one")
    phase_labels = labels[labels.en_intervalo_autorizado.eq(True)].merge(
        splits[splits.plan.eq("authorized_2024_only")], on=KEYS, validate="one_to_one")
    b_names = [f"local_presencia_exp_rezago_{lag}" for lag in LAGS]
    b = full[KEYS + BASE + b_names].copy()
    for name in b_names:
        b[name + "_missing"] = b[name].isna()
    frames = {"weekly_history_sources": source, "history_retrospective": history,
        "predictors_retrospective_all_candidates": full, "predictors_operational_fail_closed": op,
        "predictors_B_presence_candidate": b, "labels_and_splits_unchanged_reference": phase_labels,
        "availability": availability, "availability_by_target_week": by_week, "pending_impact": pending,
        "weekly_label_states": states, "training_support": support}
    frames.update({name: pd.DataFrame(data) for name, data in model_tables.items()})
    for name, frame in frames.items():
        frame.to_parquet(output / f"{name}.private.parquet", index=False)
        if name not in {"weekly_history_sources", "history_retrospective", "predictors_retrospective_all_candidates",
                         "predictors_operational_fail_closed", "predictors_B_presence_candidate", "labels_and_splits_unchanged_reference"}:
            frame.to_csv(output / f"{name}.private.csv", index=False)
    write_report({"version": VERSION, "features": catalog, "lag_reference": "origin week t; target t+1",
        "windows": "[t-W,t-1]; source week start is label target date, not label origin",
        "source_interval": "2024-01-07/2024-06-08 only; no pre-2024 history padding",
        "indicators": "value presence and source flags describe past weeks only; operational availability unverified",
        "original_counts_modified": False, "null_counts_replaced_with_zero": False}, output / "feature_catalog.private.json")
    model_b = {"version": VERSION, "name": "B_presence_experimental_candidate_distinct_from_5B_record_count_B",
        "task": "next_week_provisional_presence_under_assumed_coverage", "training_authorized": False,
        "training_enabled": False, "model_fitted": False, "official_training_authorized": False,
        "base_retrospective_context": BASE, "optional_candidates_not_auto_selected": b_names,
        "missingness_indicators": [name + "_missing" for name in b_names],
        "unknown_feature_policy": "retain NaN and rows; no implicit imputation or complete-case-only training",
        "unknown_target_policy": "exclude from any future supervised fit; keep grid for coverage",
        "native_nan_supported_by_existing_RF_environment": model_report["native_nan_supported"],
        "accumulated_4": "diagnostic candidate; redundant with four complete binary lags; not auto added",
        "accumulated_8": "no complete training history within authorized interval; not initial model B candidate",
        "original_prepared_model_B_count_features_changed": False,
        "technical_training_support_rule": SUPPORT_RULE, "support_is_scientific_validation": False,
        "model_A_modified": False, "future_hyperparameters_or_calibration_selected": False,
        "future_evaluation": "rolling-origin retrospective only until availability verified; new independent unseen season/block required"}
    write_report(model_b, output / "model_B_preparation.private.json")
    write_report(model_report, output / "model_A_audit.private.json")
    write_report(extra, output / "source_and_integrity_review.private.json")
    from sigard_ml.official.spatial_ml.temporal_feasibility_report import write_report_files
    final_git = git_state(root)
    write_report_files(output, availability, support, pending, states, model_report, model_tables, extra, final_git)
    files = [Path(__file__), Path(__file__).with_name("temporal_history.py"),
             Path(__file__).with_name("temporal_model_a_audit.py"), Path(__file__).with_name("temporal_feasibility_report.py")]
    for path in files:
        (output / path.name).write_bytes(path.read_bytes())
    write_report({"version": VERSION, "unit": "radio_censal_origin_week_target_t_plus_1",
        "data_kind": "provisional_record_counts_and_separate_assumed_experimental_presence",
        "training_performed": False, "training_authorized": False, "operational_validation": False,
        "randomness": "none; inference and deterministic feature derivation only",
        "runtime": {"python": platform.python_version(), **{package: importlib.metadata.version(package)
            for package in ("pandas", "numpy", "pyarrow", "scikit-learn", "scipy", "joblib")}},
        "implementation_sha256": {str(path.relative_to(root)): digest_path(path) for path in files},
        "sources": {"scenario_manifest_sha256": digest_path(root / SCENARIO / "integrity_manifest.private.json"),
            "model_A_manifest_sha256": digest_path(root / MODEL_A / "integrity_manifest.private.json")},
        "model_loading_boundary": "only separate scikit-learn audit of the local hash-verified model created in phase5c; not generic EDA deserialization",
        "dataset_scan": {"complete_2024_scope": True, "truncated": False, "max_input_rows": 100000,
            "max_parquet_input_bytes": 64 * 1024 * 1024,
            "full_named_scenario_artifacts_except_explicit_split_plan_selection": True,
            "split_plan_filter": "authorized_2024_only; full selected plan, not a row prefix",
            "split_file_max_rows_before_plan_filter": 250000,
            "context_and_graph_use_selected_columns_only": True},
        "human_scientific_review": "pending_user_review", "submission_ready": False}, output / "metadata.private.json")
    write_report({"before": initial_git, "after": final_git}, output / "git_state.private.json")
    verify_hashes(protected)
    require_preserved(before_workspace, workspace_snapshot(root))
    write_report({"version": VERSION, "previous_artifacts_preserved": True,
        "protected_files_sha256": protected, "preexisting_workspace_sha256": before_workspace,
        "outputs_sha256": {path.relative_to(output).as_posix(): digest_path(path) for path in sorted(output.rglob("*")) if path.is_file()}},
        output / "integrity_manifest.private.json")


def run_feasibility(root, output_name=OUTPUT):
    root = root.resolve()
    require_branch(root)
    output = checked_output(root, output_name)
    before_workspace = workspace_snapshot(root)
    initial_git = git_state(root)
    scenario, phase5c = root / SCENARIO, root / MODEL_A
    manifest = verify_manifest(scenario)
    model_manifest = verify_manifest(phase5c)
    verify_hashes(manifest["protected_files_sha256"])
    verify_hashes(model_manifest["protected_files_sha256"])
    config = read_json(phase5c / "configuration.private.json")
    phase5a = (root / config["phase5a_dir"]).resolve()
    if not phase5a.is_relative_to((root / "data/processed/official").resolve()):
        raise ValueError("Derivado fuera del almacenamiento autorizado")
    a_manifest = verify_manifest(phase5a)
    # Fase 5A usa rutas relativas para el contexto territorial; 5C no lo duplicó.
    a_protected = {}
    for name, expected in a_manifest["protected_files_sha256"].items():
        path = Path(name)
        path = path.resolve() if path.is_absolute() else (root / path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Fuente de Fase 5A fuera del ámbito local autorizado")
        a_protected[str(path)] = expected
    verify_hashes(a_protected)
    protected = protected_snapshot(root, {**model_manifest["protected_files_sha256"], **a_protected})
    review = read_json(phase5c / "review.private.json")
    if review["training_authorized"] is not False or review["coverage_verified"] is not False:
        raise ValueError("Se alteraron los bloqueos del flujo oficial")
    weekly = bounded_frame(scenario / "weekly_authorization.private.parquet", root)
    labels = bounded_frame(scenario / "labels.private.parquet", root)
    a_features = bounded_frame(scenario / "predictors_A.private.parquet", root)
    splits = bounded_frame(scenario / "splits.private.parquet", root,
                           filters=[("plan", "=", "authorized_2024_only")])
    context_columns = KEYS + ["estado_cobertura", "estado_observacion", "cobertura_comprobada",
        "registros_fecha_aproximada", "registros_asignacion_incierta", "version_fecha", "version_transformacion"]
    context = bounded_frame(phase5a / "expanded/exploratory/context.private.parquet", root, context_columns)
    source = source_history(weekly, labels, context)
    if len(source) != 263 * 22 or source.radio_censal.nunique() != 263:
        raise ValueError("Historia autorizada incompleta")
    graph_path = (root / "data/processed/territorial_master.parquet").resolve()
    if str(graph_path) not in protected or digest_path(graph_path) != protected[str(graph_path)]:
        raise ValueError("Grafo distinto del contexto territorial congelado")
    graph = bounded_frame(graph_path, root, ["radio_id", "neighbor_ids"])
    neighbors = {row.radio_id: sorted(list(row.neighbor_ids)) for row in graph.itertuples()}
    degree = a_features.groupby("radio_censal").cantidad_vecinos.first()
    if any(degree[radio] != len(adjacent) for radio, adjacent in neighbors.items()):
        raise ValueError("Grado vecinal distinto del Modelo A")
    prediction_labels = labels[labels.en_intervalo_autorizado.eq(True)].merge(
        splits[splits.plan.eq("authorized_2024_only")][KEYS + ["partition"]], on=KEYS, validate="one_to_one")
    history, operational, catalog = history_matrix(source, prediction_labels[KEYS], neighbors)
    if (len(history) != len(prediction_labels) or any(row["maximum_source_week_offset"] >= 0 for row in catalog)
            or any(row["uses_target_or_future_week"] for row in catalog)):
        raise ValueError("Pérdida de filas o riesgo de fuga por offsets")
    # Identidad independiente: acumulado 4 exige los mismos cuatro rezagos conocidos.
    for scope in ("local", "vecinos"):
        for track in TRACKS:
            lags = [f"{scope}_{track}_rezago_{lag}" for lag in LAGS]
            expected = history[lags].sum(axis=1, min_count=4).astype("Int64")
            pd.testing.assert_series_equal(history[f"{scope}_{track}_acumulado_4"], expected, check_names=False)
    availability, by_week = availability_report(history, prediction_labels, catalog)
    pending, states = pending_report(source, history, prediction_labels)
    support = training_support(availability)
    if availability.loc[(availability.partition.eq("train")) & availability.feature_or_set.eq("local_presencia_exp_acumulado_8"), "rows_feature_known"].iloc[0] != 0:
        raise ValueError("El borde de ocho semanas no concilia con el intervalo/corte congelados")
    from sigard_ml.official.spatial_ml.temporal_model_a_audit import audit_model_a
    prediction_frame = bounded_frame(phase5c / "predictions_radio_week.private.parquet", root)
    model_name = "random_forest_A.research.private.joblib"
    model_report, model_tables = audit_model_a(phase5c / model_name, model_manifest["outputs_sha256"][model_name],
        read_json(phase5c / "metadata.private.json"), review, a_features, prediction_frame)
    delay_path = root / "data/interim/official/observed/date_recovery_041/comparison.private.json"
    delay = read_json(delay_path)
    extra = {"version": VERSION, "source_cells": len(source), "source_weeks": 22, "radios": 263,
        "source_start": "2024-01-07", "source_end": "2024-06-08", "prediction_grid_rows_retained": len(history),
        "supervised_partition_grid_rows": len(prediction_labels[prediction_labels.partition.isin(PARTS)]),
        "source_recorded_counts_known": int(source.casos_observados.notna().sum()),
        "source_presence_known": int(source.presencia_exp.notna().sum()),
        "source_positive": int(source.presencia_exp.eq(1).sum()), "source_assumed_negative": int(source.presencia_exp.eq(0).sum()),
        "source_unknown": int(source.presencia_exp.isna().sum()),
        "source_positive_with_pending": int((source.presencia_exp.eq(1) & source.fuente_pendientes).sum()),
        "source_unknown_with_pending": int((source.presencia_exp.isna() & source.fuente_pendientes).sum()),
        "verified_coverage_cells": int(source.cobertura_comprobada.eq(True).sum()),
        "positive_cells_with_approximate_date": int((source.presencia_exp.eq(1) & source.fuente_fecha_aproximada).sum()),
        "historical_availability_evidence_present": False, "original_count_nulls_filled": 0,
        "legacy_delay_evidence_scope": delay["analysis_period"], "legacy_delay_evidence": delay["delay_evidence"],
        "history_source_kind_counts": states.to_dict("records"), "protected_files": len(protected),
        "forecast_protocol": "rolling origin with strictly prior weeks; not a single fixed-origin multiweek forecast",
        "purged_target_weeks": review["purged_target_weeks"],
        "purged_weeks_may_supply_later_past_features": True,
        "operational_epidemiological_history_rows_available": 0, "in_review_files_incorporated": False}
    verify_hashes(protected)
    write_outputs(root, output, source, labels, splits, a_features, history, operational, catalog,
        availability, by_week, pending, states, support, model_report, model_tables,
        protected, before_workspace, initial_git, extra)
    return {"version": VERSION, "output_dir": str(output.relative_to(root)), "training_performed": False,
        "source_review": extra, "model_A": model_report,
        "local_binary_summary": availability[availability.scope.eq("local") & availability.track.eq("presencia_exp")].to_dict("records")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=OUTPUT)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        def forbidden(*args, **kwargs):
            raise RuntimeError("Entrenamiento prohibido en Fase 5E")
        with ExitStack() as stack:
            for target in NO_FIT:
                stack.enter_context(patch(target, side_effect=forbidden))
            result = run_feasibility(Path(__file__).resolve().parents[5], args.output_dir)
        print(json.dumps({key: result[key] for key in ("version", "output_dir", "training_performed", "source_review", "model_A")}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "Viabilidad detenida; revisar integridad privada sin modificar los escenarios o modelos anteriores.\n")


if __name__ == "__main__":
    main()
