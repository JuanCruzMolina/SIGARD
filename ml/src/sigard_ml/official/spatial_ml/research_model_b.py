"""Fase 5F: B retrospectivo autorizado; A y baseline se leen congelados."""

import argparse
import importlib.metadata
from pathlib import Path
import platform
import shutil
import subprocess

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier

from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS, installed_capabilities
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.research_training import (
    ACKNOWLEDGED_LIMITS, PLAN, PERIODS, validate_design, assert_parquet_equivalent,
)
from sigard_ml.official.spatial_ml.research_diagnostics import (
    numeric_metrics, audit_sklearn, assert_close, reliability, check_prediction_grid,
    workspace_snapshot, git_state, records,
)
from sigard_ml.official.spatial_ml.temporal_feasibility import (
    SCENARIO, MODEL_A, OUTPUT as HISTORY, bounded_frame, read_json,
    verify_manifest, verify_hashes, checked_output, protected_snapshot,
)
from sigard_ml.official.spatial_ml.temporal_history import lookup

VERSION = "official-spatial-rf-B-research-0.5f.0"
OUTPUT = "data/processed/official/spatial_rf_B_05f_v1"
LAGS = [f"local_presencia_exp_rezago_{lag}" for lag in range(1, 5)]
MISSING = [name + "_missing" for name in LAGS]
FEATURES = BASE + LAGS + MISSING
MODELS = ("random_forest_A", "random_forest_B", "training_prevalence")


def validate_authorization(config, hashes):
    """El permiso de A/5E no habilita B; éste exige su propio permiso vinculado."""
    if (set(config) != {"version", "output_dir", "training_authorized", "research_authorization"}
            or config["version"] != VERSION or config["training_authorized"] is not False):
        raise ValueError("Contrato oficial debe permanecer bloqueado")
    entry = config["research_authorization"]
    expected = {"version": VERSION, "model": "B_presence_experimental",
        "research_training_authorized": True, "training_authorized": False,
        "scope": "isolated_retrospective_research_on_frozen_derivatives",
        "target_start": "2024-01-07", "target_end": "2024-06-08", "plan": PLAN,
        "negative_kind": "cero_asumido_experimental", "acknowledged_limits": ACKNOWLEDGED_LIMITS,
        "source_manifest_sha256": hashes, "features": FEATURES, "parameters": RF_PARAMETERS,
        "threshold": 0.5, "test_comparison": "exploratory_previously_examined"}
    if not isinstance(entry, dict) or set(entry) != set(expected) | {"decision_ref", "responsible_ref"}:
        raise ValueError("Falta autorización explícita diferenciada para B")
    if (any(entry[key] != value for key, value in expected.items())
            or entry["research_training_authorized"] is not True or entry["training_authorized"] is not False
            or any(not isinstance(entry[key], str) or not entry[key].strip()
                   for key in ("decision_ref", "responsible_ref"))):
        raise ValueError("Autorización B fuera del alcance retrospectivo aprobado")


def validate_candidate(candidate, reference, source, a_features, catalog):
    """Reconcilia cada celda con t-k exacto, incluidos huecos y procedencia."""
    if (list(candidate.columns) != KEYS + FEATURES or candidate.duplicated(KEYS).any()
            or source.duplicated(KEYS).any() or reference.duplicated(KEYS).any()
            or candidate[KEYS].isna().any().any() or source[KEYS].isna().any().any()):
        raise ValueError("Identidad/esquema de matriz B inválido")
    pd.testing.assert_frame_equal(candidate[KEYS].reset_index(drop=True), reference[KEYS].reset_index(drop=True))
    expected_a = reference[KEYS].merge(a_features, on=KEYS, how="left", validate="one_to_one")
    pd.testing.assert_frame_equal(candidate[KEYS + BASE].reset_index(drop=True), expected_a.reset_index(drop=True))
    if reference.apto_entrenamiento.ne(False).any():
        raise ValueError("Se modificó el bloqueo oficial en las etiquetas")
    y = source.presencia_exp
    negative = y.eq(0).fillna(False)
    positive = y.eq(1).fillna(False)
    unknown = y.isna()
    if (not y.dropna().isin([0, 1]).all()
            or not negative.eq(source.fuente_cero_asumido).all()
            or not unknown.eq(source.fuente_desconocida).all()
            or not source.loc[negative, "tipo_etiqueta"].eq("cero_asumido_experimental").all()
            or not source.loc[positive, "tipo_etiqueta"].eq("positivo_provisional").all()
            or source.loc[negative | unknown, "casos_observados"].notna().any()
            or source.cobertura_comprobada.eq(True).any()
            or source.disponibilidad_en_origen_acreditada.eq(True).any()):
        raise ValueError("Procedencia/ausencias o disponibilidad histórica alteradas")
    source_values = pd.Series(y.array, index=pd.MultiIndex.from_frame(source[KEYS]))
    for lag, name in enumerate(LAGS, 1):
        policy = next((item for item in catalog if item["feature"] == name), None)
        if (policy is None or policy["source_week_offsets"] != [-lag]
                or policy["maximum_source_week_offset"] != -lag
                or policy["uses_target_or_future_week"] is not False):
            raise ValueError("Rezago no estrictamente anterior al origen")
        actual, expected = candidate[name], lookup(source_values, candidate[KEYS], lag)
        pd.testing.assert_series_equal(actual, expected, check_names=False)
        if (not actual.dropna().isin([0, 1]).all() or candidate[name + "_missing"].isna().any()
                or not candidate[name + "_missing"].eq(actual.isna()).all()):
            raise ValueError("Faltantes convertidos o indicador inconsistente")
    return {"rows": len(candidate), "lag_cells_checked": len(candidate) * 4,
        "missing_cells_retained": int(candidate[LAGS].isna().sum().sum()),
        "source_week_offsets": [-1, -2, -3, -4], "target_week_offset": 1,
        "presence_is_binary_not_patient_count": True, "operational_availability_verified": False}


def inference_matrix(frame):
    """Sólo cambia representación numérica: pandas NA -> IEEE NaN, sin imputar."""
    matrix = frame[FEATURES].astype("float64")
    if (np.isinf(matrix.to_numpy()).any() or matrix[BASE + MISSING].isna().any().any()
            or not np.array_equal(matrix[LAGS].isna(), frame[LAGS].isna())):
        raise ValueError("Matriz numérica inválida o faltantes alterados")
    return matrix


def fit_model_b(frame):
    capabilities = installed_capabilities()
    if not capabilities["native_nan_supported"] or capabilities["estimator_fitted"]:
        raise ValueError("Entorno incompatible con NaN nativo; no modificar dependencias")
    train = frame[frame.partition.eq("train") & frame.objetivo_semana_siguiente.notna()]
    if set(train.objetivo_semana_siguiente.unique()) != {0, 1}:
        raise ValueError("Entrenamiento sin ambas clases")
    matrix = inference_matrix(train)
    if matrix[LAGS].notna().sum().eq(0).any():
        raise ValueError("Rezago sin soporte en entrenamiento")
    estimator = RandomForestClassifier(**RF_PARAMETERS)
    estimator.fit(matrix, train.objetivo_semana_siguiente.to_numpy(int))
    return estimator, train, capabilities


def evaluate(frame, stored_metrics):
    summary, weekly, calibration, audit = [], [], [], []
    for model in MODELS:
        for part in PERIODS:
            grid = frame[frame.partition.eq(part)]
            known = grid[grid.objetivo_semana_siguiente.notna()]
            y, p = known.objetivo_semana_siguiente.to_numpy(int), known[model + "_probability"].to_numpy(float)
            result = numeric_metrics(y, p)
            audit_sklearn(y, p, result, audit, model + ":" + part)
            if model in stored_metrics:
                for key, value in stored_metrics[model][part].items():
                    if key in result:
                        assert_close(key, result[key], value, audit, model + ":" + part + ":frozen_A")
            summary.append({"model": model, "partition": part, **result,
                "grid_rows": len(grid), "unknown_excluded": len(grid) - len(known),
                "mean_probability_all_radios": float(grid[model + "_probability"].mean())})
            calibration.extend({"model": model, "partition": part, **row} for row in reliability(y, p))
            for week, group in grid.groupby("fecha_inicio_semana_objetivo", sort=True):
                known_week = group[group.objetivo_semana_siguiente.notna()]
                y, p = known_week.objetivo_semana_siguiente.to_numpy(int), known_week[model + "_probability"].to_numpy(float)
                result = numeric_metrics(y, p)
                audit_sklearn(y, p, result, audit, model + ":" + part + ":" + str(week))
                weekly.append({"model": model, "partition": part, "target_week": str(week), **result,
                    "grid_rows": len(group), "unknown_excluded": len(group) - len(known_week),
                    "mean_probability_all_radios": float(group[model + "_probability"].mean())})
    return summary, weekly, calibration, audit


def missingness_groups(frame):
    rows = []
    work = frame[frame.objetivo_semana_siguiente.notna()].copy()
    work["known_lags"] = work[LAGS].notna().sum(axis=1)
    work["missing_pattern"] = work[MISSING].astype(int).astype(str).agg("".join, axis=1)
    for kind in ("known_lags", "missing_pattern"):
        for (part, group_value), group in work.groupby(["partition", kind], sort=True):
            for model in MODELS:
                rows.append({"partition": part, "group_kind": kind, "group_value": str(group_value),
                    "model": model, "distinct_target_weeks": group.fecha_inicio_semana_objetivo.nunique(),
                    **numeric_metrics(group.objetivo_semana_siguiente.to_numpy(int), group[model + "_probability"].to_numpy(float))})
    return rows


def permute_observed_history(matrix, weeks, seed):
    """Permutación conjunta dentro de semana y patrón NA: no rompe indicadores."""
    shuffled = matrix.copy(deep=True)
    groups = matrix[MISSING].astype(int).astype(str).agg("".join, axis=1)
    grouping = pd.DataFrame({"week": np.asarray(weeks), "pattern": groups.to_numpy()}, index=matrix.index)
    rng, eligible = np.random.default_rng(seed), 0
    for indices in grouping.groupby(["week", "pattern"]).groups.values():
        if len(indices) < 2 or not matrix.loc[indices, LAGS].nunique().gt(1).any():
            continue
        eligible += len(indices)
        shuffled.loc[indices, LAGS] = matrix.loc[rng.permutation(indices), LAGS].to_numpy()
    if (not np.array_equal(shuffled[LAGS].isna(), matrix[LAGS].isna())
            or not shuffled[BASE + MISSING].equals(matrix[BASE + MISSING])):
        raise ValueError("La permutación alteró disponibilidad o contexto")
    changed = ((shuffled[LAGS].ne(matrix[LAGS])) & ~(shuffled[LAGS].isna() & matrix[LAGS].isna())).any(axis=1)
    return shuffled, eligible, int(changed.sum())


def history_value_sensitivity(frame, estimator):
    """Diagnóstico descriptivo con B fijo, sin estimar otro modelo ni seleccionar."""
    rows = []
    for part in ("validation", "test"):
        group = frame[frame.partition.eq(part) & frame.objetivo_semana_siguiente.notna()]
        matrix, y = inference_matrix(group), group.objetivo_semana_siguiente.to_numpy(int)
        original = numeric_metrics(y, group.random_forest_B_probability.to_numpy(float))
        for repeat in range(5):
            shuffled, eligible, changed = permute_observed_history(matrix, group.fecha_inicio_semana_objetivo,
                                                                 RF_PARAMETERS["random_state"] + repeat)
            p = estimator.predict_proba(shuffled)[:, 1]
            result = numeric_metrics(y, p)
            rows.append({"partition": part, "repeat": repeat, "seed": RF_PARAMETERS["random_state"] + repeat,
                "n": len(group), "eligible_rows": eligible, "changed_history_rows": changed,
                "mean_absolute_probability_change": float(np.mean(np.abs(p - group.random_forest_B_probability))),
                "brier_increase": result["brier"] - original["brier"],
                "ap_drop": original["average_precision_pr_auc"] - result["average_precision_pr_auc"],
                "roc_auc_drop": original["roc_auc"] - result["roc_auc"],
                "f1_drop": original["f1"] - result["f1"]})
    return rows


def run(root, config_path):
    root = root.resolve()
    require_branch(root)
    config_path = config_path.resolve()
    if (not config_path.is_relative_to(root / "data/interim/official") or config_path.is_symlink()
            or subprocess.run(["git", "check-ignore", "--quiet", "--", str(config_path.relative_to(root))],
                              cwd=root, capture_output=True).returncode != 0):
        raise ValueError("Configuración debe ser privada y local")
    config = read_json(config_path)
    hashes = {name: digest_path(root / path / "integrity_manifest.private.json")
              for name, path in (("scenario", SCENARIO), ("model_A", MODEL_A), ("history_5E", HISTORY))}
    validate_authorization(config, hashes)
    output = checked_output(root, config["output_dir"])
    before_workspace, initial_git = workspace_snapshot(root), git_state(root)
    manifests = [verify_manifest(root / path) for path in (SCENARIO, MODEL_A, HISTORY)]
    inherited = {}
    for entry in manifests:
        inherited.update(entry["protected_files_sha256"])
    verify_hashes(inherited)
    protected = protected_snapshot(root, inherited)
    read = lambda folder, name, **kwargs: bounded_frame(root / folder / name, root, **kwargs)
    labels = read(SCENARIO, "labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
    a_features = read(SCENARIO, "predictors_A.private.parquet").sort_values(KEYS).reset_index(drop=True)
    splits = read(SCENARIO, "splits.private.parquet", filters=[("plan", "=", PLAN)])
    old_config = read_json(root / MODEL_A / "configuration.private.json")
    policy_path = (root / old_config["phase5b_dir"] / "expanded/exploratory/column_policies.private.json").resolve()
    if not policy_path.is_relative_to(root / "data/interim/official"):
        raise ValueError("Política fuera del almacenamiento privado")
    _, partitions = validate_design(labels, a_features, splits, read_json(policy_path))
    for folder in (SCENARIO, MODEL_A):
        review = read_json(root / folder / "review.private.json")
        if review["training_authorized"] is not False or review["coverage_verified"] is not False:
            raise ValueError("Se alteraron controles oficiales/cobertura")
    candidate = read(HISTORY, "predictors_B_presence_candidate.private.parquet")
    reference = read(HISTORY, "labels_and_splits_unchanged_reference.private.parquet")
    expected_ref = labels[labels.en_intervalo_autorizado.eq(True)].merge(
        splits[KEYS + ["plan", "partition", "label_known", "eligible_for_future_supervised_use"]], on=KEYS, validate="one_to_one")
    assert_parquet_equivalent(reference.sort_values(KEYS).reset_index(drop=True),
                              expected_ref.sort_values(KEYS).reset_index(drop=True))
    source = read(HISTORY, "weekly_history_sources.private.parquet")
    integrity = validate_candidate(candidate, reference, source, a_features,
                                   read_json(root / HISTORY / "feature_catalog.private.json")["features"])
    predictions = read(MODEL_A, "predictions_radio_week.private.parquet")
    frame = check_prediction_grid(predictions, labels, a_features, splits).merge(
        candidate[KEYS + LAGS + MISSING], on=KEYS, how="left", validate="one_to_one")
    matrix = inference_matrix(frame)
    verify_hashes(protected)
    estimator, train, capabilities = fit_model_b(frame)
    probability = estimator.predict_proba(matrix)[:, 1]
    replica = clone(estimator).fit(inference_matrix(train), train.objetivo_semana_siguiente.to_numpy(int))
    reproduced = replica.predict_proba(matrix)[:, 1]
    if not np.array_equal(probability, reproduced):
        raise ValueError("Predicciones B no reproducibles con la misma semilla")
    if len(train) != partitions["train"]["used"]:
        raise ValueError("Se descartaron filas por historia faltante")
    frame["random_forest_B_probability"] = probability
    frame["random_forest_B_predicted"] = (probability >= .5).astype(int)
    stored_metrics = read_json(root / MODEL_A / "metrics.private.json")
    summary, weekly, calibration, audit = evaluate(frame, stored_metrics)
    sensitivity = history_value_sensitivity(frame, estimator)
    importance = [{"feature": name, "importance_mdi": float(value),
        "group": "lag_presence" if name in LAGS else "explicit_missingness" if name in MISSING else "base_A"}
        for name, value in zip(FEATURES, estimator.feature_importances_)]
    verify_hashes(protected)
    verify_hashes(before_workspace)
    output.mkdir()
    model_path = output / "random_forest_B.research.private.joblib"
    joblib.dump(estimator, model_path)
    reloaded = joblib.load(model_path)  # Only the B file just created locally, never a supplied pickle.
    if not np.array_equal(probability, reloaded.predict_proba(matrix)[:, 1]):
        raise ValueError("Serialización B no reproduce las predicciones")
    review = {"version": VERSION, "training_performed": True, "research_training_authorized": True,
        "training_authorized": False, "production_training_enabled": False,
        "operational_model_enabled": False, "model_A_retrained_or_modified": False,
        "baseline_refitted": False, "parameters": RF_PARAMETERS, "features": FEATURES,
        "threshold": .5, "threshold_selected_on_validation_or_test": False, "calibrator_fitted": False,
        "hyperparameter_search_performed": False, "test_previously_examined": True,
        "comparison_is_exploratory": True, "prediction_is_case_count": False,
        "sample_unit": "radio censal - origin week; target binary experimental presence t+1",
        "forecast_protocol": "rolling origin retrospective, not fixed-origin multiweek operational forecast",
        "partitions": partitions, "purged_target_weeks": ["2024-03-03", "2024-05-05"],
        "purged_weeks_may_supply_strictly_past_features": True,
        "native_nan_capability": capabilities, "integrity": integrity,
        "reproducibility": {"independent_B_fits": 2, "same_seed_predictions_bitwise_equal": True,
            "all_grid_predictions_compared": len(frame), "joblib_roundtrip_equal": True},
        "acknowledged_limits": ACKNOWLEDGED_LIMITS,
        "protected_files_preserved": len(protected), "preexisting_workspace_files_preserved": len(before_workspace),
        "human_scientific_review": "pending", "in_review_files_incorporated": False,
        "missingness_sensitivity": "joint lag-value permutation within week and identical NA pattern; fixed B, five repeats; no feature selection or causal attribution"}
    tables = {"metrics": summary, "weekly_metrics": weekly, "calibration": calibration,
        "feature_importance": importance, "metric_consistency_checks": audit,
        "missingness_groups": missingness_groups(frame), "history_value_sensitivity": sensitivity}
    for name, rows in tables.items():
        pd.DataFrame(rows).to_parquet(output / (name + ".private.parquet"), index=False)
        pd.DataFrame(rows).to_csv(output / (name + ".private.csv"), index=False)
    predictions = frame[list(predictions.columns) + ["random_forest_B_probability", "random_forest_B_predicted"]]
    predictions.to_parquet(output / "predictions_radio_week.private.parquet", index=False)
    matrix.insert(0, KEYS[1], frame[KEYS[1]])
    matrix.insert(0, KEYS[0], frame[KEYS[0]])
    matrix.to_parquet(output / "inference_matrix.private.parquet", index=False)
    train[KEYS + ["partition", "objetivo_semana_siguiente", "tipo_etiqueta"]].to_parquet(
        output / "training_rows.private.parquet", index=False)
    write_report(config, output / "configuration.private.json")
    write_report(config["research_authorization"], output / "research_authorization.private.json")
    write_report(review, output / "review.private.json")
    write_report({"python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ("scikit-learn", "numpy", "scipy", "pandas", "pyarrow", "joblib")},
        "source_manifest_sha256": hashes, "code_sha256": {str(Path(__file__).relative_to(root)): digest_path(Path(__file__))}},
        output / "metadata.private.json")
    from sigard_ml.official.spatial_ml.research_model_b_report import write_reports
    write_reports(output, review, tables)
    for module in ("research_model_b.py", "research_model_b_report.py"):
        shutil.copyfile(Path(__file__).with_name(module), output / module)
    write_report({"before": initial_git, "after": git_state(root)}, output / "git_state.private.json")
    verify_hashes(protected)
    verify_hashes(before_workspace)
    write_report({"version": VERSION, "protected_files_sha256": protected,
        "preexisting_workspace_sha256": before_workspace,
        "outputs_sha256": {str(path.relative_to(output)): digest_path(path) for path in output.iterdir() if path.is_file()}},
        output / "integrity_manifest.private.json")
    return {"output_dir": str(output.relative_to(root)), "partitions": partitions,
        "metrics": summary, "reproducibility": review["reproducibility"], "integrity": integrity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.config)
    print(result["output_dir"])


if __name__ == "__main__":
    main()
