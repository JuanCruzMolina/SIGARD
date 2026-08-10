"""Validaciones del maestro territorial."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd


CODE_WIDTHS = {
    "province_code": 2,
    "department_code": 3,
    "fraccion": 2,
    "radio": 2,
    "radio_id": 9,
}


class TerritorialValidationError(ValueError):
    """Indica que una fuente viola el contrato territorial."""


def normalize_code(values: pd.Series, width: int, field_name: str) -> pd.Series:
    """Normaliza códigos numéricos como strings sin perder ceros iniciales."""
    normalized = values.astype("string").str.strip()
    missing = normalized.isna() | normalized.eq("")
    invalid = ~normalized.fillna("").str.fullmatch(r"\d+")
    too_long = normalized.fillna("").str.len().gt(width)
    if missing.any() or invalid.any() or too_long.any():
        samples = normalized[missing | invalid | too_long].drop_duplicates().head(10)
        raise TerritorialValidationError(
            f"Código inválido en {field_name}: {samples.tolist()}"
        )
    return normalized.str.zfill(width)


def duplicated_ids(frame: pd.DataFrame, key: str = "radio_id") -> list[str]:
    """Devuelve identificadores duplicados, ordenados y sin repetición."""
    return sorted(frame.loc[frame.duplicated(key, keep=False), key].unique().tolist())


def compare_id_sets(
    reference_ids: Iterable[str], candidate_ids: Iterable[str]
) -> dict[str, list[str]]:
    """Compara los códigos de una fuente con el universo cartográfico."""
    reference = set(reference_ids)
    candidate = set(candidate_ids)
    return {
        "missing_from_source": sorted(reference - candidate),
        "not_in_cartography": sorted(candidate - reference),
    }


def validate_one_to_one_sources(
    cartography: pd.DataFrame,
    sources: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Valida unicidad y correspondencia exacta de cada fuente por radio."""
    report: dict[str, Any] = {
        "cartography_duplicate_ids": duplicated_ids(cartography),
        "sources": {},
    }
    failures: list[str] = []
    if report["cartography_duplicate_ids"]:
        failures.append("cartography has duplicate radio_id values")

    for name, frame in sources.items():
        duplicates = duplicated_ids(frame)
        comparison = compare_id_sets(cartography["radio_id"], frame["radio_id"])
        source_report = {
            "rows": int(len(frame)),
            "duplicate_ids": duplicates,
            **comparison,
            "one_to_one": not duplicates and not any(comparison.values()),
        }
        report["sources"][name] = source_report
        if not source_report["one_to_one"]:
            failures.append(f"{name} does not match cartography one-to-one")

    report["all_sources_one_to_one"] = not failures
    if failures:
        raise TerritorialValidationError("; ".join(failures))
    return report
