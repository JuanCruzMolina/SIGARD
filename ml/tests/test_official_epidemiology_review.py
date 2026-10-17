"""Fase 5B.1: fixtures ficticios; no abre Excel, entrena ni calcula features."""

from dataclasses import replace
from datetime import date
import json

import pandas as pd
import pytest

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.epidemiology_review import (
    confirmation_inventory, coverage_proposals, decision_template,
    flag_implementation_evidence, pending_impact, territorial_evidence,
)
from sigard_ml.official.epidemiology_review_pipeline import DEFAULTS, private_paths, run_review, training_conditions
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from test_official_spatial_ml import RADIOS, fixture_panel


def fictional_audit():
    rows = []
    categories = [("confirmado", "included"), ("confirmado", "included"),
        ("confirmado", "included"), ("confirmado", "included"),
        ("sospechoso", "excluded"), ("descartado", "excluded"),
        ("confirmado", "included"), ("indeterminado", "pending"),
        ("confirmado", "included"), ("confirmado", "pending")]
    for i, (category, outcome) in enumerate(categories):
        rows.append({"source_id": f"fictional_{i // 2}", "sheet_ref": "sheet_01", "record_ref": f"fictional_row_{i}",
            "classification": category, "processing_outcome": outcome,
            "analysis_eligibility": "review" if category == "indeterminado" else "eligible_provisional" if category == "confirmado" else "excluded",
            "epidemiological_eligibility_validated": False, "epidemiological_identity_validated": False,
            "identity_countable": True, "episode_status": "singleton_provisional",
            "week_start": None if i == 9 else date(2024, 1, 14), "radio_candidate": RADIOS[0],
            "fecha_aproximada": False, "processing_reasons": ["date_unusable"] if i == 9 else ["eligibility_pending"] if i == 7 else []})
    return pd.DataFrame(rows)


def fictional_normalized(audit):
    result = audit[["source_id", "sheet_ref", "record_ref"]].copy()
    result["classification_label"] = audit.classification.map({"confirmado": "Confirmado", "sospechoso": "Sospechoso", "descartado": "Descartado", "indeterminado": "Unknown literal"})
    return result


def schemas():
    return {f"fictional_{i}": {"source_version": "v1", "sheet_ref": "sheet_01",
        "classification_column": "column_009", "classification_header": "clasificacion manual del caso"} for i in range(5)}


def panel():
    result = fixture_panel({RADIOS[0]: [None, 6, None, None], RADIOS[1]: [None] * 4}, start=date(2024, 1, 7))
    result.loc[result.radio_censal.eq(RADIOS[0]), "registros_pendientes_posibles"] = 1
    return result


def candidate(source="fictional_4", **changes):
    return {"source_id": source, "candidate_start": "2024-01-14", "candidate_end": "2024-01-27",
        "date_type": "inicio_sintomas", "reference_calendar_year": 2024, "confidence_in_completeness": "none",
        "coverage_proven": False, **changes}


def residence_sources():
    return [{"source_id": f"fictional_{i}", "rows": 2,
        "residence_province_column": "column_007", "province_header": "provincia residencia",
        "residence_department_column": "column_004", "department_header": "departamento residencia",
        "rows_matching_la_rioja_capital_residence_labels": 2, "rows_not_matching_residence_labels": 0,
        "province_missing": 0, "department_missing": 0, "manual_filter_column_verified": False,
        "pre_manual_filter_records_available": False, "omitted_records_count": None} for i in range(5)]


def test_recorded_confirmation_and_discard_are_not_confused_with_unknown_or_weekly_absence():
    audit = fictional_audit()
    before = audit.copy(deep=True)
    inventory, sources = confirmation_inventory(fictional_normalized(audit), audit, schemas())
    assert inventory.records.sum() == 10
    assert inventory.validated_under_current_flags.sum() == 0
    assert sum(row["recorded_confirmed_labels"] for row in sources) == 7
    statuses = inventory.set_index("canonical_category").evidence_status
    assert "recorded_confirmation_label" in statuses.loc["confirmado"].iloc[0]
    assert "explicit_recorded_discard" in statuses.loc["descartado"]
    assert "confirmation_unknown" in statuses.loc["indeterminado"]
    assert all(row["responsible_decision"] is None for row in inventory.to_dict("records"))
    pd.testing.assert_frame_equal(audit, before)


def test_zero_flags_are_explained_by_implementation_not_absence_of_confirmed_labels():
    evidence = flag_implementation_evidence()
    assert all(row["explicit_false_assignment_lines"] for row in evidence["findings"])
    assert "not evidence" in evidence["interpretation"]
    assert not evidence["automatic_flag_change_authorized"]


@pytest.mark.parametrize("problem", ["duplicate_normalized", "duplicate_audit", "missing_row"])
def test_classification_inventory_requires_preserved_row_alignment(problem):
    audit = fictional_audit()
    normalized = fictional_normalized(audit)
    if problem == "duplicate_normalized":
        normalized = pd.concat([normalized, normalized.iloc[:1]])
    elif problem == "duplicate_audit":
        audit = pd.concat([audit, audit.iloc[:1]])
    else:
        normalized = normalized.iloc[1:]
    with pytest.raises(ValueError):
        confirmation_inventory(normalized, audit, schemas())


def test_residence_consistency_does_not_prove_manual_filter_and_does_not_require_exact_geography():
    result = territorial_evidence(residence_sources(), {"selection_geographic_basis": "unknown"})
    assert all(row["rows_matching_la_rioja_capital_residence_labels"] == row["rows"] for row in result["sources"])
    assert not result["residence_field_consistency_proves_manual_filter"]
    assert not result["notification_establishment_equals_residence"]
    assert result["geographic_approximation_already_accepted"]
    assert not result["absolute_geographic_certainty_required"]


def test_pending_dates_preserve_entire_period_and_dimensions_may_overlap():
    audit = fictional_audit()
    audit.loc[7, "identity_countable"] = False
    detail, result = pending_impact(audit, panel(), {"pending_records": 2, "undated_pending": 1, "identity_pending": 1, "eligibility_pending": 1})
    assert result["identity_and_eligibility_overlap"] == 1
    assert not result["coverage_declaration_clears_pending"]
    assert not result["pending_counts_additive_across_cells"]
    assert detail.blocks_all_weeks_of_radio.sum() == 1
    assert not any(name in detail for name in ("classification_label", "event_ref", "fecha_inicio_sintomas_original", "latitude_candidate"))


def test_pending_reconciliation_does_not_silently_drop_records():
    with pytest.raises(ValueError, match="concilian"):
        pending_impact(fictional_audit(), panel(), {"pending_records": 0, "undated_pending": 1, "identity_pending": 0, "eligibility_pending": 1})


def test_interval_proposals_reuse_exact_boundaries_without_claiming_completeness():
    previous = {"strict": [candidate()], "expanded": [candidate()]}
    panels = {"strict": panel(), "expanded": panel()}
    periods = [{"source_id": source, "date_fields": {"sample_on": {"first": "2024-01-01", "last": "2024-02-01"}}} for source in schemas()]
    proposals = coverage_proposals(previous, panels, schemas(), periods)
    proposed = proposals[0]
    assert proposed["proposed_interval_start"] == "2024-01-14"
    assert proposed["proposed_interval_end"] == "2024-01-27"
    assert proposed["pending_blocked_cells_in_interval"] == 2
    assert proposed["unknown_candidate_cells_if_declared_and_separately_authorized"] == 2
    assert not any(row["declared_complete"] or row["materialization_authorized"] for row in proposals)
    assert all(row["confidence"] == "none" for row in proposals)
    unresolved = next(row for row in proposals if row["source_id"] == "fictional_2")
    assert unresolved["proposed_interval_start"] is None


@pytest.mark.parametrize("changes", [{"candidate_start": "2024-01-15"}, {"candidate_end": "2024-01-28"}, {"candidate_end": "2025-01-04"}])
def test_invalid_or_future_interval_never_uses_configured_december_end(changes):
    with pytest.raises(ValueError):
        coverage_proposals({"strict": [candidate(**changes)]}, {"strict": panel()}, schemas(), [])


def test_decision_template_remains_unsigned_without_external_documents():
    inventory, _ = confirmation_inventory(fictional_normalized(fictional_audit()), fictional_audit(), schemas())
    territory = territorial_evidence(residence_sources(), {})
    proposals = coverage_proposals({"expanded": [candidate()]}, {"expanded": panel()}, schemas(), [
        {"source_id": source, "date_fields": {}} for source in schemas()])
    result = decision_template(inventory, territory, proposals)
    assert result["coverage_declarations"] == []
    assert result["responsible_ref"] is None
    assert not result["training_authorized"] and not result["materialize_negatives_authorized"]
    assert all(row["declared_start"] is None and row["decision"] is None for row in result["coverage_proposal_decisions"])
    assert all(row["decision"] is None for row in result["classification_decisions"])
    assert result["accepted_approximations"]["approximate_geography_already_accepted"]


def test_model_A_conditions_do_not_require_unused_lags_or_absolute_spatial_precision():
    result = training_conditions()
    assert not result["Model_A_requires_epidemiological_lags"]
    assert not result["all_pending_must_be_resolved"]
    assert not result["absolute_geographic_certainty_required"]
    assert not result["blocked_unknowns_may_be_used_as_negatives"]
    assert result["current_status"] == "not_fit"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def save_manifest(directory, *, private=False, protected=None):
    filename = directory / ("integrity_manifest.private.json" if private else "integrity_manifest.json")
    save(filename, {"protected_files_sha256": protected or {}, "outputs_sha256": {
        path.relative_to(directory).as_posix(): digest_path(path) for path in directory.rglob("*") if path.is_file() and path != filename}})


@pytest.fixture
def fictional_review(tmp_path, monkeypatch):
    root, options = tmp_path, {**DEFAULTS, "source_2022_id": "fictional_2"}
    sources, provenance, quality_sources, structural_sources = [], [], [], []
    audit = fictional_audit()
    normalized = fictional_normalized(audit)
    for i in range(5):
        source_id = f"fictional_{i}"
        raw = root / f"data/raw/{source_id}.bin"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(b"FICTIONAL_SOURCE_UNCHANGED")
        sources.append(SourceAuthorization(source_id, "v1", raw.resolve(), ("Sheet",), "fictional",
            approved_extract=True, enabled=True, uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
            evidence_ref="fictional", custodian_ref="fictional", confidentiality_ref="fictional", storage_policy_ref="fictional"))
        path = root / options["phase2_dir"] / "normalized" / f"{source_id}_sheet_01.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized[normalized.source_id.eq(source_id)].drop(columns="sheet_ref").to_parquet(path, index=False)
        provenance.append({"source_id": source_id, "source_version": "v1", "source_sha256": digest_path(raw),
            "sheet_ref": "sheet_01", "normalized_sha256": digest_path(path)})
        quality_sources.append({"source_id": source_id, "sheets": [{"sheet_ref": "sheet_01", "fields": {"classification": "column_009"}}]})
        structural_sources.append({"source_id": source_id, "sheets": [{"sheet_ref": "sheet_01", "safe_headers": {"column_009": "clasificacion manual del caso"}}]})
    phase2 = root / options["phase2_dir"]
    save(phase2 / "quality_report.json", {"sources": quality_sources})
    save(phase2 / "structure_report.json", {"sources": structural_sources})
    provenance = {"sources": provenance, "quality_report_sha256": digest_path(phase2 / "quality_report.json")}
    expected_pending = {"pending_records": 2, "undated_pending": 1, "identity_pending": 0, "eligibility_pending": 1}
    for policy in ("strict", "expanded"):
        prior = root / options["observed_dir"] / policy / "exploratory"
        prior.mkdir(parents=True)
        audit.to_parquet(prior / "records_audit.parquet", index=False)
        save_manifest(prior)
        directory = root / options["coverage_dir"] / policy / "conservative"
        directory.mkdir(parents=True)
        panel().to_parquet(directory / "panel.parquet", index=False)
    save_manifest(root / options["observed_dir"])
    save(root / options["coverage_dir"] / "metadata.json", {"provenance": {"normalization": provenance}})
    save_manifest(root / options["coverage_dir"])
    universe = {"provenance": provenance, "universe": {"sources": residence_sources()},
        "previous_provenance_declaration": {"selection_geographic_basis": "unknown"},
        "previous_delay_evidence": {}, "geographic_evidence": {"location_role": "unknown"},
        "previous_geographic_sensitivity": {}, "previous_source_period_declarations": [],
        "previous_coverage_declarations": [], "previous_coverage_verifications": [],
        "uncertainty": {"policies": {policy: expected_pending for policy in ("strict", "expanded")}},
        "candidate_intervals": {policy: [candidate()] for policy in ("strict", "expanded")},
        "source_periods": [{"source_id": source, "date_fields": {}} for source in schemas()]}
    directory = root / options["universe_dir"]
    save(directory / "review.private.json", universe)
    save_manifest(directory, private=True, protected={str(path.relative_to(root)): digest_path(path)
        for path in (phase2 / "quality_report.json", phase2 / "structure_report.json")})
    directory = root / options["phase5b_dir"]
    save(directory / "review.private.json", {"datasets": {f"{policy}/conservative": {"positive": 1, "negative": 0, "unknown": 7} for policy in ("strict", "expanded")}})
    save(directory / "experiment_A.private.json", {"training_enabled": False, "parameters": {"n_estimators": 400}})
    save(directory / "metadata.private.json", {"calendar_version": "ar-snvs-2020-2026-v1"})
    save_manifest(directory, private=True)
    save(root / options["access_config"], {"fictional": True})
    registry = SourceRegistry(tuple(sources))
    monkeypatch.setattr("sigard_ml.official.epidemiology_review_pipeline.require_branch", lambda root: None)
    monkeypatch.setattr("sigard_ml.official.epidemiology_review_pipeline.load_configuration", lambda *args: ({}, registry))
    for target in ("sigard_ml.official.excel.open_authorized_workbook", "sigard_ml.official.excel.read_sheet",
        "sigard_ml.official.spatial_ml.features.build_features", "sklearn.ensemble.RandomForestClassifier.fit",
        "sklearn.ensemble.RandomForestRegressor.fit"):
        monkeypatch.setattr(target, lambda *args, **kwargs: pytest.fail("Se intentó ingestión/features/entrenamiento"))
    return root, options, registry


def test_full_diagnostic_succeeds_without_external_documents_and_preserves_everything(fictional_review):
    root, options, _ = fictional_review
    output = root / options["output_dir"]
    before = protected_snapshot(root, output)
    report = run_review(root, options)
    assert len(report["classification_sources"]) == 5
    assert not report["external_documentation_required_to_generate_diagnostic"]
    assert report["current_labels"]["expanded"] == {"positive": 1, "negative": 0, "unknown": 7}
    assert report["pending"]["expanded"]["undated_pending"] == 1
    require_preserved(before, protected_snapshot(root, output))
    template = json.loads((output / "decisions.template.private.json").read_text())
    assert not template["training_authorized"] and template["coverage_declarations"] == []
    assert "cero banderas" in (output / "decision_dossier.private.md").read_text(encoding="utf-8")
    assert "FICTIONAL_SOURCE_UNCHANGED" not in (output / "decision_dossier.private.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="nuevo"):
        run_review(root, options)
    second = {**options, "output_dir": "data/interim/official/fictional_05b1_repeat"}
    assert run_review(root, second) == report
    for path in output.iterdir():
        if path.suffix == ".parquet" or path.name in {"diagnostic.private.json", "decisions.template.private.json", "decision_dossier.private.md"}:
            assert digest_path(path) == digest_path(root / second["output_dir"] / path.name)


def test_denied_access_precedes_reading_private_artifacts(fictional_review, monkeypatch):
    root, options, registry = fictional_review
    denied = SourceRegistry((replace(registry.sources[0], enabled=False), *registry.sources[1:]))
    monkeypatch.setattr("sigard_ml.official.epidemiology_review_pipeline.load_configuration", lambda *args: ({}, denied))
    monkeypatch.setattr("sigard_ml.official.epidemiology_review_pipeline.protected_snapshot", lambda *args: pytest.fail("Lectura sin autorización"))
    with pytest.raises(AccessDenied):
        run_review(root, options)


def test_modified_normalized_classification_stops_before_outputs(fictional_review):
    root, options, _ = fictional_review
    path = root / options["phase2_dir"] / "normalized/fictional_2_sheet_01.parquet"
    path.write_bytes(b"FICTIONAL_CHANGED_CLASSIFICATION")
    with pytest.raises(ValueError, match="normalizado"):
        run_review(root, options)
    assert not (root / options["output_dir"]).exists()


@pytest.mark.parametrize("field,value", [("training_enabled", True), ("materialize_negatives", True),
    ("output_dir", "frontend/public/data"), ("output_dir", "data/interim/official/observed"),
    ("phase2_dir", "data/raw"), ("output_dir", "../outside")])
def test_unsafe_actions_and_paths_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        private_paths(tmp_path, {**DEFAULTS, field: value})
