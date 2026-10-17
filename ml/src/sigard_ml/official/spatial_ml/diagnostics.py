"""Agregados privados de disponibilidad y calidad; nunca exporta personas."""

from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.splits import class_counts

import pandas as pd


def diagnose(panel, features, audit):
    summaries, availability = {}, []
    for dimension in ("anio_epidemiologico", "radio_censal"):
        rows = []
        for value, group in panel.groupby(dimension, sort=True):
            labels = class_counts(group.objetivo_semana_siguiente)
            counts = group.casos_observados
            rows.append({dimension: value, "cells": len(group), "records_provisional": int(counts.sum(min_count=1)) if counts.notna().any() else None,
                "observation_positive": int(counts.gt(0).sum()), "observation_zero": int(counts.eq(0).sum()),
                "observation_unknown": int(counts.isna().sum()), **{f"target_{k}": v for k, v in labels.items()},
                "records_approximate_date": int(group.registros_fecha_aproximada.sum()),
                "records_uncertain_assignment": int(group.registros_asignacion_incierta.sum()),
                "cells_with_pending": int(group.registros_pendientes_posibles.gt(0).sum()),
                "partial_week_cells": int(group.ventana_semanal_parcial.sum())})
            subset = features.loc[group.index]
            for name in features.columns.difference(KEYS):
                known = int(subset[name].notna().sum())
                availability.append({"dimension": dimension, "value": str(value), "feature": name,
                    "rows": len(subset), "known": known, "unknown": len(subset) - known,
                    "known_fraction": known / len(subset),
                    "true_count": int(subset[name].sum()) if subset[name].dtype == bool else None})
        summaries["by_year" if dimension == "anio_epidemiologico" else "by_radio"] = pd.DataFrame(rows)
    # Año del objetivo, separado del año de origen.
    from sigard_ml.official.calendar import week_from_date
    target_year = panel.fecha_inicio_semana_objetivo.map(lambda day: week_from_date(day).year)
    summaries["by_target_year"] = pd.DataFrame([
        {"target_year": int(year), "rows": len(group), **class_counts(group.objetivo_semana_siguiente)}
        for year, group in panel.groupby(target_year, sort=True)])
    summaries["feature_availability"] = pd.DataFrame(availability)
    summaries["classification_by_source"] = audit.groupby(
        ["source_id", "classification", "processing_outcome"], dropna=False).size().rename("records").reset_index()
    included = audit[audit.processing_outcome.eq("included")]
    if int(panel.casos_observados.sum()) != len(included):
        raise ValueError("Los registros y los objetivos no concilian con la auditoría preservada")
    if int(panel.registros_fecha_aproximada.sum()) != int(included.fecha_aproximada.sum()):
        raise ValueError("Las fechas aproximadas no concilian")
    total = int(panel.casos_observados.sum())
    in_2024 = int(panel.loc[panel.anio_epidemiologico.eq(2024), "casos_observados"].sum())
    positive_by_radio = panel.assign(positive=panel.casos_observados.gt(0).fillna(False)).groupby("radio_censal").positive.any()
    summary = {"cells": len(panel), "radios": int(panel.radio_censal.nunique()),
        "weeks": int(panel.fecha_inicio_semana.nunique()), "provisional_records": total,
        "labels": class_counts(panel.objetivo_semana_siguiente),
        "known_observation_counts": int(panel.casos_observados.notna().sum()),
        "records_2024_fraction": in_2024 / total if total else None,
        "approximate_date_records": int(panel.registros_fecha_aproximada.sum()),
        "uncertain_assignment_records": int(panel.registros_asignacion_incierta.sum()),
        "radios_without_positive_records": int((~positive_by_radio).sum()),
        "feature_known_values": {name: int(features[name].notna().sum()) for name in features if name not in KEYS},
        "retrospective_feature_columns": len(features.columns) - len(KEYS),
        "reconciliation_verified": True, "historical_availability_verified": False,
        "training_ready": False, "classification_not_clinically_validated": True,
        "pending_cells_not_additive_across_weeks_or_radios": True}
    return summaries, summary
