"""Materializa sólo el escenario privado autorizado; no abre Excel ni entrena."""

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from sigard_ml.official.access import AuthorizedUse
from sigard_ml.official.observed_pipeline import require_branch, write_frame
from sigard_ml.official.pipeline import load_configuration
from sigard_ml.official.reports import write_report
from sigard_ml.official.spatial_pipeline import digest_path, require_preserved
from sigard_ml.official.spatial_ml.pipeline import read_json, verify_private_manifest, verify_sources
from sigard_ml.official.spatial_ml.validation import validate_panel
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.assumed_scenario import (
    VERSION, ZERO_KIND, validate_authorization, materialize_labels, distribution, chronological_review,
)
from sigard_ml.official.spatial_ml.splits import class_counts

EXPECTED_RADIOS = 263
DEFAULTS = {"version": VERSION, "access_config": "data/interim/official/access.private.json",
    "phase5a_dir": "data/processed/official/spatial_ml_05a_v2",
    "phase5b_dir": "data/interim/official/spatial_experiment_05b_v1",
    "output_dir": "data/processed/official/spatial_assumed_2024_v1",
    "training_enabled": False, "authorization": None}


def paths(root, options):
    if set(options) != set(DEFAULTS) or options["version"] != VERSION or options["training_enabled"] is not False:
        raise ValueError("Configuración fuera de alcance")
    validate_authorization(options["authorization"])
    root = root.resolve()
    interim = (root / "data/interim/official").resolve()
    processed = (root / "data/processed/official").resolve()
    if not interim.is_relative_to(root) or not processed.is_relative_to(root):
        raise ValueError("Almacenamiento fuera del entorno privado")
    inputs = {name: (root / options[name]).resolve() for name in ("access_config", "phase5a_dir", "phase5b_dir")}
    for name, path in inputs.items():
        parent = processed if name == "phase5a_dir" else interim
        if path == parent or not path.is_relative_to(parent):
            raise ValueError("Entrada fuera del almacenamiento privado")
    output = (root / options["output_dir"]).resolve()
    if output.parent != processed or output.exists() or any(output == path or output.is_relative_to(path) for path in inputs.values()):
        raise ValueError("Se requiere un destino privado nuevo")
    for path in [*inputs.values(), output]:
        result = subprocess.run(["git", "check-ignore", "--quiet", "--", str(path.relative_to(root))],
            cwd=root, capture_output=True, check=False)
        if result.returncode != 0:
            raise ValueError("Ruta no excluida de Git")
    return inputs, output


def snapshot(inputs, registry):
    # Sólo archivos listos declarados y derivados previos conocidos; no se buscan
    # ni se inventarían archivos sanitarios adicionales en revisión.
    files = {source.path for source in registry.sources}
    for path in inputs.values():
        files.update(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else files.add(path)
    root = inputs["access_config"].parents[3]
    for name in ("data/interim/official/observed", "data/interim/official/geography",
                 "ml/artifacts", "ml/models", "frontend/public/data"):
        directory = root / name
        if directory.exists():
            files.update(path for path in directory.rglob("*") if path.is_file())
    return {str(path): digest_path(path) for path in sorted(files)}


def report_text(report):
    lines = ["# Escenario experimental de cobertura asumida", "",
        "Privado. Cobertura asumida para investigación, no verificada. No se entrenó.",
        f"Universo listo autorizado: {report['ready_universe_records']} registros; no es el universo epidemiológico definitivo.",
        "Intervalo objetivo inclusivo: 2024-01-07 a 2024-06-08; fuente delivery_2024_2026; 263 radios.",
        "Política de fechas ampliada; positivos provisionales y bloqueos heredados conservados.", ""]
    for name in ("full_grid", "authorized_target_interval"):
        row = report[name]
        lines += [f"## {name}", "", f"Filas {row['rows']}; positivos {row['positive']}; negativos experimentales {row['assumed_negative']}; desconocidos {row['unknown']}.", ""]
    lines += ["## Pendientes y distribuciones", "", json.dumps(report["pending_effect"], ensure_ascii=False),
        "", "Distribuciones agregadas por semana objetivo y radio en los Parquet/CSV privados.",
        "Los pendientes pueden coexistir con un positivo: preservarlo no acredita exhaustividad del conteo.", ""]
    for plan in report["partitions"]:
        lines += [f"## {plan['name']}", "", f"Estado: {plan['status']}.", ""]
        for name, counts in plan["partitions"].items():
            lines.append(f"- {name}: positivos {counts['positive']}, negativos {counts['negative']}, desconocidos {counts['unknown']}; semanas objetivo {counts['target_weeks']}.")
    lines += ["", "## Límites y siguiente decisión", "",
        "Los ceros tienen tipo cero_asumido_experimental; no son ausencias verificadas ni ausencia real de infecciones.",
        "Sólo se crean etiquetas: casos_observados y todas las características originales conservan sus null.",
        "La matriz A es una proyección sin ajustes de las siete características ya preparadas.",
        "Población, densidad, área y vecindad del Censo 2022 son contexto retrospectivo; disponibilidad histórica no acreditada.",
        "No se reconstruyó disponibilidad ni maduración de registros; no es una evaluación operativa validada.",
        "No se valida automáticamente clasificación, identidad o residencia; la fuente 2022 permanece sin resolver.",
        "No se requieren coordenadas exactas: se conservan aproximaciones y su incertidumbre.",
        "Los bloques comparten radios y una misma temporada; dependencia espacial/temporal y distribución estacional pueden sesgar métricas futuras.",
        "Se purgan objetivos que cruzan fronteras y se excluyen desconocidos del ajuste/métricas; transformaciones y baseline sólo desde entrenamiento.",
        "Ambas clases no garantizan potencia, calibración ni generalización entre temporadas. No se amplía el intervalo automáticamente.",
        "La comparación estricta usa etiquetas originales sin generar ceros bajo otra política no autorizada.",
        "Fuentes adicionales en revisión excluidas. Incorporaciones futuras requieren versiones/hashes y derivados nuevos.",
        "Modelo A, modelos existentes, fuentes y paneles anteriores intactos. Entrenamiento requiere autorización posterior.", ""]
    return "\n".join(lines)


def run_scenario(root, options):
    require_branch(root)
    inputs, output = paths(root, options)
    _, registry = load_configuration(inputs["access_config"], root)
    if len(registry.sources) != 5 or {source.source_id for source in registry.sources} != {
            "delivery_2020", "delivery_2021", "delivery_2022", "delivery_2023", "delivery_2024_2026"}:
        raise ValueError("El universo debe contener sólo las cinco fuentes listas")
    for source in registry.sources:
        source.require_source_use(AuthorizedUse.PROCESSING)
        source.require_source_use(AuthorizedUse.INSPECTION)
    before = snapshot(inputs, registry)
    for key in ("phase5a_dir", "phase5b_dir"):
        verify_private_manifest(inputs[key])
    metadata = read_json(inputs["phase5a_dir"] / "metadata.private.json")
    verify_sources(registry, metadata["coverage_metadata"])
    model_a_path = inputs["phase5b_dir"] / "experiment_A.private.json"
    model_a = read_json(model_a_path)
    if model_a["required"] != BASE or model_a["optional"] or model_a["training_enabled"] is not False:
        raise ValueError("Modelo A diferente del preparado")
    directory = inputs["phase5a_dir"] / "expanded/exploratory"
    panel = pd.read_parquet(directory / "context.private.parquet").sort_values(KEYS).reset_index(drop=True)
    original_labels = pd.read_parquet(directory / "labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
    conservative = pd.read_parquet(inputs["phase5a_dir"] / "expanded/conservative/labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
    validate_panel(panel, set(panel.radio_censal), metadata["analysis_period"])
    if (panel.radio_censal.nunique() != EXPECTED_RADIOS
            or class_counts(panel.objetivo_semana_siguiente) != options["authorization"]["expected_label_counts"]):
        raise ValueError("La grilla o las etiquetas previas no coinciden")
    pd.testing.assert_frame_equal(original_labels[KEYS], panel[KEYS])
    pd.testing.assert_series_equal(original_labels.objetivo_semana_siguiente, panel.objetivo_semana_siguiente)
    pd.testing.assert_frame_equal(original_labels[KEYS + ["objetivo_semana_siguiente"]], conservative[KEYS + ["objetivo_semana_siguiente"]])
    labels, weekly = materialize_labels(panel, options["authorization"])
    features_path = directory / "predictors_retrospective.private.parquet"
    features = pd.read_parquet(features_path).sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(features[KEYS], labels[KEYS])
    features_a = features[KEYS + BASE].copy()
    if features_a[BASE].isna().any().any() or not np.isfinite(features_a[BASE].to_numpy(dtype=float)).all():
        raise ValueError("Núcleo A incompleto")
    assignments, partitions = chronological_review(labels)
    scope = labels[labels.en_intervalo_autorizado.eq(True)].copy()
    by_week = distribution(scope, "fecha_inicio_semana_objetivo")
    by_radio = distribution(scope, "radio_censal")
    full_radio = distribution(labels, "radio_censal")
    strict = pd.read_parquet(inputs["phase5a_dir"] / "strict/exploratory/labels.private.parquet").sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(strict[KEYS], labels[KEYS])
    original = labels.objetivo_original
    changed = labels.tipo_etiqueta.eq(ZERO_KIND)
    if int(changed.sum()) != int(weekly.ausencia_asumida_autorizada.sum()):
        raise ValueError("Celdas y objetivos no concilian")
    def counts(frame):
        return {"rows": len(frame), **class_counts(frame.objetivo_semana_siguiente),
            "assumed_negative": int(frame.tipo_etiqueta.eq(ZERO_KIND).sum())}
    report = {"version": VERSION, "training_performed": False, "training_authorized": False,
        "ready_universe_records": options["authorization"]["ready_universe_records"],
        "coverage_verified": False, "verified_negatives": 0, "labels_materialized": True,
        "full_grid": counts(labels), "authorized_target_interval": counts(scope),
        "radios": int(panel.radio_censal.nunique()), "authorized_weeks": len(by_week),
        "existing_positive_labels_preserved": int(original.eq(1).sum()),
        "pending_effect": {
            "authorized_cells_with_pending": int(scope.pendientes_semana_objetivo.gt(0).sum()),
            "unknown_blocked_by_pending": int((scope.objetivo_semana_siguiente.isna() & scope.pendientes_semana_objetivo.gt(0)).sum()),
            "positive_with_pending": int((scope.objetivo_semana_siguiente.eq(1) & scope.pendientes_semana_objetivo.gt(0)).sum()),
            "radios_with_blocked_unknown": int(scope.loc[scope.objetivo_semana_siguiente.isna() & scope.pendientes_semana_objetivo.gt(0), "radio_censal"].nunique()),
            "partial_target_weeks": int(scope.semana_objetivo_parcial.eq(True).sum()),
            "pending_records_reclassified": 0},
        "by_radio_ranges": {column: {"min": int(by_radio[column].min()), "median": float(by_radio[column].median()),
            "max": int(by_radio[column].max()), "radios_nonzero": int(by_radio[column].gt(0).sum())}
            for column in ("positive", "negative", "unknown")},
        "by_week_ranges": {column: {"min": int(by_week[column].min()), "max": int(by_week[column].max())}
            for column in ("positive", "negative", "unknown")},
        "approximate_positive_labels_in_interval": int((scope.objetivo_semana_siguiente.eq(1) & scope.objetivo_con_fecha_aproximada).sum()),
        "strict_sensitivity_original_labels_only": {
            "new_expanded_negative_strict_positive": int((changed & strict.objetivo_semana_siguiente.eq(1)).sum()),
            "expanded_positive_strict_unknown_in_interval": int((labels.en_intervalo_autorizado.eq(True) & original.eq(1) & strict.objetivo_semana_siguiente.isna()).sum()),
            "strict_zeros_materialized": False},
        "model_A": {"features": BASE, "available_pct": 100.0, "parameters_changed": False,
            "historical_census_availability_verified": False, "operational_validation": False},
        "partitions": partitions, "counts_modified": False, "features_recomputed": False,
        "in_review_files_processed": False, "randomness": "none", "previous_artifacts_preserved": True}
    require_preserved(before, snapshot(inputs, registry))
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in {"labels": labels, "weekly_authorization": weekly, "predictors_A": features_a,
                        "splits": assignments, "by_target_week": by_week, "by_radio": by_radio,
                        "by_radio_full_grid": full_radio}.items():
        write_frame(frame, output / f"{name}.private.parquet")
    for name, frame in {"by_target_week": by_week, "by_radio": by_radio}.items():
        frame.to_csv(output / f"{name}.private.csv", index=False)
    write_report(options, output / "configuration.private.json")
    write_report(options["authorization"], output / "authorization.private.json")
    write_report(report, output / "review.private.json")
    (output / "implementation.private.md").write_text(report_text(report), encoding="utf-8")
    # Copia exacta de referencia: no cambiar parámetros ni habilitar fit.
    (output / "experiment_A.reference.private.json").write_bytes(model_a_path.read_bytes())
    write_report({"version": VERSION, "calendar_version": metadata["calendar_version"],
        "date_policy": "expanded", "data_kind": "official_provisional_with_assumed_experimental_labels",
        "source_provenance": metadata["source_provenance"], "coverage_metadata": metadata["coverage_metadata"],
        "input_files_sha256": before, "feature_matrix_sha256": digest_path(features_path),
        "model_A_sha256": digest_path(model_a_path), "unit": "radio_censal_origin_week_target_t_plus_1",
        "selection": "preserve all previous labels; unknown to 0 only under explicit assumed authorization without blockers",
        "unknown_labels": "never supervised negatives unless separately authorized by this scoped assumption",
        "counts_and_history": "unchanged; experimental absence labels never used as observed counts or history",
        "previous_source_count": len(registry.sources),
        "ready_universe_records": options["authorization"]["ready_universe_records"],
        "availability": "retrospective only; census publication and outcome maturation unverified",
        "implementation_sha256": {path.name: digest_path(path) for path in (Path(__file__), Path(__file__).with_name("assumed_scenario.py"))},
        "runtime": {"pandas": pd.__version__, "numpy": np.__version__}, "training_enabled": False},
        output / "metadata.private.json")
    require_preserved(before, snapshot(inputs, registry))
    write_report({"version": VERSION, "previous_artifacts_preserved": True,
        "protected_files_sha256": before,
        "outputs_sha256": {path.relative_to(output).as_posix(): digest_path(path)
                           for path in sorted(output.rglob("*")) if path.is_file()}},
        output / "integrity_manifest.private.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--diagnose-failure", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[5]
        report = run_scenario(root, read_json(args.config))
        print(json.dumps({key: report[key] for key in ("version", "full_grid", "authorized_target_interval",
            "pending_effect", "partitions", "training_performed")}, sort_keys=True))
    except Exception as error:
        if args.diagnose_failure:
            trace, locations = error.__traceback__, []
            while trace:
                locations.append(f"{trace.tb_frame.f_code.co_name}:{trace.tb_lineno}")
                trace = trace.tb_next
            print(type(error).__name__ + " " + " -> ".join(locations))
        parser.exit(1, "No se completó el escenario; revisar integridad/configuración privadas sin volcar registros.\n")


if __name__ == "__main__":
    main()
