"""Auditoría metodológica no epidemiológica del índice estructural."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sigard_ml.territorial.analysis import deterministic_percentiles


def _matrix(frame: pd.DataFrame, features: list[str], method: str) -> dict[str, dict[str, float]]:
    matrix = frame[features].corr(method=method)
    return {row: {column: float(matrix.loc[row, column]) for column in features} for row in features}


def _ranks(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    result = frame[["radio_id"]].copy()
    for feature in features:
        ordered = frame[["radio_id", feature]].sort_values([feature, "radio_id"], kind="mergesort")
        values = pd.Series(np.arange(1, len(frame) + 1) / len(frame), index=ordered.index)
        result[f"{feature}_rank"] = values.reindex(frame.index)
    return result


def _ranking(frame: pd.DataFrame, components: list[str], name: str) -> pd.DataFrame:
    result = frame[["radio_id", *components]].copy()
    result[name] = result[components].mean(axis=1)
    ranked = deterministic_percentiles(result, name)
    return ranked[["radio_id", name, "deterministic_rank", "percentile", "relative_level"]]


def _compare(reference: pd.DataFrame, candidate: pd.DataFrame, reference_score: str, candidate_score: str) -> dict[str, Any]:
    merged = reference.merge(candidate, on="radio_id", suffixes=("_reference", "_candidate"), validate="one_to_one")
    change = (merged.deterministic_rank_candidate - merged.deterministic_rank_reference).abs()
    level_changed = merged.relative_level_reference.ne(merged.relative_level_candidate)
    movers = merged.assign(position_change=change).sort_values(["position_change", "radio_id"], ascending=[False, True]).head(15)
    return {"spearman_ranking_correlation": float(merged.deterministic_rank_reference.corr(merged.deterministic_rank_candidate, method="spearman")),
            "pearson_score_correlation": float(merged[reference_score].corr(merged[candidate_score], method="pearson")),
            "mean_absolute_position_change": float(change.mean()), "max_absolute_position_change": int(change.max()),
            "radios_changing_relative_level": int(level_changed.sum()),
            "level_transition_counts": {f"{a}->{b}": int(count) for (a, b), count in merged.groupby(["relative_level_reference", "relative_level_candidate"], observed=True).size().items()},
            "largest_position_changes": [{"radio_id": row.radio_id, "reference_rank": int(row.deterministic_rank_reference), "candidate_rank": int(row.deterministic_rank_candidate), "absolute_change": int(row.position_change), "reference_level": row.relative_level_reference, "candidate_level": row.relative_level_candidate} for row in movers.itertuples()]}


def build_audit(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    features = config["features"]
    forbidden_tokens = ("cases", "dengue", "target", "prediction", "synthetic")
    if any(any(token in feature.lower() for token in forbidden_tokens) for feature in features): raise ValueError("La auditoría no admite variables epidemiológicas o sintéticas")
    if len(frame) != 263 or frame.radio_id.nunique() != 263: raise ValueError("Se esperaban 263 radios únicos")
    ranks = _ranks(frame, features)
    rank_columns = [f"{feature}_rank" for feature in features]
    a = _ranking(ranks, rank_columns, "score_a_current")
    b = _ranking(ranks, [column for column in rank_columns if column != "area_km2_rank"], "score_b_without_area")
    c = _ranking(ranks, ["population_density_rank", "population_rank", "area_km2_rank"], "score_c_compact")
    context = ranks.copy()
    context["household_dwelling_context_rank"] = context[["households_rank", "dwellings_rank"]].mean(axis=1)
    d = _ranking(context, ["population_rank", "population_density_rank", "household_dwelling_context_rank"], "score_d_demographic_context")
    merged_a = ranks.merge(a[["radio_id", "score_a_current"]], on="radio_id", validate="one_to_one")
    contribution = {feature: {"pearson_rank_to_score": float(merged_a[f"{feature}_rank"].corr(merged_a.score_a_current, method="pearson")), "spearman_rank_to_score": float(merged_a[f"{feature}_rank"].corr(merged_a.score_a_current, method="spearman"))} for feature in features}
    leave_one_out = {}
    for feature in features:
        candidate_name = f"score_without_{feature}"
        candidate = _ranking(ranks, [column for column in rank_columns if column != f"{feature}_rank"], candidate_name)
        leave_one_out[feature] = _compare(a, candidate, "score_a_current", candidate_name)
    pearson, spearman = _matrix(frame, features, "pearson"), _matrix(frame, features, "spearman")
    high = []
    for method, matrix in (("pearson", pearson), ("spearman", spearman)):
        for index, left in enumerate(features):
            for right in features[index + 1:]:
                value = matrix[left][right]
                if abs(value) > 0.80: high.append({"method": method, "feature_a": left, "feature_b": right, "correlation": value})
    comparisons = {"A_vs_B_without_area": _compare(a, b, "score_a_current", "score_b_without_area"),
                   "A_vs_C_compact": _compare(a, c, "score_a_current", "score_c_compact"),
                   "A_vs_D_demographic_context": _compare(a, d, "score_a_current", "score_d_demographic_context"),
                   "B_vs_C": _compare(b, c, "score_b_without_area", "score_c_compact"),
                   "B_vs_D": _compare(b, d, "score_b_without_area", "score_d_demographic_context"),
                   "C_vs_D": _compare(c, d, "score_c_compact", "score_d_demographic_context")}
    return {"pipeline": config["pipeline"], "dataset": {"radios": len(frame), "features": features, "epidemiological_variables_used": False},
            "pearson_correlation": pearson, "spearman_correlation": spearman, "absolute_correlations_over_0_80": high,
            "redundancy_assessment": {"population_households_dwellings": "Population y households son altamente redundantes; households y dwellings también. Population y dwellings no superan 0.80, pero pertenecen al mismo bloque demográfico y muestran asociación considerable.", "consequence": "El promedio actual da tres de cinco votos a dimensiones estrechamente relacionadas con tamaño demográfico/residencial."},
            "effective_contribution": contribution, "leave_one_feature_out": leave_one_out,
            "formula_definitions": {"A_current": "mean(population, population_density, households, dwellings, area_km2 ranks)", "B_without_area": "mean(population, population_density, households, dwellings ranks)", "C_compact": "mean(population_density, population, area_km2 ranks)", "D_demographic_context": "mean(population_rank, population_density_rank, mean(households_rank, dwellings_rank))"},
            "formula_comparisons": comparisons, "area_assessment": {"directional_assumption_supported": False, "reason": "No existe evidencia epidemiológica en los datos disponibles para asumir que mayor superficie incremente susceptibilidad; además area_km2 se relaciona inversamente con densidad en Spearman.", "A_vs_B": comparisons["A_vs_B_without_area"]},
            "methodological_recommendation": "No adoptar todavía A como índice definitivo. Mantener A sólo como descriptor exploratorio; tratar la inclusión positiva de area_km2 como no justificada y evitar contar population, households y dwellings como tres dimensiones independientes. Antes de elegir B, C o D se requiere una definición conceptual externa y, para validación epidemiológica, datos espaciales observados.",
            "name_assessment": {"current_name_justified": False, "current": "structural_susceptibility_score", "recommended": "territorial_context_score", "reason": "Las variables describen tamaño, densidad, parque habitacional y superficie, pero no miden exposición vectorial, condiciones ambientales ni incidencia espacial; susceptibility sugiere una interpretación epidemiológica que no puede validarse."},
            "limitations": ["No se utilizaron casos, predicciones ni resultados de dengue.", "La auditoría analiza sensibilidad interna, no validez epidemiológica externa.", "Ninguna variante A/B/C/D queda adoptada automáticamente."]}


def run(config: dict[str, Any], root: Path) -> dict[str, Any]:
    return build_audit(pd.read_parquet(root / config["input"]), config)


def write_report(report: dict[str, Any], config: dict[str, Any], root: Path, overwrite: bool = False) -> None:
    path = root / config["output"]
    if path.exists() and not overwrite: raise FileExistsError(f"No se sobrescribe {path}")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--repo-root", type=Path, default=Path.cwd()); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(); config = json.loads(args.config.read_text(encoding="utf-8")); root = args.repo_root.resolve(); write_report(run(config, root), config, root, args.overwrite)


if __name__ == "__main__": main()
