"""CLI local de fase 2; nunca imprime celdas ni publica resultados."""

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from sigard_ml.official.access import AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.contracts import DataKind
from sigard_ml.official.excel import inspect_source, file_digest, open_authorized_workbook, read_sheet
from sigard_ml.official.geography import load_capital_boundary
from sigard_ml.official.normalization import DATE_FORMATS
from sigard_ml.official.reports import safe_structure, safe_quality, write_report, export_normalized, write_quality_summary
from sigard_ml.official.settings import REPORT_VERSION, LOW_PRECISION_DECIMALS
from sigard_ml.official.validation import validate_sheet


def load_configuration(path: Path, repo_root: Path | None = None) -> tuple[dict, SourceRegistry]:
    config = json.loads(path.read_text(encoding="utf-8"))
    DataKind(config.get("data_kind", "official_observed"))
    repo_root = repo_root or Path(__file__).resolve().parents[4]
    output = Path(config["output_dir"]).resolve()
    protected = [repo_root.resolve() / folder for folder in
                 ("data/interim/official", "data/processed/official")]
    if not any(output.is_relative_to(folder) for folder in protected):
        raise ValueError("La salida debe estar en un directorio oficial privado")
    if type(config.get("write_normalized", False)) is not bool:
        raise ValueError("write_normalized debe ser un booleano")
    if type(config.get("geography", {}).get("crs_confirmed", False)) is not bool:
        raise ValueError("crs_confirmed debe ser un booleano")
    root = Path(config["source_root"]).resolve(strict=True)
    sources = []
    for spec in config.get("sources", []):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", spec["source_id"]):
            raise ValueError("Referencia de fuente inválida")
        filename = spec["filename"]
        if Path(filename).name != filename or Path(filename).suffix.lower() != ".xlsx":
            raise ValueError("Nombre de fuente inválido")
        source_path = root / filename
        if source_path.resolve().parent != root:
            raise ValueError("Fuente fuera de la carpeta autorizada")
        uses = frozenset(AuthorizedUse(use) for use in config.get("uses", []))
        if not uses <= {AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}:
            raise ValueError("La fase 2 sólo habilita inspección y procesamiento")
        references = config.get("authorization", {})
        sources.append(SourceAuthorization(
            source_id=spec["source_id"], source_version=spec.get("source_version", "delivery-1"),
            path=source_path, sheets=tuple(spec.get("sheets", [])),
            subset_ref=spec.get("subset_ref", "whole_authorized_workbook"),
            approved_extract=spec.get("approved_extract", False), enabled=spec.get("enabled", False),
            uses=uses, all_sheets_approved=spec.get("all_sheets_approved", False),
            evidence_ref=references.get("evidence_ref"), custodian_ref=references.get("custodian_ref"),
            confidentiality_ref=references.get("confidentiality_ref"),
            storage_policy_ref=references.get("storage_policy_ref"),
        ))
    return config, SourceRegistry(tuple(sources))


def sheet_options(config, specification):
    layout = config.get("layouts", {}).get(specification.get("layout"), {})
    return specification.get("sheet_options", layout)


def require_expected_digest(specification, digest):
    expected = specification.get("expected_sha256")
    if expected is not None and digest != expected:
        raise ValueError("La fuente difiere de la versión autorizada en el manifiesto privado")


def inspect_delivery(config: dict, registry: SourceRegistry) -> dict:
    reports = []
    specifications = {spec["source_id"]: spec for spec in config.get("sources", [])}
    for source in registry.sources:
        before = file_digest(source)
        require_expected_digest(specifications[source.source_id], before)
        structure = inspect_source(source, sheet_options(config, specifications[source.source_id]))
        after = file_digest(source)
        if before != after:
            raise ValueError("La fuente cambió durante la lectura")
        structure["source_sha256"] = before
        reports.append(structure)
    return safe_structure({"report_version": REPORT_VERSION, "mode": "structure_only",
                           "source_count": len(reports), "sources": reports})


def validate_delivery(config, registry):
    geography = config.get("geography", {})
    if geography.get("crs_confirmed") and geography.get("crs") != "EPSG:4326":
        raise ValueError("No se transforman CRS durante fase 2")
    boundary = load_capital_boundary(Path(geography["capital_boundary"])) if geography.get("capital_boundary") else None
    as_of = date.fromisoformat(config["as_of_date"])
    specifications = {spec["source_id"]: spec for spec in config.get("sources", [])}
    reports, all_ids = [], []
    total_rows = total_complete = 0
    date_totals = {}
    geography_totals = Counter()
    classification_word_totals = Counter()
    precision_word_totals = Counter()
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.PROCESSING)
        before = file_digest(source)
        require_expected_digest(specifications[source.source_id], before)
        if source.all_sheets_approved:
            with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
                sheets = tuple(workbook.sheetnames)
        else:
            sheets = source.sheets
        options_by_sheet = sheet_options(config, specifications[source.source_id])
        sheet_reports, normalized_sheets = [], []
        for index, sheet in enumerate(sheets, 1):
            sheet_ref = f"sheet_{index:02d}"
            options = options_by_sheet.get(sheet, options_by_sheet.get(sheet_ref, {}))
            frame, schema = read_sheet(source, sheet, header_row=options.get("header_row"), column_map=options.get("column_map"))
            normalized, report, identifiers = validate_sheet(
                frame, schema, source_id=source.source_id, source_hash=before, as_of=as_of,
                boundary=boundary, crs_confirmed=geography.get("crs_confirmed", False),
                date_formats=tuple(config.get("date_formats", DATE_FORMATS)),
                allowed_classifications=config.get("allowed_classifications"),
                low_precision_decimals=geography.get("low_precision_decimals", LOW_PRECISION_DECIMALS))
            report["sheet_ref"] = sheet_ref
            sheet_reports.append(report)
            normalized_sheets.append((sheet_ref, normalized))
            total_rows += len(normalized)
            total_complete += report["structurally_complete"]
            for metric, value in report["geography"].items():
                if type(value) is int:
                    geography_totals[metric] += value
            classification_word_totals.update(report["classification_label_word_counts"])
            precision_word_totals.update(report["precision_label_word_counts"])
            for field, statistics in report["dates"].items():
                totals = date_totals.setdefault(field, Counter())
                for metric in ("valid", "missing", "invalid_format", "out_of_range", "future"):
                    totals[metric] += statistics[metric]
            all_ids.extend(identifier for identifier in identifiers if identifier is not None)
        if file_digest(source) != before:
            raise ValueError("La fuente cambió durante el procesamiento")
        if config.get("write_normalized", False):
            for sheet_ref, normalized in normalized_sheets:
                export_normalized(normalized, Path(config["output_dir"]) / "normalized", source.source_id, sheet_ref)
        reports.append({"source_id": source.source_id, "source_sha256": before,
                        "source_version": source.source_version, "sheets": sheet_reports})
    id_counts = Counter(all_ids)
    report = {"report_version": REPORT_VERSION, "mode": "preliminary_quality", "as_of_date": as_of.isoformat(),
              "data_kind": config.get("data_kind", "official_observed"), "unit": "unresolved_source_record",
              "transformation_version": REPORT_VERSION,
              "source_count": len(reports), "sources": reports,
              "summary": {"rows": total_rows, "structurally_complete": total_complete,
                          "incomplete_or_invalid": total_rows - total_complete,
                          "methodology_review_required": total_rows,
                          "dates": {field: dict(values) for field, values in date_totals.items()},
                          "geography": {**dict(geography_totals), "crs_confirmed": geography.get("crs_confirmed", False),
                                        "outside_capital_provisional": geography_totals["outside_capital_provisional"] if boundary is not None else None,
                                        "territorial_assignment_performed": False},
                          "classification_label_word_counts": dict(classification_word_totals),
                          "precision_label_word_counts": dict(precision_word_totals),
                          "repeated_event_id_rows_across_delivery": sum(count for count in id_counts.values() if count > 1),
                          "repeated_event_id_groups_across_delivery": sum(count > 1 for count in id_counts.values())},
              "questions_for_epidemiology": [
                  "Define record unit and stable episode identifier; repeated IDs are not automatically duplicates.",
                  "Validate classification domains, diagnostic groups and dengue eligibility in each delivery.",
                  "Choose epidemiological date and confirm missing date treatment and source coverage.",
                  "Confirm CRS, coordinate precision, geocoding provenance and residence meaning.",
                  "Define treatment of non-Capital residents and unassignable episodes.",
                  "Identify custodian and document retention, backups and access permissions.",
              ]}
    return safe_quality(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspección y calidad local de fuentes oficiales autorizadas")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inspect-only", action="store_true")
    arguments = parser.parse_args()
    try:
        config, registry = load_configuration(arguments.config)
        if not registry.sources:
            raise ValueError("No hay fuentes habilitadas")
        if arguments.inspect_only:
            report = inspect_delivery(config, registry)
            output = Path(config["output_dir"]) / "structure_report.json"
        else:
            report = validate_delivery(config, registry)
            output = Path(config["output_dir"]) / "quality_report.json"
        write_report(report, output)
        if not arguments.inspect_only:
            write_quality_summary(report, output.with_suffix(".md"))
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except Exception:
        # No imprimir str(exception), traceback ni variables locales.
        parser.exit(1, "El proceso no pudo completarse. Revisar autorización, configuración y formato localmente; no volcar celdas.\n")


if __name__ == "__main__":
    main()
