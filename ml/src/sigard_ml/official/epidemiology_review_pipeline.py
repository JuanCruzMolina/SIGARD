"""Fase 5B.1: diagnóstico privado desde derivados; sin ingestión ni ejecución ML."""

import argparse
import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.coverage_pipeline import require_manifest
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import safe_count, write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.spatial_ml.pipeline import read_json, verify_private_manifest, verify_sources
from sigard_ml.official.epidemiology_review import (
    VERSION, confirmation_inventory, coverage_proposals, decision_template,
    flag_implementation_evidence, pending_impact, territorial_evidence,
)

EXPECTED_SOURCES = 5
DEFAULTS = {"version": VERSION, "access_config": "data/interim/official/access.private.json",
    "phase2_dir": "data/interim/official", "observed_dir": "data/interim/official/observed/date_recovery_041",
    "coverage_dir": "data/interim/official/observed/coverage_042",
    "universe_dir": "data/interim/official/observed/universe_043_v1",
    "phase5b_dir": "data/interim/official/spatial_experiment_05b_v1",
    "output_dir": "data/interim/official/epidemiology_review_05b1_v1",
    "source_2022_id": "delivery_2022", "training_enabled": False, "materialize_negatives": False}


def private_paths(root, options):
    if set(options) != set(DEFAULTS) or options["version"] != VERSION or options["training_enabled"] is not False or options["materialize_negatives"] is not False:
        raise ValueError("Fase 5B.1 sólo prepara evidencia y decisiones")
    allowed = (root / "data/interim/official").resolve()
    paths = {key: (root / options[key]).resolve() for key in DEFAULTS if key.endswith("_dir") or key == "access_config"}
    output = paths.pop("output_dir")
    if not allowed.is_relative_to(root.resolve()) or any(not path.is_relative_to(allowed) for path in paths.values()):
        raise ValueError("Se requieren rutas privadas dentro del repositorio")
    if output.parent != allowed or output.exists() or any(output.is_relative_to(path) or path.is_relative_to(output)
        for key, path in paths.items() if key != "phase2_dir") or output == paths["phase2_dir"]:
        raise ValueError("Se requiere un destino privado nuevo, independiente y sin sobrescritura")
    return paths, output


def preserved_classification_inputs(paths, registry, universe, structure, quality):
    provenance = universe["provenance"]
    if digest_path(paths["phase2_dir"] / "quality_report.json") != provenance["quality_report_sha256"]:
        raise ValueError("Cambió el informe de normalización")
    schemas, frames = {}, []
    quality_sources = {row["source_id"]: row for row in quality["sources"]}
    structure_sources = {row["source_id"]: row for row in structure["sources"]}
    for source in registry.sources:
        entries = [row for row in provenance["sources"] if row["source_id"] == source.source_id]
        for entry in entries:
            sheet = entry["sheet_ref"]
            path = (paths["phase2_dir"] / "normalized" / f"{source.source_id}_{sheet}.parquet").resolve()
            if not path.is_relative_to(paths["phase2_dir"] / "normalized") or digest_path(path) != entry["normalized_sha256"]:
                raise ValueError("Cambió un normalizado preservado")
            frame = pd.read_parquet(path, columns=["source_id", "record_ref", "classification_label"])
            if not frame.source_id.eq(source.source_id).all():
                raise ValueError("Normalizado de otra fuente")
            frame["sheet_ref"] = sheet
            frames.append(frame)
        # La entrega actual preservada tiene una hoja por fuente. No se abre Excel
        # para reconstruir hojas/cabeceras ni se releen celdas clínicas.
        if len(entries) != 1:
            raise ValueError("Requiere conciliar explícitamente fuentes con múltiples hojas")
        sheet = entries[0]["sheet_ref"]
        q = next(row for row in quality_sources[source.source_id]["sheets"] if row["sheet_ref"] == sheet)
        s = next(row for row in structure_sources[source.source_id]["sheets"] if row["sheet_ref"] == sheet)
        headers = s.get("safe_headers", {})
        column = q["fields"].get("classification")
        schemas[source.source_id] = {"source_version": source.source_version, "sheet_ref": sheet,
            "classification_column": column, "classification_header": headers.get(column),
            "classification_header_candidates": {key: value for key, value in headers.items() if isinstance(value, str) and "clasif" in value.casefold()},
            "additional_unprojected_classification_values": "unknown; no workbook re-read in this phase",
            "classification_domain_validated_in_phase2": q.get("classification_domain_validated", False)}
    return pd.concat(frames, ignore_index=True), schemas


def training_conditions():
    return {"current_status": "not_fit", "model_A_configuration_modified": False,
        "current_missing": ["responsible validation of historical dengue definition and literal classification mapping",
            "documented manual residence filter and pre-filter reconciliation",
            "explicit exact coverage intervals backed by extraction/completeness evidence",
            "separate authorization for assumed-negative materialization and later training",
            "both classes with sufficient examples/weeks after rebuilding only newly authorized labels in a future phase",
            "label maturity and temporal evaluation limitations documented"],
        "retrospective_experimental_path": ["signed source/label/territory decisions with evidence refs",
            "if assumed coverage: explicit experimental declaration and uncertainty acceptance; preserve conservative panel",
            "pending/partial/outside-scope target cells remain unknown; use only eligible positive and supported/authorized negative labels",
            "chronological purged partitions with both classes; review sample size and dependence without forcing a split",
            "retain 2022 census as retrospective context; report calibration and compare training-prevalence baseline",
            "authorize the unchanged Model A experiment separately; no operational performance claims"],
        "operational_backtest_additional_requirements": ["historical census publication/boundary availability",
            "label availability/maturation at each historical training cutoff and source extraction cutoff",
            "point-in-time evidence for persistence baseline, otherwise abstain or use training prevalence"],
        "Model_A_requires_epidemiological_lags": False,
        "all_pending_must_be_resolved": False, "blocked_unknowns_may_be_used_as_negatives": False,
        "absolute_geographic_certainty_required": False,
        "approximate_geography": "already accepted; retain uncertainty as a limitation, not an absolute-precision gate",
        "template_signature_automatically_enables_training": False}


def decision_document(report, inventory, template):
    lines = ["# SIGARD Fase 5B.1 — dossier privado de decisiones epidemiológicas", "",
        "Estado: diagnóstico completo, decisiones pendientes. No se entrenó, reclasificó, imputó ni materializó negativos.",
        "No se repitieron ingestión, geocodificación o ingeniería de características. Configuración del Modelo A preservada.", "",
        "## 1. Diagnóstico de confirmación: por qué las banderas son cero", "",
        "El criterio actual de Fase 5B exige simultáneamente inclusión, categoría literal canónica confirmado, elegibilidad provisional y banderas de elegibilidad e identidad validadas.",
        "evaluate_eligibility fija epidemiological_eligibility_validated=False; prepare_records fija epidemiological_identity_validated=False. Las líneas y hashes del código quedan en el diagnóstico JSON.",
        "Por tanto, cero banderas validadas es un estado conservador del software: NO demuestra que los registros rotulados confirmados sean falsos o que no existan confirmados.",
        "Los archivos contienen evidencia de clasificación registrada, pero no documentan la definición histórica de dengue, el diccionario de evento ni cómo se validó ese criterio.",
        "No se exige laboratorio a todos los registros por defecto: el responsable debe identificar el criterio histórico aplicable, incluido nexo clínico/epidemiológico cuando corresponda, y respaldarlo.", ""]
    for source in report["classification_sources"]:
        lines += [f"### {source['source_id']}", "",
            f"Columna seleccionada: {source['classification_column']} ({source['classification_header']}); hoja {source['sheet_ref']}; versión {source['source_version']}.",
            f"Registros: {safe_count(source['records'])}; rotulados confirmado: {safe_count(source['recorded_confirmed_labels'])}; incluidos provisionales: {safe_count(source['included_provisional'])}.", ""]
        for row in inventory[inventory.source_id.eq(source['source_id'])].to_dict("records"):
            label = row['literal_label'] if row['literal_label'] is not None else '[sin valor]'
            lines.append(f"- Etiqueta completa `{label}`: {safe_count(row['records'])}; categoría heredada {row['canonical_category']}; estado de evidencia {row['evidence_status']}.")
        lines += ["", "Decisión a completar: validar bajo una definición histórica documentada / mantener provisional / mantener pendiente / excluir con regla explícita. No se aplica ninguna opción automáticamente.", ""]
    lines += ["## 2. Fuente 2022 y evidencia negativa", "",
        "La fuente identificada para revisión de 2022 conserva categorías sospechoso/probable/descartado; sus frecuencias exactas quedan en los JSON/Parquet privados.",
        "Probable y sospechoso no acreditan confirmación, pero tampoco prueban ausencia de enfermedad. Descartado es evidencia de una clasificación de descarte registrada para esa fila, no de ausencia en el radio-semana.",
        "Las etiquetas indeterminadas/no mapeadas significan confirmación desconocida. Las etiquetas confirmadas sí aportan evidencia registrada favorable, sin resolver por sí solas evento, criterio histórico o identidad.",
        "Debe explicarse la diferencia con la declaración previa de conservar sólo confirmados: confirmar columna/filtro real, fecha de exportación, cambios posteriores, criterio utilizado y conciliación con la entrega anterior al filtro.",
        "No se cambia el universo 2022 ni se infiere confirmación o período desde el nombre del archivo. Las fechas de muestra existentes cruzan años civiles y no delimitan completitud.", "",
        "## 3. Filtrado territorial", ""]
    for source in report["territory"]["sources"]:
        lines.append(f"- {source['source_id']}: provincia {source['residence_province_column']} ({source['province_header']}), departamento {source['residence_department_column']} ({source['department_header']}); {safe_count(source['rows_matching_la_rioja_capital_residence_labels'])} filas compatibles con La Rioja–Capital, de {safe_count(source['rows'])}.")
    lines += ["", "La concordancia de valores de residencia es evidencia interna compatible con el filtro, pero no reconstruye la operación manual. No se confunde establecimiento notificador con residencia ni se infiere residencia desde las coordenadas.",
        "Completar por fuente: columnas y valores literales usados, orden/fecha/operador del filtro, tratamiento de faltantes/no residentes y referencia de exportación anterior al filtro o conciliación firmada (filas antes/después y omisiones).", "",
        "## 4. Propuestas de intervalos para revisar, no declaraciones", "",
        "Se reutilizan las envolventes de Fase 4.3 por fuente, año de referencia y tipo de fecha, y los límites observados de Fase 4.2. Ningún intervalo tiene actualmente evidencia suficiente de completitud.",
        "Confianza en completitud: ninguna. Justificación pendiente: documento de extracción con período, campo temporal, corte, universo/filtros y conciliación semanal. Los huecos sin filas no demuestran semanas negativas.",
        "El límite configurado 31/12/2024 no es evidencia de cobertura; no se propone extender hasta diciembre ni unir huecos entre temporadas. Intervalos superpuestos son alternativas que requieren resolución, no capacidades sumables.", ""]
    for proposal in report["coverage_proposals"]:
        start, end = proposal['proposed_interval_start'], proposal['proposed_interval_end']
        if start is None:
            lines.append(f"- {proposal['proposal_id']} / {proposal['source_id']}: sin intervalo completo proponible bajo esta política; requiere revisión, no se generan negativos.")
        else:
            lines.append(f"- {proposal['proposal_id']} / {proposal['source_id']} / {proposal['date_policy']}: **{start} a {end}**, referencia {proposal['temporal_criterion']}; {safe_count(proposal['pending_blocked_cells_in_interval'])} celdas con pendientes. Criterio propuesto: etiquetas de confirmación histórica por validar y residencia La Rioja–Capital por documentar. Completitud sin respaldo, confianza ninguna.")
    lines += ["", "En decisiones.template.private.json los intervalos candidatos son sugerencias de revisión; declared_start/end permanecen vacíos y coverage_declarations sigue vacío. El responsable puede rechazarlos, corregirlos o proponer otros límites con evidencia.", "",
        "## 5. Pendientes e incertidumbres que una declaración no elimina", ""]
    for policy, summary in report["pending"].items():
        lines += [f"- {policy}: pendientes {safe_count(summary['pending_records'])}; sin fecha {safe_count(summary['undated_pending'])}; identidad pendiente {safe_count(summary['identity_pending'])}; elegibilidad pendiente {safe_count(summary['eligibility_pending'])}. Las dimensiones pueden solaparse.",
            f"  Sin fecha: {summary['radios_with_undated_pending']} radios candidatos; sin radio conocido: {safe_count(summary['undated_without_radio'])}. No se limita el período por el año del archivo. Fechas aproximadas incluidas: {safe_count(summary['included_approximate_dates'])}."]
    lines += ["", f"Los {report['pending']['expanded']['undated_pending']} pendientes sin fecha del panel ampliado bloquean todas las semanas posibles de sus radios dentro de la ventana actual. Con radio desconocido, el bloqueo sería territorial amplio. Una declaración no los elimina ni obliga a resolverlos todos si se preservan esas celdas como desconocidas.",
        "Identidades repetidas/ausentes requieren resolución de episodios documentada; las categorías no mapeadas requieren criterio explícito. No se elige automáticamente un representante ni se descarta un pendiente para habilitar ceros.",
        "Toma de muestra no es inicio de síntomas: se conserva la política ampliada como aproximación y la estricta como sensibilidad. No se corrigen semanas restando una demora promedio.",
        "La geografía aproximada YA fue aceptada. No se exige certeza domiciliaria absoluta ni nueva geocodificación. Permanecen incertidumbre de asignación, CRS/rol documentado y límites del radio como limitaciones; no se presentan como localizaciones reales de infección.", "",
        "## 6. Condiciones exactas para el Modelo A", "",
        "A no usa rezagos epidemiológicos: no se exige reconstruir una historia de predictores que ese modelo no utiliza. Sí debe documentarse la maduración/disponibilidad de etiquetas en cada corte para afirmar un backtest operativo.",
        "Ruta retrospectiva experimental, sin cambiar el Modelo A:", ""]
    lines += [f"- {item}" for item in report["training_conditions"]["retrospective_experimental_path"]]
    lines += ["", "Para afirmar operación histórica, además:", ""]
    lines += [f"- {item}" for item in report["training_conditions"]["operational_backtest_additional_requirements"]]
    totals = report['current_labels']['expanded']
    lines += ["", f"Estado actual ampliado: {totals['positive']} objetivos positivos provisionales, {totals['negative']} negativos respaldados y {totals['unknown']} desconocidos. Sigue NO APTO; la firma del documento tampoco ejecuta entrenamiento.",
        "El primer período de evaluación propuesto en 5A/5B seguirá revisándose tras disponer de ambas clases; no se fuerza un corte válido ni se cambia la configuración del bosque.", "",
        "## 7. Qué debe completar el responsable", "",
        "1. Identidad/fecha/firma o referencia documental del responsable.",
        "2. Decisión para cada etiqueta literal y fuente, definición de dengue y criterio histórico (laboratorio/nexo/otro criterio documentado), período de aplicación y evidencia.",
        "3. Procedimiento territorial real y conciliación de selección/extracción.",
        "4. Aceptar/rechazar/corregir cada propuesta de intervalo; declarar fechas exactas, fecha base, corte, justificación, evidencia y confianza; resolver solapamientos sin anular pendientes.",
        "5. Revisiones de identidades/clasificaciones pendientes o conservación expresa de sus bloqueos; reconocimiento del desplazamiento por muestras y del contexto censal retrospectivo.",
        "6. Elegir alcance retrospectivo experimental u operativo, documentar sus condiciones y dar autorizaciones separadas para negativos y luego entrenamiento.",
        "Ningún dato externo faltante bloqueó este diagnóstico: lo no comprobable se identifica como pendiente. Plantilla no firmada, sin decisiones preseleccionadas ni períodos declarados automáticamente.", "",
        "Se preservaron fuentes, paneles, features, configuraciones y modelos anteriores. Salidas privadas excluidas de Git; sin frontend/backend, commit, push o publicación. Detención para revisión.", ""]
    return "\n".join(lines)


def run_review(root, options):
    require_branch(root)
    paths, output = private_paths(root, options)
    _, registry = load_configuration(paths["access_config"], root)
    if len(registry.sources) != EXPECTED_SOURCES:
        raise ValueError("La revisión requiere las cinco fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    before = protected_snapshot(root, output)
    for key in ("observed_dir", "coverage_dir"):
        require_manifest(paths[key])
    for key in ("universe_dir", "phase5b_dir"):
        verify_private_manifest(paths[key])
    universe = read_json(paths["universe_dir"] / "review.private.json")
    coverage_metadata = read_json(paths["coverage_dir"] / "metadata.json")
    verify_sources(registry, coverage_metadata)
    if universe["provenance"] != coverage_metadata["provenance"]["normalization"]:
        raise ValueError("Procedencia de cobertura y universo diferente")
    expected_reports = read_json(paths["universe_dir"] / "integrity_manifest.private.json")["protected_files_sha256"]
    for name in ("structure_report.json", "quality_report.json"):
        path = paths["phase2_dir"] / name
        if digest_path(path) != expected_reports.get(str(path.relative_to(root))):
            raise ValueError("Cambió un diagnóstico estructural previo")
    structure, quality = (read_json(paths["phase2_dir"] / name) for name in ("structure_report.json", "quality_report.json"))
    normalized, schemas = preserved_classification_inputs(paths, registry, universe, structure, quality)
    if options["source_2022_id"] not in schemas:
        raise ValueError("La fuente 2022 configurada no está autorizada")
    phase5b = read_json(paths["phase5b_dir"] / "review.private.json")
    model_a = read_json(paths["phase5b_dir"] / "experiment_A.private.json")
    if model_a["training_enabled"] is not False:
        raise ValueError("La configuración recibida ya no es sólo preparatoria")
    report = {"version": VERSION, "training_performed": False, "negatives_materialized": False,
        "rows_reclassified": False, "external_documentation_required_to_generate_diagnostic": False,
        "classification_sources": [], "flag_implementation": flag_implementation_evidence(),
        "pending": {}, "current_labels": {}, "training_conditions": training_conditions(),
        "territory": territorial_evidence(universe["universe"]["sources"], universe["previous_provenance_declaration"]),
        "date_delay_evidence": universe["previous_delay_evidence"], "geographic_evidence": universe["geographic_evidence"],
        "geographic_sensitivity": universe["previous_geographic_sensitivity"],
        "requested_source_periods": universe["previous_source_period_declarations"],
        "existing_coverage_declarations": universe["previous_coverage_declarations"],
        "existing_coverage_verifications": universe["previous_coverage_verifications"]}
    panels, details = {}, {}
    for policy in ("strict", "expanded"):
        prior = paths["observed_dir"] / policy / "exploratory"
        require_manifest(prior)
        audit = pd.read_parquet(prior / "records_audit.parquet")
        panel = pd.read_parquet(paths["coverage_dir"] / policy / "conservative/panel.parquet")
        panels[policy] = panel
        details[policy], report["pending"][policy] = pending_impact(audit, panel, universe["uncertainty"]["policies"][policy])
        labels = panel.objetivo_semana_siguiente
        report["current_labels"][policy] = {"positive": int(labels.eq(1).sum()), "negative": int(labels.eq(0).sum()), "unknown": int(labels.isna().sum())}
        expected = phase5b["datasets"][f"{policy}/conservative"]
        if any(report["current_labels"][policy][key] != expected[key] for key in report["current_labels"][policy]):
            raise ValueError("Cambió el objetivo respecto a Fase 5B")
        if int(panel.casos_observados.sum()) != int(audit.processing_outcome.eq("included").sum()):
            raise ValueError("Los registros y el panel previo no concilian")
        if policy == "expanded":
            inventory, report["classification_sources"] = confirmation_inventory(normalized, audit, schemas)
    report["source_2022_id"] = options["source_2022_id"]
    report["coverage_proposals"] = coverage_proposals(universe["candidate_intervals"], panels, schemas, universe["source_periods"])
    template = decision_template(inventory, report["territory"], report["coverage_proposals"])
    require_preserved(before, protected_snapshot(root, output))
    output.mkdir(parents=True, exist_ok=False)
    write_frame(inventory, output / "classification_inventory.private.parquet")
    for policy, detail in details.items():
        write_frame(detail, output / f"{policy}.pending_review.private.parquet")
    for name, content in (("diagnostic.private.json", report), ("decisions.template.private.json", template),
                          ("coverage_proposals.private.json", report["coverage_proposals"]), ("configuration.private.json", options)):
        write_report(content, output / name)
    (output / "decision_dossier.private.md").write_text(decision_document(report, inventory, template), encoding="utf-8")
    write_report({"version": VERSION, "source_provenance": universe["provenance"],
        "calendar_version": read_json(paths["phase5b_dir"] / "metadata.private.json")["calendar_version"],
        "model_A_configuration_sha256": digest_path(paths["phase5b_dir"] / "experiment_A.private.json"),
        "phase5b_manifest_sha256": digest_path(paths["phase5b_dir"] / "integrity_manifest.private.json"),
        "selection": "all authorized source records and preserved outcomes; no new clinical rules",
        "external_unavailable_evidence": "explicitly unknown; not a precondition for diagnostic generation",
        "implementation_sha256": {path.name: digest_path(path) for path in sorted(Path(__file__).parent.glob("epidemiology_review*.py"))},
        "training_enabled": False, "materialization_enabled": False}, output / "metadata.private.json")
    require_preserved(before, protected_snapshot(root, output))
    write_report({"version": VERSION, "protected_files_sha256": before, "previous_artifacts_preserved": True,
        "outputs_sha256": {path.name: digest_path(path) for path in sorted(output.iterdir()) if path.is_file()}}, output / "integrity_manifest.private.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[4]
        report = run_review(root, read_json(args.config))
        print(json.dumps({"version": VERSION, "sources_audited": len(report["classification_sources"]),
            "status": "awaiting_responsible_decisions", "training_performed": False,
            "negatives_materialized": False, "external_documentation_blocked_diagnostic": False}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 5B.1. Revisar integridad/autorización privadas; no volcar registros.\n")


if __name__ == "__main__":
    main()
