"""Fase 5A: sólo derivados privados preservados; sin ingestión ni entrenamiento."""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.coverage_pipeline import require_manifest
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import safe_count, write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.calendar_rules import CALENDAR_VERSION
from sigard_ml.official.spatial_ml import VERSION
from sigard_ml.official.spatial_ml.dataset import build_dataset, territorial_context
from sigard_ml.official.spatial_ml.diagnostics import diagnose
from sigard_ml.official.spatial_ml.features import KEYS, feature_definitions
from sigard_ml.official.spatial_ml.splits import DEFAULT_PLANS, evaluation_contract, prepare_splits

DEFAULTS = {
    "version": VERSION, "access_config": "data/interim/official/access.private.json",
    "observed_dir": "data/interim/official/observed/date_recovery_041",
    "coverage_dir": "data/interim/official/observed/coverage_042",
    "universe_dir": "data/interim/official/observed/universe_043_v1",
    "geography_dir": "data/interim/official/geography",
    "cartography": "data/processed/territorial_master.parquet",
    "territorial_config": "ml/configs/territorial_master.json",
    "output_dir": "data/processed/official/spatial_ml_05a_v2",
    "split_plans": list(DEFAULT_PLANS), "training_enabled": False, "generate_zeros": False,
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def private_paths(root, options):
    if set(options) != set(DEFAULTS) or options["version"] != VERSION or options["training_enabled"] is not False or options["generate_zeros"] is not False:
        raise ValueError("Fase 5A sólo admite preparación sin ceros ni entrenamiento")
    private = (root / "data/interim/official").resolve()
    inputs = {}
    for name in ("access_config", "observed_dir", "coverage_dir", "universe_dir", "geography_dir"):
        inputs[name] = (root / options[name]).resolve()
        if not inputs[name].is_relative_to(private) or inputs[name] == private:
            raise ValueError("Las entradas oficiales deben ser privadas")
    output = (root / options["output_dir"]).resolve()
    allowed = (root / "data/processed/official").resolve()
    if not allowed.is_relative_to(root.resolve()) or output.parent != allowed or output.exists():
        raise ValueError("Se requiere una carpeta privada nueva, sin sobrescribir salidas")
    for name in ("cartography", "territorial_config"):
        inputs[name] = (root / options[name]).resolve()
        if not inputs[name].is_relative_to(root.resolve()):
            raise ValueError("Entrada territorial fuera del repositorio")
    return inputs, output


def verify_private_manifest(directory):
    manifest = read_json(directory / "integrity_manifest.private.json")
    for name, expected in manifest["outputs_sha256"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest_path(path) != expected:
            raise ValueError("El informe anterior difiere de su manifiesto")


def verify_sources(registry, metadata):
    provenance = metadata["provenance"]["normalization"]["sources"]
    if {item["source_id"] for item in provenance} != {source.source_id for source in registry.sources}:
        raise ValueError("No coinciden las fuentes autorizadas")
    for source in registry.sources:
        expected = [item for item in provenance if item["source_id"] == source.source_id]
        if any(item["source_version"] != source.source_version or item["source_sha256"] != digest_path(source.path) for item in expected):
            raise ValueError("Las fuentes cambiaron desde las fases previas")


def report_text(report, diagnostics):
    lines = ["# SIGARD Fase 5A — informe privado de implementación", "",
        "Preparación retrospectiva, provisional y no apta para entrenamiento. No se entrenó ni se generaron ceros.",
        "Unidad: radio censal–semana de origen; objetivo: al menos un registro elegible provisional en t+1.",
        "Los conteos positivos no son casos clínicamente confirmados ni totales completos de vigilancia.", "",
        "## Características y estructura", "",
        "Predictores retrospectivos, calendario, etiquetas y contexto de auditoría se guardan separados por política de fechas y cobertura.",
        "Conteo en t; rezagos t-1 a t-4; acumulados [t-W,t-1] de 4/8/12 semanas. Null si falta una semana.",
        "Vecinos queen verificados con polígonos: se requieren todos los vecinos para cada suma semanal y todas las semanas para acumular.",
        "Se conservan indicadores de valor conocido, semanas/vecinos conocidos, año-SE, seno/coseno anual y código de radio.",
        "Área, población y densidad Censo 2022 son contexto retrospectivo. No se acredita su disponibilidad histórica ni se extrapolan poblaciones.",
        "Ninguna fecha de síntomas/muestra/notificación demuestra por sí sola cuándo estuvo disponible el registro o su clasificación.",
        "No se resta una demora inventada. Incluso rezagos antiguos requieren validación de disponibilidad punto en el tiempo.",
        "La etiqueta 2025-SE1 es sólo el borde parcial del período hasta 31/12/2024; no es cobertura observada de 2025.", ""]
    for name, summary in report["datasets"].items():
        lines += [f"## {name}", "", f"Grilla: {summary['cells']} combinaciones, {summary['radios']} radios y {summary['weeks']} semanas.",
            f"Registros provisionales: {safe_count(summary['provisional_records'])}; conteos conocidos: {safe_count(summary['known_observation_counts'])}.",
            f"Objetivos: positivos {safe_count(summary['labels']['positive'])}, negativos {safe_count(summary['labels']['negative'])}, desconocidos {safe_count(summary['labels']['unknown'])}.",
            "Fracción de registros de 2024: " + (f"{summary['records_2024_fraction']:.2%}" if summary['records_2024_fraction'] is not None else "no definida") + ".",
            f"Fechas aproximadas: {safe_count(summary['approximate_date_records'])}; asignaciones inciertas: {safe_count(summary['uncertain_assignment_records'])}.", "",
            f"Radios sin registros positivos incorporados: {summary['radios_without_positive_records']}; no se interpretan como radios negativos.", "",
            "### Disponibilidad de valores retrospectivos", ""]
        for feature in ("registros_retro_origen", "registros_retro_rezago_1", "registros_retro_acumulado_4", "registros_retro_acumulado_8", "registros_retro_acumulado_12", "vecinos_retro_rezago_1", "vecinos_retro_acumulado_4", "vecinos_retro_acumulado_8", "vecinos_retro_acumulado_12"):
            count = summary["feature_known_values"][feature]
            lines.append(f"- {feature}: {safe_count(count)} valores conocidos de {summary['cells']}; disponibilidad histórica no validada.")
        lines += ["",
            "### Diagnóstico por año epidemiológico de origen", ""]
        for row in diagnostics[name]["by_year"].to_dict("records"):
            lines.append(f"- {row['anio_epidemiologico']}: registros {safe_count(row['records_provisional']) if pd.notna(row['records_provisional']) else 'desconocido'}; objetivos positivos {safe_count(row['target_positive'])}, negativos {safe_count(row['target_negative'])}, desconocidos {safe_count(row['target_unknown'])}.")
        lines += ["", "### Particiones propuestas", ""]
        for split in report["splits"][name]:
            lines.append(f"- {split['name']}: NO APTA. Validación desde {split['validation_start']}; prueba desde {split['test_start']}; fin exclusivo {split['end']}.")
            for partition, stats in split["partitions"].items():
                lines.append(f"  {partition}: positivos {safe_count(stats['positive'])}, negativos {safe_count(stats['negative'])}, desconocidos {safe_count(stats['unknown'])}.")
        lines += ["", "Disponibilidad detallada por variable/año/radio y distribución por radio sólo en Parquet privados.", ""]
    lines += ["## Requisitos pendientes", "",
        "- Declaraciones/evidencia de cobertura suficientes y negativos respaldados; no usar desconocidos como negativos.",
        "- Resolver clasificación y criterio de confirmación históricos, especialmente fuente 2022, universo anterior al filtro e identidades/episodios pendientes.",
        "- Validar rol territorial, aproximación de fechas y geografía; la inclusión provisional no confirma residencia ni localización de infección.",
        "- Reconstruir disponibilidad de registros, revisiones y etiquetas; definir maduración del objetivo y fecha de disponibilidad censal.",
        "- Revisar tamaño muestral, concentración en 2024 y particiones con ambas clases antes de comparar con baselines.",
        "El contrato de evaluación prepara prevalencia de entrenamiento y persistencia de la última semana disponible, con abstención ante desconocidos.",
        "Fuentes, calendario, versiones, selección/exclusión y hashes quedan en metadata, catálogo y manifiesto. Se preservaron las fases previas.",
        "No se modificaron frontend/backend, modelos ni fuentes. Sin commit/push. Detención para revisión del usuario.", ""]
    return "\n".join(lines)


def run_preparation(root, options):
    require_branch(root)
    inputs, output = private_paths(root, options)
    _, registry = load_configuration(inputs["access_config"], root)
    if not registry.sources:
        raise ValueError("Sin fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.PROCESSING)
        source.require_source_use(AuthorizedUse.INSPECTION)
    before = protected_snapshot(root, output)
    for key in ("observed_dir", "coverage_dir", "geography_dir"):
        require_manifest(inputs[key])
    verify_private_manifest(inputs["universe_dir"])
    coverage_meta = read_json(inputs["coverage_dir"] / "metadata.json")
    verify_sources(registry, coverage_meta)
    review = read_json(inputs["universe_dir"] / "review.private.json")
    if review["provenance"] != coverage_meta["provenance"]["normalization"]:
        raise ValueError("La revisión del universo tiene otra procedencia")
    for name, expected in review["supporting_reports_sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or digest_path(path) != expected:
            raise ValueError("Cambió un diagnóstico de Fase 4.3")
    geography = read_json(inputs["geography_dir"] / "geographic_quality.json")
    if digest_path(inputs["cartography"]) != geography["cartography"]["master_sha256"]:
        raise ValueError("Cambió el maestro territorial")
    territorial_config = read_json(inputs["territorial_config"])
    quality_path = (root / territorial_config["outputs"]["quality_report"]).resolve()
    if not quality_path.is_relative_to(root.resolve()):
        raise ValueError("Control territorial fuera del repositorio")
    quality = read_json(quality_path)
    if not quality["joins"]["all_sources_one_to_one"] or quality["output"]["rows"] != 263:
        raise ValueError("No hay contexto censal válido por radio")
    # Las huellas preservadas de Fase 3 vinculan maestro, QC y fuentes censales.
    geo_manifest = read_json(inputs["geography_dir"] / "integrity_manifest.json")
    for path in [quality_path, inputs["cartography"], *[(root / territorial_config["sources"][key]["path"]).resolve() for key in ("population", "cartography")]]:
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Fuente censal fuera del repositorio")
        expected = geo_manifest["protected_files_sha256"].get(str(path.relative_to(root)))
        if expected is None or digest_path(path) != expected:
            raise ValueError("La procedencia censal no conserva su huella anterior")
    static, neighbors = territorial_context(gpd.read_parquet(inputs["cartography"]))
    all_tables, diagnostics = {}, {}
    report = {"version": VERSION, "training_performed": False, "training_ready": False,
              "artificial_zeros_generated": False, "datasets": {}, "splits": {}}
    prior_metadata = {}
    for policy in ("strict", "expanded"):
        directory = inputs["observed_dir"] / policy / "exploratory"
        require_manifest(directory)
        audit = pd.read_parquet(directory / "records_audit.parquet")
        prior_metadata[policy] = read_json(directory / "metadata.json")
        if prior_metadata[policy]["provenance"]["normalization"] != coverage_meta["provenance"]["normalization"]:
            raise ValueError("Cambió la procedencia de la auditoría")
        for scenario in ("conservative", "exploratory"):
            name = f"{policy}/{scenario}"
            panel = pd.read_parquet(inputs["coverage_dir"] / policy / scenario / "panel.parquet").sort_values(KEYS).reset_index(drop=True)
            if not panel.escenario.eq(scenario).all() or not panel.panel_fechas.eq(policy).all():
                raise ValueError("Escenarios mezclados")
            tables = build_dataset(panel, static, neighbors, coverage_meta["analysis_period"])
            tables["splits"], report["splits"][name] = prepare_splits(panel, options["split_plans"])
            diagnostics[name], report["datasets"][name] = diagnose(panel, tables["predictors_retrospective"], audit)
            all_tables[name] = tables
    require_preserved(before, protected_snapshot(root, output))
    output.mkdir(parents=True, exist_ok=False)
    for name, tables in all_tables.items():
        directory = output / name
        directory.mkdir(parents=True)
        for table, frame in {**tables, **diagnostics[name]}.items():
            write_frame(frame, directory / f"{table}.private.parquet")
    metadata = {"version": VERSION, "data_kind": "official_observed_provisional",
        "unit": "radio_censal_origin_epidemiological_week", "target": "presence_in_exact_next_week",
        "calendar_version": CALENDAR_VERSION, "analysis_period": coverage_meta["analysis_period"],
        "coverage_metadata": coverage_meta, "observed_metadata": prior_metadata,
        "source_provenance": coverage_meta["provenance"],
        "universe_review_sha256": digest_path(inputs["universe_dir"] / "review.private.json"),
        "territorial_config": territorial_config, "census_vintage": 2022,
        "census_historical_availability_verified": False, "historical_record_availability_reconstructed": False,
        "neighbor_rule": "queen touches, exact topology of preserved polygons; graph verified in full",
        "no_patient_coordinates_or_synthetic_features": True,
        "selection": "inherited eligible provisional representative records; do not reclassify",
        "exclusions": "inherited exclusions/pending; unknown labels never negatives; no new zero policy",
        "eligibility_mode": "exploratory inherited from Phase 4.1; coverage scenario is separate",
        "chronological_mode": "retrospective only; no features of t+1; no historical availability assumption",
        "randomness": "none; deterministic sorting and arithmetic", "training_enabled": False,
        "implementation_sha256": {path.name: digest_path(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
        "input_sha256": {str(path.relative_to(root)): digest_path(path) for path in [*inputs.values(), quality_path] if path.is_file()}}
    definitions = feature_definitions(next(iter(all_tables.values()))["predictors_retrospective"].columns)
    write_report(metadata, output / "metadata.private.json")
    write_report(options, output / "configuration.private.json")
    write_report(definitions, output / "feature_definitions.private.json")
    write_report(evaluation_contract(), output / "evaluation_contract.private.json")
    write_report({key: review[key] for key in ("universe", "uncertainty", "previous_delay_evidence", "previous_geographic_sensitivity", "geographic_evidence")}, output / "inherited_quality.private.json")
    write_report(report, output / "diagnostics.private.json")
    (output / "implementation.private.md").write_text(report_text(report, diagnostics), encoding="utf-8")
    require_preserved(before, protected_snapshot(root, output))
    write_report({"version": VERSION, "protected_files_sha256": before, "previous_artifacts_preserved": True,
        "outputs_sha256": {path.relative_to(output).as_posix(): digest_path(path) for path in sorted(output.rglob("*")) if path.is_file()}}, output / "integrity_manifest.private.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[5]
        report = run_preparation(root, read_json(args.config))
        print(json.dumps({"version": VERSION, "training_ready": False, "training_performed": False,
            "datasets": {name: {"cells": value["cells"], "radios": value["radios"], "weeks": value["weeks"], "labels": value["labels"]} for name, value in report["datasets"].items()}}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 5A. Revisar integridad y configuración privadas; no volcar registros.\n")


if __name__ == "__main__":
    main()
