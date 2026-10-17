"""Comparación de políticas temporales sin alterar elegibilidad, identidad ni espacio."""

from collections import Counter

import pandas as pd

from sigard_ml.official.calendar import week_from_date
from sigard_ml.official.observed_dates import DATE_HIERARCHY, DATE_TYPES
from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.reports import safe_count

UNCHANGED_COLUMNS = ["event_ref", "classification", "analysis_eligibility", "eligibility_reason",
    "episode_ref", "episode_status", "identity_countable", "identity_resolved_by_review",
    "radio_candidate", "assignment_state", "geometry_status", "geocoding_category", "coordinate_group_ref",
    "uncertainty_reasons", "distance_to_boundary_m", "alternative_radios", "alternative_basis",
    "coordinate_group_size", "crs_confirmed", "location_role"]


def aligned_records(first, second):
    if first.duplicated(ROW_KEY).any() or second.duplicated(ROW_KEY).any():
        raise ValueError("Claves técnicas duplicadas en comparación")
    first = first.set_index(ROW_KEY).sort_index()
    second = second.set_index(ROW_KEY).sort_index()
    if not first.index.equals(second.index):
        raise ValueError("Los escenarios no conservan las mismas filas originales")
    pd.testing.assert_frame_equal(first[UNCHANGED_COLUMNS], second[UNCHANGED_COLUMNS])
    return first, second


def verify_strict_reference(baseline, strict, baseline_panel, strict_panel):
    baseline, strict = aligned_records(baseline, strict)
    pd.testing.assert_frame_equal(baseline[["processing_outcome", "week_start", "reference_date"]],
                                  strict[["processing_outcome", "week_start", "reference_date"]])
    columns = ["radio_censal", "fecha_inicio_semana", "registros_elegibles_provisionales",
               "estado_observacion", "registros_asignacion_incierta", "registros_pendientes_posibles"]
    pd.testing.assert_frame_equal(baseline_panel[columns], strict_panel[columns])


def outcome_counts(frame):
    return {outcome: int(frame.processing_outcome.eq(outcome).sum()) for outcome in ("included", "excluded", "pending")}


def compare_scenarios(strict, expanded):
    first, second = aligned_records(strict, expanded)
    included_a = first.processing_outcome.eq("included")
    included_b = second.processing_outcome.eq("included")
    recovered = ~included_a & included_b
    only_date = first.processing_reasons.map(lambda reasons: list(reasons) == ["date_unusable"])
    if (recovered & (~first.processing_outcome.eq("pending") | ~only_date)).any():
        raise ValueError("Se intentó recuperar un registro con motivos distintos de la fecha")
    if (included_a & ~included_b).any():
        raise ValueError("La política ampliada perdió registros ya incorporados")
    pd.testing.assert_series_equal(first.loc[included_a, "week_start"], second.loc[included_a, "week_start"])
    pending = first[first.processing_outcome.eq("pending")]
    reason_combinations = Counter("|".join(sorted(reasons)) for reasons in pending.processing_reasons)
    recoveries = {DATE_TYPES[field]: int((recovered & second.reference_date_field.eq(field)).sum()) for field in DATE_HIERARCHY[1:]}
    weekly_a = first.loc[included_a].groupby("week_start").size()
    weekly_b = second.loc[included_b].groupby("week_start").size()
    temporal = pd.concat([weekly_a.rename("strict"), weekly_b.rename("expanded")], axis=1).fillna(0).astype(int)
    temporal["added"] = temporal.expanded - temporal.strict
    # Un cero aquí significa ninguna fila incluida en ese escenario para la
    # comparación; nunca se escribe como cero epidemiológico en el panel.
    temporal_rows = [{"week_start": start.isoformat(), "strict_included_records": int(row.strict),
        "expanded_included_records": int(row.expanded), "added_records": int(row.added)} for start, row in temporal.iterrows()]
    annual = {}
    for name, records in (("strict", first[included_a]), ("expanded", second[included_b])):
        annual[name] = {str(int(year)): int(count) for year, count in records.groupby("epidemiological_year").size().items()}
    # Observaciones de retrasos sólo donde hay ambas fechas. No se imputan esos
    # retrasos a los recuperados ni se corrigen sus fechas.
    paired = strict.loc[strict.reference_date_usable & strict.sample_on_status.eq("valid") & strict.sample_on.notna()]
    lags = [(row.sample_on - row.reference_date).days for row in paired.itertuples()]
    crossing = sum(week_from_date(row.sample_on).start != row.week_start for row in paired.itertuples())
    positive_lags = pd.Series([lag for lag in lags if lag >= 0], dtype=float)
    return {"original_pending_reason_combinations": dict(sorted(reason_combinations.items())),
        "original_date_only_pending": int(only_date.sum()),
        "strict": {**outcome_counts(first), "represented_weeks": int(weekly_a.size)},
        "expanded": {**outcome_counts(second), "represented_weeks": int(weekly_b.size)},
        "recovered_by_date_type": recoveries, "recovered_total": int(recovered.sum()),
        "remaining_pending_reason_combinations": dict(sorted(Counter("|".join(sorted(reasons)) for reasons in
            second.loc[second.processing_outcome.eq("pending"), "processing_reasons"]).items())),
        "new_represented_weeks": int((temporal.strict.eq(0) & temporal.expanded.gt(0)).sum()),
        "weeks_with_added_records": int(temporal.added.gt(0).sum()),
        "existing_included_records_with_changed_week": 0,
        "included_records_with_possible_delay_affected_week": int((included_b & second.fecha_aproximada).sum()),
        "delay_evidence": {"paired_symptom_sample_records": len(paired), "sample_before_symptoms": sum(lag < 0 for lag in lags),
            "different_epidemiological_week": crossing,
            "nonnegative_delay_median_days": float(positive_lags.median()) if len(positive_lags) else None,
            "recovered_true_symptom_week_known": False, "delay_imputation_performed": False},
        "epidemiological_year_distribution": annual, "weekly_distribution": temporal_rows,
        "reconciliation_verified": len(first) == len(second) == sum(outcome_counts(second).values()),
        "only_date_pending_recovered": True, "alternative_dates_confirm_symptom_onset": False}


def comparison_text(report):
    a, b = report["strict"], report["expanded"]
    lines = ["# SIGARD Fase 4.1 — comparación privada", "",
        "Fechas alternativas aproximadas: no confirman el inicio real de síntomas.",
        "Panel retrospectivo exploratorio. Identidad, elegibilidad y asignación espacial siguen sin validación epidemiológica.", "",
        f"Estricto: {a['included']} incorporados, {a['pending']} pendientes; {a['represented_weeks']} semanas representadas.",
        f"Ampliado: {b['included']} incorporados, {b['pending']} pendientes; {b['represented_weeks']} semanas representadas.",
        f"Recuperados exclusivamente por fecha: {report['recovered_total']}.", ""]
    for kind, count in report["recovered_by_date_type"].items():
        lines.append(f"- {kind}: {safe_count(count)}.")
    lines += ["", "Motivos originales (combinaciones excluyentes; se suprimen cantidades positivas menores de cinco):"]
    for reason, count in report["original_pending_reason_combinations"].items():
        lines.append(f"- {reason}: {safe_count(count)}.")
    lines += ["", f"Semanas nuevas con registros: {report['new_represented_weeks']}; semanas con incorporaciones: {report['weeks_with_added_records']}.",
        f"Registros con posible desplazamiento por retraso: {report['included_records_with_possible_delay_affected_week']}.",
        "No se conoce su semana real de inicio de síntomas ni se restan días para estimarla.",
        "La distribución semanal exacta se conserva exclusivamente en comparison.private.json.",
        "Los ceros de la comparación representan ausencia de filas incluidas bajo la política, no ausencia epidemiológica comprobada.",
        "Los paneles mantienen null sin evidencia para un cero; los 263 radios y la incertidumbre espacial se conservan.",
        "El escenario estricto reproduce el panel previo. Las huellas privadas comprueban que no se sobrescribió.", ""]
    return "\n".join(lines)
