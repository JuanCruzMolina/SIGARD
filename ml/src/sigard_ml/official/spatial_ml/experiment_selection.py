"""Fase 5B: auditoría descriptiva y conjuntos predefinidos; sin ajuste."""

import pandas as pd

from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.splits import class_counts

BASE = ["superficie_km2", "poblacion", "densidad_poblacional", "cantidad_vecinos",
        "semana_epidemiologica", "estacionalidad_seno", "estacionalidad_coseno"]
SHORT = [f"registros_retro_rezago_{lag}" for lag in range(1, 5)]
LONG = [f"registros_retro_acumulado_{window}" for window in (4, 8, 12)]
NEIGHBOR = [f"vecinos_retro_rezago_{lag}" for lag in range(1, 5)] + [
    f"vecinos_retro_acumulado_{window}" for window in (4, 8, 12)]
SETS = {
    "A": {"name": "basic_spatial", "required": BASE, "optional": []},
    "B": {"name": "short_history", "required": BASE, "optional": SHORT},
    "C": {"name": "full_candidate", "required": BASE, "optional": SHORT + LONG + NEIGHBOR},
}
SUPPORT_RULE = {"minimum_known_training_values_per_class": 20,
                "minimum_known_training_fraction": 0.10,
                "scope": "known, mature labels in training partition only",
                "thresholds_scientifically_validated": False}


def percentage(numerator, denominator):
    return 100.0 * numerator / denominator if denominator else None


def align_labels(features, labels):
    if features.duplicated(KEYS).any() or labels.duplicated(KEYS).any():
        raise ValueError("Claves radio-semana repetidas")
    result = features.merge(labels[KEYS + ["objetivo_semana_siguiente"]], on=KEYS,
                            how="outer", validate="one_to_one", indicator=True)
    if not result._merge.eq("both").all():
        raise ValueError("Predictores y etiquetas no conservan la misma grilla")
    return result.drop(columns="_merge")


def column_policy(name, definitions):
    history = name.startswith(("registros_retro_", "vecinos_retro_"))
    indicator = name.endswith("_valor_disponible") or "_semanas_conocidas_" in name or "_conocidos_rezago_" in name
    definition = definitions.get(name, {})
    offsets = definition.get("source_week_offsets")
    if name.startswith("registros_retro_origen"):
        driver = "registros_retro_origen"
    elif "_semanas_conocidas_" in name:
        driver = name.replace("_semanas_conocidas_", "_acumulado_")
    elif "_conocidos_rezago_" in name:
        driver = name.replace("_conocidos_rezago_", "_rezago_")
    else:
        driver = name.removesuffix("_valor_disponible")
    if name in KEYS:
        role, utility = "excluded_key", "join and audit only; no numeric encoding of radio ID"
    elif name in BASE:
        role, utility = "required_A_B_C", "candidate structural/seasonal context; no causal interpretation"
    elif name in SHORT:
        role, utility = "optional_B_C", "short retrospective history; preserve unknowns and verify reporting availability"
    elif name in LONG + NEIGHBOR:
        role, utility = "optional_C", "exploratory history; never mandatory; training-only support gate"
    elif indicator and driver in SHORT + LONG + NEIGHBOR:
        role, utility = "derived_missingness_indicator", "derive only for optional features admitted within training fold"
    else:
        role, utility = "excluded_initial", "audit metadata, redundant indicator, origin count or year/identity sensitivity only"
    return {"feature": name, "role": role, "potential_utility": utility,
        "underlying_feature": driver, "is_availability_indicator": indicator,
        "depends_on_past_unknown_weeks": history and not name.startswith("registros_retro_origen"),
        "depends_on_unknown_origin_or_past_counts": history,
        "source_week_offsets": offsets,
        "uses_future_week": bool(offsets and max(offsets) > 0),
        "temporal_risk": "record/classification arrival and revisions unverified" if history
            else "2022 census vintage and historical publication/boundaries unverified" if name in ["radio_censal", "superficie_km2", "poblacion", "densidad_poblacional", "cantidad_vecinos"]
            else "calendar known in advance" if name in ["anio_epidemiologico", "semana_epidemiologica", "estacionalidad_seno", "estacionalidad_coseno", "fecha_inicio_semana"]
            else "metadata only; exclude from predictors",
        "historical_availability_verified": definition.get("historical_availability_verified", name == "fecha_inicio_semana")}


def audit_columns(features, labels, definitions):
    if any("objetivo" in name or "target" in name for name in features):
        raise ValueError("Variable objetivo encontrada entre predictores")
    if set(features) != set(definitions) | {"fecha_inicio_semana"}:
        raise ValueError("La matriz y el catálogo de Fase 5A no coinciden")
    frame = align_labels(features, labels)
    policies = [column_policy(name, definitions) for name in features]
    if any(row["uses_future_week"] for row in policies):
        raise ValueError("El catálogo incluye información futura")
    rows, by_year = [], []
    groups = [("all", frame)] + [(int(year), group) for year, group in frame.groupby("anio_epidemiologico", sort=True)]
    for year, group in groups:
        positive = group.objetivo_semana_siguiente.eq(1).fillna(False)
        for policy in policies:
            values = group[policy["feature"]]
            driver = group[policy["underlying_feature"]] if policy["underlying_feature"] in group else values
            count, positive_count = int(values.notna().sum()), int((positive & values.notna()).sum())
            result = {"feature": policy["feature"], "origin_year": year, "rows": len(group),
                "available": count, "unknown": int(values.isna().sum()), "available_pct": percentage(count, len(group)),
                "positive_labels": int(positive.sum()), "available_in_positive_labels": positive_count,
                "available_in_positive_labels_pct": percentage(positive_count, int(positive.sum())),
                "distinct_nonnull_values": int(values.nunique(dropna=True)),
                "constant_when_observed": values.nunique(dropna=True) <= 1,
                "underlying_unknown": int(driver.isna().sum()),
                "underlying_available_pct": percentage(int(driver.notna().sum()), len(group)),
                "true_count": int(values.eq(True).sum()) if values.dtype == bool else None}
            (rows if year == "all" else by_year).append(result)
    return pd.DataFrame(rows), pd.DataFrame(by_year), policies


def compare_sets(features, labels):
    frame = align_labels(features, labels)
    rows = []
    for year, group in [("all", frame)] + [(str(year), group) for year, group in frame.groupby("anio_epidemiologico", sort=True)]:
        for name, specification in SETS.items():
            required, optional = specification["required"], specification["optional"]
            core = group[required].notna().all(axis=1)
            complete = group[required + optional].notna().all(axis=1)
            any_history = group[optional].notna().any(axis=1) if optional else pd.Series(False, index=group.index)
            positive = group.objetivo_semana_siguiente.eq(1).fillna(False)
            rows.append({"set": name, "origin_year": year, "rows": len(group), "positive_labels": int(positive.sum()),
                "required_count": len(required), "optional_count": len(optional),
                "required_available_rows": int(core.sum()), "required_available_pct": percentage(int(core.sum()), len(group)),
                "all_candidate_values_available_rows": int(complete.sum()),
                "all_candidate_values_available_pct": percentage(int(complete.sum()), len(group)),
                "positive_rows_all_candidate_values_available": int((positive & complete).sum()),
                "positive_all_candidate_values_available_pct": percentage(int((positive & complete).sum()), int(positive.sum())),
                "rows_with_any_optional_history": int(any_history.sum()),
                "positive_rows_with_any_optional_history": int((any_history & positive).sum()),
                "row_retention_rule": "required core only; keep NaN in optional columns",
                "operationally_validated": False, "training_ready": False})
    return pd.DataFrame(rows)


def training_support(features, labels, assignments, rule=SUPPORT_RULE):
    """Sólo diagnóstico de selección futura; jamás consulta valores de evaluación."""
    frame = align_labels(features, labels)
    reports, partitions = [], []
    for plan, membership in assignments.groupby("plan", sort=True):
        if membership.duplicated(KEYS).any():
            raise ValueError("Membresía cronológica duplicada")
        joined = frame.merge(membership[KEYS + ["partition"]], on=KEYS, validate="one_to_one", how="outer", indicator=True)
        if not joined._merge.eq("both").all():
            raise ValueError("La partición no conserva la grilla")
        train = joined[joined.partition.eq("train") & joined.objetivo_semana_siguiente.notna()]
        for partition, group in joined.groupby("partition", sort=True):
            counts = class_counts(group.objetivo_semana_siguiente)
            partitions.append({"plan": plan, "partition": partition, "rows": len(group), **counts,
                "both_classes": counts["positive"] > 0 and counts["negative"] > 0,
                "class_size_review_passed": min(counts["positive"], counts["negative"]) >= rule["minimum_known_training_values_per_class"],
                "fit_for_training": False})
        for set_name, specification in SETS.items():
            for feature in specification["required"] + specification["optional"]:
                values = train[feature]
                pos = int((values.notna() & train.objetivo_semana_siguiente.eq(1)).sum())
                neg = int((values.notna() & train.objetivo_semana_siguiente.eq(0)).sum())
                enough = min(pos, neg) >= rule["minimum_known_training_values_per_class"] and len(train) > 0 and values.notna().mean() >= rule["minimum_known_training_fraction"]
                reports.append({"plan": plan, "set": set_name, "feature": feature,
                    "required": feature in specification["required"], "known_training_labels": len(train),
                    "known_values": int(values.notna().sum()), "known_positive": pos, "known_negative": neg,
                    "known_training_pct": percentage(int(values.notna().sum()), len(train)),
                    "passes_future_support_rule": bool(enough), "selection_applied": False,
                    "decision": "candidate_after_remaining_gates" if enough else "block_if_required_else_drop_optional",
                    "label_maturity_verified": False,
                    "support_scope": "retrospective known training labels only; descriptive preview",
                    "support_does_not_validate_historical_availability": True})
    return pd.DataFrame(reports), pd.DataFrame(partitions)
