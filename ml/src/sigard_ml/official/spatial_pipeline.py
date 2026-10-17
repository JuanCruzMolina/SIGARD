"""CLI privado de Fase 3: reutiliza normalizados y autorizaciones de Fase 2."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from sigard_ml.ingestion.territorial import load_cartography
from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.cartography import audit_cartography, read_radios
from sigard_ml.official.excel import file_digest, open_authorized_workbook
from sigard_ml.official.pipeline import load_configuration, require_expected_digest
from sigard_ml.official.reports import write_report
from sigard_ml.official.settings import REPORT_VERSION
from sigard_ml.official.spatial_assignment import assign_coordinates, validate_assignment_options
from sigard_ml.official.spatial_reports import boundary_sensitivity, geographic_quality, viability_text
from sigard_ml.official.spatial_settings import SPATIAL_DEFAULTS, SPATIAL_VERSION


def digest_path(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def protected_snapshot(repo_root, output):
    """Huellas privadas: fuentes, Fase 2, cartografía y artefactos científicos."""
    snapshot = {}
    for folder in ("data", "ml/artifacts", "ml/models", "frontend/public/data"):
        root = repo_root / folder
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.resolve().is_relative_to(output):
                    snapshot[str(path.relative_to(repo_root))] = digest_path(path)
    return snapshot


def require_preserved(before, after):
    if before != after:
        raise ValueError("Una fuente o artefacto protegido cambió durante el diagnóstico")


def private_output_directory(options, repo_root):
    output = (repo_root / options["output_dir"]).resolve()
    allowed = (repo_root / "data/interim/official").resolve()
    # Evita escribir sobre la carpeta de Fase 2, sus normalizados o sus fuentes.
    if not output.is_relative_to(allowed) or output == allowed or output.is_relative_to(allowed / "normalized"):
        raise ValueError("Fase 3 requiere una subcarpeta privada independiente en interim/official")
    names = {"assignments.parquet", "geographic_quality.json", "territorial_viability.md", "integrity_manifest.json"}
    if output.exists() and any(path.name not in names for path in output.iterdir()):
        raise ValueError("La carpeta de salida contiene avances ajenos a Fase 3")
    return output


def read_authorized_normalized(config, registry, repo_root):
    """Usa sólo hojas autorizadas y exige que sus fuentes sigan siendo las de Fase 2."""
    directory = (repo_root / config["output_dir"]).resolve()
    allowed = (repo_root / "data/interim/official").resolve()
    if not directory.is_relative_to(allowed):
        raise ValueError("Los normalizados deben proceder del interim oficial privado")
    quality_path = directory / "quality_report.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if quality.get("transformation_version") != REPORT_VERSION:
        raise ValueError("Versión de normalización no soportada")
    reports = {item["source_id"]: item for item in quality["sources"]}
    specifications = {item["source_id"]: item for item in config["sources"]}
    frames, provenance = [], []
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.PROCESSING)
        digest = file_digest(source)
        require_expected_digest(specifications[source.source_id], digest)
        report = reports[source.source_id]
        if report["source_sha256"] != digest or report["source_version"] != source.source_version:
            raise ValueError("El normalizado no corresponde a la fuente autorizada vigente")
        if source.all_sheets_approved:
            with open_authorized_workbook(source, AuthorizedUse.PROCESSING) as workbook:
                sheets = tuple(workbook.sheetnames)
        else:
            sheets = source.sheets
        expected_refs = [f"sheet_{index:02d}" for index in range(1, len(sheets) + 1)]
        if [item["sheet_ref"] for item in report["sheets"]] != expected_refs:
            raise ValueError("Las hojas normalizadas no coinciden con el alcance autorizado")
        for sheet_ref, sheet in zip(expected_refs, sheets, strict=True):
            source.require_use(sheet=sheet, subset_ref=source.subset_ref, use=AuthorizedUse.PROCESSING)
            path = directory / "normalized" / f"{source.source_id}_{sheet_ref}.parquet"
            if not path.resolve().is_relative_to(directory / "normalized"):
                raise ValueError("Derivado fuera de la carpeta normalizada")
            normalized = pd.read_parquet(path)
            if not normalized.source_id.eq(source.source_id).all():
                raise ValueError("Procedencia inconsistente del normalizado")
            # La referencia incluye hoja; las referencias de Fase 2 no se reescriben.
            normalized = normalized.copy()
            normalized["sheet_ref"] = sheet_ref
            frames.append(normalized)
            provenance.append({"source_id": source.source_id, "source_version": source.source_version,
                               "source_sha256": digest, "sheet_ref": sheet_ref,
                               "normalized_sha256": digest_path(path)})
        if file_digest(source) != digest:
            raise ValueError("Una fuente cambió durante la lectura")
    if not frames:
        raise ValueError("No hay normalizados autorizados")
    frame = pd.concat(frames, ignore_index=True)
    return frame, {"normalization_version": quality["transformation_version"],
                   "quality_report_sha256": digest_path(quality_path), "sources": provenance,
                   "source_periods": quality.get("summary", {}).get("dates", {})}


def assignment_options(config, options):
    geography = config.get("geography", {})
    confirmed = geography.get("crs_confirmed", False)
    coordinate_crs = geography.get("crs") if confirmed else options["assumed_crs"]
    if confirmed and not coordinate_crs:
        raise ValueError("CRS confirmado sin declaración")
    # El contrato de los normalizados de Fase 2 almacena candidatos en grados.
    if confirmed and coordinate_crs != "EPSG:4326":
        raise ValueError("El contrato normalizado de Fase 2 requiere candidatos EPSG:4326")
    result = {name: options[name] for name in ("boundary_review_m", "documented_uncertainty_m",
              "uncertainty_evidence_ref", "location_role", "geocoding_provenance_ref")}
    result.update(coordinate_crs=coordinate_crs, crs_confirmed=confirmed)
    validate_assignment_options(**{key: result[key] for key in ("coordinate_crs", "crs_confirmed",
                                "boundary_review_m", "documented_uncertainty_m", "uncertainty_evidence_ref", "location_role")})
    distances = options["sensitivity_distances_m"]
    if not isinstance(distances, list) or any(type(value) not in (int, float) or
                                            not math.isfinite(value) or value <= 0 for value in distances):
        raise ValueError("Distancias de sondeo inválidas")
    return result


def run_spatial_diagnostics(config, registry, options, repo_root):
    output = private_output_directory(options, repo_root)
    parameters = assignment_options(config, options)
    if not registry.sources:
        raise ValueError("No hay fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    before = protected_snapshot(repo_root, output)
    frame, provenance = read_authorized_normalized(config, registry, repo_root)
    radios = read_radios(repo_root / options["cartography"])
    territorial_config = json.loads((repo_root / options["territorial_config"]).read_text(encoding="utf-8"))
    reference = load_cartography(territorial_config, repo_root)
    cartography = audit_cartography(radios, reference=reference)
    cartography["master_sha256"] = digest_path(repo_root / options["cartography"])
    assignments = assign_coordinates(frame, radios, **parameters)
    assignments["transformation_version"] = SPATIAL_VERSION
    assignments["cartography_sha256"] = cartography["master_sha256"]
    assignments["coordinate_crs"] = parameters["coordinate_crs"]
    assignments["data_kind"] = config.get("data_kind", "official_observed")
    assignments["record_unit"] = "unresolved_source_record"
    sensitivity = boundary_sensitivity(frame, assignments, radios, parameters["coordinate_crs"],
                                       sorted(set(options["sensitivity_distances_m"])))
    report = {"transformation_version": SPATIAL_VERSION, "data_kind": config.get("data_kind", "official_observed"),
              "unit": "unresolved_source_record", "cartography": cartography,
              "provenance": provenance,
              "geographic_evidence": {"crs_confirmed": parameters["crs_confirmed"],
                   "coordinate_crs": parameters["coordinate_crs"], "axis_order": "x_longitude_y_latitude",
                   "crs_assumed_for_diagnosis": not parameters["crs_confirmed"],
                   "location_role": parameters["location_role"],
                   "provenance_documented": bool(parameters["geocoding_provenance_ref"]),
                   "documented_uncertainty_available": parameters["documented_uncertainty_m"] is not None,
                   "documented_uncertainty_m": parameters["documented_uncertainty_m"],
                   "boundary_review_m": parameters["boundary_review_m"]},
              "summary": geographic_quality(assignments, sensitivity),
              "protected_inputs_and_scientific_artifacts_unchanged": True}
    require_preserved(before, protected_snapshot(repo_root, output))
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "assignments.tmp"
    assignments.to_parquet(temporary, index=False)
    temporary.replace(output / "assignments.parquet")
    write_report(report, output / "geographic_quality.json")
    temporary = output / "territorial_viability.tmp"
    temporary.write_text(viability_text(report), encoding="utf-8")
    temporary.replace(output / "territorial_viability.md")
    require_preserved(before, protected_snapshot(repo_root, output))
    write_report({"transformation_version": SPATIAL_VERSION, "protected_files_sha256": before,
                  "outputs_sha256": {name: digest_path(output / name) for name in
                                     ("assignments.parquet", "geographic_quality.json", "territorial_viability.md")}},
                 output / "integrity_manifest.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Manifiesto privado existente de Fase 2")
    parser.add_argument("--spatial-config", type=Path, help="Parámetros geográficos sin registros")
    parser.add_argument("--diagnose-failure", action="store_true", help="Muestra sólo tipo de error y función/línea, sin valores")
    arguments = parser.parse_args()
    try:
        repo_root = Path(__file__).resolve().parents[4]
        config, registry = load_configuration(arguments.config, repo_root)
        options = dict(SPATIAL_DEFAULTS)
        if arguments.spatial_config:
            overrides = json.loads(arguments.spatial_config.read_text(encoding="utf-8"))
            if not set(overrides) <= set(options):
                raise ValueError("Parámetro geográfico desconocido")
            options.update(overrides)
        report = run_spatial_diagnostics(config, registry, options, repo_root)
        # Sólo resumen con vocabulario cerrado y supresión de cantidades pequeñas.
        print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    except Exception as error:
        if arguments.diagnose_failure:
            trace = error.__traceback__
            locations = []
            while trace is not None:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó el diagnóstico geográfico. Revisar autorización, normalizados y cartografía localmente; no volcar filas.\n")


if __name__ == "__main__":
    main()
