"""Fase 4.2 privada: cobertura, ceros y objetivo semanal retrospectivo; sin entrenamiento."""

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.coverage_diagnostics import panel_diagnostics, temporal_inventory
from sigard_ml.official.coverage_panel import build_coverage_panel
from sigard_ml.official.coverage_settings import COVERAGE_DEFAULTS, COVERAGE_VERSION, DATE_PANELS, SCENARIOS
from sigard_ml.official.observed_comparison import aligned_records
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import safe_count, write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, read_authorized_normalized, require_preserved


def validate_options(options):
    if set(options) != set(COVERAGE_DEFAULTS) or not isinstance(options["coverage_version"], str) or not options["coverage_version"].strip():
        raise ValueError("Configuración de cobertura desconocida o sin versión")
    policy = options["zero_policy"]
    if set(policy) != {"enabled", "allow_declared_complete_in_exploratory"} or any(type(value) is not bool for value in policy.values()):
        raise ValueError("Política de ceros inválida; pendientes y semanas parciales siempre bloquean ceros")
    declaration = options["provenance_declaration"]
    if declaration.get("selection_geographic_basis") not in {"unknown", "patient_residence", "notifying_establishment"}:
        raise ValueError("Debe distinguirse residencia de establecimiento notificador")
    if declaration.get("temporal_completeness_automatically_verified") is not False:
        raise ValueError("Una declaración de entrega no verifica automáticamente cobertura temporal")
    for name in ("source_period_declarations", "coverage_declarations", "coverage_verifications"):
        if not isinstance(options[name], list):
            raise ValueError("Las declaraciones y verificaciones deben ser listas editables")
    rule = options["diagnostic_activity_rule"]
    if set(rule) != {"min_positive_weeks", "min_positive_cells"} or any(type(value) is not int or value < 1 for value in rule.values()):
        raise ValueError("Umbral de diagnóstico inválido")
    if date.fromisoformat(options["evaluation_start"]).weekday() != 6:
        raise ValueError("El corte cronológico debe ser un domingo")


def private_directories(options, repo_root):
    allowed = (repo_root / "data/interim/official/observed").resolve()
    source = (repo_root / options["input_dir"]).resolve()
    output = (repo_root / options["output_dir"]).resolve()
    if (not source.is_relative_to(allowed) or not output.is_relative_to(allowed)
        or source == allowed or output == allowed or source.is_relative_to(output) or output.is_relative_to(source)):
        raise ValueError("Fase 4.2 requiere rutas privadas distintas de sus fases anteriores")
    names = {"strict", "expanded", "coverage_inventory.private.json", "viability.private.json",
             "viability.md", "configuration.private.json", "metadata.json", "integrity_manifest.json"}
    if output.exists() and any(path.name not in names for path in output.iterdir()):
        raise ValueError("La salida contiene archivos ajenos a Fase 4.2")
    for date_panel in DATE_PANELS:
        parent = output / date_panel
        if parent.exists() and any(path.name not in SCENARIOS for path in parent.iterdir()):
            raise ValueError("La carpeta temporal contiene archivos ajenos")
        for scenario in SCENARIOS:
            directory = parent / scenario
            if directory.exists() and any(path.name != "panel.parquet" for path in directory.iterdir()):
                raise ValueError("El escenario contiene archivos ajenos a Fase 4.2")
    return source, output


def require_manifest(directory):
    manifest = json.loads((directory / "integrity_manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["outputs_sha256"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest_path(path) != expected:
            raise ValueError("Una salida anterior difiere de su manifiesto")


def read_prior_panels(directory, normalized, normalization_provenance):
    require_manifest(directory)
    result, audits, metadata = {}, {}, {}
    for date_panel in DATE_PANELS:
        path = directory / date_panel / "exploratory"
        require_manifest(path)
        result[date_panel] = pd.read_parquet(path / "panel.parquet")
        audits[date_panel] = pd.read_parquet(path / "records_audit.parquet")
        metadata[date_panel] = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        if metadata[date_panel]["provenance"]["normalization"] != normalization_provenance:
            raise ValueError("La normalización ya no coincide con Fase 4.1")
        keys = normalized[ROW_KEY].merge(audits[date_panel][ROW_KEY], on=ROW_KEY, how="outer", indicator=True, validate="one_to_one")
        if not keys._merge.eq("both").all():
            raise ValueError("Fase 4.1 no conserva todas las filas autorizadas")
        if result[date_panel].radio_censal.nunique() != 263:
            raise ValueError("Fase 4.2 debe conservar los 263 radios")
    aligned_records(audits["strict"], audits["expanded"])
    if metadata["strict"]["analysis_period"] != metadata["expanded"]["analysis_period"]:
        raise ValueError("Los períodos estrictos y ampliados difieren")
    return result, audits, metadata


def viability_text(report):
    lines = ["# SIGARD Fase 4.2 — diagnóstico privado", "",
        "Conteos de registros elegibles provisionales; no casos únicos validados.",
        "La entrega completa de registros disponibles y el filtrado manual son declaraciones de procedencia.",
        "No prueban cobertura temporal, residencia ni ausencia epidemiológica automáticamente.", ""]
    for date_panel, scenarios in report["panels"].items():
        for scenario, summary in scenarios.items():
            obs, target = summary["observations"], summary["next_week_labels"]
            lines += [f"## {date_panel} / {scenario}", "",
                f"Registros incorporados: {safe_count(summary['incorporated_records'])}.",
                f"Observaciones radio-semana: positivas {safe_count(obs['positive'])}, ceros {safe_count(obs['negative'])}, desconocidas {safe_count(obs['unknown'])}.",
                f"Objetivos de semana siguiente: positivos {safe_count(target['positive'])}, negativos {safe_count(target['negative'])}, desconocidos {safe_count(target['unknown'])}.",
                f"Semanas con positivos: {summary['weeks_with_positive_observations']}; con ceros respaldados: {summary['weeks_with_generated_zeros']}.",
                f"Radios con positivos: {summary['radios_with_positive_observations']}; sin positivos: {summary['radios_without_positive_observations_count']}.",
                "La ausencia de positivos en un radio no prueba ausencia de casos.", ""]
    lines += ["## Evidencia pendiente", ""] + [f"- {item}" for item in report["missing_evidence"]]
    lines += ["", "La distribución semanal, los intervalos por fuente y los radios quedan sólo en JSON/Parquet privados.",
        "Las muestras son referencias aproximadas: pueden desplazar la semana real de síntomas; no se corrigen restando días.",
        "El diagnóstico cronológico excluye el origen cuyo objetivo cruza el corte; no acredita disponibilidad histórica.",
        "Sin negativos respaldados no se puede entrenar/evaluar un clasificador binario de ambas clases.",
        "No se entrenó ni se calcularon métricas predictivas. Los paneles no están habilitados para entrenamiento.", ""]
    return "\n".join(lines)


def run_coverage_pipeline(config, registry, options, repo_root):
    require_branch(repo_root)
    validate_options(options)
    if not registry.sources:
        raise ValueError("No hay fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    inputs, output = private_directories(options, repo_root)
    before = protected_snapshot(repo_root, output)
    normalized, normalization_provenance = read_authorized_normalized(config, registry, repo_root)
    base_panels, audits, prior_metadata = read_prior_panels(inputs, normalized, normalization_provenance)
    period = prior_metadata["expanded"]["analysis_period"]
    start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    inventory = temporal_inventory(normalized, audits, start, end, options["source_period_declarations"])
    panels, summaries = {}, {}
    for date_panel in DATE_PANELS:
        summaries[date_panel] = {}
        for scenario in SCENARIOS:
            panel = build_coverage_panel(base_panels[date_panel], audits[date_panel], options,
                date_panel=date_panel, scenario=scenario, period_start=start, period_end=end, repo_root=repo_root)
            panels[date_panel, scenario] = panel
            summaries[date_panel][scenario] = panel_diagnostics(panel,
                activity_rule=options["diagnostic_activity_rule"], evaluation_start=date.fromisoformat(options["evaluation_start"]))
    report = {"transformation_version": COVERAGE_VERSION, "analysis_period": period, "panels": summaries,
        "accepted_coverage_declarations": options["coverage_declarations"],
        "accepted_coverage_verifications": options["coverage_verifications"],
        "provenance_declaration": options["provenance_declaration"],
        "date_delay_diagnostic": json.loads((inputs / "comparison.private.json").read_text(encoding="utf-8"))["delay_evidence"],
        "missing_evidence": [
            "Límites exactos de los períodos solicitados por fuente y el campo temporal que define cada extracción.",
            "Declaraciones explícitas de intervalos completos/parciales, con alcance territorial y base de fechas de cada panel.",
            "Para cobertura comprobada: respaldo verificable de vigilancia/reporte semanal, conciliación de extracción y selección y revisión de reglas.",
            "Confirmación de residencia del paciente frente a establecimiento notificador y del rol de las coordenadas.",
            "Resolución de fechas, elegibilidad e identidades pendientes; sin fecha se mantiene incertidumbre sobre todo el período.",
            "Disponibilidad histórica de registros y clasificaciones para simular predicción futura sin información posterior.",
        ], "historical_availability_reconstructed": False, "training_ready": False,
        "training_performed": False, "prior_phases_preserved": True}
    require_preserved(before, protected_snapshot(repo_root, output))
    for (date_panel, scenario), panel in panels.items():
        directory = output / date_panel / scenario
        directory.mkdir(parents=True, exist_ok=True)
        write_frame(panel, directory / "panel.parquet")
    write_report(inventory, output / "coverage_inventory.private.json")
    write_report(report, output / "viability.private.json")
    write_report(options, output / "configuration.private.json")
    write_report({"transformation_version": COVERAGE_VERSION, "unit": "provisional_eligible_source_records_radio_epidemiological_week",
        "data_kind": config.get("data_kind", "official_observed"), "analysis_period": period,
        "provenance": {"normalization": normalization_provenance, "phase41_input_dir": str(inputs.relative_to(repo_root)),
            "phase41_manifest_sha256": digest_path(inputs / "integrity_manifest.json"),
            "spatial_assignment": prior_metadata["expanded"]["provenance"]["spatial_assignment"]},
        "provenance_declaration": options["provenance_declaration"],
        "location_role_from_previous_phase": prior_metadata["expanded"]["provenance"]["spatial_assignment"]["geographic_evidence"]["location_role"],
        "evidence_hashes_do_not_automatically_prove_epidemiological_completeness": True,
        "date_panels": DATE_PANELS, "coverage_scenarios": SCENARIOS,
        "target": "next_week_presence_of_provisional_eligible_records", "target_is_not_a_predictor": True,
        "temporal_mode": "retrospective", "historical_availability_reconstructed": False,
        "training_ready": False, "training_performed": False, "validated_epidemiological_absence": False,
        "previous_phases_modified": False}, output / "metadata.json")
    (output / "viability.md").write_text(viability_text(report), encoding="utf-8")
    require_preserved(before, protected_snapshot(repo_root, output))
    write_report({"transformation_version": COVERAGE_VERSION, "protected_files_sha256": before,
        "outputs_sha256": {str(path.relative_to(output)): digest_path(path) for path in sorted(output.rglob("*"))
            if path.is_file() and path != output / "integrity_manifest.json"}}, output / "integrity_manifest.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--coverage-config", type=Path)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[4]
        config, registry = load_configuration(args.config, root)
        options = dict(COVERAGE_DEFAULTS)
        if args.coverage_config:
            overrides = json.loads(args.coverage_config.read_text(encoding="utf-8"))
            if not set(overrides) <= set(options):
                raise ValueError("Opciones de cobertura desconocidas")
            options.update(overrides)
        report = run_coverage_pipeline(config, registry, options, root)
        print(json.dumps({name: {scenario: {"observations": summary["observations"], "labels": summary["next_week_labels"]}
            for scenario, summary in scenarios.items()} for name, scenarios in report["panels"].items()}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace is not None:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 4.2. Revisar cobertura y evidencia privadas; no volcar registros.\n")


if __name__ == "__main__":
    main()
