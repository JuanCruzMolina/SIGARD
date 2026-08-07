"""Pipeline de la tercera etapa reproducible de SIGARD v0.1."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from sigard_ml.simulation.allocation import ClusterParameters, population_proportional, spatial_clusters
from sigard_ml.validation.synthetic import SyntheticValidationError, quality_metrics, validate_allocation

LOGGER = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def resolve_path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def _require_columns(frame: pd.DataFrame, columns: list[str], source: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise SyntheticValidationError(f"Columnas faltantes en {source}: {missing}")


def build_allocations(config: dict[str, Any], root: Path) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    columns = config["columns"]
    territorial_path = resolve_path(root, config["inputs"]["territorial"])
    weekly_path = resolve_path(root, config["inputs"]["weekly"])
    LOGGER.info("Leyendo entradas inmutables %s y %s", territorial_path, weekly_path)
    territorial = pd.read_parquet(territorial_path)
    weeks = pd.read_parquet(weekly_path)
    _require_columns(territorial, [columns["radio_id"], columns["population"], columns["neighbors"]], str(territorial_path))
    _require_columns(weeks, [columns[key] for key in ("year", "week", "week_start", "week_end", "observed_cases", "status")], str(weekly_path))
    expected_radios = int(config["universe"]["expected_radio_count"])
    if len(territorial) != expected_radios or territorial[columns["radio_id"]].nunique() != expected_radios:
        raise SyntheticValidationError(f"El universo territorial no contiene exactamente {expected_radios} radios únicos")
    allowed = set(config["weekly_filter"]["allowed_statuses"])
    forbidden = set(config["weekly_filter"]["forbidden_statuses"])
    if weeks[columns["status"]].isin(forbidden).any():
        raise SyntheticValidationError("La entrada semanal contiene estados expresamente prohibidos")
    weeks = weeks.loc[weeks[columns["status"]].isin(allowed)].copy()
    observed = pd.to_numeric(weeks[columns["observed_cases"]], errors="coerce")
    if observed.isna().any() or (observed < 0).any() or (observed % 1 != 0).any():
        raise SyntheticValidationError("Los totales departamentales deben ser enteros no negativos y no nulos")
    weeks[columns["observed_cases"]] = observed.astype("int64")
    version, seed = config["simulation"]["version"], int(config["simulation"]["seed"])
    cluster_config = config["scenarios"]["spatial_clusters"]
    parameters = ClusterParameters(**cluster_config["parameters"])
    outputs = {
        "population_proportional": population_proportional(territorial, weeks, columns, seed, version),
        "spatial_clusters": spatial_clusters(territorial, weeks, columns, seed, version, parameters),
    }
    validations = {name: {**validate_allocation(frame, expected_radios), **quality_metrics(frame, int(config["quality_report"]["top_radio_count"]))} for name, frame in outputs.items()}
    report = {
        "pipeline": config["pipeline"], "simulation": config["simulation"], "inputs": config["inputs"],
        "unit": "radio censal - semana epidemiológica", "data_nature": {"department_cases_observed": "observado real agregado de Capital", "synthetic_cases_assigned": "asignación sintética; no representa ubicación real"},
        "variables_used": {"population_proportional": [columns["population"]], "spatial_clusters": [columns["population"], columns["neighbors"]]},
        "weekly_filter": config["weekly_filter"], "scenarios": config["scenarios"], "results": validations,
    }
    return outputs, report


def write_outputs(outputs: dict[str, pd.DataFrame], report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    paths = {name: resolve_path(root, config["outputs"][name]) for name in outputs}
    report_path = resolve_path(root, config["outputs"]["quality_report"])
    targets = [*paths.values(), report_path]
    existing = [str(path) for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas existentes: {existing}")
    for name, frame in outputs.items():
        path = paths[name]; path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True); stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true", help="Permite reemplazar sólo las salidas configuradas")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config, root = load_config(args.config.resolve()), args.repo_root.resolve()
    outputs, report = build_allocations(config, root)
    write_outputs(outputs, report, config, root, args.overwrite)
    LOGGER.info("Asignaciones generadas: %s", {name: len(frame) for name, frame in outputs.items()})


if __name__ == "__main__":
    main()
