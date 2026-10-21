"""Private local technical report; only aggregate experimental results."""

from html import escape

from sigard_ml.official.spatial_ml.robustness import MODELS, PARTS, SIX

NAMES = dict(zip(MODELS, ("A", "B", "Baseline (prior train)")))
LABELS = dict(zip(SIX, ("Precision", "Recall", "F1", "Average Precision", "ROC-AUC", "Brier")))


def value(v):
    return "ND" if v is None else (str(v) if isinstance(v, (str, int)) else f"{v:.4f}")


def percent(v):
    return "ND" if v is None else f"{v:.2%}"


def comparison(candidate, baseline, lower_is_better=False):
    if candidate is None or baseline is None:
        return "ND"
    improves = candidate < baseline if lower_is_better else candidate > baseline
    return "mejora" if improves else "no mejora"


def count_difference(candidate, baseline):
    return "ND" if candidate is None or baseline is None else f"{candidate - baseline:+d}"


def table(headers, rows):
    return "<table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(
        "<tr>" + "".join(f"<td>{escape(value(v))}</td>" for v in row) + "</tr>" for row in rows) + "</tbody></table>"


def write_report(output, data, figures):
    summary, weekly = data["partition_metrics"], data["weekly_metrics"]
    test = {r["model"]: r for r in summary if r["partition"] == "test"}
    a, b, base = (test[m] for m in MODELS)
    sections = []
    def section(title, text):
        sections.append(f"<h2>{escape(title)}</h2>" + text)
    narrative = [
        f"En prueba, de A a B: AP {value(a['average_precision_pr_auc'])}→{value(b['average_precision_pr_auc'])}, "
        f"recall {value(a['recall'])}→{value(b['recall'])}, Precision "
        f"{value(a['precision'])}→{value(b['precision'])} y F1 {value(a['f1'])}→{value(b['f1'])}. "
        f"Sus FP cambian {value(a['fp'])}→{value(b['fp'])} y sus FN {value(a['fn'])}→{value(b['fn'])}; no hay un ganador universal.",
        f"En Brier de prueba, A={value(a['brier'])}, B={value(b['brier'])} y "
        f"baseline={value(base['brier'])}. La comparación con el prior congelado se detalla "
        "por partición y métrica; no se extrapola a otros períodos.",
        "La proporción positiva entre etiquetas conocidas cambia " + "→".join(
            percent(next(r for r in summary if r['partition'] == part and r['model'] == MODELS[0])['prevalence'])
            for part in PARTS) + " (train→validación→prueba). En prueba, "
        f"el score medio es {percent(a['mean_probability'])} para A y {percent(b['mean_probability'])} para B, "
        f"frente a {percent(a['prevalence'])} de positivos experimentales. El sesgo medio "
        "score menos proporción positiva se presenta en la tabla de calibración.",
    ]
    test_weeks = sorted((r for r in weekly if r['partition'] == 'test' and r['model'] == MODELS[0]),
                        key=lambda row: row['target_week'])
    if test_weeks:
        narrative.append("Entre la primera y última semana de prueba la proporción positiva conocida cambia " +
            "→".join(percent(r['prevalence']) for r in (test_weeks[0], test_weeks[-1])) +
            ". Los denominadores se informan por semana. Son etiquetas experimentales, no incidencia acreditada.")
    unchanged = [r for r in data['successive_weeks'] if r['partition'] == 'test' and r['model'] == MODELS[0]
                 and r['exactly_unchanged'] == r['n_radios']]
    for row in unchanged:
        narrative.append(f"A repite exactamente el score de los {row['n_radios']} radios entre "
                         f"{row['before'][:10]} y {row['after'][:10]}; esa meseta no equivale a estabilidad de incidencia. "
                         "Las métricas pueden cambiar por etiquetas y composición aun con scores idénticos.")
    for row in data['auc_temporal_decomposition']:
        narrative.append(f"{NAMES[row['model']]}: AUC agrupado {row['pooled_auc_reconstructed']:.3f}, "
                         f"dentro de semana {row['within_week_auc_weighted_by_pairs']:.3f}. "
                         f"El {row['between_weeks_pair_fraction']:.1%} de los pares compara semanas diferentes; "
                         "el AUC global no resume sólo discriminación espacial contemporánea.")
    dist = [r for r in data['score_distributions'] if r['partition'] == 'test' and r['population'] == 'all_radios'
            and r['model'] == MODELS[1]]
    if dist:
        narrative.append(f"B asigna score ≥0,5 al {min(r['fraction_ge_0_5'] for r in dist):.1%}–"
                         f"{max(r['fraction_ge_0_5'] for r in dist):.1%} de la grilla en semanas de prueba. "
                         "Este rango describe alertas experimentales; los cuantiles muestran su dispersión "
                         "sin acreditar utilidad epidemiológica.")
    section("Hallazgos principales [E1–E7]", "".join(f"<p>{escape(p)}</p>" for p in narrative))
    (output / "summary.private.md").write_text(
        "# SIGARD: robustez A/B\n\nBorrador privado. Descriptivo, exploratorio; revisión humana pendiente.\n\n" +
        "\n\n".join(narrative) + "\n\n" +
        "Positivos provisionales, negativos asumidos, cobertura no plenamente acreditada, evaluación retrospectiva "
        "y prueba ya consultada. No es validación independiente ni autoriza uso epidemiológico.\n\n" +
        "Faltan etiquetas y cobertura acreditadas, disponibilidad histórica reconstruida, más temporadas, "
        "un período no examinado y costos/capacidad operativa para evaluar utilidad. Sin ajustes a partir de prueba.\n\n" +
        "Tablas y gráficos: [informe técnico](report.private.html). Evidencias E1–E7 y métodos en ese informe; "
        "hashes y versiones en manifest.private.json.\n", encoding="utf-8")
    section("Alcance y método", "<p>Borrador técnico privado, pendiente de revisión humana. Análisis descriptivo y exploratorio de "
        "los experimentos A (5C) y B (5F), sin nueva validación independiente. Unidad: radio censal–semana objetivo; "
        "presencia binaria experimental en t+1, no conteos de casos ni el objetivo sintético del MVP. "
        "A usa territorio y calendario; B añade presencia experimental en t−1…t−4 y máscaras de faltantes.</p>"
        "<p>Entrenamiento: objetivos 07/01–02/03/2024 (8 semanas); validación: 10/03–04/05 (8); "
        "prueba: 12/05–08/06 (4). Semanas objetivo 03/03 y 05/05 purgadas. Grilla común: 263 radios por semana. "
        "Se comprobó igualdad exacta de claves, particiones, etiquetas y scores A/baseline entre ambos artefactos. "
        "El baseline existente conserva la prevalencia de entrenamiento: no se ajustó uno nuevo.</p>"
        "<p>Se reutilizaron numeric_metrics, reliability, auditoría contra scikit-learn, descomposición AUC y controles "
        "SHA-256 existentes. Se contrastaron resultados globales, semanales y bins con tablas congeladas y A original. "
        "Umbral fijo 0,5; sin calibrador, inferencia desde modelos, entrenamiento ni selección. Lectura limitada a "
        "los dos experimentos y registro autorizado; no se siguieron rutas de fuentes heredadas.</p>")
    section("Comparación por partición [E1]", table(["Partición", "Modelo", "n conocidos", "Positivos", "Desconocidos", *LABELS.values()],
        [[r["partition"], NAMES[r["model"]], r["n"], r["positive"], r["unknown_excluded"], *[r[k] for k in SIX]] for r in summary]) +
        "<p>ND significa no definido; Precision sin alertas no se convierte en cero. Las métricas de entrenamiento "
        "son descriptivas dentro de muestra. Mayor es mejor salvo Brier (menor). No se declara un ganador.</p>")
    section("Prevalencia y calibración descriptiva [E1,E2]", table(
        ["Partición", "Modelo", "Prevalencia conocida", "Score medio conocidos", "Score medio grilla", "Sesgo medio", "ECE (10 bins)"],
        [[r["partition"], NAMES[r["model"]], r["prevalence"], r["mean_probability"], r["mean_probability_all_radios"],
          r["calibration_gap_mean_probability_minus_prevalence"], r["ece_10_uniform_bins_descriptive"]] for r in summary]) +
        "<p>Las proporciones dependen de positivos provisionales, negativos asumidos y exclusión de desconocidos; "
        "no estiman prevalencia poblacional ni incidencia. Sesgo positivo indica sobreestimación media de la etiqueta experimental; "
        "sesgo negativo, subestimación. ECE usa diez intervalos uniformes fijos con sus tamaños; depende del binning. "
        "Un sesgo medio pequeño puede ocultar errores por intervalo. Brier mezcla calibración y discriminación, no mide calibración aislada. "
        "Bins con muy pocas celdas pueden dar frecuencias extremas inestables; deben leerse junto a su n, sin extrapolación. "
        "La curva de fiabilidad no ajusta probabilidades ni valida riesgo epidemiológico.</p>")
    comparisons = data["baseline_comparison"]
    section("Baseline compatible [E1,E3]", table(["Partición", "Modelo", "ΔAP", "ΔROC-AUC", "ΔBrier", "Habilidad Brier"],
        [[r["partition"], NAMES[r["model"]], r["delta_average_precision_pr_auc"], r["delta_roc_auc"], r["delta_brier"], r["brier_skill"]]
         for r in comparisons]) +
        "<p>Diferencias = RF menos baseline sobre las mismas observaciones y etiquetas. Habilidad Brier = 1−Brier_RF/Brier_baseline; "
        "positiva mejora al prior congelado. AP de un score constante coincide con la proporción positiva evaluada, "
        "aunque la probabilidad del baseline siga siendo la de entrenamiento. No confundir AP con PR-AUC trapezoidal.</p>" +
        "<p>En prueba: " + "; ".join(f"{NAMES[m]} " + ", ".join(
            f"{LABELS[k]} {comparison(test[m][k], base[k], lower_is_better=k == 'brier')}"
            for k in ("average_precision_pr_auc", "roc_auc", "brier")) for m in MODELS[:2]) +
        ". Esto distingue ordenamiento y error probabilístico; no acredita utilidad sanitaria.</p>")
    section("Falsos positivos y negativos a 0,5 [E1,E4]", table(
        ["Partición", "Modelo", "TN", "FP", "FN", "TP", "Alertas", "FP/alertas", "FN/positivos"],
        [[r["partition"], NAMES[r["model"]], r["tn"], r["fp"], r["fn"], r["tp"], r["predicted_positive"],
          r["fp"] / r["predicted_positive"] if r["predicted_positive"] else None,
          r["fn"] / r["positive"] if r["positive"] else None] for r in summary]) +
        f"<p>En prueba B−A: FP {count_difference(b['fp'], a['fp'])}, FN {count_difference(b['fn'], a['fn'])}, TP {count_difference(b['tp'], a['tp'])}. "
        "Un FP sería una alerta en una celda etiquetada negativa asumida; no demuestra una falsa alarma clínica. "
        "Un FN omite una presencia provisional conocida; no mide todos los focos reales omitidos. "
        "Más alertas pueden consumir inspecciones y menos FN pueden favorecer detección, pero faltan costos, "
        "capacidad de respuesta y etiquetas acreditadas para cuantificar beneficio neto o elegir umbral.</p>" +
        table(["Partición", "Ambos correctos", "Sólo A correcto", "Sólo B correcto", "Ambos incorrectos"],
              [[r["partition"], r["both_correct"], r["only_A_correct"], r["only_B_correct"], r["both_wrong"]] for r in data["paired_errors"]]))
    section("Estabilidad entre semanas [E5,E6]", "<p>Se comparan todas las semanas disponibles; la tabla siguiente detalla prueba. "
        "Los CSV incluyen todas las semanas de entrada. No se interpreta un cambio del score como cambio real de incidencia.</p>" +
        table(["Semana objetivo", "Modelo", "n", "Prevalencia", "Score medio", "Precision", "Recall", "AP", "ROC-AUC", "Brier", "FP", "FN"],
        [[r["target_week"], NAMES[r["model"]], r["n"], r["prevalence"], r["mean_probability"],
          r["precision"], r["recall"], r["average_precision_pr_auc"], r["roc_auc"], r["brier"], r["fp"], r["fn"]]
         for r in weekly if r["partition"] == "test"]) +
        table(["Modelo", "Métrica", "Agrupada", "Media semanal", "Mínimo semanal", "Máximo semanal", "Semanas definidas"],
        [[NAMES[r["model"]], LABELS[r["metric"]], r["pooled"], r["weekly_macro_mean"], r["weekly_min"], r["weekly_max"], r["defined_weeks"]]
         for r in data["weekly_stability"] if r["partition"] == "test"]) +
        "<p>La media semanal da igual peso a cada semana; el resultado agrupado usa todas las celdas conocidas. "
        "F1/AP/ROC-AUC agrupados no son medias semanales. Brier sí concilia mediante ponderación por n. "
        "Composición y disponibilidad de etiquetas pueden variar; se distingue grilla completa de etiquetas conocidas.</p>")
    test_transitions = [r for r in data["successive_weeks"] if r["partition"] == "test"]
    section("Variación de scores y sensibilidad [E6,E7]", table(
        ["Modelo", "Desde", "Hasta", "Radios", "Sin cambio exacto", "Cambio absoluto medio", "Cambio absoluto máximo"],
        [[NAMES[r["model"]], r["before"][:10], r["after"][:10], r["n_radios"], r["exactly_unchanged"],
          r["mean_absolute_change"], r["max_absolute_change"]] for r in test_transitions]) +
        table(["Modelo", "Métrica", "Mínimo al excluir una semana", "Máximo al excluir una semana"],
        [[NAMES[m], LABELS[k], min(v) if v else None, max(v) if v else None]
         for m in MODELS for k in ("average_precision_pr_auc", "roc_auc", "brier")
         for v in [[r[k] for r in data["leave_one_week_out"] if r["model"] == m and r["partition"] == "test" and r[k] is not None]]]) +
        "<p>La exclusión de una semana recalcula métricas de scores congelados restantes; no reajusta modelos "
        "ni baseline. Es sensibilidad descriptiva, no validación cruzada, intervalo de confianza ni criterio de selección. "
        "Las distribuciones semanales informan dispersión, cuantiles y fracciones ≥0,5 y ≥0,75, simples cortes "
        "descriptivos sin significado sanitario.</p>" + table(
        ["Modelo", "AUC agrupado", "AUC dentro de semana (ponderado por pares)", "AUC entre semanas", "Fracción de pares dentro"],
        [[NAMES[r["model"]], r["pooled_auc_reconstructed"], r["within_week_auc_weighted_by_pairs"],
          r["between_weeks_auc_weighted_by_pairs"], r["within_week_pair_fraction"]] for r in data["auc_temporal_decomposition"]]))
    if figures:
        section("Gráficos agregados [E2,E5,E6]", "".join(
            f'<figure><img src="{name}.private.png" alt="{escape(alt)}"><figcaption>{escape(alt)}</figcaption></figure>'
            for name, alt in (("weekly", "Trayectorias semanales: prevalencia experimental, scores, AP y Brier; cortes temporales preservados."),
                              ("reliability", "Fiabilidad en prueba: media de score versus frecuencia experimental y tamaño de cada bin."),
                              ("dispersion", "Cuantiles 10, 50 y 90 del score sobre todos los radios, por semana; no son intervalos de confianza."))))
    section("Interpretación defendible y faltantes", "<p>Precision expresa qué fracción de alertas coincide con positivos experimentales; "
        "recall qué fracción de esos positivos se detecta; F1 resume ese equilibrio sin contabilizar TN ni costos. "
        "AP resume precisión a distintos niveles de recuperación y depende de la proporción positiva. ROC-AUC mide ordenamiento "
        "positivo–negativo, no calibración ni valor de una alerta. Brier penaliza error cuadrático del score respecto de la etiqueta.</p>"
        "<p>Puede defenderse una comparación retrospectiva reproducible sobre este escenario, con diferencias de "
        "discriminación, carga de alertas, omisiones y error probabilístico. No una superioridad epidemiológica "
        "general ni precisión espacial clínica. No se declara ganador basándose sólo en ROC-AUC o recall.</p>"
        "<p>Los positivos son provisionales; los negativos fueron asumidos experimentalmente; la cobertura "
        "no está plenamente acreditada. Evaluación retrospectiva con prueba ya consultada durante el desarrollo. "
        "Una temporada, 8/8/4 semanas, radios repetidos y vecinos dependientes impiden tratar celdas como eventos IID. "
        "No se calcularon p-valores ni intervalos IID. Scores brutos sin calibración validada; disponibilidad histórica "
        "de registros y contexto censal no acreditada.</p>"
        "<p>Faltan vigilancia y denominadores de cobertura verificables, negativos acreditados, revisión de positivos "
        "y localización/fechas, snapshots de llegada y maduración de información en cada origen, más temporadas "
        "y un período independiente no examinado, protocolo temporal congelado, incertidumbre que respete dependencia "
        "y costos/capacidad operativa explícitos. Una futura calibración o decisión de umbral requerirá datos "
        "apropiados separados de esta prueba. Esta fase no los ajusta.</p>")
    section("Evidencia, reproducción y revisión", "<p>E1: partition_metrics.private.csv; E2: calibration_bins.private.csv; "
        "E3: baseline_comparison.private.csv; E4: paired_errors.private.csv; E5: weekly_metrics.private.csv y weekly_stability.private.csv; "
        "E6: score_distributions.private.csv y successive_weeks.private.csv; E7: leave_one_week_out.private.csv y auc_temporal_decomposition.private.csv. "
        "frozen_consistency.private.csv registra cada contraste; manifest.private.json conserva hashes, versiones y código. "
        "Todos derivan exclusivamente de artefactos autorizados A/B. No hay pacientes, coordenadas ni identificadores de radio "
        "en este informe o las tablas de salida. Revisión científica humana pendiente; no autorización de publicación.</p>"
        "<p>Referencias metodológicas: <a href=\"https://scikit-learn.org/stable/modules/model_evaluation.html\">scikit-learn, métricas</a>; "
        "<a href=\"https://scikit-learn.org/stable/modules/calibration.html\">calibración</a>. "
        "Apoyo procedimental: Kassis, T., Agarwal, V., He, Y., Patel, D., &amp; Brueckner, A. M. (2026). "
        "<a href=\"https://doi.org/10.48550/arXiv.2609.00065\">Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents</a>. "
        "Consultas bibliográficas sin datos privados. Borrador elaborado con asistencia de Codex; fuentes y conclusiones requieren revisión humana.</p>")
    html = '<!doctype html><html lang="es"><meta charset="utf-8"><title>SIGARD: robustez A/B</title><style>' + \
        'body{font:15px/1.55 system-ui;max-width:1280px;margin:40px auto;padding:0 24px;color:#20262e}' + \
        'table{border-collapse:collapse;width:100%;font-size:12px;margin:20px 0}th,td{padding:7px;border-bottom:1px solid #ddd;text-align:right}' + \
        'th:first-child,td:first-child{text-align:left}h2{margin-top:36px}img{max-width:100%}figure{margin:24px 0}figcaption{font-size:13px}' + \
        '</style><h1>SIGARD: robustez y desempeño predictivo A/B</h1><p>Privado · retrospectivo · exploratorio · revisión pendiente</p>' + \
        ''.join(sections) + '</html>'
    (output / "report.private.html").write_text(html, encoding="utf-8")
