"""Etapa 5: evaluación temporal del baseline de persistencia."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from sigard_ml.evaluation.temporal import build_temporal_split, evaluate_predictions, validate_panel
from sigard_ml.models.persistence import PersistenceBaseline

LOGGER = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def resolve_path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def run_evaluation(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    panel = pd.read_parquet(resolve_path(root, config["input"]))
    columns = config["columns"]
    validate_panel(panel, columns, config.get("expected_radio_count"))
    split = build_temporal_split(panel, week_column=columns["week_start"], test_weeks=config["split"]["test_weeks"])
    test_weeks = split.loc[split.split.eq("test"), columns["week_start"]]
    test = panel.loc[panel[columns["week_start"]].isin(test_weeks)].copy()
    model = PersistenceBaseline(columns["current_cases"])
    predicted = model.predict(test[[columns["current_cases"]]])
    predictions = test[[columns["radio_id"], columns["year"], columns["week"], columns["week_start"], columns["target"]]].copy()
    predictions.columns = ["radio_id", "origin_epidemiological_year", "origin_epidemiological_week", "origin_week_start_date", "target_cases_next_week"]
    predictions["target_week_start_date"] = predictions["origin_week_start_date"] + pd.Timedelta(days=7)
    target_calendar = panel[[columns["week_start"], columns["year"], columns["week"]]].drop_duplicates()
    target_calendar.columns = ["target_week_start_date", "target_epidemiological_year", "target_epidemiological_week"]
    predictions = predictions.merge(target_calendar, on="target_week_start_date", how="left", validate="many_to_one")
    missing_calendar = predictions["target_epidemiological_year"].isna()
    if missing_calendar.any():
        predictions.loc[missing_calendar, "target_epidemiological_year"] = predictions.loc[missing_calendar, "origin_epidemiological_year"]
        predictions.loc[missing_calendar, "target_epidemiological_week"] = predictions.loc[missing_calendar, "origin_epidemiological_week"] + 1
    predictions["target_epidemiological_year"] = predictions["target_epidemiological_year"].astype("int64")
    predictions["target_epidemiological_week"] = predictions["target_epidemiological_week"].astype("int64")
    predictions["predicted_cases"] = predicted.to_numpy()
    predictions["model_name"] = "PersistenceBaseline"
    predictions["model_version"] = config["pipeline"]["version"]
    predictions["target_is_synthetic"] = True
    predictions["is_prediction"] = True
    predictions = predictions.sort_values(["origin_week_start_date", "radio_id"]).reset_index(drop=True)
    metrics, weekly = evaluate_predictions(predictions)
    train_dates = split.loc[split.split.eq("train"), columns["week_start"]]
    report = {
        "pipeline": config["pipeline"],
        "model": {"name": "PersistenceBaseline", "definition": "predicted_cases(t+1) = synthetic_cases_assigned(t)", "stochastic": False},
        "provenance": {"input": config["input"], "input_version": config["data_version"], "unit": "radio_censal - semana_epidemiologica", "target_condition": "synthetic", "prediction_condition": "predicted"},
        "reproducibility": {"seed": config["seed"], "deterministic": True},
        "split": {"strategy": "complete_weeks_last_consecutive_block_holdout", "train_week_count": int(len(train_dates)), "test_week_count": int(len(test_weeks)), "train_start": train_dates.min().date().isoformat(), "train_end": train_dates.max().date().isoformat(), "test_start": test_weeks.min().date().isoformat(), "test_end": test_weeks.max().date().isoformat(), "continuous_block_count": int(split["continuous_block"].nunique())},
        "rows": {"input": int(len(panel)), "test_predictions": int(len(predictions))},
        "metrics": metrics,
        "weekly_metrics": weekly.assign(target_week_start_date=weekly.target_week_start_date.dt.strftime("%Y-%m-%d")).to_dict(orient="records"),
        "limitations": ["El target por radio es una asignación sintética, no evidencia epidemiológica espacial.", "El baseline no se entrena: train sólo delimita el período de desarrollo anterior al test."],
    }
    return split, predictions, report


def write_outputs(split: pd.DataFrame, predictions: pd.DataFrame, report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    paths = {name: resolve_path(root, value) for name, value in config["outputs"].items()}
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"No se sobrescriben salidas existentes: {existing}")
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    split.to_parquet(paths["split"], index=False, engine="pyarrow", compression="snappy")
    predictions.to_parquet(paths["predictions"], index=False, engine="pyarrow", compression="snappy")
    with paths["metrics"].open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true", help="Reemplaza sólo las tres salidas configuradas de etapa 5")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config, root = load_config(args.config.resolve()), args.repo_root.resolve()
    split, predictions, report = run_evaluation(config, root)
    write_outputs(split, predictions, report, config, root, args.overwrite)
    LOGGER.info("Baseline evaluado sobre %d predicciones", len(predictions))


if __name__ == "__main__":
    main()
