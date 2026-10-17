"""CLI privado de Fase 4. El escenario exploratorio exige --exploratory."""

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.cartography import read_radios, validate_radios
from sigard_ml.official.classification import classify_labels, prepare_classification_map
from sigard_ml.official.eligibility import evaluate_eligibility
from sigard_ml.official.episodes import review_episode_groups
from sigard_ml.official.observed_dates import assign_record_weeks, original_date_text, validate_date_hierarchy
from sigard_ml.official.observed_panel import build_observed_panel, classify_processing_outcome
from sigard_ml.official.observed_reading import read_observed_inputs
from sigard_ml.official.observed_reports import classification_inventory, reconciliation, report_text
from sigard_ml.official.observed_settings import OBSERVED_DEFAULTS, OBSERVED_VERSION, ROW_KEY
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved


def require_branch(repo_root):
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo_root,
                            check=True, capture_output=True, text=True).stdout.strip()
    if branch != "entrenamiento-ML":
        raise ValueError("Fase 4 sólo se ejecuta en entrenamiento-ML")


def observed_output(options, repo_root, exploratory):
    base = (repo_root / options["output_dir"]).resolve()
    allowed = (repo_root / "data/interim/official/observed").resolve()
    if not base.is_relative_to(allowed):
        raise ValueError("Las salidas requieren una carpeta privada independiente de Fase 2 y 3")
    if options.get("date_hierarchy") is not None and base == allowed:
        raise ValueError("La política nueva requiere una carpeta versionada; conservar el panel anterior")
    output = base / ("exploratory" if exploratory else "conservative")
    names = {"panel.parquet", "records_audit.parquet", "reconciliation.json", "reconciliation.md",
             "classification_inventory.private.json", "metadata.json", "integrity_manifest.json"}
    if output.exists() and any(path.name not in names for path in output.iterdir()):
        raise ValueError("La salida contiene avances ajenos a Fase 4")
    return output


def validate_options(options):
    hierarchy = options.get("date_hierarchy")
    if hierarchy is not None:
        validate_date_hierarchy(hierarchy)
        if options["reference_date_field"] != "symptom_onset":
            raise ValueError("La jerarquía exige inicio de síntomas como primera referencia")
        if len(hierarchy) > 1 and options["date_rule_version"] == OBSERVED_DEFAULTS["date_rule_version"]:
            raise ValueError("El respaldo temporal exige su propia versión de regla")
    prepare_classification_map(options["classification_map"])
    for key in ("classification_version", "eligibility_version", "episode_version", "date_rule_version", "coverage_version"):
        if not isinstance(options[key], str) or not options[key].strip():
            raise ValueError("Falta una versión de reglas")
    if not options["geocoding_acceptance_ref"]:
        raise ValueError("Falta referencia de aceptación de candidatos aproximados")
    if options["auxiliary_columns"]:
        raise ValueError("Vincular auxiliares requiere datos y disponibilidad comprobados; usar observed_auxiliary")


def prepare_records(frame, radios, config, options, exploratory):
    categories = classify_labels(frame.classification_label, options["classification_map"], options["classification_version"])
    policy = dict(include=options["exploratory_include"], exclude=options["exploratory_exclude"], version=options["eligibility_version"])
    conservative = evaluate_eligibility(categories.classification, **policy)
    eligibility = evaluate_eligibility(categories.classification, exploratory=exploratory, **policy)
    identities = review_episode_groups(frame, version=options["episode_version"], resolutions=options["episode_resolutions"])
    dates = assign_record_weeks(frame, field=options["reference_date_field"],
            period_start=date.fromisoformat(options["period_start"]), period_end=date.fromisoformat(options["period_end"]),
            as_of=date.fromisoformat(config["as_of_date"]), version=options["date_rule_version"], hierarchy=options.get("date_hierarchy"))
    result = pd.concat([frame.reset_index(drop=True), categories, eligibility, identities.drop(columns=ROW_KEY + ["event_ref"]), dates], axis=1)
    if "fecha_inicio_sintomas_original" not in result:
        result["fecha_inicio_sintomas_original"] = frame.symptom_onset.map(original_date_text).reset_index(drop=True)
        result["tipo_valor_fecha_inicio_sintomas_original"] = "normalized_value_only"
    candidates = result.radio_candidate.dropna()
    if not candidates.isin(radios.radio_id).all():
        raise ValueError("Radio candidato ajeno a la cartografía vigente")
    result["fraction_candidate"] = result.radio_candidate.map(lambda value: value[:7] if pd.notna(value) else None)
    result["record_available_on"] = None
    result["epidemiological_identity_validated"] = False
    result["panel_validated"] = False
    result["transformation_version"] = OBSERVED_VERSION
    result["spatial_assignment_version"] = options["spatial_version"]
    result["approximate_location_acceptance_ref"] = options["geocoding_acceptance_ref"]
    outcomes = classify_processing_outcome(result)
    result = pd.concat([result, outcomes], axis=1)
    return result, conservative


def private_record_projection(frame):
    columns = ROW_KEY + ["event_ref", "classification", "classification_mapped", "classification_rule_version",
              "analysis_eligibility", "eligibility_reason", "eligibility_rule_version", "epidemiological_eligibility_validated",
              "episode_ref", "episode_status", "identity_group_size", "identity_countable", "identity_resolved_by_review",
              "identity_evidence_ref", "episode_rule_version", "reference_date", "reference_date_status",
              "fecha_inicio_sintomas_original", "tipo_valor_fecha_inicio_sintomas_original",
              "fecha_referencia", "tipo_fecha_referencia", "fecha_aproximada", "motivo_seleccion_fecha",
              "date_selection_rejections", "semana_potencialmente_afectada_por_retraso",
              "reference_date_usable", "date_within_analysis_period", "week_start", "week_end",
              "epidemiological_year", "epidemiological_week", "reference_date_field", "date_rule_version",
              "radio_candidate", "fraction_candidate", "assignment_state", "geometry_status", "geocoding_category",
              "uncertainty_reasons", "distance_to_boundary_m", "alternative_radios", "alternative_basis",
              "coordinate_group_ref", "coordinate_group_size", "crs_confirmed", "location_role",
              "processing_outcome", "processing_reasons", "record_available_on", "epidemiological_identity_validated",
              "panel_validated", "transformation_version", "spatial_assignment_version", "approximate_location_acceptance_ref"]
    alternative_columns = [name for field in ("consultation_on", "sample_on", "notified_on")
                           for name in (field, field + "_status", field + "_column_ref") if name in frame]
    return frame[columns + alternative_columns].copy()


def write_frame(frame, output):
    temporary = output.with_suffix(".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(output)


def run_observed_pipeline(config, registry, options, repo_root, *, exploratory=False):
    require_branch(repo_root)
    validate_options(options)
    output = observed_output(options, repo_root, exploratory)
    if not registry.sources:
        raise ValueError("No hay fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    before = protected_snapshot(repo_root, output)
    frame, provenance = read_observed_inputs(config, registry, options, repo_root)
    radios = read_radios(repo_root / options["cartography"])
    validate_radios(radios)
    options = {**options, "spatial_version": provenance["spatial_assignment"]["transformation_version"]}
    records, conservative = prepare_records(frame, radios, config, options, exploratory)
    panel = build_observed_panel(records, radios, period_start=date.fromisoformat(options["period_start"]),
            period_end=date.fromisoformat(options["period_end"]), options=options, exploratory=exploratory)
    report = {"transformation_version": OBSERVED_VERSION, "mode": "exploratory" if exploratory else "conservative",
              "analysis_period": {"start": options["period_start"], "end": options["period_end"]},
              "reference_date_field": options["reference_date_field"],
              "date_hierarchy": options.get("date_hierarchy"),
              "exploratory_include": options["exploratory_include"],
              "exploratory_exclude": options["exploratory_exclude"],
              "rule_versions": {key: options[key] for key in ("classification_version", "eligibility_version",
                   "episode_version", "date_rule_version", "coverage_version")},
              "summary": reconciliation(records, panel, conservative)}
    metadata = {"transformation_version": OBSERVED_VERSION, "data_kind": config.get("data_kind", "official_observed"),
                "unit": "provisional_eligible_source_records_radio_epidemiological_week", "mode": report["mode"],
                "analysis_period": report["analysis_period"], "rules": options, "provenance": provenance,
                "panel_validated": False, "temporal_mode": "retrospective", "historical_availability_reconstructed": False,
                "training_ready": False, "future_official_target": "next_week_occurrence",
                "geocoder_provider_per_record_confirmed": False, "auxiliaries_joined": [],
                "alternative_dates_confirm_symptom_onset": False,
                "protected_inputs_and_scientific_artifacts_unchanged": True}
    require_preserved(before, protected_snapshot(repo_root, output))
    output.mkdir(parents=True, exist_ok=True)
    write_frame(panel, output / "panel.parquet")
    write_frame(private_record_projection(records), output / "records_audit.parquet")
    write_report(report, output / "reconciliation.json")
    write_report(metadata, output / "metadata.json")
    write_report({"classification_version": options["classification_version"], "labels": classification_inventory(frame)},
                 output / "classification_inventory.private.json")
    temporary = output / "reconciliation.tmp"
    temporary.write_text(report_text(report), encoding="utf-8")
    temporary.replace(output / "reconciliation.md")
    require_preserved(before, protected_snapshot(repo_root, output))
    # El otro modo se verifica durante la ejecución, pero sus manifiestos no se
    # incluyen como entradas científicas: evita referencias hash circulares.
    other_mode = output.parent / ("conservative" if exploratory else "exploratory")
    # Las demás versiones se protegen durante la ejecución, pero sus manifiestos
    # no entran en hashes científicos recursivos entre escenarios.
    observed_root = (repo_root / "data/interim/official/observed").resolve()
    scientific_inputs = {path: digest for path, digest in before.items()
                         if not (repo_root / path).resolve().is_relative_to(observed_root)}
    write_report({"protected_files_sha256": scientific_inputs, "other_mode_preserved": True, "outputs_sha256": {
        path.name: digest_path(path) for path in sorted(output.iterdir()) if path.name != "integrity_manifest.json"}},
        output / "integrity_manifest.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--observed-config", type=Path)
    parser.add_argument("--exploratory", action="store_true", help="Activa reglas provisionales; no valida casos")
    parser.add_argument("--diagnose-failure", action="store_true")
    arguments = parser.parse_args()
    try:
        repo_root = Path(__file__).resolve().parents[4]
        config, registry = load_configuration(arguments.config, repo_root)
        options = dict(OBSERVED_DEFAULTS)
        if arguments.observed_config:
            overrides = json.loads(arguments.observed_config.read_text(encoding="utf-8"))
            if not set(overrides) <= set(options):
                raise ValueError("Parámetro del panel desconocido")
            options.update(overrides)
        report = run_observed_pipeline(config, registry, options, repo_root, exploratory=arguments.exploratory)
        print(json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    except Exception as error:
        if arguments.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace is not None:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 4. Revisar reglas, autorización y derivados privados; no volcar registros.\n")


if __name__ == "__main__":
    main()
