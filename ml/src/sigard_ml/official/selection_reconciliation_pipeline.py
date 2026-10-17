"""Fase 5B.2: Excel locales autorizados -> exclusivamente agregados privados.

Nunca imprime filas, etiquetas libres, identificadores ni excepciones de lectura.
No importa SDKs remotos, geocodificadores o entrenadores. No escribe tablas de filas.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import secrets
import subprocess

from sigard_ml.official.access import AuthorizedUse, SourceAuthorization
from sigard_ml.official.excel import find_header, is_empty, open_authorized_workbook
from sigard_ml.official.observed_pipeline import require_branch
from sigard_ml.official.reports import write_report
from sigard_ml.official.settings import identify_column, normalize_header, safe_header
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.selection_reconciliation import VERSION, compare, profile, project_record

ROLES = ("original", "manual_working", "processed")
FIELDS = {"event_id", "province", "department", "address", "symptom_onset", "sample_on", "notified_on", "updated_on"}


def validate_manifest(options, root):
    allowed = (root / "data/interim/official").resolve()
    output = (root / options["output_dir"]).resolve()
    if options.get("version") != VERSION or options.get("training_enabled") is not False or options.get("generate_negatives") is not False:
        raise ValueError("Acciones fuera del alcance de conciliación")
    if not allowed.is_relative_to(root.resolve()) or output.parent != allowed or output.exists():
        raise ValueError("Se requiere un destino oficial privado nuevo")
    if options.get("local_aggregate_processing_authorized") is not True:
        raise PermissionError("Falta autorización local para los archivos listados")
    chains = options["sources"]
    if not chains or len({entry["source_id"] for entry in chains}) != len(chains):
        raise ValueError("Fuentes vacías o repetidas")
    for entry in chains:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", entry["source_id"]):
            raise ValueError("Identificador de fuente inválido")
        if entry.get("manual_copy_status") not in {"unknown", "provided", "not_retained", "no_separate_copy"}:
            raise ValueError("Debe distinguirse la copia intermedia")
        for role in ROLES:
            spec = entry.get(role)
            if spec is None:
                continue
            configured = Path(spec["path"])
            path = configured.resolve()
            if not configured.is_absolute() or path.suffix.lower() != ".xlsx":
                raise ValueError("Se requiere una ruta local XLSX explícita")
            if path.is_relative_to((root / "frontend/public").resolve()) or path.is_relative_to(output):
                raise ValueError("Fuente en una ubicación pública o de salida")
            if spec.get("private_local_file_confirmed") is not True:
                raise PermissionError("La fuente debe estar identificada como archivo local privado")
            if path.is_relative_to(root.resolve()):
                result = subprocess.run(["git", "check-ignore", "--quiet", "--", str(path)], cwd=root,
                    capture_output=True, check=False)
                if result.returncode != 0:
                    raise PermissionError("Fuente del repositorio no excluida de Git")
            else:
                result = subprocess.run(["git", "-C", str(path.parent), "check-ignore", "--quiet", "--", str(path)],
                    capture_output=True, check=False)
                if result.returncode not in {0, 128}:  # 128: la carpeta local no pertenece a un repositorio Git.
                    raise PermissionError("Fuente externa perteneciente a Git sin exclusión")
            if not isinstance(spec.get("source_version"), str) or not spec["source_version"].strip():
                raise ValueError("Debe declararse versión de cada rol")
        if entry.get("manual_working") is not None and entry["manual_copy_status"] != "provided":
            raise ValueError("Rol de copia intermedia contradictorio")
        if entry.get("manual_copy_status") == "provided" and entry.get("manual_working") is None:
            raise ValueError("Falta la ruta de la copia intermedia declarada")
    return output


def source_authorization(source_id, role, spec):
    return SourceAuthorization(source_id + "_" + role, spec["source_version"], Path(spec["path"]).resolve(),
        tuple(spec.get("sheets", [])), "explicit_whole_file_local_reconciliation",
        approved_extract=True, enabled=True, uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
        evidence_ref="responsible_phase5b2_explicit_paths_and_local_analysis_request",
        custodian_ref="project_responsible", confidentiality_ref="local_aggregates_no_patient_output",
        storage_policy_ref="private_git_excluded_derivatives", all_sheets_approved=not bool(spec.get("sheets")))


def resolve_columns(headers, explicit):
    candidates = defaultdict(list)
    classes = {}
    for index, header in enumerate(headers, 1):
        field = identify_column(header)
        if field in FIELDS:
            candidates[field].append(index)
        if field == "opened_on":
            candidates["notified_on"].append(index)
        if "clasif" in normalize_header(header):
            classes[f"column_{index:03d}"] = index
    columns = {field: indexes[0] for field, indexes in candidates.items() if len(indexes) == 1}
    explicit = explicit or {}
    if set(explicit) - FIELDS - {"classification_columns"}:
        raise ValueError("Campos no habilitados para cotejo")
    for field, index in explicit.items():
        if field == "classification_columns":
            continue
        if type(index) is not int or not 1 <= index <= len(headers):
            raise ValueError("Índice de columna inválido")
        detected = identify_column(headers[index - 1])
        if detected is not None and detected not in {field, "opened_on" if field == "notified_on" else field}:
            raise ValueError("El índice configurado contradice un encabezado reconocido")
        columns[field] = index
    for name, index in explicit.get("classification_columns", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or type(index) is not int or not 1 <= index <= len(headers):
            raise ValueError("Columna de clasificación inválida")
        detected = identify_column(headers[index - 1])
        if detected is not None and detected not in {"classification", "algorithm_classification"}:
            raise ValueError("No se admite una columna personal como clasificación")
        classes = {key: value for key, value in classes.items() if not (key.startswith("column_") and value == index)}
        classes[name] = index
    columns["classification_columns"] = classes
    return columns


def cross_source_overlap(index):
    groups = [counts for counts in index.values() if len(counts) > 1]
    return {"equal_literal_identifier_groups_across_source_mappings": len(groups),
        "records_in_cross_source_identifier_groups": sum(sum(counts.values()) for counts in groups),
        "global_identifier_semantics_or_episode_equivalence_validated": False,
        "duplicates_removed": False, "identifiers_exported": False}


def read_local_role(source_id, role, spec, key):
    source = source_authorization(source_id, role, spec)
    before = digest_path(source.path)
    if spec.get("expected_sha256") and spec["expected_sha256"] != before:
        raise ValueError("La fuente cambió respecto a su hash configurado")
    records, schemas = [], []
    with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
        sheets = source.sheets if source.sheets else tuple(workbook.sheetnames)
        for index, sheet in enumerate(sheets, 1):
            source.require_use(sheet=sheet, subset_ref=source.subset_ref, use=AuthorizedUse.PROCESSING)
            worksheet = workbook[sheet]
            header_row, headers = find_header(worksheet, spec.get("header_row"))
            columns = resolve_columns(headers, spec.get("columns"))
            schemas.append({"sheet_ref": f"sheet_{index:02d}", "header_row": header_row,
                "columns": columns, "safe_headers": {f"column_{i:03d}": safe_header(header) for i, header in enumerate(headers, 1)}})
            for values in worksheet.iter_rows(min_row=header_row + 1, values_only=True):
                if all(is_empty(value) for value in values):
                    continue
                records.append(project_record(values, columns, key, source_id))
    if digest_path(source.path) != before:
        raise ValueError("La fuente cambió durante la lectura")
    return records, {"role": role, "path": str(source.path), "source_version": spec["source_version"],
        "sha256": before, "schemas": schemas, "profile": profile(records),
        "requested_period": spec.get("requested_period"), "extraction_period": spec.get("extraction_period"),
        "extracted_on": spec.get("extracted_on"), "extraction_date_field": spec.get("extraction_date_field"),
        "coverage_evidence_ref": spec.get("coverage_evidence_ref"),
        "workbook_created_modified_prove_extraction_date": False, "continuous_coverage_proven": False}


def validate_rule(rule):
    for name in ("accepted_classification_labels", "province_values", "department_values"):
        if not isinstance(rule.get(name), list) or not rule[name] or any(not isinstance(value, str) or not value.strip() for value in rule[name]):
            raise ValueError("La hipótesis requiere valores literales explícitos")
    if not isinstance(rule.get("classification_field"), str) or not rule["classification_field"]:
        raise ValueError("Debe declararse la columna de clasificación del criterio")
    if rule.get("require_valid_reference_date") not in {None, False, True} or rule.get("require_address_present") not in {None, False, True}:
        raise ValueError("Filtros de fecha/domicilio inválidos")
    if rule.get("reference_date_field") not in {"symptom_onset", "sample_on", "notified_on"}:
        raise ValueError("Campo temporal de referencia no declarado")


def report_text(report):
    lines = ["# SIGARD Fase 5B.2 — conciliación privada y agregada", "",
        "Sólo agregados. No se exportan identificadores (ni sus hashes), filas clínicas, nombres, documentos, domicilios o coordenadas.",
        "Los cotejos de ID son candidatos de fila, no equivalencia de episodios; no se eliminaron duplicados.",
        "Una regla literal reproducible no valida por sí sola confirmación clínica. La semántica y el filtro original requieren evidencia del responsable.", ""]
    for source in report["sources"]:
        lines += [f"## {source['source_id']}", "", f"Copia de trabajo: {source['manual_copy_status']}."]
        for role, metadata in source["files"].items():
            lines += [f"- {role}: {metadata['profile']['records']} registros; versión {metadata['source_version']}; SHA-256 en el JSON privado."]
        for pair, result in source["comparisons"].items():
            lines += ["", f"### {pair}", ""]
            lines += [f"- {name}: {count}." for name, count in result["counts"].items()]
        lines += ["", "Los inventarios completos de etiquetas y residencia, las columnas y las fechas clínicas agregadas están en report.private.json; no se imprimen en consola.",
            "Los motivos registrados son los de la hipótesis programada, no causas históricas inferidas. Fecha/domicilio ausente en una fila omitida no prueba que ese fuera el motivo manual de exclusión.", ""]
    lines += ["## Cobertura y límites", "",
        "Período solicitado, período/campo de extracción, fecha de corte y fechas clínicas observadas se informan por separado. Los metadatos de creación/modificación del Excel no prueban la extracción.",
        "Ninguna ausencia, etiqueta, extremo de fechas, nombre de archivo o coincidencia de selección declara completitud automáticamente.",
        "Para validar el procedimiento faltan, según el caso: regla original documentada, criterio histórico de confirmación, correspondencia explícita de archivos/campos, exportación/corte y conciliación del universo.",
        "La fuente configurada como 2022 debe revisarse con todos los campos de clasificación disponibles, sin cambiar etiquetas ni asumir confirmación desde su nombre.",
        "Originales y paneles anteriores preservados; sin geocodificación, negativos, entrenamiento, frontend/backend, commit, push o publicación.", ""]
    return "\n".join(lines)


def run_reconciliation(root, options, *, mode="compare"):
    require_branch(root)
    output = validate_manifest(options, root)
    if mode not in {"profile", "compare"}:
        raise ValueError("Modo no admitido")
    if any(not source.get("processed") or not source.get("original") for source in options["sources"]):
        raise ValueError("Faltan rutas explícitas de originales/procesados; no se deducen por nombre")
    before = protected_snapshot(root, output)
    key = secrets.token_bytes(32)  # Sólo RAM: agregados invariantes a esta clave; no es semilla de ML.
    report = {"version": VERSION, "mode": mode, "sources": [], "training_performed": False,
        "negatives_generated": False, "row_level_outputs_written": False, "identifiers_exported": False,
        "clinical_confirmation_validated": False, "network_services_used": False}
    all_input_hashes = {}
    cross_source = {role: defaultdict(Counter) for role in ROLES}
    for entry in options["sources"]:
        rows, files = {}, {}
        for role in ROLES:
            if entry.get(role) is not None:
                rows[role], files[role] = read_local_role(entry["source_id"], role, entry[role], key)
                if files[role]["path"] in all_input_hashes and all_input_hashes[files[role]["path"]] != files[role]["sha256"]:
                    raise ValueError("La fuente cambió entre roles")
                all_input_hashes[files[role]["path"]] = files[role]["sha256"]
                for row in rows[role]:
                    if row["cross_source_key"] is not None:
                        cross_source[role][row["cross_source_key"]][entry["source_id"]] += 1
        comparisons = {}
        if mode == "compare":
            rule = entry["selection_rule"]
            validate_rule(rule)
            for role, metadata in files.items():
                selected_field = rule["classification_field"] if role == "original" else entry[role].get("comparison_classification_field", rule["classification_field"])
                for schema in metadata["schemas"]:
                    if not {"event_id", "province", "department"} <= set(schema["columns"]) or selected_field not in schema["columns"]["classification_columns"]:
                        raise ValueError("Esquema incompleto: ejecutar perfil local y documentar columnas explícitas")
            comparisons["original_to_processed"] = compare(rows["original"], rows["processed"], rule, entry["processed"].get("comparison_classification_field"))
            if "manual_working" in rows:
                comparisons["original_to_manual_working"] = compare(rows["original"], rows["manual_working"], rule, entry["manual_working"].get("comparison_classification_field"))
                intermediate_rule = {**rule, "classification_field": entry["manual_working"].get("comparison_classification_field", rule["classification_field"])}
                comparisons["manual_working_to_processed"] = compare(rows["manual_working"], rows["processed"], intermediate_rule, entry["processed"].get("comparison_classification_field"))
        report["sources"].append({"source_id": entry["source_id"], "manual_copy_status": entry["manual_copy_status"],
            "files": files, "comparisons": comparisons,
            "files_equal_by_sha256": [{"roles": [a, b], "same_bytes": files[a]["sha256"] == files[b]["sha256"]}
                for a in files for b in files if a < b],
            "selection_rule_hypothesis": entry.get("selection_rule"), "clinical_criterion_evidence_ref": entry.get("clinical_criterion_evidence_ref")})
    report["totals"] = {role: sum(source["files"].get(role, {}).get("profile", {}).get("records", 0) for source in report["sources"]) for role in ROLES}
    report["cross_source_identifier_overlap"] = {role: cross_source_overlap(index) for role, index in cross_source.items()}
    report["totals_unit"] = "source-file rows over explicit role mappings; not unique persons or episodes"
    report["processed_total_matches_expected"] = report["totals"]["processed"] == options["expected_processed_records"]
    if not report["processed_total_matches_expected"]:
        raise ValueError("Los procesados no concilian con el total actual configurado")
    require_preserved(before, protected_snapshot(root, output))
    if any(digest_path(Path(path)) != expected for path, expected in all_input_hashes.items()):
        raise ValueError("Una fuente externa cambió durante la conciliación")
    output.mkdir(parents=True, exist_ok=False)
    write_report(report, output / "report.private.json")
    write_report(options, output / "configuration.private.json")
    (output / "report.private.md").write_text(report_text(report), encoding="utf-8")
    require_preserved(before, protected_snapshot(root, output))
    write_report({"version": VERSION, "protected_files_sha256": before, "inputs_sha256": all_input_hashes,
        "implementation_sha256": {path.name: digest_path(path) for path in sorted(Path(__file__).parent.glob("selection_reconciliation*.py"))},
        "outputs_sha256": {path.name: digest_path(path) for path in sorted(output.iterdir()) if path.is_file()}}, output / "integrity_manifest.private.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=["profile", "compare"], default="compare")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[4]
        options = json.loads(args.config.read_text(encoding="utf-8"))
        report = run_reconciliation(root, options, mode=args.mode)
        # Lista cerrada: no etiquetas clínicas, datos de filas, IDs, rutas o excepciones.
        print(json.dumps({"version": VERSION, "status": "aggregate_reconciliation_completed",
            "source_count": len(report["sources"]), "totals": report["totals"],
            "processed_total_matches_expected": report["processed_total_matches_expected"],
            "row_level_outputs_written": False, "training_performed": False, "negatives_generated": False}, sort_keys=True))
    except Exception:
        parser.exit(1, "Conciliación no completada. Revisar rutas, permisos, roles y esquema localmente; no volcar filas ni excepciones de datos.\n")


if __name__ == "__main__":
    main()
