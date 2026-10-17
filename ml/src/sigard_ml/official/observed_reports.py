"""Conciliación privada y resúmenes seguros, separados del panel sin supresión."""

import hashlib

from sigard_ml.official.classification import classification_key
from sigard_ml.official.reports import safe_count


def safe_histogram(values):
    return {str(key): safe_count(int(count)) for key, count in values.value_counts().sort_index().items()}


def classification_inventory(frame):
    """Inventario local: etiquetas sólo en archivo privado, nunca en stdout."""
    groups = {}
    for label in frame.classification_label:
        key = classification_key(label)
        if key is not None:
            groups[key] = groups.get(key, 0) + 1
    return [{"label": key, "label_ref": hashlib.sha256(key.encode()).hexdigest(),
             "rows": safe_count(count)} for key, count in sorted(groups.items())]


def reconciliation(frame, panel, conservative):
    outcomes = frame.processing_outcome.value_counts()
    included, excluded, pending = (int(outcomes.get(name, 0)) for name in ("included", "excluded", "pending"))
    if included + excluded + pending != len(frame):
        raise ValueError("Los desenlaces de las filas no concilian")
    if int(panel.registros_elegibles_provisionales.sum()) != included:
        raise ValueError("Los conteos agregados no concilian con las filas")
    return {"initial_records": safe_count(len(frame)),
            "classification_interpretable": safe_count(int(frame.classification.ne("indeterminado").sum())),
            "classification_unmapped": safe_count(int((~frame.classification_mapped).sum())),
            "classification_counts": safe_histogram(frame.classification),
            "eligible_under_current_policy": safe_count(int(frame.analysis_eligibility.eq("eligible_provisional").sum())),
            "eligible_under_conservative_policy": safe_count(int(conservative.analysis_eligibility.eq("eligible_provisional").sum())),
            "eligibility_counts": safe_histogram(frame.analysis_eligibility),
            "usable_reference_dates": safe_count(int(frame.reference_date_usable.sum())),
            "unusable_reference_dates": safe_count(int((~frame.reference_date_usable).sum())),
            "date_status_counts": safe_histogram(frame.reference_date_status),
            "date_within_analysis_period": safe_count(int(frame.date_within_analysis_period.sum())),
            "identity_status_counts": safe_histogram(frame.episode_status),
            "identity_pending_for_count": safe_count(int((~frame.identity_countable &
                    ~frame.identity_resolved_by_review).sum())),
            "identity_resolved_by_review": safe_count(int(frame.identity_resolved_by_review.sum())),
            "repeated_identifier_records": safe_count(int(frame.identity_group_size.gt(1).sum())),
            "repeated_identifier_groups": safe_count(int(frame.loc[frame.identity_group_size.gt(1), "event_ref"].nunique())),
            "records_with_radio_candidate": safe_count(int(frame.radio_candidate.notna().sum())),
            "included_records": safe_count(included), "excluded_records": safe_count(excluded),
            "pending_records": safe_count(pending),
            "included_reference_date_types": safe_histogram(frame.loc[frame.processing_outcome.eq("included"), "tipo_fecha_referencia"]),
            "included_approximate_dates": safe_count(int((frame.processing_outcome.eq("included") & frame.fecha_aproximada).sum())),
            "represented_epidemiological_weeks": int(frame.loc[frame.processing_outcome.eq("included"), "week_start"].nunique()),
            "processing_reason_counts": safe_histogram(frame.processing_reasons.explode().dropna()),
            "panel_observation_state_counts": safe_histogram(panel.estado_observacion),
            "panel_cells": len(panel), "panel_weeks": int(panel.fecha_inicio_semana.nunique()),
            "explicit_zero_cells": safe_count(int(panel.registros_elegibles_provisionales.eq(0).sum())),
            "null_count_cells": safe_count(int(panel.registros_elegibles_provisionales.isna().sum())),
            "reconciliation_verified": True,
            "unvalidated_panel": True, "training_labels_generated": False}


def report_text(report):
    summary = report["summary"]
    lines = ["# SIGARD: panel exploratorio oficial (privado)", "",
             f"Modo: {report['mode']}. Transformación: {report['transformation_version']}.",
             "Unidad: registros elegibles provisionales por radio censal y semana epidemiológica.",
             "No representa casos únicos confirmados y validados. No está listo para entrenamiento.", "",
             f"Período solicitado: {report['analysis_period']['start']} a {report['analysis_period']['end']}.",
             "Las semanas son domingo-sábado; las semanas que intersectan parcialmente la ventana quedan parciales.", "",
             "## Clasificación e identidad", ""]
    for category, count in summary["classification_counts"].items():
        lines.append(f"- {category}: {count} registros.")
    lines += ["", "Correspondencias completas de etiquetas; nunca se filtra por palabras dentro de textos.",
              f"Categorías admitidas en el escenario exploratorio: {', '.join(report['exploratory_include'])}.",
              "Las categorías indeterminadas quedan pendientes.",
              "La política conservadora no incluye registros hasta validar las reglas epidemiológicas.",
              "Un identificador no repetido se admite provisionalmente; no demuestra identidad epidemiológica única.",
              "Las repeticiones quedan pendientes salvo resolución manual completa con evidencia y representante declarado.", "",
              "## Conciliación", ""]
    for label, key in (("Filas iniciales", "initial_records"), ("Clasificación interpretable", "classification_interpretable"),
                       ("Elegibles bajo política actual", "eligible_under_current_policy"),
                       ("Fecha utilizable", "usable_reference_dates"), ("Fecha no utilizable", "unusable_reference_dates"),
                       ("Identidad pendiente para contar", "identity_pending_for_count"),
                       ("Con candidato censal", "records_with_radio_candidate"),
                       ("Incluidas", "included_records"), ("Excluidas", "excluded_records"), ("Pendientes", "pending_records")):
        lines.append(f"- {label}: {summary[key]}.")
    lines += ["", "Incluidas + excluidas + pendientes = filas iniciales, comprobado antes de suprimir cantidades pequeñas.",
              "Los indicadores de problemas pueden solaparse; no deben sumarse como desenlaces independientes.",
              "Los pendientes posibles por celda pueden afectar varias semanas/radios: tampoco se suman como filas distintas.", "",
              "## Cobertura y geografía", "",
              f"Celdas radio-semana: {summary['panel_cells']}; semanas: {summary['panel_weeks']}.",
              f"Ceros respaldados: {summary['explicit_zero_cells']}; conteos nulos: {summary['null_count_cells']}.",
              "La cobertura no se infiere de años de archivo, fechas extremas ni ausencia de registros.",
              "Incluso un conteo positivo puede ser incompleto cuando la cobertura de la fuente no está acreditada.",
              "Cero requiere evidencia explícita de cobertura completa, semana íntegra y ausencia de pendientes que la afecten.",
              "Se aceptan candidatos aproximados existentes conforme a la decisión del proyecto. No se vuelve a geocodificar.",
              "Nominatim y Georef son proveedores declarados por el proyecto; su atribución por registro no está verificada.",
              "Se conservan estado, categoría de precisión, distancia, motivos y procedencia de Fase 3 en la auditoría privada.",
              "Un candidato interior no acredita residencia exacta. Los límites ambiguos nunca reciben un candidato arbitrario.",
              "La fracción censal se conserva como código de siete dígitos para una comparación agregada posterior.", "",
              "## Límite temporal y siguientes pasos", "",
              f"Campo temporal inicial: {report['reference_date_field']}; jerarquía explícita: {report.get('date_hierarchy')}.",
              "Una fecha alternativa es aproximada y no confirma el inicio real de síntomas; puede desplazar la semana por retrasos.",
              "No se reconstruyó cuándo cada registro o clasificación era conocido históricamente: el panel es retrospectivo.",
              "No se generan etiquetas negativas, variables de la semana objetivo ni entrenamiento.",
              "La unión opcional de auxiliares exige claves territoriales/semanales y disponibilidad anterior o igual al corte.",
              "Queda pendiente validar clasificación, unidad de episodio, cobertura, fecha y semántica de ubicación.",
              "La probabilidad de registros en la semana siguiente es el objetivo futuro del circuito oficial; no se altera el MVP.",
              "Los archivos son privados. Cantidades positivas menores de cinco se suprimen sólo en reportes; el Parquet conserva null.", ""]
    return "\n".join(lines)
