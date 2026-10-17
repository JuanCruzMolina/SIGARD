"""Planes cronológicos con purga de objetivos que cruzan cada límite."""

from datetime import date, timedelta

import pandas as pd

from sigard_ml.official.spatial_ml.features import KEYS

DEFAULT_PLANS = (
    {"name": "seasons_2023_2024", "validation_start": "2023-01-01", "test_start": "2023-12-31", "end": "2024-12-29"},
    {"name": "within_2024_diagnostic", "validation_start": "2024-03-03", "test_start": "2024-05-05", "end": "2024-12-29"},
)


def class_counts(labels):
    return {"positive": int(labels.eq(1).sum()), "negative": int(labels.eq(0).sum()), "unknown": int(labels.isna().sum())}


def prepare_splits(panel, plans=DEFAULT_PLANS):
    assignments, diagnostics = [], []
    for plan in plans:
        validation, test, end = (date.fromisoformat(plan[key]) for key in ("validation_start", "test_start", "end"))
        if not validation < test < end or any(day.weekday() != 6 for day in (validation, test, end)):
            raise ValueError("Cortes cronológicos inválidos")
        if not panel.fecha_inicio_semana.min() < validation or end > panel.fecha_inicio_semana.max():
            raise ValueError("Cortes fuera del período observado")
        target_end = panel.fecha_inicio_semana_objetivo.map(lambda day: day + timedelta(days=6))
        masks = {"train": target_end.lt(validation),
                 "validation": panel.fecha_inicio_semana.ge(validation) & target_end.lt(test),
                 "test": panel.fecha_inicio_semana.ge(test) & target_end.lt(end)}
        assigned = pd.Series("purged_or_outside", index=panel.index)
        stats = {}
        for name, mask in masks.items():
            assigned.loc[mask] = name
            labels = panel.loc[mask, "objetivo_semana_siguiente"]
            counts = class_counts(labels)
            stats[name] = {"rows": int(mask.sum()), **counts,
                "both_classes": counts["positive"] > 0 and counts["negative"] > 0,
                "positive_target_weeks": int(panel.loc[mask & panel.objetivo_semana_siguiente.eq(1).fillna(False), "fecha_inicio_semana_objetivo"].nunique()),
                "negative_target_weeks": int(panel.loc[mask & panel.objetivo_semana_siguiente.eq(0).fillna(False), "fecha_inicio_semana_objetivo"].nunique())}
        result = panel[KEYS].copy()
        result["plan"] = plan["name"]
        result["partition"] = assigned
        result["label_known"] = panel.objetivo_semana_siguiente.notna()
        result["eligible_for_future_supervised_use"] = False
        assignments.append(result)
        both = all(item["both_classes"] for item in stats.values())
        diagnostics.append({**plan, "partitions": stats,
            "purged_or_outside": int(assigned.eq("purged_or_outside").sum()),
            "both_classes_in_every_partition": both, "fit_for_training": False, "status": "not_fit",
            "reasons": ["Historical record/classification availability not reconstructed",
                        "Epidemiological eligibility, dates and spatial assignment remain provisional"]
                       + ([] if both else ["Missing supported class in at least one partition"]),
            "sample_size_threshold_validated": False})
    return pd.concat(assignments, ignore_index=True), diagnostics


def evaluation_contract():
    return {"task": "next_week_presence_of_provisional_eligible_records", "training_enabled": False,
        "unknown_labels": "exclude from supervised fit and metrics; retain in coverage denominator",
        "negative_labels": "only inherited supported zeros; conservative/exploratory separately",
        "split": "all radios share dates; target_end < next partition origin_start; no random rows",
        "outcome_maturation": "verify label availability dates and extraction cutoff before any fitting",
        "predictors": "catalog allowlist; retrospective history/static context need point-in-time validation",
        "preprocessing": "fit encoders, imputation, calibration and tuning on training only",
        "baselines": [
            {"name": "training_prevalence", "rule": "probability from known, mature training labels only"},
            {"name": "last_available_week_presence", "rule": "1 if origin > 0; 0 only if supported zero; abstain if unknown/unavailable"}],
        "future_metrics": ["Brier score", "log loss", "average precision", "ROC AUC with both classes", "calibration", "coverage and abstention"],
        "concentration": "report by season/year, macro over weeks/radios and 2024 concentration",
        "minimum_class_counts": "both classes necessary, not sufficient; review sample size and temporal independence",
        "metrics_computed": False}
