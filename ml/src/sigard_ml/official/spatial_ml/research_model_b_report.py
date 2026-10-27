"""Informe agregado privado de 5F, sin recursos de red ni datos individuales."""

from html import escape

import numpy as np
import pandas as pd

from sigard_ml.official.spatial_ml.research_model_b import MODELS


def number(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "no definida"
    if isinstance(value, (float, np.floating)):
        return f"{value:.4f}"
    return str(value)


def table(rows, columns):
    header = "".join(f"<th>{escape(label)}</th>" for _, label in columns)
    body = "".join("<tr>" + "".join(f"<td>{escape(number(row.get(key)))}</td>" for key, _ in columns) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"


def write_reports(output, review, tables):
    metrics, weekly, importance = tables["metrics"], tables["weekly_metrics"], tables["feature_importance"]
    test = {row["model"]: row for row in metrics if row["partition"] == "test"}
    a, b, base = (test[name] for name in MODELS)
    changes = {key: b[key] - a[key] for key in ("precision", "recall", "f1", "average_precision_pr_auc", "roc_auc", "brier")}
    improved = changes["average_precision_pr_auc"] > 0 and changes["brier"] < 0
    conclusion = ("B aporta evidencia exploratoria de mejora frente a A en Average Precision y Brier de prueba."
                  if improved else "B no aporta una mejora conjunta en Average Precision y Brier de prueba frente a A.")
    conclusion += " La conclusión es descriptiva y debe ponderarse junto con recall, errores semanales y el baseline; no constituye validación independiente ni epidemiológica."
    lag_mdi = sum(row["importance_mdi"] for row in importance if row["group"] == "lag_presence")
    missing_mdi = sum(row["importance_mdi"] for row in importance if row["group"] == "explicit_missingness")
    permutation = pd.DataFrame(tables["history_value_sensitivity"])
    sensitivity = permutation.groupby("partition", sort=False)[["n", "eligible_rows", "changed_history_rows", "mean_absolute_probability_change", "ap_drop", "brier_increase", "roc_auc_drop"]].mean().reset_index().to_dict("records")
    weekly_roc = []
    for model in MODELS:
        group = [row for row in weekly if row["partition"] == "test" and row["model"] == model]
        pairs = sum(row["positive"] * row["negative"] for row in group)
        within = sum(row["roc_auc"] * row["positive"] * row["negative"] for row in group) / pairs
        weekly_roc.append({"model": model, "pooled_roc": test[model]["roc_auc"], "same_week_pair_weighted_roc": within,
            "same_week_pairs": pairs, "same_week_pair_fraction": pairs / (a["positive"] * a["negative"])})
    peak_a = max((row for row in weekly if row["model"] == "random_forest_A"), key=lambda row: row["positive"])
    peak_b = next(row for row in weekly if row["model"] == "random_forest_B" and row["target_week"] == peak_a["target_week"])
    test_weeks = []
    for week in sorted({row["target_week"] for row in weekly if row["partition"] == "test"}):
        ar, br = (next(row for row in weekly if row["target_week"] == week and row["model"] == model) for model in MODELS[:2])
        test_weeks.append(f"{week}: {ar['positive']} positivos/{ar['negative']} negativos; probabilidad media A={ar['mean_probability']:.4f}, B={br['mean_probability']:.4f}; "
            f"F1 A={ar['f1']:.4f}, B={br['f1']:.4f}; ROC dentro de semana A={ar['roc_auc']:.4f}, B={br['roc_auc']:.4f}.")
    limitations = [
        "Prueba ya examinada en fases anteriores: comparación exploratoria. No se eligieron umbrales, hiperparámetros ni calibradores con ella. Umbral 0,5 congelado antes del ajuste.",
        "Sólo 8 semanas de entrenamiento, 8 de validación y 4 de prueba; radio-semanas conocidas de prueba no equivalen a eventos temporalmente independientes. Los radios vecinos y las semanas repetidas están correlacionados. No se calculan p-valores ni intervalos basados en filas independientes.",
        "Prevalencia 7,19% → 67,35% → 11,03%. El cambio entre períodos modifica Precision/AP y la calibración. ROC global incluye pares entre semanas y puede reflejar descenso temporal además de discriminación espacial; se informa ROC por semana.",
        "Positivos provisionales y negativos cero_asumido_experimental: ausencia de registro no es ausencia verificada de dengue. Cobertura epidemiológica no acreditada. Los desconocidos se excluyen como etiquetas, conservando las filas con historia faltante.",
        "Rezago k = presencia binaria del radio en t−k, origen t y objetivo t+1; no cuenta pacientes. Historia desde 07/01/2024, sin inventar semanas anteriores. Semanas purgadas excluidas del ajuste pueden aportar historia estrictamente pasada.",
        "Reconstrucción retrospectiva de origen móvil: una semana de prueba ya pasada puede alimentar un origen posterior. No es un pronóstico multisemanal emitido en un único origen ni acredita disponibilidad en tiempo real.",
        "No se acreditaron fechas de llegada y maduración de registros, inicio de síntomas frente a muestra/registro, ni disponibilidad histórica del Censo 2022. Persisten incertidumbres en fecha, ubicación y clasificación. Los flags aproximados de 2024 no documentan por sí solos exactitud ni ausencia de retrasos.",
        "MDI favorece variables con más cortes y reparte información entre predictores redundantes (superficie, población, densidad, vecinos; y rezagos correlacionados). No mide causalidad ni prueba utilidad operativa. balanced_subsample y cambio de prevalencia tampoco garantizan probabilidades calibradas.",
    ]
    missing_text = (f"MDI: rezagos={lag_mdi:.4f}, indicadores explícitos de faltantes={missing_mdi:.4f}. "
        "Los árboles también detectan NaN dentro de los propios rezagos: MDI baja de los indicadores no descarta aprendizaje del patrón de faltantes. "
        "Las tablas por cantidad/patrón de historia conocida muestran su asociación con etiquetas, semanas y scores. "
        "La permutación conjunta de los rezagos entre radios con la misma semana y máscara NA conserva indicadores y contexto. "
        "La pérdida de AP o aumento de Brier sólo describe sensibilidad a valores observados; cinco repeticiones no son intervalos de confianza, "
        "y este diagnóstico no identifica qué fracción causal de la mejora procede de faltantes. No se ajustó un modelo adicional ni se seleccionaron variables.")
    recommendations = [
        "Prioridad 1 — datos: verificar cobertura, clasificación positiva, fechas de inicio/muestra/registro y disponibilidad/versiones en cada origen; acreditar Censo y georreferenciación. Mantener estados desconocido/asumido/verificado separados.",
        "Prioridad 2 — evaluación independiente: congelar B, features, umbral y protocolo antes de obtener otra temporada o período prospectivo no examinado; evaluar origen móvil con snapshots reales y retrasos, más semanas y métricas espaciales dentro de semana. Analizar bloques temporales/espaciales respetando dependencia.",
        "Prioridad 3 — con el dataset actual: validación temporal interna sólo sobre entrenamiento para decisiones futuras, estratificación por disponibilidad y comparación con baselines de persistencia estrictamente pasados, bajo una autorización posterior. La prueba actual no puede volver a ser independiente.",
        "Prioridad 4 — ingeniería/calibración futura: estudiar ventanas y redundancia sólo con datos admitidos y análisis de entrenamiento; reservar bloque cronológico interno suficiente para calibración. No ajustar calibración ni elegir hiperparámetros a partir de esta prueba.",
    ]
    paragraphs = [
        "Entrenamiento completado exclusivamente como investigación retrospectiva autorizada. A y baseline conservan sus artefactos y predicciones. training_authorized=false; ningún modelo operativo activado. Informe privado generado automáticamente, pendiente de revisión humana.",
        "B utiliza las siete variables de A más cuatro presencias experimentales y cuatro flags _missing (1=sin dato, equivalente al complemento de disponibilidad). Se reutiliza la matriz de 5E; no hay imputación, selección de casos completos, escalado, búsqueda ni calibración.",
        "RF: 400 árboles, profundidad 10, min_samples_leaf=5, min_samples_split=10 heredado, max_features=sqrt, balanced_subsample, semilla 20261016 y n_jobs=1. La instalación scikit-learn " + review["native_nan_capability"]["scikit_learn_version"] + " declara soporte nativo de NaN, comprobado antes del ajuste; no se modificaron dependencias.",
        conclusion,
        f"En prueba, cambio B−A: Precision {changes['precision']:+.4f}, Recall {changes['recall']:+.4f}, F1 {changes['f1']:+.4f}, AP {changes['average_precision_pr_auc']:+.4f}, ROC {changes['roc_auc']:+.4f}, Brier {changes['brier']:+.4f}. Brier del baseline={base['brier']:.4f} frente a B={b['brier']:.4f}.",
        f"Pico de positivos por radio-semana {peak_a['target_week']}: {peak_a['positive']}/{peak_a['n']}, probabilidad media A={peak_a['mean_probability']:.4f}, B={peak_b['mean_probability']:.4f}; recall A={peak_a['recall']:.4f}, B={peak_b['recall']:.4f}. No se confunde este pico de presencia en radios con cantidad de pacientes.",
        missing_text,
        f"Reproducibilidad: dos ajustes de B con idénticos datos, orden y semilla reprodujeron bit a bit las {review['reproducibility']['all_grid_predictions_compared']} probabilidades de la grilla; recarga joblib idéntica. Verificación de {review['integrity']['lag_cells_checked']} celdas de rezagos y {len(tables['metric_consistency_checks'])} identidades/contrastes de métricas. Se preservaron hashes de {review['protected_files_preserved']} artefactos/fuentes y {review['preexisting_workspace_files_preserved']} archivos de trabajo. JUnit y verificación de entrega se conservan en el directorio privado interim homónimo.",
        "Archivos: dos módulos nuevos de ejecución/informe, pruebas y documentación; este directorio contiene configuración/autorización explícita, B serializado, matriz de inferencia, claves de ajuste, predicciones por radio-semana agregadas sin datos de personas, tablas de métricas/calibración/MDI/sensibilidad, versiones, copia de código, estado Git y manifiesto SHA-256. No se sobrescribieron A, 5E, fuentes ni modelos anteriores.",
        "Git: rama entrenamiento-ML, cambios previos preservados; nuevos módulos/pruebas/documentación sin staging. Artefactos privados excluidos. Sin commit ni push. Los desgloses exactos están en git_state.private.json. No se modificaron frontend ni backend durante esta fase.",
    ]
    sections = [("Resumen", paragraphs[:6]), ("Historia y faltantes", [paragraphs[6]]),
        ("Limitaciones y validez", limitations), ("Pasos posteriores", recommendations),
        ("Pruebas y entrega", paragraphs[7:]),
        ("Referencias y asistencia", ["RandomForestClassifier: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html",
            "Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065. Skills utilizadas como ayuda de procedimiento; no sustituyen revisión científica humana."])]
    html = ["<!doctype html><html lang='es'><meta charset='utf-8'><title>SIGARD Fase 5F — privado</title>",
        "<style>body{font:16px system-ui;max-width:1280px;margin:40px auto;padding:0 24px;color:#172b3a;line-height:1.5}h1,h2{color:#174c5c}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border:1px solid #ccd6dc;text-align:right}th{background:#edf4f6}p{max-width:1050px}.scroll{overflow-x:auto;margin-bottom:24px}</style>",
        "<h1>SIGARD · Fase 5F · Modelo B</h1><p>Privado · reconstrucción retrospectiva experimental · revisión humana pendiente</p>"]
    for heading, items in sections:
        html.append("<h2>" + escape(heading) + "</h2>" + "".join("<p>" + escape(item) + "</p>" for item in items))
    html.append("<h2>Observaciones utilizadas y excluidas</h2>" + table([{"partition": name, **value} for name, value in review["partitions"].items()],
        [("partition", "Partición"), ("used", "Etiquetadas"), ("positive", "Positivas"), ("negative", "Negativas asumidas"), ("unknown_excluded", "Desconocidas excluidas"), ("prevalence", "Prevalencia"), ("target_weeks", "Semanas")]))
    cols = [("partition", "Partición"), ("model", "Modelo"), ("precision", "Precision"), ("recall", "Recall"), ("f1", "F1"),
        ("average_precision_pr_auc", "Average Precision"), ("pr_auc_trapezoidal", "PR-AUC trap."), ("roc_auc", "ROC-AUC global"), ("brier", "Brier"), ("mean_probability", "Prob. media etiquetas conocidas"), ("confusion_matrix_true_rows_predicted_columns_0_1", "Matriz [[TN,FP],[FN,TP]]")]
    html.append("<h2>Comparación sobre las mismas filas</h2><p>Umbral 0,5. AP es el resumen principal de precisión-recall; el área trapezoidal se distingue explícitamente. Precision del baseline sin predicciones positivas: no definida.</p>" + table(metrics, cols))
    weeklycols = [("target_week", "Semana objetivo"), ("model", "Modelo"), ("positive", "Positivos"), ("negative", "Negativos"), ("unknown_excluded", "Desconocidos"), ("prevalence", "Prevalencia"), ("mean_probability", "Prob. media conocidas"), ("mean_probability_all_radios", "Prob. media 263 radios"), ("tp", "TP"), ("fp", "FP"), ("tn", "TN"), ("fn", "FN"), ("precision", "Precision"), ("recall", "Recall"), ("f1", "F1"), ("average_precision_pr_auc", "AP"), ("roc_auc", "ROC semanal"), ("brier", "Brier")]
    html.append("<h2>Cuatro semanas de prueba</h2>" + "".join("<p>" + escape(item) + "</p>" for item in test_weeks) + table([row for row in weekly if row["partition"] == "test"], weeklycols))
    html.append("<h2>ROC global frente a dentro de semana</h2>" + table(weekly_roc, [("model", "Modelo"), ("pooled_roc", "ROC global"), ("same_week_pair_weighted_roc", "ROC ponderada por pares dentro de semana"), ("same_week_pair_fraction", "Fracción de pares de misma semana")]))
    html.append("<h2>Importancias MDI de B</h2>" + table(sorted(importance, key=lambda row: -row["importance_mdi"]), [("feature", "Variable"), ("group", "Grupo"), ("importance_mdi", "MDI")]))
    html.append("<h2>Sensibilidad a valores, conservando patrón NA y semana</h2>" + table(sensitivity, [(key, key) for key in sensitivity[0]]))
    groups = [row for row in tables["missingness_groups"] if row["group_kind"] == "known_lags" and row["model"] == "random_forest_B"]
    html.append("<h2>Historia conocida y composición</h2>" + table(groups, [("partition", "Partición"), ("group_value", "Rezagos conocidos"), ("n", "Filas"), ("distinct_target_weeks", "Semanas"), ("prevalence", "Prevalencia"), ("mean_probability", "Prob. B"), ("average_precision_pr_auc", "AP B"), ("brier", "Brier B")]))
    html.append("<h2>Calibración descriptiva, diez bins uniformes</h2>" + table(tables["calibration"], [("model", "Modelo"), ("partition", "Partición"), ("bin", "Bin"), ("n", "N"), ("mean_probability", "Probabilidad media"), ("fraction_positive", "Fracción positiva")]))
    html.append("<h2>Serie semanal completa</h2>" + table(weekly, weeklycols) + "</html>")
    (output / "report.private.html").write_text("\n".join(html), encoding="utf-8")
    markdown = ["# SIGARD Fase 5F — informe privado", ""]
    for heading, items in sections:
        markdown += ["## " + heading, "", *[item + "\n" for item in items]]
    markdown += ["## Descenso en prueba", "", *[item + "\n" for item in test_weeks],
        "Tablas comparativas completas en report.private.html y archivos metrics/weekly_metrics/calibration/feature_importance.private.csv; sin datos de pacientes.", ""]
    (output / "report.private.md").write_text("\n".join(markdown), encoding="utf-8")
