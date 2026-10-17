"""Informe científico privado desde agregados auditados; revisión humana pendiente."""

from html import escape
import hashlib
import json

import pandas as pd

PARTS = ("train", "validation", "test")
RF, BASELINE = "random_forest_A", "training_prevalence"
NAMES = {"train": "Entrenamiento", "validation": "Validación", "test": "Prueba"}


def number(value, digits=4):
    return "no definida" if value is None else f"{value:.{digits}f}"


def recommendations():
    return [
        {"priority": "P0", "category": "datos_adicionales", "recommendation": "Documentar cobertura por semana/radio, definición histórica de positivo, elegibilidad, residencia, episodios y criterio de exclusión antes de interpretar resultados epidemiológicos.",
         "requires": "Evidencia de vigilancia/extracción y revisión responsable; no cambiar retrospectivamente el escenario congelado.", "status": "proposed_not_executed"},
        {"priority": "P0", "category": "datos_adicionales", "recommendation": "Acreditar fechas de disponibilidad y revisión de registros, maduración del objetivo y publicación de población/límites censales; incorporar más temporadas sólo después de su autorización.",
         "requires": "Metadatos punto en el tiempo, versiones y fuentes revisadas; no usar fuentes pendientes ahora.", "status": "proposed_not_executed"},
        {"priority": "P1", "category": "dataset_actual", "recommendation": "Congelar un protocolo posterior, mantener resultados 5C/5D como exploratorios y auditar cobertura de etiquetas, cohortes fijas y calidad por origen con el dataset actual.",
         "requires": "Ningún dato nuevo para auditorías descriptivas; no prometer validación externa con estas cuatro semanas.", "status": "descriptive_audits_done_no_model_changes"},
        {"priority": "P1", "category": "evaluacion_seleccion_temporal", "recommendation": "Predefinir evaluación de origen móvil con purga t+1, selección interna cronológica y un bloque futuro todavía no examinado; comparar con baselines temporales de disponibilidad acreditada.",
         "requires": "Autorización posterior para ajustar; suficiente historia madura de ambas clases. El test actual ya fue examinado y no debe reciclarse como validación final intacta.", "status": "proposed_not_executed"},
        {"priority": "P1", "category": "calibracion", "recommendation": "Comparar probabilidades crudas con calibración sigmoide sencilla sólo sobre predicciones de bloques internos posteriores al ajuste y anteriores al test futuro; evaluar Brier, log loss, curvas y tamaños por bin.",
         "requires": "Etiquetas maduras, ambas clases y suficientes semanas. No ajustar un calibrador aquí ni usar prueba. La calibración no resuelve cobertura o positivos provisionales.", "status": "proposed_not_executed"},
        {"priority": "P1", "category": "ingenieria_caracteristicas", "recommendation": "Priorizar señales recientes de actividad y demoras verificadas (rezagos/ventanas locales y vecinales) si puede acreditarse su disponibilidad; preservar NaN cuando falten semanas.",
         "requires": "Historia observada suficiente y fechas de disponibilidad; los ceros asumidos no se convierten en conteos históricos. No basta con que exista una columna retrospectiva.", "status": "proposed_not_executed"},
        {"priority": "P2", "category": "dataset_actual", "recommendation": "En un estudio futuro autorizado, contrastar familias de contexto estructural y estacional por ablaciones predefinidas e importancia agrupada, sin eliminar variables por MDI de este ensayo.",
         "requires": "Evaluación interna cronológica; población/densidad/superficie no aportan tres fuentes independientes de información.", "status": "proposed_not_executed"},
        {"priority": "P2", "category": "calibracion", "recommendation": "Investigar el efecto del balanceo de clases y de la prevalencia cambiante mediante comparaciones planificadas en entrenamiento/validación interna; no atribuirle causalmente la sobreestimación actual.",
         "requires": "Fase posterior con autorización y protocolo. No elegir nuevos hiperparámetros ni aplicar correcciones de prior desde los resultados de prueba.", "status": "proposed_not_executed"},
        {"priority": "P2", "category": "evaluacion_seleccion_temporal", "recommendation": "Añadir sensibilidad por bloques espaciales para una pregunta explícita de generalización territorial y cuantificar incertidumbre por temporadas/bloques cuando haya soporte independiente suficiente.",
         "requires": "Más semanas/temporadas y estructura de dependencia defendible. No bootstrap IID de 861 filas ni intervalos supuestamente robustos con cuatro semanas.", "status": "proposed_not_executed"},
    ]


def write_diagnostic_report(output, data, checks, protected_count, git_state):
    summary, weekly = data["summary"], data["weekly"]
    def metric(model, part):
        return next(r for r in summary if r["model"] == model and r["partition"] == part)
    test = metric(RF, "test")
    baseline = metric(BASELINE, "test")
    test_weeks = sorted([r for r in weekly if r["model"] == RF and r["partition"] == "test"], key=lambda r: r["target_week"])
    peak = max((r for r in weekly if r["model"] == RF), key=lambda r: r["positive"])
    first, last = test_weeks[0], test_weeks[-1]
    roc_split = next(r for r in data["roc_decomposition"] if r["model"] == RF)
    first_transition = data["stability"]["successive_week_correlations"][0]
    matched = sorted([r for r in data["matched"] if r["model"] == RF], key=lambda r: r["target_week"])
    recs = recommendations()
    lines = ["# SIGARD Fase 5D — diagnóstico científico privado del RF espacial A", "",
        "Borrador técnico para revisión del usuario. Análisis descriptivo post hoc; sin aprobación epidemiológica ni preparación para publicación.",
        "No se entrenaron modelos, no se cargaron archivos joblib, no se ajustó un calibrador y no se cambiaron hiperparámetros, umbrales, etiquetas o cobertura.",
        "Unidad: radio censal–semana de origen; objetivo de presencia de un registro elegible provisional en la semana exacta t+1. No es un conteo de casos ni una probabilidad de infección acreditada.", "",
        "## 1. Pregunta, procedencia y método", "",
        "Se analiza exclusivamente el escenario congelado de Fase 5C, con positivos provisionales y negativos cero_asumido_experimental. Fuentes listas preservadas; no se incorporaron archivos en revisión. [E1,E2]",
        "Entradas principales: predictions_radio_week, metrics, temporal_diagnostics, calibration, feature_importance, configuración y manifiesto de spatial_rf_05c_v1. La matriz A y sus etiquetas se consultan desde el escenario congelado referenciado por esa configuración. [E1,E2]",
        "Se verificaron hashes antes/después, grilla, clases, particiones, t+1, umbral 0,5 y baseline igual a prevalencia de entrenamiento. Precision/recall/F1 y Brier se recalcularon por fórmulas; ROC-AUC por rangos medios y AP por acumulación respetando empates; se contrastaron con scikit-learn y los productos guardados. [E3]",
        f"Pasaron {checks} comprobaciones de consistencia matemática. Los conteos de confusión y los errores Brier/log loss agregados concilian con las semanas; AUC y F1 agrupados no se sustituyen por promedios semanales. [E3]",
        "AP es la medida PR primaria sin interpolación. El área trapezoidal secundaria conservada puede resultar artificialmente alta para scores constantes; no se usa como evidencia de habilidad del baseline. [R1]",
        "Precision sin predicciones positivas se declara no definida; Fase 5C guardó cero por convención explícita. Se verificó esa convención sin alterar los valores originales. [E3]", "",
        "## 2. Rendimiento y comparación con baseline", ""]
    for part in PARTS:
        r, b = metric(RF, part), metric(BASELINE, part)
        lines += [f"### {NAMES[part]}", "",
            f"{r['n']} etiquetas conocidas de {r['grid_rows']} celdas; {r['positive']} positivas, {r['negative']} negativas asumidas y {r['unknown_excluded']} desconocidas excluidas. Prevalencia {r['prevalence']:.2%}; cobertura de etiqueta {r['known_label_coverage']:.2%}. [E3]",
            f"RF: precision {number(r['precision'])}, recall {number(r['recall'])}, F1 {number(r['f1'])}, AP {number(r['average_precision_pr_auc'])}, ROC-AUC {number(r['roc_auc'])}, Brier {number(r['brier'])}, log loss {number(r['log_loss'])}. [E3]",
            f"Baseline: precision no definida (cero convencional en 5C), recall {number(b['recall'])}, F1 {number(b['f1'])}, AP {number(b['average_precision_pr_auc'])}, ROC-AUC {number(b['roc_auc'])}, Brier {number(b['brier'])}, log loss {number(b['log_loss'])}. No predice positivos a 0,5. [E3]",
            f"Matriz RF [[TN,FP],[FN,TP]]: {r['confusion_matrix_true_rows_predicted_columns_0_1']}; baseline: {b['confusion_matrix_true_rows_predicted_columns_0_1']}. [E3]", ""]
    lines += [f"En prueba, el RF mejora AP ({test['average_precision_pr_auc']:.4f} frente a {baseline['average_precision_pr_auc']:.4f}) y ROC-AUC, pero empeora Brier ({test['brier']:.4f} frente a {baseline['brier']:.4f}) y log loss. Hay discriminación descriptiva relativa al baseline constante, sin superioridad uniforme en calidad probabilística. [E3]",
        f"El AUC agrupado {roc_split['pooled_auc_reconstructed']:.4f} se descompone exactamente por pares positivo–negativo: AUC dentro de la misma semana {roc_split['within_week_auc_weighted_by_pairs']:.4f} ({roc_split['within_week_pair_fraction']:.2%} de pares) y entre semanas {roc_split['between_weeks_auc_weighted_by_pairs']:.4f} ({roc_split['between_weeks_pair_fraction']:.2%}). El AUC agrupado mezcla ordenamiento entre radios contemporáneos y contraste temporal entre semanas; no equivale a discriminación espacial de cada semana. No se asumen pares independientes. [E4]",
        "El rendimiento de entrenamiento es de resustitución y resulta optimista para generalización. Un baseline de prevalencia fija no modela el brote ni equivale a comparar contra un baseline temporal dinámico fuerte. [E3,R2]", "",
        "![Curvas ROC y precision–recall por partición](figures/06_ranking_curves.png)", "",
        "## 3. Cuatro semanas de prueba: errores y descenso", ""]
    for r in test_weeks:
        b = next(q for q in weekly if q["model"] == BASELINE and q["target_week"] == r["target_week"])
        lines += [f"### Objetivo {r['target_week']} a {r['target_end']}", "",
            f"{r['n']} conocidas: {r['positive']} positivas provisionales y {r['negative']} negativas experimentales; {r['unknown_excluded']} desconocidas excluidas. Prevalencia {r['prevalence']:.2%}. [E3]",
            f"Probabilidad RF media {r['mean_probability']:.2%} sobre conocidas y {r['mean_probability_all_radios']:.2%} sobre los 263 radios; baseline {b['mean_probability']:.2%}. [E3]",
            f"TP={r['tp']}, FP={r['fp']}, TN={r['tn']}, FN={r['fn']}. Precision {number(r['precision'])}, recall {number(r['recall'])}, F1 {number(r['f1'])}, AP {number(r['average_precision_pr_auc'])}, ROC-AUC {number(r['roc_auc'])}, Brier {number(r['brier'])}; baseline Brier {number(b['brier'])}. [E3]", ""]
    lines += [f"La prevalencia conocida cae {(first['prevalence'] - last['prevalence']) * 100:.2f} puntos porcentuales, de {first['prevalence']:.2%} a {last['prevalence']:.2%}; la probabilidad RF media conocida cae {(first['mean_probability'] - last['mean_probability']) * 100:.2f} puntos, de {first['mean_probability']:.2%} a {last['mean_probability']:.2%}. Mantiene probabilidades elevadas al disminuir la presencia registrada. [E3]",
        f"Sensibilidad descriptiva con los mismos {data['stability']['matched_known_radios']} radios conocidos en las cuatro semanas: prevalencia {matched[0]['prevalence']:.2%} a {matched[-1]['prevalence']:.2%}, probabilidad media {matched[0]['mean_probability']:.2%} a {matched[-1]['mean_probability']:.2%}. Esto reduce cambios de composición por desconocidos, sin resolver el sesgo de seleccionar una cohorte completa. [E4]",
        f"Entre {first_transition['first_week']} y {first_transition['second_week']}, {first_transition['radios_with_exactly_unchanged_probability']} de 263 radios mantienen exactamente su score; cambio absoluto máximo {first_transition['maximum_absolute_probability_change']:.3g}. La pequeña diferencia entre medias de etiquetas conocidas en esas semanas proviene de su composición, porque los scores individuales guardados son iguales. [E4]",
        "Las probabilidades de toda la grilla y de la cohorte fija se conservan separadas. La suma de probabilidades refiere a radios con etiqueta positiva esperada, nunca a cantidad de pacientes/casos. [E3,E4]", "",
        "![Errores semanales del RF en prueba](figures/03_test_weekly_errors.png)", "",
        "## 4. Calibración de probabilidades", ""]
    for part in PARTS:
        r = metric(RF, part)
        lines += [f"- {NAMES[part]}: media RF {r['mean_probability']:.2%}, prevalencia {r['prevalence']:.2%}, sesgo medio {(r['mean_probability'] - r['prevalence']) * 100:+.2f} puntos, ECE de diez bins {r['ece_10_uniform_bins_descriptive']:.4f}. [E3]",
            f"- Componentes del Brier en {NAMES[part].lower()}: negativos {r['brier_negative_contribution']:.6f}, positivos {r['brier_positive_contribution']:.6f}; suman {r['brier']:.6f}. Son contribuciones por etiqueta, no descomposición de Murphy de calibración/resolución. [E3]"]
    lines += ["", "La curva de confiabilidad usa los diez bins uniformes fijos heredados. Se muestran tamaños y frecuencias; no se ajusta calibrador, pendiente o intercepto. ECE depende del binning y del tamaño de cada bin: no es una prueba formal. [E3,R2]",
        "Brier combina calibración, discriminación y prevalencia; no mide calibración aislada. El sesgo medio y las curvas aportan evidencia descriptiva adicional de subestimación en validación y sobreestimación en prueba. No se interpreta probabilidad de etiqueta experimental como riesgo de infección. [E3,R2]",
        "El balanceo de clases puede contribuir a que scores crudos no correspondan a la prevalencia poblacional, pero este ensayo no aísla su efecto frente a cambio temporal, faltantes selectivos u otras causas; no se atribuye causalidad. [I1]", "",
        "![Confiabilidad e histogramas de probabilidad](figures/02_calibration.png)", "",
        "## 5. Cambio temporal y distribución de características", "",
        "Las fechas son de la semana objetivo: entrenamiento 07/01–02/03 (8 semanas), validación 10/03–04/05 (8), prueba 12/05–08/06 (4). Origen inicial 31/12/2023; objetivos purgados 03/03 y 05/05. [E1,E2]",
        "La prevalencia pasa de 7,19% a 67,35% y después 11,03%; la cobertura de etiquetas conocidas pasa de 81,27% a 96,96% y 81,84%. Se analizan distribuciones de todos los radios y del subconjunto conocido por separado. [E3,E5]",
        f"El pico de radios con etiqueta positiva entre semanas evaluadas se ubica el {peak['target_week']}: {peak['positive']}/{peak['n']} ({peak['prevalence']:.2%}); media RF {peak['mean_probability']:.2%}. No equivale al pico clínico de casos. [E3]",
        "Los tres predictores estacionales de validación están fuera del rango de entrenamiento conocido. En prueba, semana y coseno están fuera en todas las filas; el seno sólo parcialmente. Un árbol particiona el soporte observado y no aprende por sí mismo la trayectoria futura de un brote fuera de ese soporte. [E5,I1]",
        "Las variables estructurales son constantes por radio y, en la grilla completa de 263 radios, sus distribuciones son idénticas entre bloques. Las diferencias al filtrar etiquetas conocidas son cambios de composición de evaluación, no cambios demográficos medidos en el tiempo. Las distancias KS/Wasserstein son descriptivas sin p-valores IID. [E5]",
        "Estos resultados son compatibles con desajuste temporal, predominio de contexto estructural y ausencia de señales recientes de actividad en A. No identifican una causa única ni demuestran que agregar historia o calibrar resolverá el problema; historia incompleta o no disponible en origen puede añadir sesgo/fuga. No se reentrena para comprobarlo durante esta fase. [I1]", "",
        "![Prevalencia, probabilidades y cobertura temporal](figures/01_temporal_probability.png)", "",
        "![Soporte de las variables estacionales](figures/04_temporal_feature_support.png)", "",
        "## 6. Redundancia y límites de importancia de variables", "",
        f"Las correlaciones Pearson/Spearman se calculan sobre {data['redundancy']['unique_radios']} radios únicos, sin multiplicar el tamaño por semanas. La identidad densidad=población/superficie se verifica con error relativo máximo {data['redundancy']['density_identity_max_relative_error']:.3g}. Existe redundancia algebraica aunque una correlación lineal entre pares no sea alta. [E5]",
        "Para población y área positivas, log(densidad)=log(población)−log(superficie): no son tres mediciones informativamente independientes. Vecinos puede relacionarse con forma/tamaño de polígonos y urbanización; las correlaciones observadas no permiten declararlo redundante ni causalmente determinante por sí solas. [E5,I1]", ""]
    for row in sorted(data["importance"], key=lambda r: r["importance_mdi"], reverse=True):
        lines.append(f"- {row['feature']}: MDI {row['importance_mdi']:.2%}; dispersión entre árboles {row['tree_std_descriptive']:.4f}. [E6]")
    rho = next(r['correlation'] for r in data['correlations'] if r['method'] == 'spearman'
        and r['feature_one'] == 'superficie_km2' and r['feature_two'] == 'densidad_poblacional')
    neighbor_rho = next(r['correlation'] for r in data['correlations'] if r['method'] == 'spearman'
        and r['feature_one'] == 'cantidad_vecinos' and r['feature_two'] == 'densidad_poblacional')
    lines += ["", f"Spearman superficie–densidad es {rho:.4f}; vecinos–densidad {neighbor_rho:.4f}. La asociación inversa entre área y densidad es descriptiva y coexiste con la identidad algebraica; la asociación con vecinos es más débil y no justifica eliminarlo por redundancia sin evaluación posterior predefinida. [E5]"]
    lines += ["", "MDI distribuye disminuciones de impureza en el ajuste: no mide aporte causal, información exclusiva ni estabilidad fuera del entrenamiento. Puede favorecer variables continuas/de alta cardinalidad y repartir importancia entre predictores redundantes; sumar o comparar porcentajes no identifica determinantes epidemiológicos. La dispersión entre árboles no es un intervalo de confianza. No se eliminan variables. [E6,R3]", "",
        "![Correlaciones estructurales e importancia MDI](figures/05_redundancy_and_mdi.png)", "",
        "## 7. Validez experimental y límites epidemiológicos", "",
        "Las 861 celdas de prueba son mediciones repetidas en cuatro semanas consecutivas y sobre los mismos radios. No constituyen 861 eventos temporalmente independientes. Radios vecinos comparten contexto y posiblemente vigilancia; la dependencia temporal/espacial reduce información independiente. [E1,E3]",
        "No se calculan p-valores, intervalos binomiales IID, bootstrap por filas ni significancia para diferencias de métricas. Cuatro semanas no permiten una estimación robusta de generalización entre temporadas; tampoco prueban transferibilidad a radios nuevos. [I1]",
        "Los positivos son registros elegibles provisionales, sin convertirlos en confirmación clínica ni ubicación real de infección. Los negativos son asunciones experimentales, no ausencias verificadas. No hay cobertura epidemiológica comprobada; subregistro, etiquetas incompletas y desconocidos selectivos pueden cambiar todas las métricas. [E1,E2]",
        "La disponibilidad histórica del Censo 2022 y de sus límites, y la maduración/llegada de etiquetas, siguen sin acreditarse. La purga y el catálogo sin offsets futuros previenen ciertos errores computacionales, pero no certifican disponibilidad operativa punto en el tiempo. [E1,E2]", ""]
    for row in data["dates"]["by_partition"]:
        lines.append(f"- {NAMES[row['partition']]}: {row['positive_labels_with_approximate_date_flag']} positivos con bandera de fecha aproximada entre {row['provisional_positive_labels']}; {row['positive_labels_coexisting_with_pending']} positivos coexisten con pendientes. [E7]")
    delay = data["dates"]["earlier_source_delay_evidence"]
    lines += ["", f"La auditoría previa global 2020–2024 informa {delay['paired_symptom_sample_records']} registros con síntomas/muestra emparejados y {delay['different_epidemiological_week']} con semanas distintas; mediana no negativa {delay['nonnegative_delay_median_days']} días. Es evidencia agregada de otras fases, no una demora estimada específicamente para este test. No se traslada esa mediana a etiquetas o fechas. [E7]",
        "En este escenario no hay positivos con bandera de fecha aproximada en los bloques evaluados. Por ello no hay evidencia para atribuir el descenso del rendimiento a sustitución síntomas→muestra dentro del test; la bandera tampoco acredita que toda fecha original sea exacta. Ubicaciones, residencia y clasificación conservan su incertidumbre. [E7,I1]",
        "Las recomendaciones se desprenden de un diagnóstico exploratorio. No se interpreta un buen AUC como validación epidemiológica, ni el peor Brier como identificación de una causa única. [I1]", "",
        "## 8. Recomendaciones priorizadas para una fase posterior", ""]
    for index, row in enumerate(recs, 1):
        lines += [f"### {index}. {row['priority']} — {row['category']}", "", row["recommendation"],
                  "Requisitos: " + row["requires"], "Estado: " + row["status"], ""]
    lines += ["## 9. Pruebas, trazabilidad y archivos", "",
        f"El ejecutor verificó {checks} identidades/contrastes de métricas y hashes de {protected_count} archivos protegidos. La CLI bloquea llamadas de ajuste de RF/clasificador dummy/calibrador/regresión logística/Pipeline y carga joblib; no se necesita deserializar modelos para auditar sus probabilidades guardadas. [E3,E8]",
        "Las pruebas de esta fase usan arrays y grillas ficticias sin ajustar estimadores. Cubren AP con empates, ROC por rangos, confusión, Brier, log loss, métricas no definidas, calibración, agregación semanal, cohortes fijas, redundancia exacta, hashes y rechazo de incoherencias. El registro final de pruebas se conserva como evidencia privada adicional. [E8]",
        "Productos nuevos: informe Markdown/HTML, seis figuras PNG/SVG, tablas agregadas Parquet/CSV, payload gráfico agregado, fuentes/copias de scripts, recomendaciones, registro de evidencias, metadatos de entornos, estado de Git y manifiesto SHA-256. No se exportan pacientes, domicilios o coordenadas. Los productos de Fase 5C y los modelos previos se conservan intactos. [E8]",
        "Archivos de implementación nuevos: research_diagnostics.py, research_diagnostic_plots.py y research_diagnostic_report.py, pruebas específicas y documentación de Fase 5D. No se modifican implementaciones previas ni frontend/backend. [E8]", "",
        "## 10. Estado de Git y revisión", "",
        f"Rama {git_state['branch']}; HEAD {git_state['head']}. Se preserva el estado previo del workspace; existen cambios previos ajenos a esta fase. Nada se añade al índice y no se realiza commit/push. El estado detallado se guarda en git_state.private.json. [E8]",
        "La revisión humana de los resultados científicos queda pendiente del usuario. Este informe fue generado con asistencia de IA y validación computacional local; no tiene aprobación clínica, institucional o para publicación inferida.", "",
        "## Evidencias y referencias", "",
        "E1: manifiesto/configuración/revisión privados de Fase 5C. E2: matriz, etiquetas y particiones del escenario asumido congelado. E3: tablas de métricas y auditoría matemática nuevas. E4: cohorte fija y estabilidad de probabilidades. E5: distribuciones/correlaciones/redundancia. E6: MDI guardada. E7: banderas de fecha y comparación previa de recuperación. E8: manifiestos/estado de Git y pruebas de esta fase. I1: interpretación exploratoria, sin identificación causal; requiere revisión humana.",
        "R1: scikit-learn, average_precision_score. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html",
        "R2: scikit-learn, Probability calibration. https://scikit-learn.org/stable/modules/calibration.html",
        "R3: scikit-learn, Permutation Importance vs Random Forest Feature Importance (MDI). https://scikit-learn.org/stable/auto_examples/inspection/plot_permutation_importance.html",
        "R4: Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065",
        "Se aplicaron scikit-learn, statistical-analysis, matplotlib, scientific-critical-thinking y scientific-writing para trazabilidad del borrador. Sólo se consultaron referencias metodológicas públicas en la web; el procesamiento de datos privados fue local.", ""]
    markdown = "\n".join(lines)
    (output / "report.private.md").write_text(markdown, encoding="utf-8")
    body = []
    for line in lines:
        if not line:
            continue
        if line.startswith("!["):
            alt, url = line[2:].split("](", 1)
            body.append(f'<figure><img src="{escape(url[:-1])}" alt="{escape(alt)}"><figcaption>{escape(alt)}</figcaption></figure>')
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            body.append(f"<h{level}>{escape(line[level:].strip())}</h{level}>")
        else:
            body.append("<p>" + escape(line) + "</p>")
    body += ["<h2>Tablas auditadas</h2>"]
    for name, title, columns in (
        ("test_weekly_metrics", "Cuatro semanas de prueba: ambos modelos", ["model", "target_week", "n", "positive", "negative", "unknown_excluded", "mean_probability", "tp", "fp", "tn", "fn", "precision", "recall", "f1", "average_precision_pr_auc", "roc_auc", "brier"]),
        ("baseline_comparison", "Diferencias RF menos baseline", None),
        ("matched_test_cohort", "Mismos radios conocidos en las cuatro semanas", ["model", "target_week", "n", "positive", "prevalence", "mean_probability", "fp", "fn", "brier"]),
        ("feature_distributions", "Características: grilla completa y etiquetas conocidas", None),
        ("structural_correlations", "Correlaciones: un registro por radio", None)):
        table = pd.read_parquet(output / f"{name}.private.parquet")
        if columns:
            table = table[columns]
        body.append(f"<details><summary>{escape(title)}</summary><div class='table'>" + table.to_html(index=False, float_format=lambda x: f"{x:.5f}", na_rep="No definida", escape=True) + "</div></details>")
    html = "<!doctype html><html lang='es'><meta charset='utf-8'><title>SIGARD — diagnóstico privado Fase 5D</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#1e2933;max-width:1100px;margin:auto;padding:40px}h1{font-size:28px}h2{border-bottom:1px solid #ccd3d7;padding-top:22px}h3{font-size:18px}img{width:100%;height:auto}figure{margin:25px 0}figcaption{font-size:13px;color:#53616c}.table{overflow:auto}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccd3d7;padding:7px;text-align:right}summary{cursor:pointer;font-weight:600;padding:10px}details{margin:12px 0}@media print{body{padding:0}figure{break-inside:avoid}}</style><body>" + "\n".join(body) + "</body></html>"
    (output / "report.private.html").write_text(html, encoding="utf-8")
    (output / "recommendations.private.json").write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = {"status": "automated_evidence_binding_human_review_pending", "submission_ready": False,
        "sources": {"E1": "Fase 5C source manifest/config/review", "E2": "frozen assumed scenario predictors/labels/splits",
            "E3": "partition_metrics, weekly_metrics, calibration_bins, metric_consistency_audit, baseline_comparison",
            "E4": "matched_test_cohort, roc_week_pairs, supplementary_diagnostics.stability/roc_decomposition", "E5": "feature_distributions, structural_correlations, supplementary_diagnostics.redundancy",
            "E6": "feature_importance (immutable 5C derivative)", "E7": "supplementary_diagnostics.dates",
            "E8": "integrity_manifest, git_state, test receipt", "I1": "exploratory interpretation, not causal identification"},
        "claims": [{"line": index + 1, "sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
                    "text_status": "awaiting_human_review"} for index, line in enumerate(lines) if "[E" in line or "[I" in line],
        "references_checked": "official scikit-learn pages and current arXiv record consulted; no private data transmitted"}
    (output / "evidence_registry.private.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
