"""Fase 5B privada: auditoría, configuración y previsualización; sin entrenar."""

import argparse
import json
from pathlib import Path

import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.coverage_pipeline import require_manifest
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import safe_count, write_report
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.pipeline import read_json, verify_private_manifest, verify_sources
from sigard_ml.official.spatial_ml.validation import validate_panel
from sigard_ml.official.spatial_ml.experiment_selection import SETS, audit_columns, compare_sets, training_support
from sigard_ml.official.spatial_ml.experiment_coverage import declared_coverage_preview, eligibility_review
from sigard_ml.official.spatial_ml.experiment_protocol import VERSION, experiment_protocol
from sigard_ml.official.universe_pipeline import declaration_template

EXPECTED_RADIOS = 263
DEFAULTS = {"version": VERSION, "access_config": "data/interim/official/access.private.json",
    "phase5a_dir": "data/processed/official/spatial_ml_05a_v2",
    "universe_dir": "data/interim/official/observed/universe_043_v1",
    "observed_dir": "data/interim/official/observed/date_recovery_041",
    "output_dir": "data/interim/official/spatial_experiment_05b_v1",
    "source_2022_id": "delivery_2022", "training_enabled": False, "materialize_assumed_zeros": False}


def experiment_paths(root, options):
    if set(options) != set(DEFAULTS) or options["version"] != VERSION or options["training_enabled"] is not False or options["materialize_assumed_zeros"] is not False:
        raise ValueError("Fase 5B sólo permite preparación, sin entrenamiento ni negativos")
    private = (root / "data/interim/official").resolve()
    processed = (root / "data/processed/official").resolve()
    inputs = {key: (root / options[key]).resolve() for key in ("access_config", "phase5a_dir", "universe_dir", "observed_dir")}
    output = (root / options["output_dir"]).resolve()
    if not private.is_relative_to(root.resolve()) or not processed.is_relative_to(root.resolve()):
        raise ValueError("Almacenamiento privado fuera del repositorio")
    if any(not path.is_relative_to(processed if key == "phase5a_dir" else private) for key, path in inputs.items()):
        raise ValueError("Entradas fuera del almacenamiento oficial privado")
    if output.parent != private or output.exists() or any(path.is_relative_to(output) or output.is_relative_to(path) for path in inputs.values()):
        raise ValueError("Se requiere un destino privado nuevo y separado de las fases anteriores")
    return inputs, output


def label_policy_comparison(strict, expanded):
    joined = strict[KEYS + ["objetivo_semana_siguiente"]].merge(
        expanded[KEYS + ["objetivo_semana_siguiente"]], on=KEYS, validate="one_to_one", how="outer", indicator=True,
        suffixes=("_strict", "_expanded"))
    if not joined._merge.eq("both").all():
        raise ValueError("Las políticas de fechas no conservan la misma grilla")
    a, b = joined.objetivo_semana_siguiente_strict, joined.objetivo_semana_siguiente_expanded
    same = a.eq(b).fillna(False) | (a.isna() & b.isna())
    return {"rows": len(joined), "same_label_or_both_unknown": int(same.sum()),
        "different_label_or_knowledge_state": int((~same).sum()),
        "expanded_positive_strict_unknown": int((b.eq(1).fillna(False) & a.isna()).sum()),
        "strict_positive_expanded_unknown": int((a.eq(1).fillna(False) & b.isna()).sum()),
        "positive_negative_disagreements": int(((a.eq(1) & b.eq(0)) | (a.eq(0) & b.eq(1))).sum()),
        "clinical_confirmation_inferred": False, "policy_selected_by_predictive_performance": False}


def report_text(report, tables):
    lines = ["# SIGARD Fase 5B — selección y preparación del experimento espacial", "",
        "Preparación privada y retrospectiva. No se entrenó, imputó, evaluó modelos ni materializó negativos.",
        "Se auditaron las 55 columnas de cada matriz de Fase 5A. Porcentajes calculados entre todas las celdas y entre objetivos t+1 positivos provisionales.",
        "Las auditorías completas por variable y año se conservan en column_audit y column_by_year privados.", "",
        "## Variables y conjuntos", "",
        "A: superficie, población, densidad Censo 2022, cantidad de vecinos, SE y seno/coseno estacional.",
        "B: núcleo A más rezagos locales 1–4 opcionales; C: B más acumulados locales 4/8/12 y rezagos/acumulados vecinales opcionales.",
        "Radio y fecha son claves; año, conteo contemporáneo de origen y metadatos constantes se excluyen del primer modelo.",
        "Indicadores de faltantes se derivan únicamente para las columnas opcionales retenidas con información de entrenamiento.",
        "No se exige historia completa para retener filas: el núcleo A es obligatorio; la historia permanece NaN.",
        "Población/densidad y topología Censo 2022 son contexto retrospectivo, sin publicación histórica acreditada.", "",
        "## Tratamiento de faltantes", "",
        "Estrategia inicial: NaN nativo y banderas de faltantes; no imputación numérica ni relleno con cero.",
        "Se distinguen valor desconocido, cero respaldado heredado, contexto espacial presente y valor temporalmente no disponible/no acreditado.",
        "Una vista operativa enmascara valores sin evidencia de disponibilidad al origen; un rezago no elimina por sí solo demoras de carga o revisión.",
        "Columnas opcionales totalmente desconocidas en entrenamiento se omiten dentro de ese corte; un núcleo obligatorio desconocido bloquea el experimento.",
        "Cualquier futura imputación exigiría nueva versión y parámetros ajustados sólo con entrenamiento y etiquetas conocidas/maduras; nunca se llamaría conteo observado.", ""]
    for name, summary in report["datasets"].items():
        lines += [f"## {name}", "", f"Grilla: {summary['rows']} celdas. Objetivos positivos {safe_count(summary['positive'])}, negativos {safe_count(summary['negative'])}, desconocidos {safe_count(summary['unknown'])}.", ""]
        for row in tables[name]["set_comparison"].query("origin_year == 'all'").to_dict("records"):
            pct = row['positive_all_candidate_values_available_pct']
            lines.append(f"- {row['set']}: núcleo disponible {row['required_available_pct']:.2f}%; todos los candidatos conocidos {row['all_candidate_values_available_pct']:.2f}%; entre positivos " + (f"{pct:.2f}%" if pct is not None and pd.notna(pct) else "sin denominador") + ".")
        lines += ["", "Tener todos los candidatos conocidos es sólo un diagnóstico; no es filtro obligatorio de filas.",
            f"Casos que cumplen banderas previas de validación clínica/identidad: {safe_count(summary['eligibility']['confirmed_under_existing_validation_flags'])}.",
            f"Capacidad histórica condicional de Fase 4.3: {summary['phase43_conditional_capacity']}; no son etiquetas.",
            f"Intervalos explícitamente declarados: {summary['coverage']['declared_intervals']}; negativos materializados: ninguno.", ""]
        for row in tables[name]["partition_classes"].to_dict("records"):
            if row['partition'] != 'purged_or_outside':
                lines.append(f"- {row['plan']} / {row['partition']}: positivos {safe_count(row['positive'])}, negativos {safe_count(row['negative'])}, desconocidos {safe_count(row['unknown'])}; NO APTO.")
    parameters = report["protocol"]["parameters"]
    lines += ["", "## Protocolo preparado", "", f"RandomForestClassifier: {json.dumps(parameters, sort_keys=True)}.",
        "Semillas predefinidas; pesos balanced_subsample sólo desde entrenamiento, sin convertir desconocidos ni balancear evaluación.",
        "Baselines: prevalencia de entrenamiento y persistencia de última semana disponible con abstención ante faltantes.",
        "Evaluación futura: precisión promedio/PR, ROC AUC con ambas clases, precisión/recall/F1, matriz de confusión, Brier, log loss y curva de calibración.",
        "Calibración opcional sólo en bloque cronológico interno de entrenamiento; test final intacto. No se calcularon métricas.",
        "Se reutilizan cortes cronológicos purgados y se comparan fechas estrictas/ampliadas con idénticos parámetros, semillas y cortes.",
        "La concentración en 2024 obliga a informar estabilidad por año/temporada, dependencia temporal y cobertura de predicción.", "",
        "## Elegibilidad y cobertura pendiente", "",
        "La fuente 2022 conserva sus clasificaciones canónicas previas y desenlaces: no se reclasifica ni se declara confirmación desde una etiqueta literal.",
        "Se requiere revisar definición histórica de dengue, filtros de confirmación, evento, universo previo al filtro, episodios y residencia.",
        "La plantilla de Fase 4.3 se reutiliza sin firmar, completar períodos ni declarar vigilancia completa automáticamente.",
        "Para habilitar un escenario experimental se necesitan responsable, firma/evidencia, intervalos y extracciones explícitos, filtros y criterio de confirmación, confianza, políticas de fechas y conciliación del universo.",
        "Se necesita además autorización separada para materializar. Pendientes, semanas parciales, positivos y desconocidos fuera del intervalo siempre se preservan.",
        "Ninguna partición dispone de ambas clases actuales. Los umbrales de soporte opcional son diagnósticos y no validan tamaño muestral.", "",
        "## Archivos y reproducibilidad", "",
        "Módulos experiment_selection, experiment_missing, experiment_coverage, experiment_protocol y experiment_pipeline, configuración de ejemplo y pruebas ficticias nuevas.",
        "Configuraciones A/B/C, auditorías por columna/año, comparación de conjuntos, soporte sólo en entrenamiento, inventario de elegibilidad y previsualizaciones de cobertura quedan privados.",
        "Metadatos y manifiesto conservan versiones, hashes de entradas/implementación/salidas y entorno. Se exige carpeta nueva y se comprueba conservación de datos y artefactos previos.",
        "No se modificaron los módulos de Fase 5A, modelos existentes, fuentes, frontend o backend. Sin commit/push/publicación. Detención para revisión.", ""]
    return "\n".join(lines)


def run_experiment_preparation(root, options):
    require_branch(root)
    inputs, output = experiment_paths(root, options)
    _, registry = load_configuration(inputs["access_config"], root)
    if not registry.sources:
        raise ValueError("Sin autorización de fuentes")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.INSPECTION)
        source.require_source_use(AuthorizedUse.PROCESSING)
    before = protected_snapshot(root, output)
    verify_private_manifest(inputs["phase5a_dir"])
    verify_private_manifest(inputs["universe_dir"])
    require_manifest(inputs["observed_dir"])
    metadata = read_json(inputs["phase5a_dir"] / "metadata.private.json")
    verify_sources(registry, metadata["coverage_metadata"])
    if metadata["training_enabled"] is not False:
        raise ValueError("La entrada no es el dataset de preparación preservado")
    for name, expected in metadata["implementation_sha256"].items():
        if Path(name).name != name or digest_path(Path(__file__).parent / name) != expected:
            raise ValueError("Cambió la implementación de Fase 5A")
    universe_path = inputs["universe_dir"] / "review.private.json"
    if digest_path(universe_path) != metadata["universe_review_sha256"]:
        raise ValueError("La revisión de universo ya no coincide con Fase 5A")
    universe = read_json(universe_path)
    universe_config = read_json(inputs["universe_dir"] / "configuration.private.json")
    if universe_config["training_enabled"] is not False or universe_config["generate_assumed_zeros"] is not False:
        raise ValueError("La configuración de Fase 4.3 habilita acciones fuera de alcance")
    if universe["provenance"] != metadata["source_provenance"]["normalization"]:
        raise ValueError("La revisión del universo usa otras fuentes")
    definitions = read_json(inputs["phase5a_dir"] / "feature_definitions.private.json")
    source_ids = {source.source_id for source in registry.sources}
    if options["source_2022_id"] not in source_ids:
        raise ValueError("La fuente configurada para revisar 2022 no está autorizada")
    protocol = experiment_protocol()
    all_tables, all_policies, labels_by_policy = {}, {}, {}
    report = {"version": VERSION, "training_performed": False, "negatives_materialized": False,
              "imputation_performed": False, "training_ready": False, "protocol": protocol, "datasets": {}}
    for policy in ("strict", "expanded"):
        observed = inputs["observed_dir"] / policy / "exploratory"
        require_manifest(observed)
        audit = pd.read_parquet(observed / "records_audit.parquet")
        inventory, eligibility = eligibility_review(audit, source_2022=options["source_2022_id"])
        for scenario in ("conservative", "exploratory"):
            name = f"{policy}/{scenario}"
            directory = inputs["phase5a_dir"] / name
            features = pd.read_parquet(directory / "predictors_retrospective.private.parquet").sort_values(KEYS).reset_index(drop=True)
            labels = pd.read_parquet(directory / "labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
            context = pd.read_parquet(directory / "context.private.parquet").sort_values(KEYS).reset_index(drop=True)
            assignments = pd.read_parquet(directory / "splits.private.parquet")
            validate_panel(context, set(context.radio_censal), metadata["analysis_period"])
            if len(features.columns) != 55 or len(context.radio_censal.unique()) != EXPECTED_RADIOS:
                raise ValueError("No se conserva la estructura de Fase 5A")
            if labels.apto_entrenamiento.any() or not labels.escenario.eq(scenario).all() or not labels.panel_fechas.eq(policy).all():
                raise ValueError("Etiquetas habilitadas o escenarios mezclados")
            pd.testing.assert_frame_equal(labels[KEYS], context[KEYS])
            pd.testing.assert_series_equal(labels.objetivo_semana_siguiente, context.objetivo_semana_siguiente)
            column_audit, column_year, policies = audit_columns(features, labels, definitions)
            support, partitions = training_support(features, labels, assignments)
            preview, coverage = declared_coverage_preview(context, universe_config["coverage_declarations"], source_ids, date_policy=policy)
            all_tables[name] = {"column_audit": column_audit, "column_by_year": column_year,
                "set_comparison": compare_sets(features, labels), "training_feature_support": support,
                "partition_classes": partitions, "eligibility_inventory": inventory,
                "assumed_coverage_preview": preview}
            all_policies[name] = policies
            target = labels.objetivo_semana_siguiente
            counts = {"positive": int(target.eq(1).sum()), "negative": int(target.eq(0).sum()), "unknown": int(target.isna().sum())}
            prior = universe["statistics"][policy]["overall"]["next_week_labels"]
            if prior != counts:
                raise ValueError("Las etiquetas ya no concilian con Fase 4.3")
            report["datasets"][name] = {"rows": len(features), **counts, "eligibility": eligibility,
                "coverage": coverage,
                "phase43_conditional_capacity": universe["statistics"][policy]["overall"]["potential_next_week_negatives_conditional"],
                "history_availability_verified": False, "census_historical_availability_verified": False,
                "training_ready": False}
            labels_by_policy[name] = labels
    report["date_policy_comparison"] = {scenario: label_policy_comparison(labels_by_policy[f"strict/{scenario}"], labels_by_policy[f"expanded/{scenario}"])
                                         for scenario in ("conservative", "exploratory")}
    require_preserved(before, protected_snapshot(root, output))
    output.mkdir(parents=True, exist_ok=False)
    for name, tables in all_tables.items():
        directory = output / name
        directory.mkdir(parents=True)
        for table, frame in tables.items():
            write_frame(frame, directory / f"{table}.private.parquet")
        write_report(all_policies[name], directory / "column_policies.private.json")
    for name, specification in SETS.items():
        write_report({"version": VERSION, "set": name, **specification, "training_enabled": False,
            "parameters": protocol["parameters"], "missingness": protocol["imputation"],
            "optional_support_rule": protocol["optional_selection_rule"],
            "date_policies": ["strict", "expanded"], "coverage_scenarios": ["conservative", "experimental_assumed_not_materialized"],
            "retrospective_only": True}, output / f"experiment_{name}.private.json")
    write_report(protocol, output / "protocol.private.json")
    write_report(options, output / "configuration.private.json")
    write_report(declaration_template(source_ids), output / "coverage_declaration.template.private.json")
    write_report(universe_config, output / "phase43_configuration.private.json")
    write_report(report, output / "review.private.json")
    (output / "implementation.private.md").write_text(report_text(report, all_tables), encoding="utf-8")
    write_report({"version": VERSION, "phase5a_version": metadata["version"],
        "calendar_version": metadata["calendar_version"], "data_kind": metadata["data_kind"],
        "source_provenance": metadata["source_provenance"], "analysis_period": metadata["analysis_period"],
        "selection_exclusion": {"features": all_policies, "labels": "inherited, no reclassification or unknown-to-negative conversion"},
        "training_enabled": False, "materialization_enabled": False,
        "implementation_sha256": {path.name: digest_path(path) for path in sorted(Path(__file__).parent.glob("experiment_*.py"))},
        "input_manifests_sha256": {name: digest_path(path / "integrity_manifest.private.json") for name, path in inputs.items() if name in {"phase5a_dir", "universe_dir"}},
        "runtime": protocol["environment"]}, output / "metadata.private.json")
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
        report = run_experiment_preparation(root, read_json(args.config))
        print(json.dumps({"version": VERSION, "training_performed": False, "negatives_materialized": False,
            "datasets": {name: {key: value[key] for key in ("rows", "positive", "negative", "unknown")} for name, value in report["datasets"].items()}}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó Fase 5B. Revisar configuración/integridad privadas; no volcar registros.\n")


if __name__ == "__main__":
    main()
