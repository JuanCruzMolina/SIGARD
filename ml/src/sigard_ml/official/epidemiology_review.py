"""Fase 5B.1: evidencia preservada y decisiones pendientes, sin reclasificar."""

import ast
from datetime import date
from pathlib import Path

import pandas as pd

from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.spatial_pipeline import digest_path

VERSION = "official-epidemiology-decision-review-0.5b.1"


def flag_implementation_evidence():
    """Ubica asignaciones explícitas a False; no las interpreta como diagnóstico."""
    directory = Path(__file__).parent
    findings = []
    for filename, function, field in (
        ("eligibility.py", "evaluate_eligibility", "epidemiological_eligibility_validated"),
        ("observed_pipeline.py", "prepare_records", "epidemiological_identity_validated"),
    ):
        path = directory / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines = []
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name != function:
                continue
            for item in ast.walk(node):
                if isinstance(item, ast.Dict):
                    for key, value in zip(item.keys, item.values, strict=True):
                        if isinstance(key, ast.Constant) and key.value == field and isinstance(value, ast.Constant) and value.value is False:
                            lines.append(value.lineno)
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant) and item.value.value is False:
                    for target in item.targets:
                        if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value == field:
                            lines.append(item.lineno)
        findings.append({"file": filename, "function": function, "field": field,
            "explicit_false_assignment_lines": sorted(set(lines)), "sha256": digest_path(path)})
    return {"findings": findings,
        "combined_gate": "included AND canonical confirmado AND eligible_provisional AND eligibility_validated AND identity_validated",
        "interpretation": "Zero validated flags are a conservative software state, not evidence that recorded confirmed labels are false",
        "automatic_flag_change_authorized": False}


def confirmation_inventory(normalized, audit, source_schemas):
    if normalized.duplicated(ROW_KEY).any() or audit.duplicated(ROW_KEY).any():
        raise ValueError("Claves de registros repetidas")
    joined = normalized[ROW_KEY + ["classification_label"]].merge(audit, on=ROW_KEY, how="outer", indicator=True, validate="one_to_one")
    if not joined._merge.eq("both").all():
        raise ValueError("Normalizados y auditoría no conservan las mismas filas")
    rows, summaries = [], []
    for source, group in joined.groupby("source_id", sort=True):
        schema = source_schemas[source]
        for (label, category), cells in group.groupby(["classification_label", "classification"], dropna=False, sort=True):
            if category == "confirmado":
                evidence = "recorded_confirmation_label_with_unvalidated_criterion"
            elif category == "descartado":
                evidence = "explicit_recorded_discard_label_not_a_weekly_negative"
            elif category in {"probable", "sospechoso"}:
                evidence = "recorded_not_confirmed_category_not_proof_of_absence"
            else:
                evidence = "confirmation_unknown_or_unmapped"
            validated = (cells.processing_outcome.eq("included") & cells.classification.eq("confirmado")
                & cells.analysis_eligibility.eq("eligible_provisional")
                & cells.epidemiological_eligibility_validated.eq(True) & cells.epidemiological_identity_validated.eq(True))
            rows.append({"source_id": source, "sheet_ref": schema["sheet_ref"],
                "classification_column": schema["classification_column"], "classification_header": schema["classification_header"],
                "literal_label": None if pd.isna(label) else str(label), "canonical_category": str(category),
                "records": len(cells), "included_provisional": int(cells.processing_outcome.eq("included").sum()),
                "pending": int(cells.processing_outcome.eq("pending").sum()),
                "excluded": int(cells.processing_outcome.eq("excluded").sum()),
                "validated_under_current_flags": int(validated.sum()), "evidence_status": evidence,
                "criterion_validated": False, "responsible_decision": None})
        summaries.append({"source_id": source, **schema, "records": len(group),
            "canonical_counts": {str(k): int(v) for k, v in group.classification.value_counts().items()},
            "eligible_validation_flags_true": int(group.epidemiological_eligibility_validated.eq(True).sum()),
            "identity_validation_flags_true": int(group.epidemiological_identity_validated.eq(True).sum()),
            "recorded_confirmed_labels": int(group.classification.eq("confirmado").sum()),
            "included_provisional": int(group.processing_outcome.eq("included").sum()),
            "validated_clinical_criterion_available": False,
            "cannot_determine_from_files": ["historical case definition and event dictionary",
                "laboratory versus accepted clinical/epidemiological linkage criterion",
                "manual confirmation filter and state of classification at extraction time"]})
    return pd.DataFrame(rows), summaries


def territorial_evidence(universe_sources, declaration):
    result = []
    for source in universe_sources:
        result.append({key: source.get(key) for key in (
            "source_id", "rows", "residence_province_column", "province_header", "residence_department_column",
            "department_header", "rows_matching_la_rioja_capital_residence_labels", "rows_not_matching_residence_labels",
            "province_missing", "department_missing", "manual_filter_column_verified", "pre_manual_filter_records_available",
            "omitted_records_count", "notifier_header_refs", "event_header", "event_semantics_verified")})
    return {"sources": result, "prior_declaration": declaration,
        "evidence_level": "residence values consistent; manual operation not independently reconstructed",
        "residence_field_consistency_proves_manual_filter": False,
        "notification_establishment_equals_residence": False,
        "responsible_must_supply": ["exact province/department residence columns and literal selected values",
            "whether locality or notifying establishment was also used, and in what order",
            "pre-filter export or signed reconciliation, with rows before/after and omissions",
            "filter date, operator, source version/hash and saved query or documented manual procedure",
            "treatment of missing/contradictory residence, duplicates and nonresidents"],
        "geographic_approximation_already_accepted": True, "absolute_geographic_certainty_required": False}


def pending_impact(audit, panel, expected):
    pending = audit[audit.processing_outcome.eq("pending")].copy()
    undated = pending.week_start.isna()
    identity = ~pending.identity_countable
    eligibility = pending.analysis_eligibility.ne("eligible_provisional")
    summary = {"pending_records": len(pending), "undated_pending": int(undated.sum()),
        "identity_pending": int(identity.sum()), "eligibility_pending": int(eligibility.sum()),
        "identity_and_eligibility_overlap": int((identity & eligibility).sum()),
        "radios_with_undated_pending": int(pending.loc[undated, "radio_candidate"].nunique()),
        "undated_without_radio": int((undated & pending.radio_candidate.isna()).sum()),
        "included_approximate_dates": int((audit.processing_outcome.eq("included") & audit.fecha_aproximada).sum()),
        "blocked_panel_cells": int(panel.registros_pendientes_posibles.gt(0).sum()),
        "unknown_cells_blocked": int((panel.casos_observados.isna() & panel.registros_pendientes_posibles.gt(0)).sum()),
        "undated_scope": "all weeks of current analysis period at candidate radio; all radios if no candidate",
        "do_not_assign_undated_year_from_source_name": True, "pending_counts_additive_across_cells": False,
        "coverage_declaration_clears_pending": False, "blockers_preserved": True}
    for current, previous in (("pending_records", "pending_records"), ("undated_pending", "undated_pending"),
                              ("identity_pending", "identity_pending"), ("eligibility_pending", "eligibility_pending")):
        if summary[current] != expected[previous]:
            raise ValueError("Los pendientes ya no concilian con Fase 4.3")
    columns = ROW_KEY + ["classification", "analysis_eligibility", "episode_status", "identity_countable",
        "week_start", "radio_candidate", "processing_reasons"]
    detail = pending[columns].copy()
    detail["blocks_all_weeks_of_radio"] = undated
    detail["blocks_all_radios_of_possible_week"] = pending.radio_candidate.isna()
    return detail, summary


def coverage_proposals(candidates, panels, source_schemas, source_periods):
    rows = []
    for policy, intervals in candidates.items():
        panel = panels[policy]
        for index, interval in enumerate(intervals):
            source = interval["source_id"]
            start, end = interval["candidate_start"], interval["candidate_end"]
            scope = pd.Series(False, index=panel.index)
            if start is not None and end is not None:
                first, last = date.fromisoformat(start), date.fromisoformat(end)
                if first.weekday() != 6 or last.weekday() != 5 or not first <= last <= date(2024, 12, 31):
                    raise ValueError("Propuesta fuera del calendario/período preservado")
                scope = panel.fecha_inicio_semana.ge(first) & panel.fecha_fin_semana.le(last)
            schema = source_schemas[source]
            rows.append({**interval, "proposal_id": f"{policy}_{index + 1:02d}", "date_policy": policy,
                "proposed_interval_start": start, "proposed_interval_end": end,
                "temporal_criterion": interval["date_type"],
                "confirmation_column": schema["classification_column"], "confirmation_criterion": "responsible must validate historical literal labels and dengue event definition",
                "territorial_criterion": "patient residence: La Rioja province / Capital department; manual procedure to document",
                "completeness_justification": None, "evidence_for_completeness_available": False,
                "confidence": "none", "responsible_decision": None,
                "status": "proposal_not_declaration" if start is not None else "no_full_week_candidate",
                "pending_blocked_cells_in_interval": int((scope & panel.registros_pendientes_posibles.gt(0)).sum()),
                "unknown_candidate_cells_if_declared_and_separately_authorized": int((scope & panel.casos_observados.isna() & panel.registros_pendientes_posibles.eq(0) & ~panel.ventana_semanal_parcial).sum()),
                "limitations": ["observed envelope does not establish continuous extraction/reporting",
                    "source overlap/date-basis reconciliation required; do not add overlapping capacities",
                    "sample fallback may shift true symptom week; no delay correction imputed",
                    "pending blockers remain; no automatic extension to December 2024"],
                "declared_complete": False, "materialization_authorized": False})
    for source in sorted(set(source_schemas) - {row["source_id"] for row in rows}):
        period = next(item for item in source_periods if item["source_id"] == source)
        rows.append({"proposal_id": source + "_unresolved", "source_id": source, "date_policy": "unresolved",
            "proposed_interval_start": None, "proposed_interval_end": None, "status": "no_eligible_interval_to_propose",
            "observed_date_fields_for_review_only": period["date_fields"],
            "reason": "No preserved eligible interval available in Phase 4.3; classification/universe and date review required",
            "confidence": "none", "completeness_justification": None, "declared_complete": False,
            "materialization_authorized": False, "responsible_decision": None})
    return rows


def decision_template(classifications, territory, proposals):
    return {"version": VERSION, "status": "unsigned_non_executable_decision_template",
        "responsible_ref": None, "decision_date": None, "signature_or_document_ref": None,
        "classification_decisions": [{"source_id": row["source_id"], "column": row["classification_column"],
            "literal_label": row["literal_label"], "records": row["records"], "recorded_category": row["canonical_category"],
            "decision": None, "allowed_decisions": ["validate_under_documented_historical_definition", "retain_provisional", "keep_pending", "exclude_under_explicit_rule"],
            "dengue_event_definition_ref": None, "confirmation_criterion_ref": None,
            "criterion_type": None, "applicable_start": None, "applicable_end": None, "evidence_ref": None}
            for row in classifications.to_dict("records")],
        "territory_decisions": [{"source_id": row["source_id"],
            "proposed_province_column": row["residence_province_column"], "proposed_department_column": row["residence_department_column"],
            "actual_columns_and_literal_values": None, "residence_used_in_manual_filter": None,
            "notifying_establishment_used": None, "filter_order_and_date": None,
            "prefilter_reconciliation_ref": None, "evidence_ref": None} for row in territory["sources"]],
        "coverage_proposal_decisions": [{"proposal_id": row["proposal_id"], "source_id": row["source_id"],
            "candidate_start_for_review": row["proposed_interval_start"], "candidate_end_for_review": row["proposed_interval_end"],
            "decision": None, "allowed_decisions": ["reject", "retain_unknown", "declare_exact_interval_after_evidence_review"],
            "declared_start": None, "declared_end": None, "date_basis": None, "date_panels": [],
            "requested_extraction_start": None, "requested_extraction_end": None, "extraction_cutoff": None,
            "case_definition_ref": None, "territorial_filter_ref": None, "completeness_justification": None,
            "coverage_evidence_refs": [], "confidence": None, "overlap_resolution_ref": None,
            "pending_policy": "preserve_blockers"} for row in proposals],
        "pending_decisions": {"undated_records": "keep_unknown_and_preserve_blockers_until_documented_resolution",
            "identity_episodes_review_ref": None, "unmapped_classification_review_ref": None,
            "do_not_need_to_resolve_all_pending_to_use_other_unblocked_cells": True},
        "accepted_approximations": {"approximate_geography_already_accepted": True,
            "absolute_spatial_certainty_required": False, "sample_date_sensitivity_acknowledgment": None,
            "census_2022_retrospective_context": True, "uncertainty_does_not_disappear_after_signature": True},
        "experiment_mode_decision": None, "allowed_modes": ["retrospective_experimental", "operational_backtest_requires_point_in_time_evidence"],
        "coverage_declarations": [], "materialize_negatives_authorized": False, "training_authorized": False,
        "template_completion_does_not_execute_decisions": True}
