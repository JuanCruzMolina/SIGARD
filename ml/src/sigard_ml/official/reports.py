"""Exportación local separada; reportes agregados y proyecciones privadas."""

import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.settings import MIN_SAFE_COUNT


def safe_count(count: int):
    return f"<{MIN_SAFE_COUNT}" if 0 < count < MIN_SAFE_COUNT else count


def safe_structure(report: dict) -> dict:
    for source in report["sources"]:
        for sheet in source["sheets"]:
            if "rows" in sheet:
                sheet["rows"] = safe_count(sheet["rows"])
            for column in sheet.get("column_structure", []):
                column["empty_rows"] = safe_count(column["empty_rows"])
    return report


def safe_quality(value, key=""):
    """Suprime cantidades pequeñas sin desgloses por persona o radio."""
    if isinstance(value, dict):
        return {name: safe_quality(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [safe_quality(item) for item in value]
    if type(value) is int and key not in {"source_count", "columns", "header_row", "period_year_min", "period_year_max"}:
        return safe_count(value)
    return value


def write_report(report: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)


def export_normalized(frame: pd.DataFrame, directory: Path, source_id: str, sheet_ref: str):
    """Proyección privada: excluye nombres, documentos, domicilios e IDs reales."""
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{source_id}_{sheet_ref}.parquet"
    temporary = output.with_suffix(".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(output)


def write_quality_summary(report: dict, output: Path) -> None:
    """Resumen legible generado del JSON seguro, sin incorporar filas."""
    summary = report["summary"]
    geography = summary["geography"]
    symptoms = summary["dates"].get("symptom_onset", {})
    lines = ["# SIGARD: calidad preliminar de la entrega oficial", "",
             f"Versión: {report['report_version']}. Corte del control: {report['as_of_date']}.", "",
             f"Fuentes: {report['source_count']}. Filas: {summary['rows']}.",
             f"Completas según requisitos estructurales: {summary['structurally_complete']}.",
             f"Incompletas o con valores no interpretables: {summary['incomplete_or_invalid']}.",
             f"Pendientes de definición epidemiológica: {summary['methodology_review_required']}.", "",
             "## Fechas", "",
             f"Inicio de síntomas: {symptoms.get('valid')} interpretables; "
             f"{symptoms.get('invalid_format')} no interpretables; {symptoms.get('missing')} ausentes.",
             "No se reemplaza inicio de síntomas por toma de muestra ni se asignan semanas aún.", "",
             "## Repeticiones", "",
             f"IDs de evento repetidos: {summary['repeated_event_id_rows_across_delivery']} filas en "
             f"{summary['repeated_event_id_groups_across_delivery']} grupos. No se eliminó ningún registro.", "",
             "## Geografía preliminar", "",
             f"Pares dentro de rangos globales: {geography.get('valid_global_range')}.",
             f"Filas que comparten coordenadas con otras de su misma hoja: {geography.get('repeated_coordinate_rows')}.",
             f"Fuera de Capital bajo la hipótesis geográfica provisional: {geography.get('outside_capital_provisional')}.",
             "CRS y precisión siguen pendientes de confirmación; no se asignaron radios.",
             "Las menciones de calle/interpolación/barrio son etiquetas de origen, no precisión validada.", "",
             "## Estructura por fuente", ""]
    for source in report["sources"]:
        for sheet in source["sheets"]:
            lines.append(f"- {source['source_id']} / {sheet['sheet_ref']}: {sheet['rows']} filas, {sheet['columns']} columnas.")
    lines += ["", "El reporte es local y privado. Cantidades positivas menores de cinco se suprimen.",
              "El JSON asociado conserva los controles detallados, procedencia y preguntas pendientes.", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(output)
