"""Informe privado de viabilidad, separado de cualquier ajuste de modelos."""

from html import escape
import json

import pandas as pd

from sigard_ml.official.spatial_ml.temporal_history import PARTS, LAGS

NAMES = {"train": "Entrenamiento", "validation": "Validación", "test": "Prueba"}


def write_report_files(output, availability, support, pending, states, model_report, model_tables, extra, git):
    def row(part, name):
        return availability[availability.partition.eq(part) & availability.feature_or_set.eq(name)].iloc[0]
    first = model_tables["model_A_leaf_pairs"][0]
    summary = {"unit": "radio_censal_origin_week_target_t_plus_1", "training_authorized": False,
        "new_model_fitted": False, "model_A_modified": False, "retrospective_not_operational": True,
        "history_is_demonstrated_predictive_improvement": False,
        "answers": {"recover_useful_temporal_information": "yes, retrospective experimental presence history; predictive value remains untested",
            "recover_verified_case_count_history_from_assumed_zeros": "no; experimental presence zeros are not complete verified count observations",
            "model_A_plateau": "different calendar inputs enter identical leaves in every tree; frozen inference exactly reproduced",
            "prepare_model_B": "yes, a distinct experimental presence-history candidate with NaN retained; no fitting authorized",
            "operational_forecast": "not validated: record arrival/maturation, surveillance coverage and census availability unverified",
            "independent_future_evaluation": "predefined rolling-origin selection and calibration inside training, followed by an unseen future block/season"}}
    (output / "review.private.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# SIGARD Fase 5E — viabilidad de características temporales", "",
        "Informe privado, descriptivo y retrospectivo para revisión del usuario. Sin entrenamiento, calibración, selección de hiperparámetros o modificación del Modelo A. No apto para aprobación epidemiológica o publicación inferida.", "",
        "## 1. ¿Podemos recuperar información temporal útil con los ceros autorizados?", "",
        "Sí, como historia de presencia experimental. No se ha demostrado aún una mejora predictiva y no se recuperan conteos completos de casos desde esas etiquetas. Se construyen tres pistas separadas: presencia binaria experimental, cantidad de registros provisionales realmente registrados y esos mismos registros en celdas sin pendientes. [E1,E2]",
        f"El intervalo de semanas fuente 07/01–08/06/2024 contiene {extra['source_cells']} celdas ({extra['radios']} radios por {extra['source_weeks']} semanas): {extra['source_positive']} positivas provisionales, {extra['source_assumed_negative']} negativas asumidas y {extra['source_unknown']} desconocidas. Hay {extra['source_recorded_counts_known']} conteos registrados conocidos y {extra['source_presence_known']} presencias experimentales conocidas. [E1]",
        f"No hay cobertura comprobada en ninguna de las {extra['source_cells']} celdas. Los ceros siguen etiquetados como cero_asumido_experimental. Ningún null de casos_observados fue reemplazado por cero; los {extra['source_assumed_negative']} ceros sólo se copian desde etiquetas binarias explícitas a la pista de presencia. [E1,E2]",
        "La suma de cuatro presencias cuenta semanas positivas (0 a 4), no casos. La suma vecinal cuenta pares vecino–semana positivos, no pacientes. Los acumulados de registros conservan su unidad de registros provisionales y son desconocidos si falta cualquier semana o vecino requerido. [E2]", "",
        "## 2. ¿Cuánta historia puede reconstruirse sin inventar datos?", "",
        "Convención temporal: t es la semana de origen de la predicción y el objetivo es t+1. Rezago 1 refiere a t−1, no a t; por tanto está dos semanas antes de la semana objetivo. Los acumulados son [t−4,t−1] y [t−8,t−1]. Se excluye incluso el conteo de la semana de origen, conservando el criterio inicial de Fase 5B. [E2]",
        "Cada etiqueta anterior se indexa por su propia fecha_inicio_semana_objetivo al construir la semana fuente. No se reutiliza la fecha de origen de esa etiqueta como si fuera la fecha observada: así se evita adelantar la historia una semana. Los rezagos consultan fechas exactas y no saltan huecos. [E2]",
        "No se completan bordes con semanas anteriores al 07/01/2024, ni se amplía el período asumido. Una ventana con cualquier valor desconocido queda desconocida, aunque tenga semanas positivas conocidas. Los indicadores de cuántas semanas tienen valor no son acumulados de casos. [E2]", ""]
    for part in PARTS:
        base = row(part, "local_presencia_exp_rezago_1")
        lines += [f"### {NAMES[part]}", "",
            f"Grilla {base.grid_rows}; etiquetas objetivo conocidas {base.known_targets}. Se conservan filas con predictores faltantes y objetivos desconocidos; los últimos sólo se excluirían de un ajuste supervisado futuro. [E3]"]
        for name, label in [(f"local_presencia_exp_rezago_{lag}", f"Rezago {lag}") for lag in LAGS] + [
            ("local_presencia_exp_rezagos_1_a_4_conjuntos", "Los cuatro rezagos conjuntamente"),
            ("local_presencia_exp_acumulado_4", "Acumulado binario de cuatro semanas"),
            ("local_presencia_exp_acumulado_8", "Acumulado binario de ocho semanas")]:
            r = row(part, name)
            lines.append(f"- {label}: {r.rows_feature_known}/{r.grid_rows} filas con valor ({r.fraction_grid_available:.2%}); {r.rows_feature_and_target_known} con objetivo conocido: {r.target_positive_when_feature_known} positivos y {r.target_negative_when_feature_known} negativos; {r.distinct_target_weeks_feature_known} semanas con algún soporte y {r.target_weeks_with_both_classes_and_feature} semanas con ambas clases. [E3]")
        lines.append("")
    lines += ["El acumulado de ocho semanas tiene cero soporte en entrenamiento: no es una variable inicial defendible para aprender con los cortes congelados. Que aparezca en validación o prueba no habilita seleccionarla usando esos períodos. Cuatro rezagos completos y acumulado de cuatro tienen el mismo soporte; sumar no rellena faltantes. [E3]", "",
        "### Conteos provisionales y vecindad", "",
        "Los conteos se ofrecen como pista de comparación, no se completan con los ceros binarios. Si hay pendientes pueden ser cantidades registradas parciales; la pista sin pendientes los enmascara conservadoramente, sin convertirla por ello en vigilancia completa. [E2,E4]"]
    for part in PARTS:
        for scope in ("local", "vecinos"):
            for track in ("presencia_exp", "registros_provisionales", "registros_sin_pendientes"):
                r = row(part, f"{scope}_{track}_rezagos_1_a_4_conjuntos")
                lines.append(f"- {NAMES[part]}, {scope}, {track}: cuatro rezagos completos en {r.rows_feature_known} filas de grilla y {r.rows_feature_and_target_known} con objetivo conocido; {r.target_positive_when_feature_known} positivos, {r.target_negative_when_feature_known} negativos; {r.distinct_target_weeks_feature_known} semanas. [E3]")
    lines += ["", "La vecindad se toma del grafo censal congelado y se contrasta con cantidad_vecinos del Modelo A; no se recalculan geometrías. Un agregado vecinal exige todos los vecinos y una ventana exige todas las semanas. Si no hay vecinos, el valor es desconocido, nunca cero inventado. Los candidatos vecinales no se incorporan automáticamente al Modelo B. [E2,E3]", "",
        "### Impacto de pendientes y fechas", "",
        f"En las semanas fuente, {extra['source_positive_with_pending']} celdas positivas coexisten con pendientes y {extra['source_unknown_with_pending']} celdas desconocidas están bloqueadas por pendientes. Una presencia positiva provisional puede conservarse pese a pendientes, pero no prueba que su conteo esté completo. Los pendientes desconocidos nunca originan ceros. [E1,E4]"]
    for r in pending.to_dict("records"):
        lines.append(f"- {NAMES[r['partition']]}, ventana {r['window']}: {r['rows_history_contains_pending']} filas con al menos una semana fuente con pendientes; {r['rows_history_contains_unknown']} con desconocidos; {r['rows_binary_complete_despite_pending_positives']} con presencia completa pese a positivos pendientes. [E4]")
    delay = extra["legacy_delay_evidence"]
    lines += ["", f"No hay celdas positivas marcadas con fecha aproximada en el intervalo fuente ({extra['positive_cells_with_approximate_date']}). La auditoría previa global 2020–2024, fuera de este subconjunto específico, tiene {delay['paired_symptom_sample_records']} pares síntomas–muestra y {delay['different_epidemiological_week']} con semanas distintas; mediana no negativa {delay['nonnegative_delay_median_days']} días. No se aplica esa demora global a fechas de 2024 ni se infiere llegada de registros a partir de síntomas/muestra. [E1,E6]", "",
        "## 3. ¿Por qué el Modelo A repite probabilidades entre semanas?", "",
        f"La auditoría independiente del RF A reproduce exactamente sus {model_report['inference_rows_replayed']} predicciones guardadas, usando las siete columnas en el orden original, sin imputador, escalado, codificador o Pipeline aprendido. El calendario se recalcula desde la semana de origen y coincide. Se comprueban las entradas float64 y el float32 interno usado por los árboles. [E5]",
        f"Entre {first['first_target_week']} y {first['second_target_week']}, cambian las filas de entrada de los {first['radios_with_different_input_rows']} radios porque cambian las variables estacionales; las cuatro variables estructurales permanecen iguales. Sin embargo, se conservan las hojas en {first['same_leaf_radio_tree_pairs']}/{first['total_radio_tree_pairs']} pares radio–árbol y las probabilidades son idénticas en {first['identical_probability_radios']} radios. No se está reutilizando accidentalmente la misma matriz. [E5]", ""]
    for r in model_tables["model_A_weekly_inputs"][:6]:
        # La tabla completa acompaña al informe; aquí se muestran las primeras dos semanas.
        lines.append(f"- Objetivo {r['target_week']}, origen {r['origin_week']}, {r['feature']}: valor {r['value_float64']:.10f}; float32 {r['value_float32_used_by_trees']:.10f}. [E5]")
    for r in model_tables["model_A_thresholds"]:
        if r["feature"] in ("semana_epidemiologica", "estacionalidad_seno", "estacionalidad_coseno"):
            lines.append(f"- {r['feature']}: entrenamiento [{r['minimum_training_value']:.8f}, {r['maximum_training_value']:.8f}], umbrales del bosque [{r['minimum_threshold']:.8f}, {r['maximum_threshold']:.8f}], {r['split_nodes']} nodos de división. [E5]")
    lines += ["", "Los valores de semana y coseno de las primeras semanas de prueba están fuera del soporte de entrenamiento; el seno tampoco cruza ningún umbral aprendido entre esas dos fechas. Ningún nodo estacional cambia de decisión en esa transición. Entradas numéricamente distintas pueden recorrer exactamente las mismas ramas: es un comportamiento esperado de árboles con regiones de predicción constantes. [E5,R1]",
        "Se recorren manualmente todos los árboles sobre las cuatro matrices semanales y se reconstruyen las probabilidades desde sus hojas, conciliando con apply/predict_proba. Las sensibilidades de una variable a la vez y un barrido con calendarios coherentes se guardan aparte, sin usar etiquetas para elegir nada. Las sustituciones de una sola variable son un diagnóstico computacional y pueden formar tripletas calendario no físicas. [E5]",
        "La meseta local no implica que el bosque ignore todas las variables estacionales: el barrido coherente permite ver su respuesta en otros valores. No se detecta un error en claves, calendario, orden de columnas, transformación o replay de esta implementación congelada. La conclusión está limitada al código/matriz/modelo auditados y no valida el sistema epidemiológico. Modelo y estado de árboles conservan sus hashes antes/después. [E5]", "",
        "## 4. ¿Es viable preparar un Modelo B experimental?", "",
        "Sí, como candidato retrospectivo separado basado en presencia experimental, conservando NaN y todos los radios. Se genera predictors_B_presence_candidate con el núcleo A y candidatos locales de presencia t−1 a t−4 e indicadores de faltantes. No es un modelo entrenado ni una selección autorizada de variables. [E2,E3,E7]",
        "Se distingue explícitamente del B preparado en Fase 5B, cuyos rezagos son conteos de registros. No se cambia silenciosamente la unidad de esas variables ni la configuración original. Los conteos registrados, con/sin pendientes, quedan disponibles como pistas separadas para revisión. [E2,E7]", "",
        "### Soporte técnico sólo desde entrenamiento", ""]
    chosen = support[support.scope.eq("local") & support.track.eq("presencia_exp")]
    for r in chosen.to_dict("records"):
        lines.append(f"- {r['feature_or_set']}: {r['known_training_values']} valores con objetivo conocido, fracción {r['known_training_fraction']:.2%}, positivos {r['positive_training_targets']}, negativos {r['negative_training_targets']}, semanas {r['distinct_training_weeks']}; regla técnica heredada satisfecha: {r['legacy_technical_support_rule_met']}. [E3]")
    lines += ["", "La regla heredada de 5B (20 valores por clase y 10% de disponibilidad) es un filtro técnico orientativo, no una justificación de independencia, potencia o validez epidemiológica. No se selecciona por resultados de validación/prueba. Un acumulado de cuatro es redundante con cuatro rezagos completos; un acumulado de ocho sin valores en entrenamiento no se agrega al candidato inicial. [E3,E7]",
        "La selección completa de filas no se impone: una fila con uno o más rezagos faltantes permanece en las matrices. El RF instalado admite NaN, pero su rendimiento con estas nuevas variables sólo podrá evaluarse en una fase posterior autorizada; soporte de software no implica soporte científico. [E5,E7]", "",
        "Los indicadores de faltantes pueden reflejar el circuito de vigilancia, clasificación o georreferenciación y no sólo actividad epidemiológica. Su disponibilidad retrospectiva no acredita que ese estado de faltante se conociera en cada origen. Deben conservar procedencia y evaluarse como posibles señales de selección/cobertura, no como ausencias de infección. [E1,E7]", "",
        "## 5. ¿Qué impide interpretarlo como pronóstico operativo?", "",
        "No se dispone de evidencia de cuándo estuvo disponible cada observación, revisión de clasificación o declaración de ausencia. Las fechas de síntomas/muestra describen eventos, no disponibilidad del registro en el origen. Por eso toda la historia epidemiológica operativa queda enmascarada como desconocida, con disponibilidad acreditada falsa y estado no_acreditada. No se inventa una demora de notificación. [E1,E2,E6]",
        "La vista operativa también enmascara población, densidad, área y topología del Censo 2022, cuya disponibilidad histórica no se acreditó. Mantiene sólo el calendario conocido de antemano y las claves actuales como referencia técnica, sin convertir el universo censal actual en una geografía operativa validada. La falta del núcleo censal acreditado mantiene bloqueado un ajuste oficial. [E2,E7]",
        "Persisten cobertura epidemiológica no verificada, positivos provisionales, ceros asumidos, pendientes, incertidumbre de fechas/ubicaciones, dependencia entre radios vecinos y pocas semanas de una única temporada. Ninguna cantidad de valores retrospectivos disponibles elimina esas limitaciones. [E1,E4,E6]",
        "El diseño de historia es de origen móvil: para cada t sólo usa semanas anteriores. En prueba puede utilizar etiquetas de semanas de prueba anteriores, ya ocurridas en ese origen, pero hoy reconstruidas retrospectivamente. Esto no equivale a pronosticar todo el bloque de prueba de una sola vez desde el inicio; sin disponibilidad acreditada sigue siendo un ensayo retrospectivo. [E2]",
        "Las semanas objetivo purgadas 03/03 y 05/05 siguen excluidas del uso supervisado. Pueden servir como historia de semanas posteriores únicamente cuando ya son pasado respecto de ese origen; purgar una etiqueta de entrenamiento no elimina automáticamente su observación histórica. No se usa t, t+1 ni semanas posteriores como predictores. [E2]", "",
        "## 6. ¿Qué evaluación independiente futura necesitamos?", "",
        "Primero, aprobar un protocolo de investigación y una autorización de entrenamiento separada para B; mantener los artefactos de A y estos resultados congelados. No hay autorización de ajuste en esta fase. [E7]",
        "Predefinir candidatos, faltantes y baselines con sólo entrenamiento; usar origen móvil con purga t+1 y, si se estudia calibración/umbrales, bloques internos cronológicos con etiquetas maduras. No usar el test actual para optimizar hiperparámetros, cortes o calibración. La historia futura debe reconstruirse con versiones disponibles en cada origen, no con una extracción final que ya conoce revisiones. [E7]",
        "El test de 2024 ya fue examinado en 5C/5D/5E. Comparar B allí sólo daría evidencia retrospectiva exploratoria y no una validación final intacta. Se necesita un bloque futuro o temporada no examinada, con cobertura, maduración y condiciones de disponibilidad documentadas, para una evaluación independiente defendible. No incorporar fuentes todavía en revisión para obtenerlo. [E7]",
        "Comparar A, B y baselines sobre los mismos radios/semanas/cobertura conocida y reportar cuánto cambian los denominadores por faltantes. Conservar el conjunto completo de grilla y una sensibilidad de soporte común sin confundirla con la población general. Informar incertidumbre por temporadas/bloques adecuados cuando haya suficientes unidades; no tratar las 861 celdas como independientes ni bootstrap IID por filas. [E7]", "",
        "## Pruebas, conservación, archivos y Git", "",
        "Las pruebas específicas no entrenan modelos: comprueban el mapeo de fechas de etiqueta a semana fuente, rezagos exactos, límites, huecos, ventanas incompletas, vecinos, pendientes, independencia de información futura, disponibilidad operativa cerrada y recorrido manual de árboles de fixture. La integración inspecciona exclusivamente el RF A propio con hash/versión verificados, bajo bloqueos de fit. El recibo final registra resultados de pruebas y verificación independiente. [E8]",
        f"Se conservaron {extra['prediction_grid_rows_retained']} filas de la grilla autorizada, incluidas purgas y objetivos desconocidos; {extra['supervised_partition_grid_rows']} pertenecen a train/validation/test. No se modifican fuentes, escenarios conservadores, etiquetas, modelos ni resultados de 5C/5D. Los hashes protegidos se comprueban antes/después. [E8]",
        "Se crean cuatro módulos: temporal_history.py, temporal_model_a_audit.py, temporal_feasibility.py y temporal_feasibility_report.py; pruebas y documentación específicas. Productos privados: historia semanal de procedencia, matrices retrospectiva/operativa/candidata B, referencia intacta de etiquetas/particiones, disponibilidad por partición/semana/clase, pendientes, auditoría de A, catálogo, metadatos, informe y manifiesto. No hay pacientes, domicilios o coordenadas individuales en las salidas nuevas. [E8]",
        f"Rama {git['branch']}; HEAD {git['head']}. Se mantienen cambios previos del workspace. Sin modificaciones de frontend/backend, sin staging, commit, push o publicación. Revisión científica humana pendiente del usuario. [E8]", "",
        "## Evidencias y referencias", "",
        "E1: weekly_history_sources y source_and_integrity_review. E2: matrices y catálogo temporal. E3: availability, availability_by_target_week y training_support. E4: pending_impact y weekly_label_states. E5: model_A_audit y tablas de replay/umbrales/hojas/sensibilidad. E6: procedencia de fechas y auditoría previa de recuperación, de alcance global explícito. E7: model_B_preparation, límites del protocolo y recomendaciones exploratorias. E8: manifiestos, pruebas, metadatos y Git.",
        "R1: scikit-learn, RandomForestClassifier y DecisionTreeClassifier: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html ; https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeClassifier.html",
        "R2: scikit-learn, Model persistence: https://scikit-learn.org/stable/model_persistence.html . Sólo se carga el artefacto local confiable y verificado de Fase 5C; la inspección del modelo se separa del flujo EDA, que no deserializa modelos.",
        "R3: Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065 . Se aplicaron scikit-learn, exploratory-data-analysis, statistical-analysis y scientific-critical-thinking; el informe conserva trazabilidad de borrador conforme a scientific-writing.",
        "Las referencias web fueron sólo metodológicas y públicas; ningún dato privado fue transmitido a servicios externos. Las salidas se excluyen de Git y quedan para revisión local.", ""]
    markdown = "\n".join(lines)
    (output / "report.private.md").write_text(markdown, encoding="utf-8")
    body = []
    for line in lines:
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            body.append(f"<h{level}>{escape(line[level:].strip())}</h{level}>")
        else:
            body.append("<p>" + escape(line) + "</p>")
    body.append("<h2>Tablas agregadas de revisión</h2>")
    displays = [("Disponibilidad local de presencia experimental", availability[availability.scope.eq("local") & availability.track.eq("presencia_exp")]),
        ("Soporte de entrenamiento de todos los candidatos", support), ("Impacto de pendientes", pending)]
    for name, data in model_tables.items():
        displays.append((name, pd.DataFrame(data)))
    for title, table in displays:
        body.append(f"<details><summary>{escape(title)}</summary><div class='table'>" + table.to_html(
            index=False, float_format=lambda value: f"{value:.6f}", na_rep="Desconocido", escape=True) + "</div></details>")
    html = "<!doctype html><html lang='es'><meta charset='utf-8'><title>SIGARD Fase 5E — informe privado</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1100px;margin:auto;padding:40px;color:#1e2933}h1{font-size:28px}h2{border-bottom:1px solid #ccd3d7;padding-top:20px}h3{font-size:19px}.table{overflow:auto}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccd3d7;padding:6px;text-align:right}summary{cursor:pointer;font-weight:600;padding:12px}details{margin:12px 0}</style><body>" + "\n".join(body) + "</body></html>"
    (output / "report.private.html").write_text(html, encoding="utf-8")
