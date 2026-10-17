"""Fase 4.3: diagnóstico del universo y capacidad condicional, sin crear etiquetas."""

from collections import Counter
from datetime import date, timedelta

import pandas as pd

from sigard_ml.official.coverage_diagnostics import binary_counts, chronological_masks


UNIVERSE_VERSION = "official-universe-review-0.4.3"
MISSING_DECLARATIONS = (
    "Responsable, fecha y referencia de la declaración; justificación, procedencia y confianza por intervalo.",
    "Inicio y fin exactos solicitados por fuente, campo de fecha de extracción y fecha de corte.",
    "Columna y valores literales del filtro de confirmación; definición histórica de dengue y tratamiento del nexo.",
    "Columna y valores del filtro territorial; residencia del paciente frente a establecimiento notificador.",
    "Conciliación con exportación anterior al filtro manual, criterios de exclusión y registros posiblemente omitidos.",
    "Intervalos completos, radios y política de fechas estricta/ampliada a los que se aplica la declaración.",
    "Resolución documentada de pendientes; la declaración de completitud no puede ignorarlos.",
    "Aceptación explícita del uso experimental de fecha de muestra y geografía aproximadas, sin validarlas como exactas.",
)


def candidate_intervals(audit):
    """Envolventes descriptivas por fuente/año/tipo de fecha, NO declaraciones.

    Sólo propone semanas completas interiores a los extremos de fechas presentes.
    Ni una envolvente ni una sucesión de semanas activas prueban completitud.
    """
    included = audit.loc[audit.processing_outcome.eq("included")].copy()
    included["reference_calendar_year"] = included.reference_date.map(lambda day: day.year)
    result = []
    for (source, year, kind), group in included.groupby(
            ["source_id", "reference_calendar_year", "tipo_fecha_referencia"], sort=True):
        first, last = min(group.reference_date), max(group.reference_date)
        if not 2020 <= year <= 2024:
            raise ValueError("Las fuentes actuales no habilitan observaciones 2025/2026")
        start = first + timedelta(days=(6 - first.weekday()) % 7)
        end = last - timedelta(days=(last.weekday() - 5) % 7)
        complete = start <= end
        result.append({"source_id": source, "reference_calendar_year": int(year), "date_type": kind,
            "observed_start": first.isoformat(), "observed_end": last.isoformat(),
            "included_records": len(group), "weeks_with_included_records": int(group.week_start.nunique()),
            "candidate_start": start.isoformat() if complete else None,
            "candidate_end": end.isoformat() if complete else None,
            "candidate_complete_weeks": (end - start).days // 7 + 1 if complete else 0,
            "status": "proposal_not_declaration", "confidence_in_completeness": "none",
            "justification": "Envolvente de fechas presentes; requiere declaración de extracción completa y revisión de huecos.",
            "provenance": "phase41_preserved_records_audit", "coverage_proven": False})
    return result


def _capacity_mask(panel, intervals):
    scope = pd.Series(False, index=panel.index)
    for entry in intervals:
        if entry["candidate_start"] is not None:
            start, end = date.fromisoformat(entry["candidate_start"]), date.fromisoformat(entry["candidate_end"])
            scope |= panel.fecha_inicio_semana.ge(start) & panel.fecha_fin_semana.le(end)
    return (scope & panel.casos_observados.isna() & panel.registros_pendientes_posibles.eq(0)
            & ~panel.ventana_semanal_parcial & panel.anio_epidemiologico.le(2024))


def diagnostic_view(panel, intervals):
    """Añade máscaras de capacidad a una copia en memoria; jamás asigna y=0."""
    keys = ["radio_censal", "fecha_inicio_semana"]
    if panel.duplicated(keys).any():
        raise ValueError("Panel radio-semana duplicado")
    result = panel.copy(deep=True)
    result["potential_negative_if_interval_declared_complete"] = _capacity_mask(result, intervals)
    lookup = result.set_index(keys)["potential_negative_if_interval_declared_complete"].to_dict()
    result["potential_next_week_negative"] = [
        bool(lookup.get((radio, start), False)) for radio, start in
        result[["radio_censal", "fecha_inicio_semana_objetivo"]].itertuples(index=False, name=None)]
    calendar = result[["fecha_inicio_semana", "anio_epidemiologico"]].drop_duplicates()
    if calendar.fecha_inicio_semana.duplicated().any():
        raise ValueError("Año epidemiológico inconsistente en una semana")
    years = calendar.set_index("fecha_inicio_semana").anio_epidemiologico
    result["target_epidemiological_year"] = result.fecha_inicio_semana_objetivo.map(years).astype("Int64")
    return result


def summarize(group):
    counts = group.casos_observados
    positive, negative = int(counts.gt(0).sum()), int(counts.eq(0).sum())
    potential = int(group.potential_negative_if_interval_declared_complete.sum())
    targets = binary_counts(group.objetivo_semana_siguiente)
    return {"cells": len(group), "positive_observations_provisional": positive,
        "verified_zero_observations": int((counts.eq(0) & group.estado_observacion.eq("cero_comprobado_bajo_reglas")).sum()),
        "assumed_zero_observations": int((counts.eq(0) & group.estado_observacion.eq("cero_declarado_provisional")).sum()),
        "unknown_observations": int(counts.isna().sum()), "provisional_records": int(counts.sum()),
        "potential_negative_observations_conditional": potential,
        "unknown_cells_blocked_by_pending": int((counts.isna() & group.registros_pendientes_posibles.gt(0)).sum()),
        "next_week_labels": targets, "potential_next_week_negatives_conditional": int(group.potential_next_week_negative.sum()),
        "known_origin_count_next_week_labels": binary_counts(group.loc[group.casos_observados.notna(), "objetivo_semana_siguiente"]),
        "known_origin_count_potential_next_week_negatives": int((group.casos_observados.notna() & group.potential_next_week_negative).sum()),
        "known_label_positive_fraction": targets["positive"] / (targets["positive"] + targets["negative"]) if targets["positive"] + targets["negative"] else None,
        "conditional_negative_to_positive_ratio": potential / positive if positive else None,
        "both_classes_available": bool(positive and negative), "training_performed": False}


def panel_statistics(panel, intervals, cuts):
    view = diagnostic_view(panel, intervals)
    yearly, target_yearly, radios, weekly, splits = [], [], [], [], []
    for year, group in view.groupby("anio_epidemiologico", sort=True):
        if 2020 <= year <= 2024:
            yearly.append({"epidemiological_year": int(year), **summarize(group)})
    for year, group in view.groupby("target_epidemiological_year", sort=True):
        if 2020 <= year <= 2024:
            target_yearly.append({"target_epidemiological_year": int(year),
                **binary_counts(group.objetivo_semana_siguiente),
                "potential_negative_conditional": int(group.potential_next_week_negative.sum())})
    for radio, group in view.groupby("radio_censal", sort=True):
        radios.append({"radio_censal": radio, **summarize(group)})
    for start, group in view.groupby("fecha_inicio_semana", sort=True):
        weekly.append({"week_start": start.isoformat(), "week_end": group.fecha_fin_semana.iloc[0].isoformat(), **summarize(group)})
    for value in cuts:
        cut = date.fromisoformat(value)
        if not date(2020, 1, 1) <= cut <= date(2024, 12, 31):
            raise ValueError("El corte debe permanecer dentro de los años disponibles")
        train, evaluation = chronological_masks(view, cut)
        target_end = view.fecha_inicio_semana_objetivo.map(lambda day: day + timedelta(days=6))
        for label, mask, capacity in (
            ("train", train, target_end.lt(cut)),
            ("evaluation", evaluation, view.fecha_inicio_semana.ge(cut))):
            splits.append({"evaluation_origin_start": value, "partition": label,
                **binary_counts(view.loc[capacity, "objetivo_semana_siguiente"]),
                "potential_negative_conditional": int((capacity & view.potential_next_week_negative).sum()),
                "known_origin_count_positive": int((mask & view.casos_observados.notna() & view.objetivo_semana_siguiente.eq(1)).sum()),
                "boundary_known_labels_excluded": int((view.objetivo_valido & ~train & ~evaluation).sum()),
                "historical_availability_reconstructed": False, "training_ready": False})
    return {"overall": summarize(view), "by_observation_year": yearly, "by_target_year": target_yearly,
        "by_radio": radios, "by_week": weekly, "chronological_splits": splits,
        "boundary_cells_not_observed_years": int((~view.anio_epidemiologico.between(2020, 2024)).sum()),
        "potential_counts_are_not_labels_or_proven_coverage": True}


def uncertainty_summary(strict, expanded):
    keys = ["source_id", "sheet_ref", "record_ref"]
    if strict.duplicated(keys).any() or expanded.duplicated(keys).any():
        raise ValueError("Auditoría duplicada")
    aligned = strict[keys + ["processing_outcome"]].merge(
        expanded[keys + ["processing_outcome"]], on=keys, how="outer", suffixes=("_strict", "_expanded"), indicator=True, validate="one_to_one")
    if not aligned._merge.eq("both").all():
        raise ValueError("Las políticas de fecha no conservan las mismas filas")
    recovered = (aligned.processing_outcome_strict.ne("included") & aligned.processing_outcome_expanded.eq("included")).sum()
    panels = {}
    for name, audit in (("strict", strict), ("expanded", expanded)):
        pending = audit[audit.processing_outcome.eq("pending")]
        included = audit[audit.processing_outcome.eq("included")]
        undated = pending[pending.week_start.isna()]
        reasons = Counter("|".join(sorted(row)) for row in pending.processing_reasons)
        positive_cells = set(included[["radio_candidate", "week_start"]].itertuples(index=False, name=None))
        eligibility_only = pending.loc[pending.identity_countable & pending.analysis_eligibility.ne("eligible_provisional")
                                       & pending.week_start.notna() & pending.radio_candidate.notna()]
        review_cells = set(eligibility_only[["radio_candidate", "week_start"]].itertuples(index=False, name=None))
        panels[name] = {"included_records": len(included), "pending_records": len(pending),
            "excluded_records": int(audit.processing_outcome.eq("excluded").sum()),
            "undated_pending": len(undated), "dated_pending": int(pending.week_start.notna().sum()),
            "radios_with_undated_pending": int(undated.radio_candidate.nunique()),
            "undated_pending_without_radio": int(undated.radio_candidate.isna().sum()),
            "identity_pending": int((~pending.identity_countable).sum()),
            "eligibility_pending": int(pending.analysis_eligibility.ne("eligible_provisional").sum()),
            "eligibility_only_records_with_identity_and_date": len(eligibility_only),
            "potential_new_positive_cells_if_eligibility_confirmed": len(review_cells - positive_cells),
            "potential_positive_counts_are_not_new_labels": True,
            "pending_reason_combinations": dict(sorted(reasons.items())),
            "approximate_date_included_records": int(included.fecha_aproximada.sum()),
            "uncertain_geographic_included_records": int(included.assignment_state.eq("uncertain").sum()),
            "classification_counts": {str(key): int(value) for key, value in audit.classification.value_counts().items()},
            "possible_undated_period": {"start": "2020-01-01", "end": "2024-12-31"},
            "undated_records_not_assigned_from_source_filename": True}
    return {"recovered_included_records": int(recovered), "policies": panels,
        "time_of_symptoms_of_sample_fallback_unknown": True,
        "pending_counts_must_not_be_summed_across_cells": True,
        "geographic_probes_are_not_probability_or_error_bounds": True}


def declaration_readiness(declarations, source_ids):
    """Valida un borrador, sin autorizar ejecución ni materializar ceros."""
    if not isinstance(declarations, list):
        raise ValueError("Las declaraciones deben ser una lista")
    if not declarations:
        return {"status": "missing_explicit_declaration", "missing": list(MISSING_DECLARATIONS),
                "assumed_zeros_generated": False, "execution_authorized": False}
    required_text = ("responsible_ref", "declared_on", "declaration_ref", "justification", "provenance_ref",
                     "case_definition_ref", "manual_filter_reconciliation_ref", "temporal_basis_statement")
    for entry in declarations:
        if any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in required_text):
            raise ValueError("Declaración incompleta: responsable, procedencia, criterio o conciliación faltante")
        date.fromisoformat(entry["declared_on"])
        start, end = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
        if not date(2020, 1, 1) <= start <= end <= date(2024, 12, 31):
            raise ValueError("No se admiten intervalos observados de 2025/2026")
        if (entry.get("geographic_basis") != "patient_residence" or entry.get("state") != "complete"
                or entry.get("confidence") not in {"low", "medium", "high"}
                or entry.get("pending_policy") != "preserve_blockers"
                or entry.get("experimental_approximation_acknowledged") is not True):
            raise ValueError("La declaración debe distinguir residencia, confianza e incertidumbres sin eliminar bloqueos")
        sources = entry.get("source_ids")
        panels = entry.get("date_panels")
        if (not isinstance(sources, list) or not sources or len(set(sources)) != len(sources)
                or not set(sources) <= set(source_ids) or not isinstance(panels, list) or not panels
                or len(set(panels)) != len(panels) or not set(panels) <= {"strict", "expanded"}):
            raise ValueError("Fuentes o políticas de fecha inválidas")
        if entry.get("radio_scope") != "all_263_capital_radios":
            raise ValueError("La propuesta requiere alcance territorial explícito de los 263 radios")
        extractions = entry.get("source_extractions")
        if (not isinstance(extractions, list) or len(extractions) != len(sources)
                or {row.get("source_id") for row in extractions} != set(sources)):
            raise ValueError("Faltan períodos de extracción por cada fuente declarada")
        for extraction in extractions:
            fields = ("original_export_ref", "confirmation_filter_column", "extraction_date_field", "extraction_cutoff")
            if any(not isinstance(extraction.get(key), str) or not extraction[key].strip() for key in fields):
                raise ValueError("Faltan filtros literales, campo temporal o exportación anterior al filtrado")
            first = date.fromisoformat(extraction["requested_start"])
            last = date.fromisoformat(extraction["requested_end"])
            if first > last or date.fromisoformat(extraction["extraction_cutoff"]) < last:
                raise ValueError("Período solicitado o corte de extracción incompatible")
            labels = extraction.get("confirmation_filter_values")
            geography = extraction.get("geographic_filter_columns_and_values")
            if (not isinstance(labels, list) or not labels or any(not isinstance(value, str) or not value.strip() for value in labels)
                    or not isinstance(geography, dict) or not geography
                    or any(not isinstance(key, str) or not key.strip() or not isinstance(value, list) or not value
                           or any(not isinstance(label, str) or not label.strip() for label in value)
                           for key, value in geography.items())):
                raise ValueError("Faltan valores literales de los filtros epidemiológico y territorial")
    for i, first in enumerate(declarations):
        for second in declarations[i + 1:]:
            if (set(first["date_panels"]) & set(second["date_panels"])
                    and max(first["start"], second["start"]) <= min(first["end"], second["end"])):
                raise ValueError("Declaraciones superpuestas requieren una resolución única")
    return {"status": "draft_requires_source_reconciliation_and_user_authorization",
            "declarations": len(declarations), "assumed_zeros_generated": False, "execution_authorized": False}
