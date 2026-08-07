"""Pipeline reproducible de dengue y clima semanal para Capital."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from sigard_ml.transformation.temporal import aggregate_climate, aggregate_dengue, integrate_weekly, select_modeling_weeks
from sigard_ml.validation.temporal import TemporalValidationError, epidemiological_week_start, integer_values, require_columns

LOGGER = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def resolve_path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def load_dengue(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    columns = config["columns"]["dengue"]
    required = list(columns.values())
    selected: list[pd.DataFrame] = []
    reports: list[dict[str, Any]] = []
    for source in config["sources"]["dengue"]:
        path = resolve_path(root, source["path"])
        LOGGER.info("Leyendo dengue: %s", path)
        raw = pd.read_csv(path, sep=source["delimiter"], encoding=source["encoding"], dtype="string", skip_blank_lines=False)
        require_columns(raw, required, str(path))
        exact_duplicates = int(raw.duplicated().sum())
        blank_rows = int(raw[required].isna().all(axis=1).sum())
        area = config["area"]
        filtered = raw.loc[raw[columns["province"]].str.strip().str.casefold().eq(area["province"].casefold()) & raw[columns["department"]].str.strip().str.casefold().eq(area["department"].casefold())].copy()
        year, invalid_year = integer_values(filtered[columns["year"]], columns["year"], 1)
        week, invalid_week = integer_values(filtered[columns["week"]], columns["week"], 1)
        cases, invalid_cases = integer_values(filtered[columns["cases"]], columns["cases"], 0)
        invalid_week |= week.gt(53).fillna(False)
        invalid_week |= epidemiological_week_start(year, week).isna()
        invalid = invalid_year | invalid_week | invalid_cases
        coverage = source["coverage"]
        coverage_start = epidemiological_week_start(pd.Series([coverage["epidemiological_year"]]), pd.Series([coverage["week_min"]])).iloc[0]
        coverage_end_start = epidemiological_week_start(pd.Series([coverage["epidemiological_year"]]), pd.Series([coverage["week_max"]])).iloc[0]
        nonblank = raw.dropna(subset=[columns["year"], columns["week"]])
        raw_year = pd.to_numeric(nonblank[columns["year"]], errors="coerce")
        raw_week = pd.to_numeric(nonblank[columns["week"]], errors="coerce")
        report = {"path": source["path"], "encoding": source["encoding"], "snapshot": source["snapshot"], "rows": int(len(raw)), "blank_rows": blank_rows, "exact_duplicate_rows_all_areas": exact_duplicates, "declared_coverage": {**coverage, "week_start_date": coverage_start.date().isoformat(), "week_end_date": (coverage_end_start + pd.Timedelta(days=6)).date().isoformat()}, "actual_values_all_areas": {"year_min": int(raw_year.min()), "year_max": int(raw_year.max()), "week_min": int(raw_week.min()), "week_max": int(raw_week.max())}, "capital_rows": int(len(filtered)), "capital_exact_duplicate_rows": int(filtered.duplicated().sum()), "capital_invalid_year_rows": int(invalid_year.sum()), "capital_invalid_week_rows": int(invalid_week.sum()), "capital_invalid_case_rows": int(invalid_cases.sum())}
        reports.append(report)
        actual = report["actual_values_all_areas"]
        coverage_mismatch = actual != {"year_min": coverage["epidemiological_year"], "year_max": coverage["epidemiological_year"], "week_min": coverage["week_min"], "week_max": coverage["week_max"]}
        if filtered.empty or invalid.any() or coverage_mismatch:
            raise TemporalValidationError(f"Dengue inválido en {path}: {report}")
        selected.append(pd.DataFrame({"epidemiological_year": year.astype("int64"), "epidemiological_week": week.astype("int64"), "dengue_cases_observed": cases.astype("int64")}))
    combined = pd.concat(selected, ignore_index=True)
    if combined.duplicated(["epidemiological_year", "epidemiological_week"], keep=False).any():
        LOGGER.info("Hay múltiples estratos por semana; se sumarán sus cantidades")
    return combined, reports


def dengue_coverage(config: dict[str, Any]) -> pd.DataFrame:
    """Expande los intervalos declarados y verificables de cada extracción."""
    rows: list[dict[str, int]] = []
    for source in config["sources"]["dengue"]:
        coverage = source["coverage"]
        rows.extend({"epidemiological_year": coverage["epidemiological_year"], "epidemiological_week": week} for week in range(coverage["week_min"], coverage["week_max"] + 1))
    return pd.DataFrame(rows).drop_duplicates().sort_values(["epidemiological_year", "epidemiological_week"]).reset_index(drop=True)


def load_climate(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = config["sources"]["climate"]
    columns = config["columns"]["climate"]
    path = resolve_path(root, source["path"])
    LOGGER.info("Leyendo clima: %s", path)
    raw = pd.read_csv(path, sep=source["delimiter"], encoding=source["encoding"], skiprows=source["skiprows"])
    require_columns(raw, list(columns.values()), str(path))
    date = pd.to_datetime(raw[columns["date"]], format="%Y-%m-%d", errors="coerce")
    values: dict[str, pd.Series] = {}
    invalid_numeric: dict[str, int] = {}
    for output, configured in columns.items():
        if output == "date":
            continue
        values[output] = pd.to_numeric(raw[configured], errors="coerce")
        invalid_numeric[output] = int(values[output].isna().sum() - raw[configured].isna().sum())
    valid_dates = pd.DatetimeIndex(date.dropna())
    missing_dates = pd.date_range(valid_dates.min(), valid_dates.max()).difference(valid_dates)
    report = {"path": source["path"], "encoding": source["encoding"], "rows": int(len(raw)), "date_min": date.min().date().isoformat(), "date_max": date.max().date().isoformat(), "invalid_date_rows": int(date.isna().sum()), "duplicate_date_rows": int(date.duplicated(keep=False).sum()), "missing_calendar_dates": [value.date().isoformat() for value in missing_dates], "exact_duplicate_rows": int(raw.duplicated().sum()), "null_counts": {column: int(raw[column].isna().sum()) for column in columns.values()}, "invalid_numeric_rows": invalid_numeric}
    if report["invalid_date_rows"] or report["duplicate_date_rows"] or any(invalid_numeric.values()):
        raise TemporalValidationError(f"Clima inválido en {path}: {report}")
    return pd.DataFrame({"date": date, **values}), report


def missing_week_keys(frame: pd.DataFrame) -> list[str]:
    starts = pd.DatetimeIndex(frame["week_start_date"].sort_values().unique())
    expected = pd.date_range(starts.min(), starts.max(), freq="W-SUN")
    return [date.date().isoformat() for date in expected.difference(starts)]


def build_temporal_weekly(config: dict[str, Any], root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    dengue_daily, dengue_sources = load_dengue(config, root)
    climate_daily, climate_source = load_climate(config, root)
    dengue = aggregate_dengue(dengue_daily)
    climate = aggregate_climate(climate_daily)
    coverage = dengue_coverage(config)
    integrated = integrate_weekly(dengue, climate, coverage)
    modeling = select_modeling_weeks(integrated)
    partial = climate.loc[~climate["climate_week_complete"], ["week_start_date", "climate_days_observed"]]
    annual = dengue.groupby("epidemiological_year")["dengue_cases_observed"].sum()
    status_counts = integrated["epidemiological_status"].value_counts().to_dict()
    missing_inside = integrated.loc[integrated["epidemiological_status"].eq("missing_record"), "week_start_date"]
    report = {
        "pipeline": config["pipeline"],
        "area": config["area"],
        "epidemiological_calendar": {
            **config["epidemiological_calendar"],
            "validation": {
                "official_2024_week_1": "2023-12-31/2024-01-06",
                "iso_2024_week_1": "2024-01-01/2024-01-07",
                "conclusion": "La fuente usa calendario epidemiológico argentino domingo-sábado; no se trata como ISO.",
            },
        },
        "semantics": {
            "dengue_cases_observed": "Suma de 'cantidad' sobre estratos publicados para Capital; la fuente contiene conteos agregados, no casos individuales.",
            "epidemiological_status": {
                "observed": "Existe registro y el total es mayor que cero.",
                "explicit_zero": "Existe registro y el total publicado es cero.",
                "missing_record": "La semana está dentro del intervalo publicado, pero Capital no tiene registro; casos permanece nulo.",
                "outside_source_coverage": "La semana está fuera de todos los intervalos publicados; casos permanece nulo.",
            },
            "missing_climate": "climate_data_available=false y métricas climáticas nulas; no hay imputación.",
        },
        "inputs": {"dengue": dengue_sources, "climate": climate_source},
        "dengue": {
            "week_start_min": dengue["week_start_date"].min().date().isoformat(),
            "week_start_max": dengue["week_start_date"].max().date().isoformat(),
            "observed_weeks": int(status_counts.get("observed", 0)),
            "explicit_zero_weeks": int(status_counts.get("explicit_zero", 0)),
            "missing_records_within_source_coverage": int(status_counts.get("missing_record", 0)),
            "missing_record_week_starts": missing_inside.dt.date.astype(str).tolist(),
            "weeks_outside_source_coverage": int(status_counts.get("outside_source_coverage", 0)),
            "annual_totals": {str(k): int(v) for k, v in annual.items()},
            "output_null_counts": {k: int(v) for k, v in dengue.isna().sum().items()},
        },
        "climate": {
            "week_start_min": climate["week_start_date"].min().date().isoformat(),
            "week_start_max": climate["week_start_date"].max().date().isoformat(),
            "weeks": int(len(climate)),
            "missing_weeks": missing_week_keys(climate),
            "partial_weeks": [{"week_start_date": row.week_start_date.date().isoformat(), "days_observed": int(row.climate_days_observed)} for row in partial.itertuples(index=False)],
            "output_null_counts": {k: int(v) for k, v in climate.isna().sum().items()},
        },
        "integrated": {
            "weeks": int(len(integrated)),
            "epidemiological_status_counts": {str(k): int(v) for k, v in status_counts.items()},
            "weeks_without_climate_data": int((~integrated["climate_data_available"]).sum()),
            "null_counts": {k: int(v) for k, v in integrated.isna().sum().items()},
        },
        "modeling": {
            "weeks": int(len(modeling)),
            "inclusion_criterion": "epidemiological_status in {observed, explicit_zero} AND climate_week_complete=true; no se imputan casos ni clima.",
            "excluded_status_counts": {str(k): int(v) for k, v in integrated.loc[~integrated["epidemiological_status"].isin(["observed", "explicit_zero"]), "epidemiological_status"].value_counts().items()},
            "eligible_status_weeks_excluded_for_incomplete_climate": int((integrated["epidemiological_status"].isin(["observed", "explicit_zero"]) & ~integrated["climate_week_complete"]).sum()),
            "null_counts": {k: int(v) for k, v in modeling.isna().sum().items()},
        },
    }
    return dengue, climate, integrated, modeling, report


def write_outputs(dengue: pd.DataFrame, climate: pd.DataFrame, integrated: pd.DataFrame, modeling: pd.DataFrame, report: dict[str, Any], config: dict[str, Any], root: Path) -> None:
    outputs = config["outputs"]
    for name, frame in (("dengue", dengue), ("climate", climate), ("integrated", integrated), ("modeling", modeling)):
        path = resolve_path(root, outputs[name]); path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    report_path = resolve_path(root, outputs["quality_report"])
    with report_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True); stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args(); logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(args.config.resolve()); root = args.repo_root.resolve()
    outputs = build_temporal_weekly(config, root); write_outputs(*outputs, config, root)
    LOGGER.info("Pipeline temporal generado: %d semanas", len(outputs[2]))


if __name__ == "__main__":
    main()
