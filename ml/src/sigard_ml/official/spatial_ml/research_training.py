"""Fase 5C: RF A retrospectivo, con permiso propio y sin habilitar producción."""

import argparse
from datetime import date, timedelta
import importlib.metadata
from io import BytesIO
import json
from pathlib import Path
import platform
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, f1_score,
    log_loss, precision_recall_curve, precision_score, recall_score,
    roc_auc_score, auc,
)

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, require_preserved
from sigard_ml.official.spatial_ml.assumed_scenario import (
    ZERO_KIND, chronological_review, materialize_labels,
)
from sigard_ml.official.spatial_ml.assumed_scenario_pipeline import snapshot
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import KEYS, calendar_predictors
from sigard_ml.official.spatial_ml.pipeline import read_json, verify_private_manifest, verify_sources

VERSION = "official-spatial-rf-research-0.5c.0"
PLAN = "authorized_2024_only"
THRESHOLD = 0.5
PERIODS = {
    "train": (date(2024, 1, 7), date(2024, 3, 2), 8),
    "validation": (date(2024, 3, 10), date(2024, 5, 4), 8),
    "test": (date(2024, 5, 12), date(2024, 6, 8), 4),
}
ACKNOWLEDGED_LIMITS = [
    "assumed_negatives_not_verified_absences", "provisional_positive_eligibility",
    "unverified_label_arrival_and_maturation", "unverified_census_historical_availability",
    "approximate_dates_and_spatial_assignments", "few_dependent_weeks_and_neighboring_radios",
    "retrospective_research_only_no_epidemiological_validation",
]
DEFAULTS = {
    "version": VERSION, "access_config": "data/interim/official/access.private.json",
    "phase5a_dir": "data/processed/official/spatial_ml_05a_v2",
    "phase5b_dir": "data/interim/official/spatial_experiment_05b_v1",
    "scenario_dir": "data/processed/official/spatial_assumed_2024_v1",
    "output_dir": "data/processed/official/spatial_rf_05c_v1",
    "training_authorized": False, "research_authorization": None,
}


def validate_research_authorization(entry, scenario_hash):
    """Permiso de derivados congelados; no altera permisos de acceso oficiales."""
    required = {"version", "decision_ref", "responsible_ref", "research_training_authorized",
                "training_authorized", "scope", "scenario_manifest_sha256", "target_start",
                "target_end", "plan", "model", "negative_kind", "acknowledged_limits"}
    if not isinstance(entry, dict) or set(entry) != required:
        raise ValueError("Falta autorización explícita diferenciada de investigación")
    if (entry["version"] != VERSION or entry["research_training_authorized"] is not True
            or entry["training_authorized"] is not False
            or entry["scope"] != "isolated_retrospective_research_on_frozen_derivatives"
            or entry["scenario_manifest_sha256"] != scenario_hash
            or entry["target_start"] != "2024-01-07" or entry["target_end"] != "2024-06-08"
            or entry["plan"] != PLAN or entry["model"] != "A"
            or entry["negative_kind"] != ZERO_KIND
            or entry["acknowledged_limits"] != ACKNOWLEDGED_LIMITS
            or any(not isinstance(entry[key], str) or not entry[key].strip()
                   for key in ("decision_ref", "responsible_ref"))):
        raise ValueError("Autorización de investigación fuera del alcance aprobado")


def private_paths(root, options):
    root = root.resolve()
    if (set(options) != set(DEFAULTS) or options["version"] != VERSION
            or options["training_authorized"] is not False):
        raise ValueError("Contrato oficial debe permanecer bloqueado")
    inputs = {}
    for key in ("access_config", "phase5a_dir", "phase5b_dir", "scenario_dir"):
        path = (root / options[key]).resolve()
        storage = (root / ("data/interim/official" if key in ("access_config", "phase5b_dir")
                           else "data/processed/official")).resolve()
        if not storage.is_relative_to(root) or path == storage or not path.is_relative_to(storage):
            raise ValueError("Entrada fuera del almacenamiento privado")
        inputs[key] = path
    output = (root / options["output_dir"]).resolve()
    if (output.parent != (root / "data/processed/official").resolve() or output.exists()
            or any(output == path or output.is_relative_to(path) or path.is_relative_to(output)
                   for path in inputs.values())):
        raise ValueError("Se exige una ruta privada nueva sin superposición")
    for path in [*inputs.values(), output]:
        result = subprocess.run(["git", "check-ignore", "--quiet", "--", str(path.relative_to(root))],
                                cwd=root, capture_output=True, check=False)
        if result.returncode != 0:
            raise ValueError("Ruta no excluida de Git")
    validate_research_authorization(options["research_authorization"],
                                   digest_path(inputs["scenario_dir"] / "integrity_manifest.private.json"))
    return inputs, output


def validate_design(labels, features, splits, policies):
    """Integridad computacional; no certifica disponibilidad histórica censal."""
    if (labels.empty or labels.duplicated(KEYS).any() or features.duplicated(KEYS).any()
            or labels[KEYS].isna().any().any() or labels.radio_censal.nunique() != 263
            or list(features.columns) != KEYS + BASE):
        raise ValueError("Grilla, identidad o lista de predictores inválida")
    pd.testing.assert_frame_equal(labels[KEYS], features[KEYS])
    if features[BASE].isna().any().any() or not np.isfinite(features[BASE].to_numpy(dtype=float)).all():
        raise ValueError("Predictores obligatorios incompletos/no finitos")
    if (labels.apto_entrenamiento.ne(False).any() or not labels.panel_fechas.eq("expanded").all()
            or not labels.fecha_inicio_semana_objetivo.eq(
                labels.fecha_inicio_semana.map(lambda day: day + timedelta(days=7))).all()
            or not labels.fecha_fin_semana_objetivo.dropna().eq(
                labels.loc[labels.fecha_fin_semana_objetivo.notna(), "fecha_inicio_semana_objetivo"].map(
                    lambda day: day + timedelta(days=6))).all()):
        raise ValueError("Objetivo t+1, política o bloqueo oficial alterado")
    if not labels.objetivo_semana_siguiente.dropna().isin([0, 1]).all():
        raise ValueError("Etiquetas no binarias")
    negative = labels.objetivo_semana_siguiente.eq(0).fillna(False)
    assumed = labels.tipo_etiqueta.eq(ZERO_KIND)
    if (not negative.eq(assumed).all() or labels.loc[assumed, "objetivo_original"].notna().any()
            or not labels.loc[assumed, "pendientes_semana_objetivo"].eq(0).all()
            or not labels.loc[assumed, "semana_objetivo_parcial"].eq(False).all()
            or not labels.loc[assumed, "en_intervalo_autorizado"].eq(True).all()):
        raise ValueError("Negativos ajenos al escenario asumido autorizado")
    selected_policies = {row["feature"]: row for row in policies if row["feature"] in BASE}
    if set(selected_policies) != set(BASE):
        raise ValueError("Catálogo A incompleto")
    for row in selected_policies.values():
        if (row["uses_future_week"] is not False or row["depends_on_unknown_origin_or_past_counts"]
                or any(offset > 0 for offset in (row["source_week_offsets"] or []))):
            raise ValueError("Predictor dependiente de historia o información futura")
    calendar = features[KEYS].copy()
    year_week = calendar.fecha_inicio_semana.map(DEFAULT_CALENDAR.date_week)
    calendar["anio_epidemiologico"] = year_week.map(lambda item: item[0])
    calendar["semana_epidemiologica"] = year_week.map(lambda item: item[1])
    expected = calendar_predictors(calendar)
    for name in ("semana_epidemiologica", "estacionalidad_seno", "estacionalidad_coseno"):
        if not np.allclose(features[name].to_numpy(float), expected[name].to_numpy(float), rtol=0, atol=1e-12):
            raise ValueError("Calendario no corresponde a la semana de origen")
    for name in BASE[:4]:
        if features.groupby("radio_censal")[name].nunique(dropna=False).ne(1).any():
            raise ValueError("Contexto estático depende de semanas futuras")
    rebuilt, _ = chronological_review(labels)
    inherited = splits[splits.plan.eq(PLAN)].sort_values(KEYS).reset_index(drop=True)
    expected_split = rebuilt[rebuilt.plan.eq(PLAN)].sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(inherited, expected_split)
    joined = labels.merge(features, on=KEYS, validate="one_to_one").merge(
        inherited[KEYS + ["partition"]], on=KEYS, validate="one_to_one")
    summary = {}
    previous_end = None
    for part, (start, end, weeks) in PERIODS.items():
        frame = joined[joined.partition.eq(part)]
        if (frame.empty or frame.fecha_inicio_semana_objetivo.min() != start
                or frame.fecha_fin_semana_objetivo.max() != end
                or frame.fecha_inicio_semana_objetivo.nunique() != weeks
                or not frame.en_intervalo_autorizado.eq(True).all()
                or frame.groupby("fecha_inicio_semana_objetivo").size().ne(263).any()
                or (previous_end and previous_end >= frame.fecha_inicio_semana.min())):
            raise ValueError("Particiones cronológicas o purga incompatibles")
        previous_end = end
        known = frame.objetivo_semana_siguiente.dropna()
        if set(known.unique()) != {0, 1}:
            raise ValueError("Falta una clase en una partición")
        summary[part] = {"grid_rows": len(frame), "used": len(known), "positive": int(known.sum()),
            "negative": int(known.eq(0).sum()), "unknown_excluded": int(frame.objetivo_semana_siguiente.isna().sum()),
            "prevalence": float(known.mean()), "target_weeks": weeks, "first_target": str(start),
            "last_target_end": str(end), "first_origin": str(frame.fecha_inicio_semana.min()),
            "coverage_known_labels": len(known) / len(frame)}
    scope = joined[joined.en_intervalo_autorizado.eq(True)]
    purged = scope[~scope.partition.isin(PERIODS)]
    if set(purged.fecha_inicio_semana_objetivo.unique()) != {date(2024, 3, 3), date(2024, 5, 5)}:
        raise ValueError("Semanas purgadas alteradas")
    return joined, summary


def classification_metrics(y, probability, threshold=THRESHOLD):
    y, probability = np.asarray(y, dtype=int), np.asarray(probability, dtype=float)
    if (len(y) == 0 or len(y) != len(probability) or not np.isin(y, [0, 1]).all()
            or not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any()):
        raise ValueError("Evaluación inválida")
    predicted = (probability >= threshold).astype(int)
    both = len(np.unique(y)) == 2
    precision, recall, _ = precision_recall_curve(y, probability) if both else (None, None, None)
    return {"n": len(y), "positive": int(y.sum()), "negative": int((y == 0).sum()),
        "prevalence": float(y.mean()), "threshold": threshold,
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "average_precision_pr_auc": float(average_precision_score(y, probability)) if both else None,
        "pr_auc_trapezoidal": float(auc(recall, precision)) if both else None,
        "roc_auc": float(roc_auc_score(y, probability)) if both else None,
        "brier": float(brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, np.column_stack([1 - probability, probability]), labels=[0, 1])),
        "confusion_matrix_true_rows_predicted_columns_0_1": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
        "predicted_positive": int(predicted.sum()), "mean_probability": float(probability.mean()),
        "calibration_gap_mean_probability_minus_prevalence": float(probability.mean() - y.mean()),
        "precision_zero_division_policy": "0 when no positive predictions; not evidence of precision",
        "ranking_metrics_defined": both}


def reliability_bins(y, probability):
    """Diez intervalos uniformes fijos; exportar sólo bins no vacíos."""
    y, probability = np.asarray(y, dtype=int), np.asarray(probability, dtype=float)
    index = np.minimum((probability * 10).astype(int), 9)
    rows = []
    for number in range(10):
        mask = index == number
        if mask.any():
            rows.append({"bin": number, "lower": number / 10, "upper": (number + 1) / 10,
                "n": int(mask.sum()), "positive": int(y[mask].sum()),
                "mean_probability": float(probability[mask].mean()), "fraction_positive": float(y[mask].mean())})
    return rows


def fit_models(frame):
    """Sólo entrenamiento conocido; umbral/variables/parámetros predefinidos."""
    train = frame[frame.partition.eq("train") & frame.objetivo_semana_siguiente.notna()]
    x, y = train[BASE], train.objetivo_semana_siguiente.astype(int)
    if set(y.unique()) != {0, 1}:
        raise ValueError("Entrenamiento sin ambas clases")
    forest = RandomForestClassifier(**RF_PARAMETERS).fit(x, y)
    baseline = DummyClassifier(strategy="prior", random_state=20261016).fit(x, y)
    return {"random_forest_A": forest, "training_prevalence": baseline}


def evaluate_models(frame, models):
    evaluated = frame[frame.partition.isin(PERIODS)].copy()
    predictions = evaluated[KEYS + ["fecha_inicio_semana_objetivo", "partition", "objetivo_semana_siguiente",
                                  "tipo_etiqueta"]].copy()
    metrics, calibration, temporal = {}, [], []
    for name, model in models.items():
        probability = model.predict_proba(evaluated[BASE])[:, list(model.classes_).index(1)]
        predictions[name + "_probability"] = probability
        predictions[name + "_predicted"] = (probability >= THRESHOLD).astype("int8")
        metrics[name] = {}
        for part in PERIODS:
            group = predictions[predictions.partition.eq(part)]
            known = group[group.objetivo_semana_siguiente.notna()]
            y, p = known.objetivo_semana_siguiente.astype(int), known[name + "_probability"]
            result = classification_metrics(y, p)
            bins = reliability_bins(y, p)
            result["ece_10_uniform_bins_descriptive"] = sum(
                row["n"] * abs(row["fraction_positive"] - row["mean_probability"]) for row in bins) / len(known)
            metrics[name][part] = result
            calibration.extend({"model": name, "partition": part, **row} for row in bins)
        for (part, week), group in predictions.groupby(["partition", "fecha_inicio_semana_objetivo"], sort=True):
            known = group[group.objetivo_semana_siguiente.notna()]
            temporal.append({"model": name, "partition": part, "target_week": week,
                "grid_rows": len(group), "unknown_excluded": len(group) - len(known),
                "sum_probabilities_all_radios": float(group[name + "_probability"].sum()),
                "predicted_positive_all_radios": int(group[name + "_predicted"].sum()),
                **classification_metrics(known.objetivo_semana_siguiente, known[name + "_probability"])})
    return predictions, metrics, pd.DataFrame(calibration), pd.DataFrame(temporal)


def range_diagnostics(frame):
    train = frame[frame.partition.eq("train") & frame.objetivo_semana_siguiente.notna()]
    rows = []
    for feature in BASE:
        lo, hi = float(train[feature].min()), float(train[feature].max())
        for part in PERIODS:
            values = frame.loc[frame.partition.eq(part) & frame.objetivo_semana_siguiente.notna(), feature]
            rows.append({"feature": feature, "partition": part, "train_min": lo, "train_max": hi,
                "partition_min": float(values.min()), "partition_max": float(values.max()),
                "outside_training_range": int(((values < lo) | (values > hi)).sum()), "n": len(values)})
    return pd.DataFrame(rows)


def verify_frozen_hashes(mapping):
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_file() or digest_path(path) != expected:
            raise ValueError("Un artefacto congelado difiere de su hash; detener investigación")


def assert_parquet_equivalent(stored, reconstructed):
    """Comparar con la misma serialización: Arrow normaliza strings y nulls."""
    serialized = BytesIO(reconstructed.to_parquet(index=False))
    pd.testing.assert_frame_equal(stored, pd.read_parquet(serialized))


def protected_files(root, inputs, registry):
    result = snapshot(inputs, registry)
    # Captura archivos existentes de interfaz/API sin cargar dependencias o datos nuevos.
    listing = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "--", "frontend", "backend"],
                             cwd=root, check=True, capture_output=True, text=True).stdout.splitlines()
    for name in listing:
        path = root / name
        if path.is_file():
            result[str(path)] = digest_path(path)
    return result


def report_markdown(report, importance, temporal):
    lines = ["# SIGARD Fase 5C — experimento privado retrospectivo", "",
        "Entrenamiento técnico autorizado exclusivamente para investigación. training_authorized=false en el flujo oficial.",
        "Unidad: radio censal–semana de origen; clasificación de presencia provisional en t+1. No estima cantidad de casos.",
        "Negativos: cero_asumido_experimental. No son ausencias verificadas. Ninguna métrica valida epidemiología.", "",
        "RF A: 400 árboles, profundidad 10, mínimo 5 por hoja, sqrt, balanced_subsample; semilla 20261016.",
        "Baseline: DummyClassifier prior, prevalencia de etiquetas conocidas de entrenamiento; sin actualización posterior.",
        "Umbral 0,5 congelado antes del ajuste según Fase 5B. No se seleccionan umbrales con validación o prueba.",
        "Sólo 8/8/4 semanas de una temporada y etiquetas inmaduras no acreditadas: no hay soporte para un ajuste robusto.",
        "Sin búsqueda de hiperparámetros, calibrador, imputación, reequilibrado de evaluación ni historia epidemiológica.", ""]
    for part, row in report["partitions"].items():
        lines += [f"## {part}", "", f"Objetivos {row['first_target']} a {row['last_target_end']}; origen inicial {row['first_origin']}.",
            f"Usados {row['used']} de {row['grid_rows']}; positivos {row['positive']}; negativos asumidos {row['negative']}; desconocidos excluidos {row['unknown_excluded']}.",
            f"Prevalencia {row['prevalence']:.4%}; {row['target_weeks']} semanas; los radios no son réplicas independientes.", ""]
        for model, results in report["metrics"].items():
            m = results[part]
            lines += [f"### {model}", "",
                f"Precision {m['precision']:.6f}; recall {m['recall']:.6f}; F1 {m['f1']:.6f}; PR-AUC/AP {m['average_precision_pr_auc']:.6f}; ROC-AUC {m['roc_auc']:.6f}; Brier {m['brier']:.6f}.",
                f"PR-AUC trapezoidal {m['pr_auc_trapezoidal']:.6f} (secundaria; AP es la medida primaria); log loss {m['log_loss']:.6f}.",
                f"Matriz [[TN,FP],[FN,TP]]: {m['confusion_matrix_true_rows_predicted_columns_0_1']}.",
                f"Probabilidad media {m['mean_probability']:.6f}; prevalencia {m['prevalence']:.6f}; ECE descriptivo {m['ece_10_uniform_bins_descriptive']:.6f}.", ""]
    lines += ["## Importancia de variables", "", "Disminución media de impureza (MDI), calculada sólo desde entrenamiento; no causal ni evidencia de precisión espacial.",
        "Puede favorecer variables continuas; población/densidad/área y semana/seno/coseno son redundantes. No se usa para reseleccionar variables.", ""]
    for row in importance.to_dict("records"):
        lines.append(f"- {row['feature']}: {row['importance_mdi']:.6f}; dispersión entre árboles {row['tree_std_descriptive']:.6f} (no intervalo de confianza).")
    rf_week = temporal[temporal.model.eq("random_forest_A")]
    peak = rf_week.sort_values(["positive", "target_week"], ascending=[False, True]).iloc[0]
    lines += ["", "## Pico y descenso (diagnóstico retrospectivo)", "",
        f"Pico de radios con etiqueta positiva conocida entre semanas evaluadas: {peak.target_week}, {int(peak.positive)} de {int(peak.n)}; prevalencia {peak.prevalence:.2%}.",
        f"RF en esa semana: recall {peak.recall:.4f}, precision {peak.precision:.4f}, Brier {peak.brier:.4f}, probabilidad media {peak.mean_probability:.4f}.",
        "El pico se define por etiquetas agregadas radio-semana, no por casos clínicos ni incidencia. No interviene en la selección del modelo.",
        "Todas las semanas y modelos, incluido el descenso en prueba, se conservan en temporal_diagnostics.private.*.",
        "Los árboles no extrapolan una curva estacional fuera del soporte de entrenamiento; revisar feature_ranges.private.*.", "",
        "## Análisis crítico y disponibilidad", "",
        "La prevalencia cambia entre ascenso, pico y descenso; AP depende de prevalencia y Brier mezcla discriminación y calibración.",
        "El baseline retiene la prevalencia de entrenamiento: no se usa la prevalencia futura para hacerlo competitivo.",
        "Calibración: diez bins uniformes fijos, sólo bins ocupados, Brier, log loss, ECE y diferencia media; no se ajusta un calibrador.",
        "Las semanas pertenecen a una sola temporada; sólo cuatro en prueba. No se calculan intervalos ni pruebas suponiendo filas independientes.",
        "Los mismos radios aparecen en todos los bloques y los vecinos comparten ambiente y vigilancia: no se evalúa generalización a territorios nuevos.",
        "No hay cobertura epidemiológica verificada: un cero asumido puede contener infecciones o registros ausentes. El rendimiento mide acuerdo con ese escenario.",
        "Los positivos derivan de registros elegibles provisionales; no se valida clasificación, identidad, residencia ni lugar de infección.",
        "Las fechas y ubicaciones aproximadas pueden desplazar objetivos entre semanas/radios; no se publican coordenadas, domicilios o pacientes.",
        "Se verifica que calendario sea de origen, contexto sea estático, t+1 sea exacto y catálogo no tenga offsets futuros; ningún dato del objetivo entra como predictor.",
        "La disponibilidad histórica de población, límites y topología del Censo 2022 NO está acreditada. Se usan como contexto retrospectivo por autorización explícita.",
        "La llegada/revisión y maduración de etiquetas no está reconstruida. Ausencia de fuga computacional no acredita disponibilidad operativa punto en el tiempo.",
        "Desconocidos excluidos de ajuste y métricas; sí conservados en denominadores de cobertura y predicciones de toda la grilla evaluada.",
        "Se preservan purgas 2024-03-03 y 2024-05-05 (semanas objetivo). Ningún predictor desconocido se convierte en cero.",
        "Los bloqueos oficiales, fuentes, modelos existentes y etiquetas originales se conservan por hashes. No se entrenó el flujo oficial.", "",
        "## Reproducibilidad", "", json.dumps(report["reproducibility"], ensure_ascii=False, indent=2), "",
        "Configuración/autorización vinculada al hash del manifiesto de escenario; versiones instaladas y pip freeze, código copiado, hashes de entradas/salidas y modelos aislados.",
        "Sólo se deserializan los joblib escritos por esta ejecución. No son modelos desplegables ni se cargan desde API.", "",
        "## Referencias de implementación", "",
        "- scikit-learn, RandomForestClassifier: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html",
        "- scikit-learn, Probability calibration: https://scikit-learn.org/stable/modules/calibration.html",
        "- Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065",
        "Se aplicaron las skills scikit-learn, statistical-analysis, scientific-critical-thinking y criterios de procedencia/privacidad de geopandas; no se rehacen uniones ni geocodificación.", ""]
    return "\n".join(lines)


def run_research(root, options):
    root = root.resolve()
    require_branch(root)
    inputs, output = private_paths(root, options)
    _, registry = load_configuration(inputs["access_config"], root)
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    before = protected_files(root, inputs, registry)
    for key in ("phase5a_dir", "phase5b_dir", "scenario_dir"):
        verify_private_manifest(inputs[key])
    scenario = inputs["scenario_dir"]
    frozen = read_json(scenario / "integrity_manifest.private.json")["protected_files_sha256"]
    verify_frozen_hashes(frozen)
    metadata = read_json(scenario / "metadata.private.json")
    verify_frozen_hashes(metadata["input_files_sha256"])
    verify_sources(registry, metadata["coverage_metadata"])
    if metadata["training_enabled"] is not False or metadata["date_policy"] != "expanded":
        raise ValueError("El escenario oficial dejó de estar bloqueado")
    model_a = read_json(scenario / "experiment_A.reference.private.json")
    if (model_a["parameters"] != RF_PARAMETERS or model_a["required"] != BASE or model_a["optional"]
            or model_a["training_enabled"] is not False or model_a["set"] != "A"
            or digest_path(scenario / "experiment_A.reference.private.json") != metadata["model_A_sha256"]):
        raise ValueError("Modelo A diferente de la configuración aprobada")
    labels = pd.read_parquet(scenario / "labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
    features = pd.read_parquet(scenario / "predictors_A.private.parquet").sort_values(KEYS).reset_index(drop=True)
    splits = pd.read_parquet(scenario / "splits.private.parquet")
    phase_a = inputs["phase5a_dir"] / "expanded/exploratory"
    original = pd.read_parquet(phase_a / "context.private.parquet").sort_values(KEYS).reset_index(drop=True)
    recreated, _ = materialize_labels(original, read_json(scenario / "authorization.private.json"))
    assert_parquet_equivalent(labels, recreated)
    original_features = pd.read_parquet(phase_a / "predictors_retrospective.private.parquet").sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(features, original_features[KEYS + BASE])
    if digest_path(phase_a / "predictors_retrospective.private.parquet") != metadata["feature_matrix_sha256"]:
        raise ValueError("Matriz de origen alterada")
    policies = read_json(inputs["phase5b_dir"] / "expanded/exploratory/column_policies.private.json")
    frame, partitions = validate_design(labels, features, splits, policies)
    reference_review = read_json(scenario / "review.private.json")
    if reference_review["training_authorized"] is not False or reference_review["coverage_verified"] is not False:
        raise ValueError("Condición oficial/cobertura alterada")
    inherited = next(plan for plan in reference_review["partitions"] if plan["name"] == PLAN)
    for part, counts in partitions.items():
        for ours, theirs in (("used", None), ("positive", "positive"), ("negative", "negative"),
                            ("unknown_excluded", "unknown"), ("target_weeks", "target_weeks")):
            expected = (inherited["partitions"][part]["positive"] + inherited["partitions"][part]["negative"]
                        if theirs is None else inherited["partitions"][part][theirs])
            if counts[ours] != expected:
                raise ValueError("Distribuciones no concilian con escenario preservado")
    require_preserved(before, protected_files(root, inputs, registry))
    # Todos los controles fundamentales preceden a fit y a la creación del destino.
    models = fit_models(frame)
    predictions, metrics, calibration, temporal = evaluate_models(frame, models)
    all_x = frame.loc[frame.partition.isin(PERIODS), BASE]
    train = frame[frame.partition.eq("train") & frame.objetivo_semana_siguiente.notna()]
    replay = {}
    for name, model in models.items():
        repeated = clone(model).fit(train[BASE], train.objetivo_semana_siguiente.astype(int))
        equal = np.array_equal(model.predict_proba(all_x), repeated.predict_proba(all_x))
        if not equal:
            raise ValueError("El reentrenamiento determinista no reproduce probabilidades")
        replay[name] = {"same_seed_refit_bitwise_equal": equal}
    forest = models["random_forest_A"]
    importance = pd.DataFrame({"feature": BASE, "importance_mdi": forest.feature_importances_,
        "tree_std_descriptive": np.std([tree.feature_importances_ for tree in forest.estimators_], axis=0)}
        ).sort_values("importance_mdi", ascending=False).reset_index(drop=True)
    ranges = range_diagnostics(frame)
    require_preserved(before, protected_files(root, inputs, registry))
    output.mkdir(parents=True, exist_ok=False)
    write_report(options, output / "configuration.private.json")
    write_report(options["research_authorization"], output / "research_authorization.private.json")
    for name, model in models.items():
        path = output / f"{name}.research.private.joblib"
        joblib.dump(model, path, compress=3)
        replay[name]["saved_model_reload_bitwise_equal"] = bool(np.array_equal(
            model.predict_proba(all_x), joblib.load(path).predict_proba(all_x)))
        if not replay[name]["saved_model_reload_bitwise_equal"]:
            raise ValueError("El modelo serializado no reproduce las predicciones")
    train_keys = train[KEYS]
    train_keys.to_parquet(output / "training_keys.private.parquet", index=False)
    for name, data in {"predictions_radio_week": predictions, "calibration": calibration,
                       "temporal_diagnostics": temporal, "feature_importance": importance,
                       "feature_ranges": ranges}.items():
        write_frame(data, output / f"{name}.private.parquet")
        if name != "predictions_radio_week":
            data.to_csv(output / f"{name}.private.csv", index=False)
    # Proyección agregada por semana: sin identificadores individuales o coordenadas.
    aggregates = temporal.drop(columns=["confusion_matrix_true_rows_predicted_columns_0_1"])
    aggregates.to_csv(output / "predictions_aggregated.private.csv", index=False)
    scope = frame[frame.en_intervalo_autorizado.eq(True)]
    purged = scope[~scope.partition.isin(PERIODS)]
    report = {"version": VERSION, "training_performed": True, "research_training_authorized": True,
        "training_authorized": False, "production_training_enabled": False, "coverage_verified": False,
        "epidemiological_validation": False, "partitions": partitions, "metrics": metrics,
        "threshold": THRESHOLD, "threshold_selected_on_validation_or_test": False, "calibrator_fitted": False,
        "features": BASE, "parameters": RF_PARAMETERS, "baseline": "training_prevalence_frozen",
        "purged_rows": len(purged), "purged_target_weeks": sorted(map(str, purged.fecha_inicio_semana_objetivo.unique())),
        "reproducibility": replay, "fundamental_integrity_checks_passed": True,
        "computational_future_predictors_found": False, "historical_census_availability_verified": False,
        "label_availability_maturation_verified": False, "previous_artifacts_preserved": True,
        "negative_kind": ZERO_KIND, "acknowledged_limits": ACKNOWLEDGED_LIMITS,
        "sample_unit": "radio_censal_origin_week_target_t_plus_1_presence",
        "prediction_is_case_count": False, "date_policy": "expanded", "scenario_manifest_sha256":
            digest_path(scenario / "integrity_manifest.private.json")}
    write_report(report, output / "review.private.json")
    write_report(metrics, output / "metrics.private.json")
    (output / "report.private.md").write_text(report_markdown(report, importance, temporal), encoding="utf-8")
    versions = {name: importlib.metadata.version(name) for name in (
        "scikit-learn", "pandas", "numpy", "scipy", "joblib", "threadpoolctl", "geopandas", "shapely", "pyproj", "pyarrow")}
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--local"],
                            capture_output=True, text=True, check=True).stdout
    (output / "environment.private.txt").write_text(freeze, encoding="utf-8")
    source_dir = Path(__file__).parent.parent
    code_paths = sorted(source_dir.rglob("*.py"))
    for path in code_paths:
        destination = output / "implementation" / path.relative_to(source_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    write_report({"version": VERSION, "runtime": versions, "python": platform.python_version(),
        "platform": platform.platform(), "executable": sys.executable, "calendar_version": metadata["calendar_version"],
        "unit": report["sample_unit"], "data_kind": "provisional_positives_assumed_experimental_negatives",
        "date_policy": "expanded", "source_provenance": metadata["source_provenance"],
        "implementation_sha256": {str(path.relative_to(root)): digest_path(path) for path in code_paths},
        "training_rows_order": "sorted radio_censal, fecha_inicio_semana", "seed": 20261016,
        "prediction_probability_semantics": "agreement with experimental label, not verified infection probability",
        "training_authorized": False, "research_training_authorized": True,
        "official_and_scientific_gates": {"unchanged": True, "research_exception": ACKNOWLEDGED_LIMITS}},
        output / "metadata.private.json")
    require_preserved(before, protected_files(root, inputs, registry))
    write_report({"version": VERSION, "previous_artifacts_preserved": True,
        "protected_files_sha256": before, "frozen_scenario_protected_files_verified": len(frozen),
        "outputs_sha256": {path.relative_to(output).as_posix(): digest_path(path)
                           for path in sorted(output.rglob("*")) if path.is_file()}},
        output / "integrity_manifest.private.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[5]
        result = run_research(root, read_json(args.config))
        print(json.dumps({key: result[key] for key in ("version", "training_performed", "training_authorized",
            "research_training_authorized", "partitions", "metrics", "reproducibility")}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "Experimento detenido; revisar integridad/autorización privadas sin volcar registros.\n")


if __name__ == "__main__":
    main()
