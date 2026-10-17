"""Fase 5D: diagnóstico de artefactos congelados; sin cargar/ajustar modelos."""

import argparse
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import rankdata, wasserstein_distance
from sklearn import metrics as skm

from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, require_preserved
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.experiment_selection import BASE

VERSION = "official-spatial-rf-diagnostics-0.5d.0"
PARTS = ("train", "validation", "test")
MODELS = ("random_forest_A", "training_prevalence")
THRESHOLD = 0.5
DEFAULT_INPUT = "data/processed/official/spatial_rf_05c_v1"
DEFAULT_OUTPUT = "data/processed/official/spatial_rf_diagnostics_05d_v1"
STATIC = BASE[:4]
NO_FIT_TARGETS = (
    "sklearn.ensemble.RandomForestClassifier.fit", "sklearn.ensemble.RandomForestRegressor.fit",
    "sklearn.dummy.DummyClassifier.fit", "sklearn.calibration.CalibratedClassifierCV.fit",
    "sklearn.linear_model.LogisticRegression.fit", "sklearn.pipeline.Pipeline.fit", "joblib.load",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_hashes(mapping):
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_file() or digest_path(path) != expected:
            raise ValueError("Artefacto protegido modificado; diagnóstico detenido")


def verify_manifest(directory):
    manifest = read_json(directory / "integrity_manifest.private.json")
    for name, expected in manifest["outputs_sha256"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest_path(path) != expected:
            raise ValueError("El artefacto no coincide con su manifiesto")
    return manifest


def checked_paths(root, input_dir, output_dir):
    root = root.resolve()
    private = (root / "data/processed/official").resolve()
    source, destination = (root / input_dir).resolve(), (root / output_dir).resolve()
    if (not private.is_relative_to(root) or source == private or not source.is_relative_to(private)
            or destination.parent != private or destination.exists()
            or source == destination or destination.is_relative_to(source) or source.is_relative_to(destination)):
        raise ValueError("Se exige entrada privada y destino nuevo independiente")
    for path in (source, destination):
        if subprocess.run(["git", "check-ignore", "--quiet", "--", str(path.relative_to(root))],
                          cwd=root, capture_output=True, check=False).returncode != 0:
            raise ValueError("Entrada/salida no excluida de Git")
    return source, destination


def numeric_metrics(y, probability):
    """Fórmulas independientes; AP respeta empates y ROC usa rangos medios."""
    raw_y, p = np.asarray(y), np.asarray(probability, dtype=float)
    if not np.isin(raw_y, [0, 1]).all():
        raise ValueError("Etiquetas no binarias")
    y = raw_y.astype(int)
    if (not len(y) or len(y) != len(p) or not np.isin(y, [0, 1]).all()
            or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any()):
        raise ValueError("Etiquetas/probabilidades inválidas")
    predicted = p >= THRESHOLD
    positive, negative = int(y.sum()), int((y == 0).sum())
    tp = int(((y == 1) & predicted).sum())
    fp = int(((y == 0) & predicted).sum())
    fn, tn = positive - tp, negative - fp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / positive if positive else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    roc = ((rankdata(p)[y == 1].sum() - positive * (positive + 1) / 2) / (positive * negative)
           if positive and negative else None)
    ap = None
    if positive:
        order = np.argsort(-p, kind="stable")
        scores, labels = p[order], y[order]
        ends = np.r_[np.flatnonzero(np.diff(scores) != 0), len(scores) - 1]
        cumulative = np.cumsum(labels)[ends]
        ap = float(np.sum(np.diff(np.r_[0, cumulative]) / positive * cumulative / (ends + 1)))
    eps = np.finfo(float).eps
    clipped = np.clip(p, eps, 1 - eps)
    pr_trap = None
    if positive and negative:
        curve_p, curve_r, _ = skm.precision_recall_curve(y, p)
        pr_trap = float(skm.auc(curve_r, curve_p))
    bins = reliability(y, p)
    return {"n": len(y), "positive": positive, "negative": negative, "prevalence": positive / len(y),
        "threshold": THRESHOLD, "precision": precision, "recall": recall, "f1": f1,
        "average_precision_pr_auc": ap, "pr_auc_trapezoidal": pr_trap,
        "roc_auc": float(roc) if roc is not None else None,
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
        "confusion_matrix_true_rows_predicted_columns_0_1": [[tn, fp], [fn, tp]],
        "tn": tn, "fp": fp, "fn": fn, "tp": tp, "predicted_positive": tp + fp,
        "mean_probability": float(p.mean()),
        "calibration_gap_mean_probability_minus_prevalence": float(p.mean() - y.mean()),
        "ece_10_uniform_bins_descriptive": float(sum(
            r["n"] * abs(r["mean_probability"] - r["fraction_positive"]) for r in bins) / len(y)),
        "brier_negative_contribution": float(np.sum(p[y == 0] ** 2) / len(y)),
        "brier_positive_contribution": float(np.sum((1 - p[y == 1]) ** 2) / len(y)),
        "mean_probability_negatives": float(p[y == 0].mean()) if negative else None,
        "mean_probability_positives": float(p[y == 1].mean()) if positive else None,
        "precision_undefined": precision is None, "recall_undefined": recall is None,
        "f1_undefined": f1 is None, "roc_auc_undefined": roc is None}


def reliability(y, p):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    index = np.minimum((p * 10).astype(int), 9)
    rows = []
    for number in range(10):
        mask = index == number
        if mask.any():
            rows.append({"bin": number, "lower": number / 10, "upper": (number + 1) / 10,
                "n": int(mask.sum()), "positive": int(y[mask].sum()),
                "mean_probability": float(p[mask].mean()), "fraction_positive": float(y[mask].mean())})
    return rows


def assert_close(name, actual, expected, audit, scope):
    if isinstance(expected, (float, np.floating)) and np.isnan(expected):
        expected = None
    # Fase 5C usó precision=0 por convención cuando no había predicciones positivas.
    compatible = 0.0 if actual is None and name == "precision" and expected == 0 else actual
    if compatible is None or expected is None:
        equal, difference = compatible is expected, None
    elif isinstance(compatible, (list, tuple, np.ndarray)):
        def nested(value):
            return [nested(item) for item in value] if isinstance(value, (list, tuple, np.ndarray)) else value
        one, two = np.asarray(nested(compatible)), np.asarray(nested(expected))
        equal = np.array_equal(one, two)
        difference = float(np.max(np.abs(one - two))) if one.shape == two.shape else None
    elif isinstance(compatible, (bool, str)):
        equal, difference = compatible == expected, None
    else:
        difference = abs(float(compatible) - float(expected))
        equal = bool(np.isclose(compatible, expected, rtol=1e-12, atol=1e-12))
    audit.append({"scope": scope, "metric": name, "matches": bool(equal), "absolute_difference": difference})
    if not equal:
        raise ValueError("Métrica o identidad matemática inconsistente")


def audit_sklearn(y, p, result, audit, scope):
    checks = {"brier": skm.brier_score_loss(y, p),
        "confusion_matrix_true_rows_predicted_columns_0_1": skm.confusion_matrix(y, np.asarray(p) >= .5, labels=[0, 1]).tolist(),
        "precision": skm.precision_score(y, np.asarray(p) >= .5, zero_division=0),
        "recall": skm.recall_score(y, np.asarray(p) >= .5, zero_division=0),
        "f1": skm.f1_score(y, np.asarray(p) >= .5, zero_division=0),
        "log_loss": skm.log_loss(y, np.column_stack([1 - np.asarray(p), p]), labels=[0, 1])}
    if len(np.unique(y)) == 2:
        checks.update(average_precision_pr_auc=skm.average_precision_score(y, p), roc_auc=skm.roc_auc_score(y, p))
    for name, expected in checks.items():
        assert_close(name, result[name], expected, audit, scope + ":sklearn")
    assert_close("brier_components", result["brier_negative_contribution"] + result["brier_positive_contribution"],
                 result["brier"], audit, scope + ":identity")


def check_prediction_grid(predictions, labels, features, splits):
    if predictions.empty or predictions.duplicated(KEYS).any() or predictions[KEYS].isna().any().any():
        raise ValueError("Claves de predicciones inválidas")
    if set(predictions.partition.unique()) != set(PARTS):
        raise ValueError("Particiones inesperadas")
    keys = [*KEYS, "fecha_inicio_semana_objetivo", "objetivo_semana_siguiente", "tipo_etiqueta"]
    existing = labels[keys].sort_values(KEYS).reset_index(drop=True)
    merged = predictions.merge(existing, on=KEYS, validate="one_to_one", suffixes=("", "_reference"), indicator=True)
    if not merged._merge.eq("both").all():
        raise ValueError("Predicción sin etiqueta de origen")
    for name in keys[2:]:
        actual, expected = merged[name], merged[name + "_reference"]
        if not (actual.eq(expected).fillna(False) | (actual.isna() & expected.isna())).all():
            raise ValueError("Etiquetas guardadas distintas del escenario")
    assigned = splits[splits.plan.eq("authorized_2024_only")]
    expected = assigned[assigned.partition.isin(PARTS)].sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(predictions[KEYS + ["partition"]].sort_values(KEYS).reset_index(drop=True),
                                  expected[KEYS + ["partition"]])
    if not predictions.fecha_inicio_semana_objetivo.eq(
            predictions.fecha_inicio_semana.map(lambda day: day + timedelta(days=7))).all():
        raise ValueError("Objetivo distinto de t+1")
    for part, weeks in zip(PARTS, (8, 8, 4)):
        group = predictions[predictions.partition.eq(part)]
        if (group.fecha_inicio_semana_objetivo.nunique() != weeks or group.radio_censal.nunique() != 263
                or group.groupby("fecha_inicio_semana_objetivo").size().ne(263).any()):
            raise ValueError("Grilla semanal incompleta")
    if (list(features.columns) != KEYS + BASE or features.duplicated(KEYS).any()
            or not np.isfinite(features[BASE].to_numpy(dtype=float)).all()):
        raise ValueError("Matriz A inválida")
    joined = predictions.merge(features, on=KEYS, validate="one_to_one", how="left")
    if joined[BASE].isna().any().any():
        raise ValueError("Predicciones sin características de origen")
    known = joined.objetivo_semana_siguiente.notna()
    if not joined.loc[known, "objetivo_semana_siguiente"].isin([0, 1]).all():
        raise ValueError("Etiquetas no binarias")
    negative = joined.objetivo_semana_siguiente.eq(0).fillna(False)
    if not joined.loc[negative, "tipo_etiqueta"].eq("cero_asumido_experimental").all():
        raise ValueError("Negativos ajenos al escenario asumido")
    for model in MODELS:
        p = joined[model + "_probability"].to_numpy(float)
        if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
            raise ValueError("Probabilidades inválidas")
        if not np.array_equal((p >= .5).astype(int), joined[model + "_predicted"].to_numpy(int)):
            raise ValueError("Predicción de clase incompatible con umbral congelado")
    return joined


def diagnose_predictions(frame, stored_metrics, stored_temporal, stored_calibration):
    audit, summary, weekly, calibration, curves = [], [], [], [], []
    prior = float(frame.loc[frame.partition.eq("train") & frame.objetivo_semana_siguiente.notna(),
                            "objetivo_semana_siguiente"].mean())
    if not np.allclose(frame.training_prevalence_probability, prior, rtol=0, atol=1e-15):
        raise ValueError("El baseline usa una probabilidad distinta de la prevalencia de entrenamiento")
    for model in MODELS:
        for part in PARTS:
            group = frame[frame.partition.eq(part)]
            known = group[group.objetivo_semana_siguiente.notna()]
            y, p = known.objetivo_semana_siguiente.to_numpy(int), known[model + "_probability"].to_numpy(float)
            result = numeric_metrics(y, p)
            scope = model + ":" + part
            audit_sklearn(y, p, result, audit, scope)
            for name, expected in stored_metrics[model][part].items():
                if name in result:
                    assert_close(name, result[name], expected, audit, scope + ":phase5c")
            result.update(model=model, partition=part, grid_rows=len(group), unknown_excluded=len(group) - len(known),
                known_label_coverage=len(known) / len(group), mean_probability_all_radios=float(group[model + "_probability"].mean()))
            summary.append(result)
            bins = reliability(y, p)
            old = stored_calibration[stored_calibration.model.eq(model) & stored_calibration.partition.eq(part)]
            if set(old.bin) != {row["bin"] for row in bins}:
                raise ValueError("Bins de calibración inconsistentes")
            for row in bins:
                original = old[old.bin.eq(row["bin"])].iloc[0]
                for name, value in row.items():
                    assert_close(name, value, original[name], audit, scope + ":calibration")
                calibration.append({"model": model, "partition": part, **row})
            pr_p, pr_r, _ = skm.precision_recall_curve(y, p)
            fpr, tpr, _ = skm.roc_curve(y, p)
            curves.append({"model": model, "partition": part, "recall": pr_r.tolist(),
                "precision": pr_p.tolist(), "fpr": fpr.tolist(), "tpr": tpr.tolist(),
                "ap": result["average_precision_pr_auc"], "roc_auc": result["roc_auc"], "prevalence": result["prevalence"]})
            for week, data in group.groupby("fecha_inicio_semana_objetivo", sort=True):
                known_week = data[data.objetivo_semana_siguiente.notna()]
                wy, wp = known_week.objetivo_semana_siguiente.to_numpy(int), known_week[model + "_probability"].to_numpy(float)
                row = numeric_metrics(wy, wp)
                scope_week = scope + ":" + str(week)
                audit_sklearn(wy, wp, row, audit, scope_week)
                row.update(model=model, partition=part, target_week=str(week),
                    target_end=str(week + timedelta(days=6)), grid_rows=len(data),
                    unknown_excluded=len(data) - len(known_week), known_label_coverage=len(known_week) / len(data),
                    mean_probability_all_radios=float(data[model + "_probability"].mean()),
                    sum_probabilities_all_radios=float(data[model + "_probability"].sum()),
                    predicted_positive_all_radios=int(data[model + "_predicted"].sum()))
                original = stored_temporal[stored_temporal.model.eq(model) & stored_temporal.partition.eq(part)
                    & stored_temporal.target_week.eq(week)]
                if len(original) != 1:
                    raise ValueError("Semana ausente o duplicada en diagnóstico previo")
                for name, expected in original.iloc[0].items():
                    if name in row and name not in ("target_week",):
                        assert_close(name, row[name], expected, audit, scope_week + ":phase5c")
                weekly.append(row)
            part_weeks = [row for row in weekly if row["model"] == model and row["partition"] == part]
            for count in ("n", "positive", "negative", "tp", "fp", "tn", "fn", "predicted_positive"):
                assert_close(count, sum(row[count] for row in part_weeks), result[count], audit, scope + ":weekly_sum")
            for value in ("brier", "mean_probability", "log_loss"):
                assert_close(value, sum(row[value] * row["n"] for row in part_weeks) / result["n"],
                             result[value], audit, scope + ":weighted_weekly")
    comparison = []
    for part in PARTS:
        rf = next(row for row in summary if row["model"] == MODELS[0] and row["partition"] == part)
        baseline = next(row for row in summary if row["model"] == MODELS[1] and row["partition"] == part)
        comparison.append({"partition": part, "n": rf["n"], "prevalence": rf["prevalence"],
            "delta_ap_rf_minus_baseline": rf["average_precision_pr_auc"] - baseline["average_precision_pr_auc"],
            "delta_roc_auc_rf_minus_baseline": rf["roc_auc"] - baseline["roc_auc"],
            "delta_brier_rf_minus_baseline": rf["brier"] - baseline["brier"],
            "brier_skill_against_frozen_training_prior": 1 - rf["brier"] / baseline["brier"],
            "delta_log_loss_rf_minus_baseline": rf["log_loss"] - baseline["log_loss"]})
    return summary, weekly, calibration, audit, curves, comparison


def empirical_ks_distance(a, b):
    """Distancia descriptiva entre CDF; no se calculan p-valores IID."""
    a, b = np.sort(a), np.sort(b)
    if not len(a) or not len(b):
        raise ValueError("Distribución vacía")
    points = np.unique(np.r_[a, b])
    return float(np.max(np.abs(np.searchsorted(a, points, side="right") / len(a)
                              - np.searchsorted(b, points, side="right") / len(b))))


def feature_diagnostics(frame, importance):
    if set(importance.feature) != set(BASE) or len(importance) != len(BASE):
        raise ValueError("Variables MDI inesperadas")
    if (not np.isfinite(importance.importance_mdi).all() or importance.importance_mdi.lt(0).any()
            or not np.isclose(importance.importance_mdi.sum(), 1, rtol=0, atol=1e-12)):
        raise ValueError("Importancias MDI inconsistentes")
    for feature in STATIC:
        if frame.groupby("radio_censal")[feature].nunique(dropna=False).ne(1).any():
            raise ValueError("Contexto geográfico variable dentro del mismo radio")
    structural = frame.drop_duplicates("radio_censal")[STATIC]
    identity = structural.poblacion / structural.superficie_km2
    relative = np.abs(structural.densidad_poblacional - identity) / np.maximum(np.abs(identity), 1)
    if relative.max() > 1e-10:
        raise ValueError("Densidad no corresponde a población/superficie")
    positive = structural.poblacion.gt(0) & structural.densidad_poblacional.gt(0)
    logres = (np.log(structural.loc[positive, "densidad_poblacional"])
              - np.log(structural.loc[positive, "poblacion"]) + np.log(structural.loc[positive, "superficie_km2"]))
    correlations = []
    for method in ("pearson", "spearman"):
        matrix = structural.corr(method=method)
        for one in STATIC:
            for two in STATIC:
                correlations.append({"method": method, "feature_one": one, "feature_two": two,
                                     "correlation": float(matrix.loc[one, two]), "unique_radios": len(structural)})
    distributions = []
    for population in ("all_radios_grid", "known_labels_only"):
        subset = frame if population == "all_radios_grid" else frame[frame.objetivo_semana_siguiente.notna()]
        train = subset[subset.partition.eq("train")]
        for part in PARTS:
            group = subset[subset.partition.eq(part)]
            for feature in BASE:
                values, reference = group[feature].to_numpy(float), train[feature].to_numpy(float)
                distributions.append({"population": population, "partition": part, "feature": feature,
                    "n": len(values), "unique_radios": int(group.radio_censal.nunique()), "distinct": int(len(np.unique(values))),
                    "mean": float(values.mean()), "std_descriptive": float(values.std()),
                    "minimum": float(values.min()), "q25": float(np.quantile(values, .25)),
                    "median": float(np.median(values)), "q75": float(np.quantile(values, .75)), "maximum": float(values.max()),
                    "training_minimum": float(reference.min()), "training_maximum": float(reference.max()),
                    "outside_training_range": int(((values < reference.min()) | (values > reference.max())).sum()),
                    "outside_training_fraction": float(((values < reference.min()) | (values > reference.max())).mean()),
                    "empirical_ks_distance_no_p_value": empirical_ks_distance(reference, values),
                    "wasserstein_distance_in_feature_units": float(wasserstein_distance(reference, values))})
    redundancy = {"unique_radios": len(structural), "density_identity_max_relative_error": float(relative.max()),
        "log_density_minus_log_population_plus_log_area_max_abs": float(np.abs(logres).max()),
        "positive_population_radios_for_log_identity": int(positive.sum()),
        "all_grid_static_distributions_identical_across_partitions": all(
            row["empirical_ks_distance_no_p_value"] == 0 for row in distributions
            if row["population"] == "all_radios_grid" and row["feature"] in STATIC),
        "importance_type": "training_MDI_not_causal_or_unique_contribution",
        "importances_sum": float(importance.importance_mdi.sum())}
    return distributions, correlations, redundancy


def matched_test_diagnostics(frame):
    test = frame[frame.partition.eq("test")]
    count = test[test.objetivo_semana_siguiente.notna()].groupby("radio_censal").size()
    radios = set(count[count.eq(4)].index)
    if not radios:
        raise ValueError("No hay radios conocidos en todas las semanas de prueba")
    matched = test[test.radio_censal.isin(radios)]
    rows = []
    for week, data in matched.groupby("fecha_inicio_semana_objetivo", sort=True):
        for model in MODELS:
            rows.append({"target_week": str(week), "model": model, "population": "same_radios_known_in_all_four_test_weeks",
                **numeric_metrics(data.objetivo_semana_siguiente, data[model + "_probability"])})
    pivot = test.pivot(index="radio_censal", columns="fecha_inicio_semana_objetivo", values="random_forest_A_probability")
    if pivot.isna().any().any():
        raise ValueError("Grilla de probabilidades de prueba incompleta")
    change = pivot.iloc[:, -1] - pivot.iloc[:, 0]
    pairs = []
    for before, after in zip(pivot.columns[:-1], pivot.columns[1:]):
        delta = pivot[after] - pivot[before]
        pairs.append({"first_week": str(before), "second_week": str(after),
            "pearson_probability_correlation_descriptive": float(pivot[before].corr(pivot[after])),
            "spearman_probability_correlation_descriptive": float(pivot[before].corr(pivot[after], method="spearman")),
            "radios_with_exactly_unchanged_probability": int(delta.eq(0).sum()),
            "maximum_absolute_probability_change": float(delta.abs().max())})
    stability = {"all_test_radios": len(pivot), "matched_known_radios": len(radios),
        "first_to_last_probability_change_mean": float(change.mean()),
        "first_to_last_probability_change_median": float(change.median()),
        "radios_probability_decreased": int(change.lt(-1e-12).sum()),
        "radios_probability_increased": int(change.gt(1e-12).sum()),
        "radios_probability_unchanged": int(change.abs().le(1e-12).sum()), "successive_week_correlations": pairs,
        "interpretation": "descriptive paired radios, not independent events; cohort selection may bias representativeness"}
    return rows, stability


def roc_week_pair_diagnostics(frame):
    """Identidad de concordancia AUC: pares de semanas, sin inferencia IID."""
    test = frame[frame.partition.eq("test") & frame.objetivo_semana_siguiente.notna()]
    weeks = sorted(test.fecha_inicio_semana_objetivo.unique())
    table, summaries = [], []
    for model in MODELS:
        pairs = []
        for positive_week in weeks:
            positives = test.loc[test.fecha_inicio_semana_objetivo.eq(positive_week)
                & test.objetivo_semana_siguiente.eq(1), model + "_probability"].to_numpy(float)
            for negative_week in weeks:
                negatives = test.loc[test.fecha_inicio_semana_objetivo.eq(negative_week)
                    & test.objetivo_semana_siguiente.eq(0), model + "_probability"].to_numpy(float)
                total = len(positives) * len(negatives)
                delta = positives[:, None] - negatives[None, :]
                concordance = float((delta > 0).sum() + .5 * (delta == 0).sum())
                pairs.append({"model": model, "positive_week": str(positive_week),
                    "negative_week": str(negative_week), "same_week": positive_week == negative_week,
                    "positive_negative_pairs": total, "concordance_with_half_ties": concordance,
                    "auc_for_week_pair": concordance / total if total else None})
        total = sum(r["positive_negative_pairs"] for r in pairs)
        summary = {"model": model, "pair_total": total,
            "pooled_auc_reconstructed": sum(r["concordance_with_half_ties"] for r in pairs) / total}
        for label, flag in (("within_week", True), ("between_weeks", False)):
            group = [r for r in pairs if r["same_week"] == flag]
            n = sum(r["positive_negative_pairs"] for r in group)
            summary[label + "_pair_fraction"] = n / total
            summary[label + "_auc_weighted_by_pairs"] = sum(r["concordance_with_half_ties"] for r in group) / n if n else None
        expected = numeric_metrics(test.objetivo_semana_siguiente, test[model + "_probability"])["roc_auc"]
        if not np.isclose(expected, summary["pooled_auc_reconstructed"], rtol=0, atol=1e-12):
            raise ValueError("No concilia la descomposición temporal de ROC-AUC")
        table.extend(pairs)
        summaries.append(summary)
    return table, summaries


def date_diagnostics(predictions, labels, earlier_comparison):
    joined = predictions.merge(labels[KEYS + ["objetivo_con_fecha_aproximada", "pendientes_semana_objetivo"]],
                               on=KEYS, validate="one_to_one")
    result = []
    for part in PARTS:
        data = joined[joined.partition.eq(part)]
        pos = data[data.objetivo_semana_siguiente.eq(1)]
        result.append({"partition": part, "provisional_positive_labels": len(pos),
            "positive_labels_with_approximate_date_flag": int(pos.objetivo_con_fecha_aproximada.eq(True).sum()),
            "positive_labels_coexisting_with_pending": int(pos.pendientes_semana_objetivo.gt(0).sum())})
    return {"by_partition": result, "earlier_source_delay_evidence": earlier_comparison["delay_evidence"],
        "earlier_delay_evidence_scope": earlier_comparison["analysis_period"],
        "delay_imputation_or_relabeling": False,
        "interpretation": "sample dates need not equal onset; global historical delay audit cannot be transferred to the 2024 test subset"}


def records(data):
    return json.loads(pd.DataFrame(data).to_json(orient="records", double_precision=15))


def git_state(root):
    def run(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    return {"branch": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
        "status_porcelain": run("status", "--porcelain", "--untracked-files=all").splitlines(),
        "staged_paths": run("diff", "--cached", "--name-only").splitlines(),
        "commit_performed": False, "push_performed": False}


def workspace_snapshot(root):
    listing = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root).decode("utf-8")
    paths = {root / name for name in listing.split("\0") if name}
    return {str(path): digest_path(path) for path in sorted(paths) if path.is_file()}


def run_diagnostics(root, input_dir=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT, plot_python=None):
    root = root.resolve()
    require_branch(root)
    source, output = checked_paths(root, input_dir, output_dir)
    before_workspace = workspace_snapshot(root)
    initial_git = git_state(root)
    manifest = verify_manifest(source)
    verify_hashes(manifest["protected_files_sha256"])
    config = read_json(source / "configuration.private.json")
    review = read_json(source / "review.private.json")
    if (review["training_authorized"] is not False or review["production_training_enabled"] is not False
            or review["coverage_verified"] is not False or review["threshold"] != .5):
        raise ValueError("Condiciones oficiales/umbral alterados")
    scenario = (root / config["scenario_dir"]).resolve()
    private = (root / "data/processed/official").resolve()
    if scenario == private or not scenario.is_relative_to(private):
        raise ValueError("Escenario fuera del almacenamiento privado")
    verify_manifest(scenario)
    earlier_dates = root / "data/interim/official/observed/date_recovery_041/comparison.private.json"
    protected = dict(manifest["protected_files_sha256"])
    protected.update({str(path): digest_path(path) for directory in (source, scenario)
                      for path in directory.rglob("*") if path.is_file()})
    protected[str(earlier_dates)] = digest_path(earlier_dates)
    predictions = pd.read_parquet(source / "predictions_radio_week.private.parquet")
    labels = pd.read_parquet(scenario / "labels.private.parquet")
    features = pd.read_parquet(scenario / "predictors_A.private.parquet")
    splits = pd.read_parquet(scenario / "splits.private.parquet")
    frame = check_prediction_grid(predictions, labels, features, splits)
    summary, weekly, calibration, audit, curves, comparison = diagnose_predictions(frame,
        read_json(source / "metrics.private.json"), pd.read_parquet(source / "temporal_diagnostics.private.parquet"),
        pd.read_parquet(source / "calibration.private.parquet"))
    importance = pd.read_parquet(source / "feature_importance.private.parquet")
    distributions, correlations, redundancy = feature_diagnostics(frame, importance)
    matched, stability = matched_test_diagnostics(frame)
    roc_pairs, roc_decomposition = roc_week_pair_diagnostics(frame)
    for row in roc_decomposition:
        expected = next(item["roc_auc"] for item in summary if item["model"] == row["model"] and item["partition"] == "test")
        assert_close("roc_auc_week_pair_decomposition", row["pooled_auc_reconstructed"], expected, audit, row["model"] + ":test")
    dates = date_diagnostics(predictions, labels, read_json(earlier_dates))
    verify_hashes(protected)
    require_preserved(before_workspace, workspace_snapshot(root))
    output.mkdir(parents=True, exist_ok=False)
    tables = {"partition_metrics": summary, "weekly_metrics": weekly,
        "test_weekly_metrics": [row for row in weekly if row["partition"] == "test"],
        "calibration_bins": calibration, "metric_consistency_audit": audit, "baseline_comparison": comparison,
        "feature_distributions": distributions, "structural_correlations": correlations,
        "matched_test_cohort": matched, "roc_week_pairs": roc_pairs,
        "feature_importance": importance.to_dict("records")}
    for name, data in tables.items():
        pd.DataFrame(data).to_parquet(output / f"{name}.private.parquet", index=False)
        pd.DataFrame(data).to_csv(output / f"{name}.private.csv", index=False)
    write_report({"redundancy": redundancy, "stability": stability, "dates": dates,
        "roc_decomposition": roc_decomposition}, output / "supplementary_diagnostics.private.json")
    payload = {"version": VERSION, "unit": "radio_censal_origin_week_provisional_presence_t_plus_1",
        "period": "target weeks 2024-01-07 to 2024-06-08; two purged weeks excluded",
        "summary": records(summary), "weekly": records(weekly), "calibration": records(calibration),
        "comparison": records(comparison), "curves": curves, "distributions": records(distributions),
        "correlations": records(correlations), "importance": records(importance), "matched": records(matched),
        "redundancy": redundancy, "stability": stability, "dates": dates, "roc_decomposition": roc_decomposition}
    write_report(payload, output / "figure_data.private.json")
    plot_script = Path(__file__).with_name("research_diagnostic_plots.py")
    if plot_python is None or not Path(plot_python).is_file():
        raise ValueError("Se requiere Python aislado con Matplotlib; resultados parciales privados conservados")
    plotting = subprocess.run([str(Path(plot_python).resolve()), "-B", str(plot_script), "--input",
        str(output / "figure_data.private.json"), "--output", str(output / "figures")],
        cwd=root, capture_output=True, text=True, check=False)
    if plotting.returncode:
        raise ValueError("Falló render privado; revisar dependencias sin volcar datos")
    plot_runtime = read_json(output / "figures/render_runtime.private.json")
    # El informe se genera desde las mismas tablas que se auditaron y graficaron.
    from sigard_ml.official.spatial_ml.research_diagnostic_report import write_diagnostic_report
    state = git_state(root)
    write_diagnostic_report(output, payload, len(audit), len(protected), state)
    code = [Path(__file__), plot_script, Path(__file__).with_name("research_diagnostic_report.py")]
    for path in code:
        (output / path.name).write_bytes(path.read_bytes())
    write_report({"version": VERSION, "input_dir": str(source.relative_to(root)),
        "output_dir": str(output.relative_to(root)), "training_performed": False, "models_loaded": False,
        "calibration_fitted": False, "threshold_changed": False, "labels_or_coverage_changed": False,
        "training_authorized": False, "production_training_enabled": False,
        "mathematical_checks": len(audit), "all_checks_passed": all(row["matches"] for row in audit),
        "guarded_fit_and_model_load_calls": list(NO_FIT_TARGETS),
        "runtime": {"python": platform.python_version(), **{name: importlib.metadata.version(name)
                    for name in ("numpy", "pandas", "scikit-learn", "scipy", "pyarrow")}},
        "plot_runtime": plot_runtime, "source_model_parameters": review["parameters"],
        "source_model_parameters_modified": False, "source_manifest_sha256": digest_path(source / "integrity_manifest.private.json"),
        "implementation_sha256": {str(path.relative_to(root)): digest_path(path) for path in code},
        "sampling_unit": "radio-week; only four dependent test weeks; no IID inference",
        "human_scientific_review": "pending_user_review", "submission_ready": False}, output / "metadata.private.json")
    write_report({"before": initial_git, "after": state, "preexisting_workspace_files_unchanged": True},
                 output / "git_state.private.json")
    verify_hashes(protected)
    require_preserved(before_workspace, workspace_snapshot(root))
    write_report({"version": VERSION, "previous_artifacts_preserved": True,
        "protected_files_sha256": protected, "preexisting_workspace_sha256": before_workspace,
        "outputs_sha256": {path.relative_to(output).as_posix(): digest_path(path)
                           for path in sorted(output.rglob("*")) if path.is_file()}},
        output / "integrity_manifest.private.json")
    return {"version": VERSION, "output_dir": str(output.relative_to(root)), "training_performed": False,
        "models_loaded": False, "checks_passed": len(audit), "protected_files_unchanged": len(protected),
        "test_metrics": [row for row in summary if row["partition"] == "test"], "redundancy": redundancy,
        "matched_test_radios": stability["matched_known_radios"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    parser.add_argument("--plot-python", type=Path, required=True)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[5]
        def forbidden(*args, **kwargs):
            raise RuntimeError("Entrenamiento o carga de modelo prohibidos en Fase 5D")
        with ExitStack() as stack:
            for target in NO_FIT_TARGETS:
                stack.enter_context(patch(target, side_effect=forbidden))
            result = run_diagnostics(root, args.input_dir, args.output_dir, args.plot_python)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "Diagnóstico detenido; revisar evidencia privada sin modificar artefactos de Fase 5C.\n")


if __name__ == "__main__":
    main()
