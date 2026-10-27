"""Inventario temporal y viabilidad retrospectiva; no entrena ni estima métricas."""

from datetime import date, timedelta
from itertools import combinations

import pandas as pd

from sigard_ml.official.calendar import week_from_date, weeks_between
from sigard_ml.official.coverage_panel import validate_coverage_panel
from sigard_ml.official.episodes import validate_episode_summary

PRINCIPAL_COVERAGE_PROJECTION_VERSION = "principal-coverage-eligibility-1"


def interval_summary(values, cache):
    dates = sorted(set(values.dropna()))
    for day in dates:
        if day not in cache:
            cache[day] = week_from_date(day)
    represented = {cache[day].start for day in dates}
    gaps = [week.start.isoformat() for week in weeks_between(dates[0], dates[-1]) if week.start not in represented] if dates else []
    return {"valid_records": int(values.notna().sum()), "observed_start": dates[0].isoformat() if dates else None,
        "observed_end": dates[-1].isoformat() if dates else None, "represented_weeks": len(represented),
        "weeks_without_observed_date_between_extrema": gaps,
        "continuous_coverage_proven": False}


def principal_eligibility_matrix(panel, *, source_versions, identity_by_week=None):
    """Proyecta un panel agregado existente, sin recalcular cobertura o episodios.

    Selecciona semanas con registros provisionales positivos. No recibe pacientes,
    ni carga archivos, ni convierte el escenario de cobertura en aprobación P1–P6.
    Los resúmenes P2 opcionales son conciliaciones del mismo alcance semanal; el
    llamador debe comprobar su procedencia y disponibilidad, como exige el adaptador.
    """
    validate_coverage_panel(panel)
    if not pd.api.types.is_integer_dtype(panel.casos_observados.dtype):
        raise ValueError("El panel debe conservar conteos enteros nullable")
    if panel.duplicated(["radio_censal", "fecha_inicio_semana"]).any():
        raise ValueError("Celdas agregadas duplicadas")
    identity_by_week = {} if identity_by_week is None else identity_by_week
    universe = set(panel.radio_censal)
    weekly, source_weeks = [], []
    for start, group in panel.groupby("fecha_inicio_semana", sort=True):
        positives = group.loc[group.casos_observados.gt(0).fillna(False)]
        if positives.empty:
            continue
        week = week_from_date(start)
        pending_mentions = int(group.registros_pendientes_posibles.sum())
        partial = bool(group.ventana_semanal_parcial.any())
        identity = identity_by_week.get(start)
        if identity is not None:
            validate_episode_summary(identity)
        identity_pending = (identity is None or identity["exact_episode_count"] is None)
        records = int(positives.casos_observados.sum())
        if identity is not None and identity["eligible_records"] != records:
            raise ValueError("P2 no concilia el alcance semanal de registros provisionales")
        for values in positives.fuentes_con_registros:
            values = list(values) if not isinstance(values, str) and values is not None else []
            if not values or not all(isinstance(value, str) and value for value in values) or len(set(values)) != len(values):
                raise ValueError("Una celda positiva carece de fuentes agregadas únicas")
        sources = sorted({source for values in positives.fuentes_con_registros for source in values})
        if not sources or any(source not in source_versions or not source_versions[source] for source in sources):
            raise ValueError("Fuente de registros sin versión documentada")
        reasons = ["provisional_record_unit_not_accredited_episodes", "maturity_not_documented",
                   "effective_availability_not_documented", "source_extraction_completeness_not_documented"]
        if not group.cobertura_comprobada.eq("complete").all():
            reasons.append("coverage_not_verified_for_entire_territory")
        if partial:
            reasons.append("partial_week")
        grid_complete = set(group.radio_censal) == universe
        if not grid_complete:
            reasons.append("incomplete_radio_grid")
        if pending_mentions:
            reasons.append("pending_records_may_modify_count")
        if identity_pending:
            reasons.append("P2_unknown_or_unresolved")
        uncertain = int(positives.registros_asignacion_incierta.sum())
        if uncertain:
            reasons.append("spatial_assignment_uncertain")
        # Este panel conserva unidad provisional. P2 y cobertura por sí solos
        # no acreditan P1/P4/P5/P6 ni autorizan un total como etiqueta por radio.
        weekly.append({"week_start": start.isoformat(), "week_end": week.end.isoformat(),
            "epidemiological_year": week.year, "epidemiological_week": week.number,
            "provisional_records": records, "observation_status": "positive_provisional",
            "positive_accredited": False, "backed_zero": False,
            "coverage_states": sorted(group.estado_cobertura.unique()),
            "declared_states": sorted(group.cobertura_declarada.unique()),
            "verified_states": sorted(group.cobertura_comprobada.unique()),
            "coverage_sufficient_for_whole_territory": bool(group.cobertura_comprobada.eq("complete").all()
                and grid_complete and not partial and not pending_mentions),
            "partial_week": partial, "pending_may_modify_count": bool(pending_mentions or identity_pending),
            "pending_cell_mentions": pending_mentions, "pending_mentions_are_not_unique_episodes": True,
            "classification_pending_records": None, "identity_pending_records": None,
            "identity_summary": identity, "P2_status": "unknown_or_unresolved" if identity_pending else "reviewed_identity_only",
            "assigned_provisional_records": records, "uncertain_assignment_records": uncertain,
            "maturity": "unknown", "available_on": None, "training_eligible": False,
            "accredited_episode_count": None, "permitted_use": "retrospective_provisional_description",
            "block_reasons": reasons,
            "declaration_refs": sorted(set(group.declaracion_cobertura_ref.dropna())),
            "verification_refs": sorted(set(group.verificacion_cobertura_ref.dropna())),
            "adapter_status": "blocked_requires_radio_week_accreditation_and_availability"})
        for source in sources:
            exclusive, ambiguous = 0, 0
            for row in positives.itertuples():
                values = list(row.fuentes_con_registros)
                if source in values:
                    if len(values) == 1:
                        exclusive += int(row.casos_observados)
                    else:
                        ambiguous += int(row.casos_observados)
            source_weeks.append({"week_start": start.isoformat(), "source_id": source,
                "source_version": source_versions[source], "provisional_positive_present": True,
                "provisional_records": exclusive if ambiguous == 0 else None,
                "provisional_records_lower_bound": exclusive, "provisional_records_upper_bound": exclusive + ambiguous,
                "source_attribution": "exact_from_aggregate_cells" if ambiguous == 0 else "mixed_source_cells_not_disaggregated",
                "source_coverage": "unknown", "source_maturity": "unknown",
                "source_pending_classification": None, "source_pending_identity": None,
                "block_reason": "source_period_and_extraction_completeness_not_accredited"})
    if set(identity_by_week) - {date.fromisoformat(row["week_start"]) for row in weekly}:
        raise ValueError("P2 contiene semanas ajenas a la matriz seleccionada")
    return {"transformation_version": PRINCIPAL_COVERAGE_PROJECTION_VERSION,
        "unit": "provisional_records_capital_week_with_source_context", "weeks": weekly, "source_weeks": source_weeks,
        "grid_weeks": int(panel.fecha_inicio_semana.nunique()),
        "selected_provisional_weeks": len(weekly), "other_grid_weeks_not_evidence_of_zero": int(panel.fecha_inicio_semana.nunique()) - len(weekly),
        "coverage_sufficient_weeks": sum(row["coverage_sufficient_for_whole_territory"] for row in weekly),
        "accredited_count_weeks": 0, "backed_zero_weeks_in_selected_positive_matrix": 0,
        "grid_weeks_with_any_backed_zero_cell": int(panel.loc[
            panel.estado_observacion.eq("cero_comprobado_bajo_reglas"), "fecha_inicio_semana"].nunique()),
        "grid_partial_weeks": int(panel.loc[panel.ventana_semanal_parcial, "fecha_inicio_semana"].nunique()),
        "adapter_bundle_ready": False, "training_authorized": False}


def temporal_inventory(normalized, audits, period_start, period_end, source_declarations):
    cache, sources = {}, []
    declared = {}
    for item in source_declarations:
        start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        if (item["source_id"] not in set(normalized.source_id) or start > end
            or not item.get("declaration_ref") or item.get("date_basis") not in
            {"symptom_onset", "sample_on", "notification", "unknown"}):
            raise ValueError("Período solicitado por fuente sin referencia o base temporal identificada")
        declared.setdefault(item["source_id"], []).append(item)
    for source_id, group in normalized.groupby("source_id", sort=True):
        fields = {}
        for field in ("symptom_onset", "sample_on"):
            fields[field] = interval_summary(group.loc[group[field + "_status"].eq("valid"), field], cache)
        sources.append({"source_id": source_id, "source_records": len(group),
            "requested_period_declarations": declared.get(source_id, []),
            "requested_period_documented": source_id in declared,
            "observed_date_intervals": fields, "file_name_used_to_infer_coverage": False,
            "coverage_complete_proven": False})
    panels = {}
    study_weeks = weeks_between(period_start, period_end)
    overlaps = []
    for name, records in audits.items():
        included = records[records.processing_outcome.eq("included")]
        pending = records[records.processing_outcome.eq("pending")]
        undated = pending[pending.week_start.isna()]
        source_intervals = []
        for source_id, group in included.groupby("source_id"):
            source_intervals.append({"source_id": source_id, **interval_summary(group.reference_date, cache)})
        for first, second in combinations(source_intervals, 2):
            if max(first["observed_start"], second["observed_start"]) <= min(first["observed_end"], second["observed_end"]):
                overlaps.append({"date_panel": name, "source_ids": [first["source_id"], second["source_id"]],
                                 "meaning": "observed_intervals_overlap_not_proof_of_duplicate_cases_or_complete_coverage"})
        represented = set(included.week_start)
        panels[name] = {"included_records": len(included), "pending_records": len(pending),
            "current_classification_counts": {str(kind): int(count) for kind, count in records.classification.value_counts().sort_index().items()},
            "manual_selection_declaration_automatically_reconciled": False,
            "represented_weeks": len(represented), "intervals_by_source": source_intervals,
            "weeks_by_reference_date_type": {str(kind): int(group.week_start.nunique()) for kind, group in included.groupby("tipo_fecha_referencia")},
            "weeks_without_included_records": [week.start.isoformat() for week in study_weeks if week.start not in represented],
            "undated_pending_records": len(undated), "radios_affected_by_undated_pending": int(undated.radio_candidate.nunique()),
            "undated_pending_possible_period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
            "source_years_used_to_restrict_pending": False}
    return {"sources": sources, "date_panels": panels, "overlapping_source_intervals": overlaps,
        "analysis_period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "represented_dates_do_not_prove_coverage": True}


def chronological_masks(panel, evaluation_start):
    """Separa por semanas completas, excluyendo el origen cuyo objetivo cruza el corte."""
    if evaluation_start.weekday() != 6:
        raise ValueError("El corte cronológico debe comenzar un domingo")
    target_end = panel.fecha_inicio_semana_objetivo.map(lambda day: day + timedelta(days=6))
    train = panel.objetivo_valido & target_end.lt(evaluation_start)
    evaluation = panel.objetivo_valido & panel.fecha_inicio_semana.ge(evaluation_start)
    return train, evaluation


def binary_counts(values):
    return {"positive": int(values.eq(1).sum()), "negative": int(values.eq(0).sum()), "unknown": int(values.isna().sum())}


def panel_diagnostics(panel, *, activity_rule, evaluation_start):
    counts = panel.casos_observados
    positive = counts.gt(0).fillna(False)
    negative = counts.eq(0).fillna(False)
    zeros = panel[negative]
    all_radios = set(panel.radio_censal)
    positive_radios = set(panel.loc[positive, "radio_censal"])
    eligible_origin = panel.candidato_retrospectivo_con_conteo_origen
    distribution = []
    for start, group in panel.groupby("fecha_inicio_semana", sort=True):
        distribution.append({"origin_week_start": start.isoformat(),
            "target_week_start": group.fecha_inicio_semana_objetivo.iloc[0].isoformat(),
            "positive_observations": int(group.casos_observados.gt(0).sum()),
            "negative_observations": int(group.casos_observados.eq(0).sum()),
            "unknown_observations": int(group.casos_observados.isna().sum()),
            "target_labels": binary_counts(group.objetivo_semana_siguiente)})
    activity = []
    for year, group in panel.groupby("anio_epidemiologico", sort=True):
        positives = group[group.casos_observados.gt(0).fillna(False)]
        negatives = group[group.casos_observados.eq(0).fillna(False)]
        threshold = positives.fecha_inicio_semana.nunique() >= activity_rule["min_positive_weeks"] and len(positives) >= activity_rule["min_positive_cells"]
        activity.append({"epidemiological_year": int(year), "positive_cells": len(positives),
            "positive_weeks": int(positives.fecha_inicio_semana.nunique()), "positive_radios": int(positives.radio_censal.nunique()),
            "negative_cells": len(negatives), "descriptive_activity_threshold_met": bool(threshold),
            "threshold_is_not_validated_training_requirement": True,
            "binary_training_ready": False})
    train, evaluation = chronological_masks(panel, evaluation_start)
    split = {"evaluation_start": evaluation_start.isoformat(), "training_target_ends_before_evaluation": True,
        "train_labels": binary_counts(panel.loc[train, "objetivo_semana_siguiente"]),
        "evaluation_labels": binary_counts(panel.loc[evaluation, "objetivo_semana_siguiente"]),
        "known_origin_train_labels": binary_counts(panel.loc[train & eligible_origin, "objetivo_semana_siguiente"]),
        "known_origin_evaluation_labels": binary_counts(panel.loc[evaluation & eligible_origin, "objetivo_semana_siguiente"]),
        "valid_labels_excluded_at_boundary": int((panel.objetivo_valido & ~train & ~evaluation).sum()),
        "binary_classes_present_in_both_partitions": bool(panel.loc[train, "objetivo_semana_siguiente"].eq(0).any()
            and panel.loc[train, "objetivo_semana_siguiente"].eq(1).any()
            and panel.loc[evaluation, "objetivo_semana_siguiente"].eq(0).any()
            and panel.loc[evaluation, "objetivo_semana_siguiente"].eq(1).any()),
        "historical_availability_reconstructed": False, "viable_for_training_now": False}
    coverage = panel.estado_cobertura
    return {"cells": len(panel), "radios": len(all_radios), "grid_weeks": int(panel.fecha_inicio_semana.nunique()),
        "incorporated_records": int(counts.sum()),
        "observations": {"positive": int(positive.sum()), "negative": int(negative.sum()), "unknown": int(counts.isna().sum())},
        "next_week_labels": binary_counts(panel.objetivo_semana_siguiente),
        "valid_targets_with_known_origin_count": int(eligible_origin.sum()),
        "approximate_date_positive_records": int(panel.registros_fecha_aproximada.sum()),
        "labels_with_approximate_target_date": int(panel.objetivo_con_fecha_aproximada.sum()),
        "weeks_with_verified_complete_cells": int(panel.loc[coverage.eq("completa_comprobada"), "fecha_inicio_semana"].nunique()),
        "weeks_with_declared_complete_cells": int(panel.loc[coverage.eq("completa_declarada_provisional"), "fecha_inicio_semana"].nunique()),
        "weeks_with_generated_zeros": int(zeros.fecha_inicio_semana.nunique()),
        "weeks_with_positive_observations": int(panel.loc[positive, "fecha_inicio_semana"].nunique()),
        "weeks_complete_for_all_radios": int(panel.groupby("fecha_inicio_semana").estado_cobertura.apply(
            lambda states: states.isin(["completa_comprobada", "completa_declarada_provisional"]).all()).sum()),
        "radios_with_positive_observations": len(positive_radios),
        "radios_without_positive_observations": sorted(all_radios - positive_radios),
        "radios_without_positive_observations_count": len(all_radios - positive_radios),
        "unverified_or_partial_weeks": int(panel.loc[~coverage.eq("completa_comprobada"), "fecha_inicio_semana"].nunique()),
        "temporal_distribution": distribution, "activity_by_epidemiological_year": activity,
        "chronological_split_diagnostic": split, "training_performed": False}
