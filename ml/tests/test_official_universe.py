"""Regresiones de Fase 4.3 con datos ficticios; no usa fuentes oficiales reales."""

from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from sigard_ml.official.universe import (
    UNIVERSE_VERSION, candidate_intervals, declaration_readiness, diagnostic_view,
    panel_statistics, uncertainty_summary,
)
from sigard_ml.official.universe_pipeline import declaration_template, residence_inventory, run_review


def panel_fixture():
    starts = [date(2024, 1, 7) + timedelta(weeks=i) for i in range(4)]
    panel = pd.DataFrame({"radio_censal": ["fictional"] * 4, "anio_epidemiologico": [2024] * 4,
        "fecha_inicio_semana": starts, "fecha_fin_semana": [day + timedelta(days=6) for day in starts],
        "fecha_inicio_semana_objetivo": [day + timedelta(days=7) for day in starts],
        "casos_observados": pd.array([1, None, None, None], dtype="Int64"),
        "estado_observacion": ["positivo_provisional", "sin_respaldo_para_cero", "pendientes", "parcial"],
        "registros_pendientes_posibles": [0, 0, 1, 0], "ventana_semanal_parcial": [False, False, False, True],
        "objetivo_semana_siguiente": pd.array([None] * 4, dtype="Int8"), "objetivo_valido": [False] * 4})
    return panel


def intervals_fixture():
    return [{"candidate_start": "2024-01-07", "candidate_end": "2024-02-03"}]


def audit_fixture():
    rows = []
    for i, (day, outcome) in enumerate([(date(2024, 1, 7), "included"),
                                       (date(2024, 2, 3), "included"), (None, "pending")]):
        rows.append({"source_id": "fictional_source", "sheet_ref": "fictional_sheet", "record_ref": str(i),
            "reference_date": day, "week_start": day - timedelta(days=(day.weekday() + 1) % 7) if day else None,
            "tipo_fecha_referencia": "inicio_sintomas" if day else None, "processing_outcome": outcome,
            "processing_reasons": [] if day else ["date_unusable"], "radio_candidate": "fictional",
            "identity_countable": True, "analysis_eligibility": "eligible_provisional",
            "fecha_aproximada": False, "assignment_state": "uncertain", "classification": "confirmado"})
    return pd.DataFrame(rows)


def valid_declaration():
    return {"responsible_ref": "fictional-owner", "declared_on": "2026-10-15", "declaration_ref": "fictional",
        "start": "2024-01-07", "end": "2024-02-03", "source_ids": ["fictional_source"],
        "date_panels": ["strict"], "radio_scope": "all_263_capital_radios", "geographic_basis": "patient_residence",
        "state": "complete", "confidence": "low", "justification": "fictional justification",
        "provenance_ref": "fictional provenance", "case_definition_ref": "fictional dengue criterion",
        "manual_filter_reconciliation_ref": "fictional reconciliation", "temporal_basis_statement": "fictional symptoms",
        "pending_policy": "preserve_blockers", "experimental_approximation_acknowledged": True,
        "source_extractions": [{"source_id": "fictional_source", "requested_start": "2024-01-01", "requested_end": "2024-02-03",
            "extraction_date_field": "symptom_onset", "extraction_cutoff": "2024-03-01", "original_export_ref": "fictional",
            "confirmation_filter_column": "fictional classification", "confirmation_filter_values": ["fictional confirmed"],
            "geographic_filter_columns_and_values": {"fictional residence": ["fictional Capital"]}}]}


def test_unknowns_remain_null_and_pending_partial_and_undeclared_cells_are_not_negatives():
    panel = panel_fixture()
    before = panel.copy(deep=True)
    view = diagnostic_view(panel, intervals_fixture())
    assert view.potential_negative_if_interval_declared_complete.tolist() == [False, True, False, False]
    assert view.potential_next_week_negative.tolist() == [True, False, False, False]
    assert view.casos_observados.isna().sum() == 3
    assert not view.casos_observados.eq(0).any()
    assert not diagnostic_view(panel, []).potential_next_week_negative.any()
    pd.testing.assert_frame_equal(panel, before)


def test_partial_declared_interval_never_contributes_boundary_zeros():
    panel = panel_fixture()
    view = diagnostic_view(panel, [{"candidate_start": "2024-01-15", "candidate_end": "2024-01-20"}])
    assert not view.potential_negative_if_interval_declared_complete.any()


def test_candidate_envelope_is_not_a_declaration_and_does_not_use_filename_year():
    audit = audit_fixture()
    audit["source_id"] = "fictional_source_2020"
    result = candidate_intervals(audit)
    assert result[0]["reference_calendar_year"] == 2024
    assert result[0]["candidate_start"] == "2024-01-07"
    assert result[0]["candidate_end"] == "2024-02-03"
    assert result[0]["status"] == "proposal_not_declaration"
    assert result[0]["confidence_in_completeness"] == "none"
    assert result[0]["coverage_proven"] is False


def test_future_records_and_noncontiguous_target_lookups_are_not_used():
    audit = audit_fixture()
    audit.loc[0, "reference_date"] = date(2025, 1, 7)
    with pytest.raises(ValueError, match="2025"):
        candidate_intervals(audit)
    panel = panel_fixture().drop(index=1)
    assert not diagnostic_view(panel, intervals_fixture()).potential_next_week_negative.iloc[0]


def test_target_year_statistics_do_not_confuse_origin_year_and_next_week_year():
    panel = panel_fixture().iloc[:2].copy()
    panel["fecha_inicio_semana"] = [date(2023, 12, 24), date(2023, 12, 31)]
    panel["fecha_fin_semana"] = [date(2023, 12, 30), date(2024, 1, 6)]
    panel["fecha_inicio_semana_objetivo"] = [date(2023, 12, 31), date(2024, 1, 7)]
    panel["anio_epidemiologico"] = [2023, 2024]
    panel["objetivo_semana_siguiente"] = pd.array([1, None], dtype="Int8")
    panel["objetivo_valido"] = [True, False]
    report = panel_statistics(panel, [], ["2024-01-07"])
    assert report["by_target_year"][0]["target_epidemiological_year"] == 2024
    assert report["by_target_year"][0]["positive"] == 1
    assert len(report["by_radio"]) == 1


def test_chronological_diagnostics_exclude_target_crossing_cutoff():
    panel = panel_fixture()
    panel["objetivo_semana_siguiente"] = pd.array([1, 1, 1, None], dtype="Int8")
    panel["objetivo_valido"] = [True, True, True, False]
    stats = panel_statistics(panel, [], ["2024-01-21"])
    train, evaluation = stats["chronological_splits"]
    assert train["positive"] == 1 and evaluation["positive"] == 1
    assert train["boundary_known_labels_excluded"] == 1
    assert evaluation["unknown"] == 1
    assert not train["training_ready"] and not evaluation["training_ready"]


def test_uncertainties_keep_undated_identity_and_approximate_location_visible():
    strict = audit_fixture()
    expanded = strict.copy(deep=True)
    expanded.loc[2, "processing_outcome"] = "included"
    expanded.loc[2, "fecha_aproximada"] = True
    expanded.loc[2, "reference_date"] = date(2024, 1, 14)
    expanded.loc[2, "week_start"] = date(2024, 1, 14)
    report = uncertainty_summary(strict, expanded)
    assert report["recovered_included_records"] == 1
    assert report["policies"]["strict"]["undated_pending"] == 1
    assert report["policies"]["expanded"]["approximate_date_included_records"] == 1
    assert report["policies"]["expanded"]["uncertain_geographic_included_records"] == 3
    assert report["policies"]["strict"]["possible_undated_period"]["end"] == "2024-12-31"


def test_missing_declaration_stops_generation_and_valid_draft_still_needs_authorization():
    report = declaration_readiness([], {"fictional_source"})
    assert report["status"] == "missing_explicit_declaration"
    assert len(report["missing"]) == 8
    assert not report["execution_authorized"] and not report["assumed_zeros_generated"]
    declaration = valid_declaration()
    before = deepcopy(declaration)
    report = declaration_readiness([declaration], {"fictional_source"})
    assert not report["execution_authorized"]
    assert declaration == before


@pytest.mark.parametrize("change", [
    {"end": "2025-01-01"}, {"geographic_basis": "notifying_establishment"},
    {"pending_policy": "ignore_undated"}, {"confidence": None},
    {"manual_filter_reconciliation_ref": ""}, {"source_extractions": []},
    {"experimental_approximation_acknowledged": False}, {"source_ids": ["unknown"]},
    {"date_panels": ["strict", "strict"]}, {"radio_scope": "only_positive_radios"},
])
def test_incomplete_or_unsafe_declarations_are_rejected(change):
    with pytest.raises(ValueError):
        declaration_readiness([{**valid_declaration(), **change}], {"fictional_source"})


def test_overlapping_declarations_and_missing_filter_values_are_rejected():
    entry = valid_declaration()
    with pytest.raises(ValueError, match="superpuestas"):
        declaration_readiness([entry, deepcopy(entry)], {"fictional_source"})
    entry["source_extractions"][0]["confirmation_filter_values"] = []
    with pytest.raises(ValueError, match="valores literales"):
        declaration_readiness([entry], {"fictional_source"})


def test_template_is_unsigned_and_run_never_overwrites_previous_scenarios(tmp_path, monkeypatch):
    template = declaration_template({"fictional_source"})
    assert template["coverage_declarations"] == []
    assert template["interval_template"]["responsible_ref"] is None
    monkeypatch.setattr("sigard_ml.official.universe_pipeline.require_branch", lambda path: None)
    options = {"version": UNIVERSE_VERSION, "generate_assumed_zeros": False, "training_enabled": False,
               "output_dir": "data/interim/official/observed/coverage_042"}
    with pytest.raises(ValueError, match="nueva"):
        run_review(tmp_path, options)
    with pytest.raises(ValueError, match="sin ceros"):
        run_review(tmp_path, {**options, "generate_assumed_zeros": True})
    assert not (tmp_path / "data").exists()


def test_residence_inventory_tolerates_masked_headers_and_does_not_infer_manual_filter(monkeypatch):
    frame = pd.DataFrame({"column_001": ["La Rioja", "La Rioja"], "column_002": ["Capital", "Capital"]})
    schema = {"fields": {"province": "column_001", "department": "column_002"}}
    monkeypatch.setattr("sigard_ml.official.universe_pipeline.read_sheet", lambda *args, **kwargs: (frame, schema))
    source = SimpleNamespace(source_id="fictional_source", sheets=("fictional_sheet",))
    registry = SimpleNamespace(sources=(source,))
    config = {"sources": [{"source_id": "fictional_source"}]}
    structure = {"sources": [{"source_id": "fictional_source", "sheets": [
        {"safe_headers": {"column_001": "provincia residencia", "column_002": "departamento residencia", "column_003": None}}]}]}
    report = residence_inventory(config, registry, structure, audit_fixture().iloc[:2])
    item = report["sources"][0]
    assert item["rows_matching_la_rioja_capital_residence_labels"] == 2
    assert not item["manual_filter_column_verified"]
    assert not item["clinical_confirmation_verified"]
    assert item["omitted_records_count"] is None
    assert "La Rioja" not in str(report)
