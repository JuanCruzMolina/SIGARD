"""Reutiliza Fases 2/3; recupera identidad opaca y fechas con semántica identificada."""

import hashlib
import json

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.episodes import event_reference
from sigard_ml.official.excel import file_digest, find_header, open_authorized_workbook, read_sheet, value_type
from sigard_ml.official.observed_dates import DATE_HIERARCHY, identify_reference_header, original_date_text, parse_reference_date
from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.pipeline import sheet_options
from sigard_ml.official.spatial_pipeline import digest_path, read_authorized_normalized
from sigard_ml.official.validation import field_values


def read_event_references(config, registry, repo_root):
    """Misma clave de fila de Fase 2. Ningún identificador original sale de memoria."""
    specifications = {spec["source_id"]: spec for spec in config["sources"]}
    rows, date_schemas = [], []
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.PROCESSING)
        digest = file_digest(source)
        if source.all_sheets_approved:
            with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
                sheets = tuple(workbook.sheetnames)
        else:
            sheets = source.sheets
        layouts = sheet_options(config, specifications[source.source_id])
        for number, sheet in enumerate(sheets, 1):
            sheet_ref = f"sheet_{number:02d}"
            layout = layouts.get(sheet, layouts.get(sheet_ref, {}))
            frame, schema = read_sheet(source, sheet, header_row=layout.get("header_row"), column_map=layout.get("column_map"))
            with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
                _, headers = find_header(workbook[sheet], schema["header_row"])
            date_columns = {}
            for index, header in enumerate(headers, 1):
                field = identify_reference_header(header)
                if field:
                    if field in date_columns:
                        raise ValueError("Encabezados temporales duplicados requieren revisión explícita")
                    date_columns[field] = f"column_{index:03d}"
            if date_columns.get("symptom_onset") != schema["fields"].get("symptom_onset"):
                raise ValueError("El inicio de síntomas configurado no tiene semántica identificada")
            date_schemas.append({"source_id": source.source_id, "sheet_ref": sheet_ref,
                "source_sha256": digest, "header_row": schema["header_row"], "identified_date_columns": date_columns,
                "format_convention": "day_first_four_digit_year_or_native_excel_date",
                "administrative_dates_used": False})
            identifiers = field_values(frame, schema["fields"], "event_id")
            for excel_row, identifier in zip(frame.index, identifiers, strict=True):
                row = {"source_id": source.source_id, "sheet_ref": sheet_ref,
                             "record_ref": hashlib.sha256(f"{digest}:{excel_row}".encode()).hexdigest(),
                             "event_ref": event_reference(identifier)}
                onset_column = date_columns.get("symptom_onset")
                original = frame.at[excel_row, onset_column] if onset_column else None
                row["fecha_inicio_sintomas_original"] = original_date_text(original)
                row["tipo_valor_fecha_inicio_sintomas_original"] = value_type(original)
                for field in DATE_HIERARCHY[1:]:
                    column = date_columns.get(field)
                    raw = frame.at[excel_row, column] if column else None
                    row[field], row[field + "_status"] = parse_reference_date(raw)
                    row[field + "_column_ref"] = column
                rows.append(row)
        if file_digest(source) != digest:
            raise ValueError("Una fuente cambió al recuperar referencias de identidad")
    return pd.DataFrame(rows), date_schemas


def load_existing_assignments(normalized, provenance, options, repo_root):
    directory = (repo_root / options["spatial_dir"]).resolve()
    allowed = (repo_root / "data/interim/official").resolve()
    if not directory.is_relative_to(allowed):
        raise ValueError("Las asignaciones deben proceder de Fase 3 privada")
    report_path = directory / "geographic_quality.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads((directory / "integrity_manifest.json").read_text(encoding="utf-8"))
    for name in ("assignments.parquet", "geographic_quality.json"):
        if digest_path(directory / name) != manifest["outputs_sha256"][name]:
            raise ValueError("Una salida de Fase 3 difiere de su manifiesto")
    expected = {(item["source_id"], item["sheet_ref"]): item["normalized_sha256"]
                for item in report["provenance"]["sources"]}
    current = {(item["source_id"], item["sheet_ref"]): item["normalized_sha256"] for item in provenance["sources"]}
    if current != expected or provenance["quality_report_sha256"] != report["provenance"]["quality_report_sha256"]:
        raise ValueError("Los normalizados no son los diagnosticados en Fase 3")
    assignments = pd.read_parquet(directory / "assignments.parquet")
    if len(assignments) != len(normalized) or assignments.duplicated(ROW_KEY).any():
        raise ValueError("La asignación no conserva una salida por fila normalizada")
    columns = ROW_KEY + ["radio_candidate", "assignment_state", "geometry_status", "geocoding_category",
                         "uncertainty_reasons", "distance_to_boundary_m", "alternative_radios", "alternative_basis",
                         "coordinate_group_ref", "coordinate_group_size", "crs_confirmed", "location_role"]
    matched = normalized.merge(assignments[columns], on=ROW_KEY, how="outer", validate="one_to_one", indicator=True)
    if not matched._merge.eq("both").all():
        raise ValueError("Claves de Fase 2 y Fase 3 incompatibles")
    unique = matched.geometry_status.eq("unique_interior")
    if matched.radio_candidate.notna().ne(unique).any():
        raise ValueError("Un candidato no corresponde a un interior geométrico único")
    if digest_path(repo_root / options["cartography"]) != report["cartography"]["master_sha256"]:
        raise ValueError("La cartografía ya no es la utilizada en Fase 3")
    return matched.drop(columns="_merge"), {"transformation_version": report["transformation_version"],
             "assignment_sha256": digest_path(directory / "assignments.parquet"),
             "report_sha256": digest_path(report_path), "cartography_sha256": report["cartography"]["master_sha256"],
             "geographic_evidence": report["geographic_evidence"]}


def read_observed_inputs(config, registry, options, repo_root):
    normalized, provenance = read_authorized_normalized(config, registry, repo_root)
    identities, date_schemas = read_event_references(config, registry, repo_root)
    if identities.duplicated(ROW_KEY).any() or len(identities) != len(normalized):
        raise ValueError("Las referencias recuperadas no conservan las filas de Fase 2")
    # Sólo reemplaza candidatos temporales en memoria; Fase 2 permanece inmutable.
    alternative_columns = [field + suffix for field in DATE_HIERARCHY[1:] for suffix in ("", "_status")]
    normalized = normalized.drop(columns=alternative_columns, errors="ignore")
    normalized = normalized.merge(identities, on=ROW_KEY, how="outer", validate="one_to_one", indicator=True)
    if not normalized._merge.eq("both").all():
        raise ValueError("No coincide la identidad técnica entre fuentes y normalizados")
    normalized = normalized.drop(columns="_merge")
    frame, spatial = load_existing_assignments(normalized, provenance, options, repo_root)
    return frame.reset_index(drop=True), {"normalization": provenance, "spatial_assignment": spatial,
                                         "reference_date_schema": date_schemas}
