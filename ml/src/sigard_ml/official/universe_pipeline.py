"""Fase 4.3 privada: lee salidas preservadas, produce diagnósticos, nunca paneles."""

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.coverage_pipeline import read_prior_panels, require_manifest
from sigard_ml.official.excel import read_sheet
from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.pipeline import load_configuration, sheet_options
from sigard_ml.official.settings import normalize_header
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, read_authorized_normalized, require_preserved
from sigard_ml.official.universe import (
    MISSING_DECLARATIONS, UNIVERSE_VERSION, candidate_intervals, declaration_readiness,
    panel_statistics, uncertainty_summary,
)
from sigard_ml.official.validation import field_values


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def residence_inventory(config, registry, structure, audits):
    """Lee sólo para agregación; nunca exporta celdas ni registros individuales."""
    specs = {item["source_id"]: item for item in config["sources"]}
    sources = []
    for source in registry.sources:
        report = next(item for item in structure["sources"] if item["source_id"] == source.source_id)
        if len(report["sheets"]) != 1:
            raise ValueError("La revisión de universo requiere resolver las hojas por fuente")
        schema_report = report["sheets"][0]
        sheet = source.sheets[0] if source.sheets else None
        if sheet is None:
            from sigard_ml.official.excel import open_authorized_workbook
            with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
                if len(workbook.sheetnames) != 1:
                    raise ValueError("Entrega con hojas no conciliadas")
                sheet = workbook.sheetnames[0]
        options = sheet_options(config, specs[source.source_id])
        layout = options.get(sheet, options.get("sheet_01", {}))
        frame, schema = read_sheet(source, sheet, header_row=layout.get("header_row"), column_map=layout.get("column_map"))
        fields = schema["fields"]
        provinces = pd.Series(field_values(frame, fields, "province"), dtype="object").map(normalize_header)
        departments = pd.Series(field_values(frame, fields, "department"), dtype="object").map(normalize_header)
        province_match = provinces.isin(["la rioja", "larioja"])
        department_match = departments.eq("capital")
        event = pd.Series(field_values(frame, fields, "event"), dtype="object").map(normalize_header)
        source_audit = audits[audits.source_id.eq(source.source_id)]
        if len(source_audit) != len(frame):
            raise ValueError("La fuente no concilia con las filas de la auditoría anterior")
        safe_headers = schema_report.get("safe_headers", {})
        sources.append({"source_id": source.source_id, "rows": len(frame),
            "residence_province_column": fields.get("province"), "residence_department_column": fields.get("department"),
            "province_header": safe_headers.get(fields.get("province")),
            "department_header": safe_headers.get(fields.get("department")),
            "rows_matching_la_rioja_capital_residence_labels": int((province_match & department_match).sum()),
            "province_missing": int(provinces.eq("").sum()), "department_missing": int(departments.eq("").sum()),
            "rows_not_matching_residence_labels": int((~(province_match & department_match)).sum()),
            "event_field_present": "event" in fields, "event_field_nonempty": int(event.ne("").sum()),
            "event_header": safe_headers.get(fields.get("event")), "event_semantics_verified": False,
            "event_label_mentions_dengue": int(event.str.contains(r"\bdengue\b", regex=True).sum()),
            "classification_column": fields.get("classification"),
            "classification_header": safe_headers.get(fields.get("classification")),
            "canonical_classifications": {str(key): int(value) for key, value in source_audit.classification.value_counts().items()},
            "notifier_header_refs": {key: value for key, value in safe_headers.items()
                if isinstance(value, str) and any(word in value for word in ("establecimiento", "notificacion", "carga"))},
            "clinical_confirmation_verified": False, "manual_filter_column_verified": False,
            "pre_manual_filter_records_available": False, "omitted_records_count": None})
    return {"sources": sources, "unit": "source_records_not_validated_unique_cases",
            "residence_headers_do_not_prove_manual_selection_basis": True,
            "confirmed_label_does_not_prove_laboratory_confirmation": True}


def source_periods(normalized):
    result = []
    for source, group in normalized.groupby("source_id", sort=True):
        fields = {}
        for field in ("symptom_onset", "sample_on"):
            values = group.loc[group[field + "_status"].eq("valid"), field].dropna()
            years = values.map(lambda value: value.year)
            if years.ge(2025).any():
                raise ValueError("La entrega cambió: revisar las fuentes antes de ampliar el diagnóstico")
            fields[field] = {"valid_records": len(values), "first": min(values).isoformat() if len(values) else None,
                "last": max(values).isoformat() if len(values) else None,
                "by_calendar_year": {str(int(year)): int(count) for year, count in years.value_counts().sort_index().items()}}
        result.append({"source_id": source, "records": len(group), "date_fields": fields,
            "requested_period_documented": False, "continuous_coverage_proven": False})
    return result


def declaration_template(source_ids):
    return {"status": "draft_not_signed_not_executable", "coverage_declarations": [],
        "interval_template": {"responsible_ref": None, "declared_on": None, "declaration_ref": None,
            "start": None, "end": None, "state": "complete", "source_ids": [], "date_panels": [],
            "radio_scope": "all_263_capital_radios", "geographic_basis": "patient_residence",
            "justification": None, "provenance_ref": None, "confidence": None,
            "case_definition_ref": None, "manual_filter_reconciliation_ref": None,
            "temporal_basis_statement": None, "pending_policy": "preserve_blockers",
            "experimental_approximation_acknowledged": False,
            "source_extractions": [{"source_id": source, "requested_start": None, "requested_end": None,
                "extraction_date_field": None, "extraction_cutoff": None, "original_export_ref": None,
                "confirmation_filter_column": None, "confirmation_filter_values": [],
                "geographic_filter_columns_and_values": {}} for source in sorted(source_ids)]},
        "missing_information": list(MISSING_DECLARATIONS), "generation_authorized": False}


def report_text(report):
    lines = ["# SIGARD Fase 4.3 — universo epidemiológico y cobertura asumida", "",
        "Diagnóstico privado; registros provisionales, no casos únicos validados.",
        "No se generaron ceros, etiquetas ni paneles. No se entrenó.",
        "Los intervalos candidatos son propuestas descriptivas y no declaraciones de completitud.", ""]
    for name, stats in report["statistics"].items():
        totals = stats["overall"]
        lines.extend([f"## Política temporal {name}", "",
            f"Positivos radio-semana: {totals['positive_observations_provisional']}; "
            f"ceros comprobados: {totals['verified_zero_observations']}; "
            f"ceros asumidos: {totals['assumed_zero_observations']}; desconocidos: {totals['unknown_observations']}.",
            f"Objetivos t+1: {totals['next_week_labels']}.",
            f"Capacidad condicional en envolventes candidatas: {totals['potential_negative_observations_conditional']} "
            f"observaciones negativas; {totals['potential_next_week_negatives_conditional']} objetivos negativos.",
            "Esas cantidades NO son negativos disponibles: requieren intervalos declarados, conciliación del universo y autorización.", ""])
        for row in stats["by_observation_year"]:
            lines.append(f"- {row['epidemiological_year']}: registros {row['provisional_records']}; "
                f"positivos {row['positive_observations_provisional']}; desconocidos {row['unknown_observations']}; "
                f"negativos potenciales condicionados {row['potential_negative_observations_conditional']}.")
        lines.extend(["", "Los agregados por radio y semana se conservan únicamente en archivos privados.", ""])
    lines.extend(["## Declaración necesaria", "", *[f"- {item}" for item in MISSING_DECLARATIONS], "",
        "Los 90 pendientes sin fecha no se restringen por el nombre del archivo. La completitud no elimina el bloqueo por pendientes.",
        "Las fechas de muestra y las ubicaciones aproximadas no se consideran exactas. Todos los objetivos siguen siendo provisionales.",
        "Sin negativos disponibles no es viable entrenar ni evaluar un clasificador binario de ambas clases.",
        "La disponibilidad histórica de registros y clasificaciones sigue sin reconstruirse.",
        "Las divisiones cronológicas son diagnósticas; excluyen la transición que cruza el corte y no eligen un corte por rendimiento.",
        "Detención: pendiente de declaración/evidencia y autorización para materializar el escenario exploratorio.", ""])
    return "\n".join(lines)


def run_review(repo_root, options):
    require_branch(repo_root)
    if options.get("version") != UNIVERSE_VERSION or options.get("generate_assumed_zeros") is not False or options.get("training_enabled") is not False:
        raise ValueError("Fase 4.3 sólo autoriza diagnóstico, sin ceros ni entrenamiento")
    output = (repo_root / options["output_dir"]).resolve()
    allowed = (repo_root / "data/interim/official/observed").resolve()
    prior_paths = [allowed / name for name in ("conservative", "exploratory", "date_recovery_041", "coverage_042")]
    if (not output.is_relative_to(allowed) or output == allowed or output.exists()
            or any(output.is_relative_to(path) or path.is_relative_to(output) for path in prior_paths)):
        raise ValueError("La revisión requiere una carpeta privada nueva, separada de las fases previas")
    before = protected_snapshot(repo_root, output)
    access_path = (repo_root / options["access_config"]).resolve()
    if not access_path.is_relative_to((repo_root / "data/interim/official").resolve()):
        raise ValueError("La autorización debe proceder de almacenamiento privado")
    config, registry = load_configuration(access_path, repo_root)
    normalized, provenance = read_authorized_normalized(config, registry, repo_root)
    _, audits, _ = read_prior_panels(allowed / "date_recovery_041", normalized, provenance)
    coverage = allowed / "coverage_042"
    require_manifest(coverage)
    metadata = read_json(coverage / "metadata.json")
    if metadata["provenance"]["normalization"] != provenance or metadata["analysis_period"] != {"start": "2020-01-01", "end": "2024-12-31"}:
        raise ValueError("La procedencia o el período no coincide con las fases anteriores")
    previous_options = read_json(coverage / "configuration.private.json")
    declaration_status = declaration_readiness(options["coverage_declarations"], set(normalized.source_id))
    structure = read_json(repo_root / "data/interim/official/structure_report.json")
    universe = residence_inventory(config, registry, structure, audits["expanded"])
    statistics, candidates = {}, {}
    for policy in ("strict", "expanded"):
        # No modifica el escenario conservador; sólo lee y diagnostica su copia en memoria.
        panel = pd.read_parquet(coverage / policy / "conservative/panel.parquet")
        candidates[policy] = candidate_intervals(audits[policy])
        statistics[policy] = panel_statistics(panel, candidates[policy], options["evaluation_starts"])
        if int(panel.casos_observados.sum()) != int(audits[policy].processing_outcome.eq("included").sum()):
            raise ValueError("No concilian los conteos provisionales anteriores")
    supporting = [allowed / "date_recovery_041/comparison.private.json", coverage / "viability.private.json",
                  coverage / "coverage_inventory.private.json", repo_root / "data/interim/official/period_audit_20202026/audit.private.json"]
    report = {"version": UNIVERSE_VERSION, "status": "awaiting_declaration_and_user_authorization",
        "target": "next_week_at_least_one_provisional_confirmed_dengue_record_in_radio",
        "methodological_limit": "No equivale todavía a probabilidad de caso clínicamente validado ni ubicación espacial real.",
        "analysis_period": metadata["analysis_period"], "data_kind": "official_observed",
        "provenance": provenance, "supporting_reports_sha256": {path.relative_to(repo_root).as_posix(): digest_path(path) for path in supporting},
        "previous_provenance_declaration": previous_options["provenance_declaration"],
        "previous_source_period_declarations": previous_options["source_period_declarations"],
        "previous_coverage_declarations": previous_options["coverage_declarations"],
        "previous_coverage_verifications": previous_options["coverage_verifications"],
        "previous_delay_evidence": read_json(allowed / "date_recovery_041/comparison.private.json").get("delay_evidence", {}),
        "previous_classification_inventory": read_json(allowed / "exploratory/classification_inventory.private.json"),
        "universe": universe, "source_periods": source_periods(normalized), "candidate_intervals": candidates,
        "uncertainty": uncertainty_summary(audits["strict"], audits["expanded"]), "statistics": statistics,
        "declaration_readiness": declaration_status, "assumed_zeros_generated": False,
        "panels_regenerated": False, "calendar_audit_repeated": False, "training_performed": False,
        "geographic_evidence": read_json(repo_root / "data/interim/official/geography/geographic_quality.json")["geographic_evidence"]}
    geography_report = read_json(repo_root / "data/interim/official/geography/geographic_quality.json")
    report["previous_geographic_sensitivity"] = geography_report.get("summary", {}).get("boundary_sensitivity", {})
    require_preserved(before, protected_snapshot(repo_root, output))
    output.mkdir(parents=True, exist_ok=False)
    def save_json(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    save_json("review.private.json", report)
    save_json("configuration.private.json", options)
    save_json("declaration.template.private.json", declaration_template(set(normalized.source_id)))
    for policy, stats in statistics.items():
        for name in ("by_observation_year", "by_target_year", "by_radio", "by_week", "chronological_splits"):
            pd.json_normalize(stats[name]).to_parquet(output / f"{policy}.{name}.private.parquet", index=False)
    (output / "review.private.md").write_text(report_text(report), encoding="utf-8")
    require_preserved(before, protected_snapshot(repo_root, output))
    save_json("integrity_manifest.private.json", {"protected_files_sha256": before, "protected_files_unchanged": True,
        "outputs_sha256": {path.name: digest_path(path) for path in sorted(output.iterdir()) if path.is_file()}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    report = run_review(root, read_json(args.config))
    print(json.dumps({"status": report["status"], "assumed_zeros_generated": False,
        "policies": {name: stats["overall"] for name, stats in report["statistics"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
