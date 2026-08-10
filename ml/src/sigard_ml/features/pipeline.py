"""Pipeline de la cuarta etapa reproducible de SIGARD v0.1."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from sigard_ml.features.radio_week import build_panel
from sigard_ml.validation.modeling_panel import validate_and_report, validate_inputs

LOGGER = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def resolve_path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def run_pipeline(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    paths = {name: resolve_path(root, value) for name, value in config["inputs"].items()}
    LOGGER.info("Leyendo entradas inmutables: %s", paths)
    territorial = pd.read_parquet(paths["territorial"])
    weekly = pd.read_parquet(paths["weekly"])
    synthetic = pd.read_parquet(paths["synthetic"])
    validate_inputs(territorial, weekly, synthetic, config)
    panel, modeling = build_panel(territorial, weekly, synthetic, config)
    report = validate_and_report(panel, modeling, territorial, config)
    return panel, modeling, report


def write_outputs(panel: pd.DataFrame, modeling: pd.DataFrame, report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    output_paths = {name: resolve_path(root, value) for name, value in config["outputs"].items()}
    existing = [str(path) for path in output_paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas existentes: {existing}")
    for name, frame in (("full_panel", panel), ("modeling_panel", modeling)):
        path = output_paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    report_path = output_paths["quality_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true", help="Permite reemplazar sólo las tres salidas de esta etapa")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config, root = load_config(args.config.resolve()), args.repo_root.resolve()
    panel, modeling, report = run_pipeline(config, root)
    write_outputs(panel, modeling, report, config, root, args.overwrite)
    LOGGER.info("Panel completo: %d filas; aptas para entrenamiento: %d", len(panel), len(modeling))


if __name__ == "__main__":
    main()
