"""Fase 4.1 privada: conserva el panel anterior y compara fechas estrictas/ampliadas."""

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.observed_comparison import compare_scenarios, comparison_text, verify_strict_reference
from sigard_ml.official.observed_dates import DATE_HIERARCHY, DATE_TYPES, select_reference_date, validate_date_hierarchy
from sigard_ml.official.observed_pipeline import require_branch, run_observed_pipeline
from sigard_ml.official.observed_settings import OBSERVED_DEFAULTS
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved

RECOVERY_VERSION = "official-date-recovery-0.4.1"


def run_date_recovery(config, registry, repo_root, *, baseline_dir, overrides=None):
    require_branch(repo_root)
    if not registry.sources:
        raise ValueError("No hay fuentes autorizadas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    allowed = (repo_root / "data/interim/official/observed").resolve()
    baseline = (repo_root / baseline_dir).resolve()
    if not baseline.is_relative_to(allowed):
        raise ValueError("La referencia debe ser un panel privado de Fase 4")
    metadata = json.loads((baseline / "metadata.json").read_text(encoding="utf-8"))
    if metadata["mode"] != "exploratory" or metadata["rules"]["reference_date_field"] != "symptom_onset" or metadata["rules"].get("date_hierarchy"):
        raise ValueError("La referencia debe ser el escenario exploratorio estricto anterior")
    manifest = json.loads((baseline / "integrity_manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["outputs_sha256"].items():
        if digest_path(baseline / name) != digest:
            raise ValueError("La referencia difiere de su manifiesto privado")
    overrides = overrides or {}
    editable = {"output_dir", "date_hierarchy", "date_rule_version"}
    if not set(overrides) <= editable:
        raise ValueError("Fase 4.1 sólo permite cambiar la política de fechas y la carpeta versionada")
    output = (repo_root / overrides.get("output_dir", "data/interim/official/observed/date_recovery_041")).resolve()
    if (not output.is_relative_to(allowed) or output == allowed or
        output.is_relative_to(baseline) or baseline.is_relative_to(output)):
        raise ValueError("La recuperación requiere una carpeta privada distinta del panel anterior")
    output_names = {"strict", "expanded", "comparison.private.json", "comparison.md",
                    "scenario_configs.private.json", "integrity_manifest.json"}
    if output.exists() and any(path.name not in output_names for path in output.iterdir()):
        raise ValueError("La carpeta versionada contiene archivos ajenos a Fase 4.1")
    hierarchy = overrides.get("date_hierarchy", list(DATE_HIERARCHY))
    validate_date_hierarchy(hierarchy)
    before = protected_snapshot(repo_root, output)
    baseline_audit = pd.read_parquet(baseline / "records_audit.parquet")
    baseline_panel = pd.read_parquet(baseline / "panel.parquet")
    common = {**OBSERVED_DEFAULTS, **metadata["rules"]}
    configurations, scenario_reports = {}, {}
    for name, policy, version in (
        ("strict", ["symptom_onset"], "symptom-onset-strict-0.4.1"),
        ("expanded", hierarchy, overrides.get("date_rule_version", "reference-date-hierarchy-0.4.1")),
    ):
        options = {**common, "output_dir": str((output / name).relative_to(repo_root)),
                   "date_hierarchy": policy, "date_rule_version": version}
        configurations[name] = options
        scenario_reports[name] = run_observed_pipeline(config, registry, options, repo_root, exploratory=True)
    strict_dir, expanded_dir = output / "strict/exploratory", output / "expanded/exploratory"
    strict = pd.read_parquet(strict_dir / "records_audit.parquet")
    expanded = pd.read_parquet(expanded_dir / "records_audit.parquet")
    verify_strict_reference(baseline_audit, strict, baseline_panel, pd.read_parquet(strict_dir / "panel.parquet"))
    comparison = compare_scenarios(strict, expanded)
    # Oportunidad independiente de cada alternativa, siempre entre los pendientes
    # originales exclusivamente por fecha y con idéntico período/corte.
    only_date = strict.processing_outcome.eq("pending") & strict.processing_reasons.map(lambda reasons: list(reasons) == ["date_unusable"])
    limits = {"period_start": date.fromisoformat(common["period_start"]),
              "period_end": date.fromisoformat(common["period_end"]), "as_of": date.fromisoformat(config["as_of_date"])}
    comparison["independent_alternative_opportunities"] = {
        DATE_TYPES[field]: sum(select_reference_date(row, [field], **limits)[0] is not None for _, row in strict.loc[only_date].iterrows())
        for field in DATE_HIERARCHY[1:]}
    comparison.update({"transformation_version": RECOVERY_VERSION, "analysis_period": scenario_reports["strict"]["analysis_period"],
        "grid_weeks": int(baseline_panel.fecha_inicio_semana.nunique()), "radios": int(baseline_panel.radio_censal.nunique()),
        "baseline_reproduced": True, "baseline_preserved": True,
        "approximate_location_and_spatial_uncertainty_preserved": True, "training_performed": False})
    require_preserved(before, protected_snapshot(repo_root, output))
    write_report(comparison, output / "comparison.private.json")
    (output / "comparison.md").write_text(comparison_text(comparison), encoding="utf-8")
    write_report(configurations, output / "scenario_configs.private.json")
    require_preserved(before, protected_snapshot(repo_root, output))
    write_report({"transformation_version": RECOVERY_VERSION, "protected_files_sha256": before,
        "baseline_dir": str(baseline.relative_to(repo_root)), "baseline_preserved": True,
        "outputs_sha256": {str(path.relative_to(output)): digest_path(path) for path in sorted(output.rglob("*"))
            if path.is_file() and path != output / "integrity_manifest.json"}}, output / "integrity_manifest.json")
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--recovery-config", type=Path)
    parser.add_argument("--baseline-dir", default="data/interim/official/observed/exploratory")
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[4]
        config, registry = load_configuration(args.config, root)
        overrides = json.loads(args.recovery_config.read_text(encoding="utf-8")) if args.recovery_config else None
        result = run_date_recovery(config, registry, root, baseline_dir=args.baseline_dir, overrides=overrides)
        print(json.dumps({key: result[key] for key in ("strict", "expanded", "recovered_by_date_type",
            "recovered_total", "new_represented_weeks", "weeks_with_added_records", "baseline_reproduced", "baseline_preserved")}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace is not None:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 4.1. Revisar autorización, fechas y referencia privada; no volcar registros.\n")


if __name__ == "__main__":
    main()
