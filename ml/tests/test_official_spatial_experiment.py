"""Fase 5B: pruebas ficticias, con fit y lectura de Excel prohibidos."""

from dataclasses import replace
from datetime import date
import json

import pandas as pd
import pytest

from sigard_ml.official.access import AccessDenied, SourceRegistry
from sigard_ml.official.spatial_ml.features import build_features, feature_definitions
from sigard_ml.official.spatial_ml.pipeline import run_preparation
from sigard_ml.official.spatial_ml.splits import prepare_splits
from sigard_ml.official.spatial_ml.experiment_selection import (
    BASE, SHORT, SETS, audit_columns, compare_sets, training_support,
)
from sigard_ml.official.spatial_ml.experiment_missing import numeric_view
from sigard_ml.official.spatial_ml.experiment_coverage import declared_coverage_preview, eligibility_review
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS, experiment_protocol
from sigard_ml.official.spatial_ml.experiment_pipeline import (
    DEFAULTS, experiment_paths, label_policy_comparison, run_experiment_preparation,
)
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.universe_pipeline import declaration_template

from test_official_spatial_ml import (
    RADIOS, NEIGHBORS, PLANS, fixture_panel, static_fixture, fictional_preparation,
)


def fixture_features(counts=None):
    panel = fixture_panel(counts)
    features = build_features(panel, static_fixture(), NEIGHBORS)
    return panel, features, feature_definitions(features.columns)


def test_all_55_columns_audited_by_year_and_next_week_positive_label():
    values = [None, 1, None, 3] * 4
    panel, features, definitions = fixture_features({radio: values for radio in RADIOS})
    audit, yearly, policies = audit_columns(features, panel, definitions)
    assert len(audit) == 55 and len(policies) == 55
    assert len(yearly) == 55 * panel.anio_epidemiologico.nunique()
    lag = audit.set_index("feature").loc["registros_retro_rezago_1"]
    positive = panel.objetivo_semana_siguiente.eq(1).fillna(False)
    assert lag.available == features.registros_retro_rezago_1.notna().sum()
    assert lag.available_in_positive_labels == (positive & features.registros_retro_rezago_1.notna()).sum()
    assert lag.available_pct < 100
    flag = audit.set_index("feature").loc["registros_retro_acumulado_12_valor_disponible"]
    assert flag.available_pct == 100 and flag.underlying_available_pct == 0
    assert not any(policy["uses_future_week"] for policy in policies)
    assert next(row for row in policies if row["feature"] == "poblacion")["historical_availability_verified"] is False


def test_year_without_positive_labels_has_no_percentage_denominator():
    panel, features, definitions = fixture_features({radio: [None] * 16 for radio in RADIOS})
    audit, yearly, _ = audit_columns(features, panel, definitions)
    assert audit.available_in_positive_labels_pct.isna().all()
    assert yearly.available_in_positive_labels_pct.isna().all()


def test_sets_keep_all_rows_when_optional_history_is_unknown():
    panel, features, _ = fixture_features({radio: [None] * 16 for radio in RADIOS})
    result = compare_sets(features, panel).query("origin_year == 'all'").set_index("set")
    assert result.required_available_pct.eq(100).all()
    assert result.loc["A", "all_candidate_values_available_pct"] == 100
    assert result.loc[["B", "C"], "all_candidate_values_available_pct"].eq(0).all()
    assert result.loc["B", "optional_count"] == 4
    assert result.loc["C", "optional_count"] == 14
    assert all(SETS[name]["required"] == BASE for name in SETS)


@pytest.mark.parametrize("mutation", ["target", "future_offset", "catalog", "duplicate_label", "missing_label"])
def test_audit_rejects_target_leakage_and_misaligned_catalog_or_labels(mutation):
    panel, features, definitions = fixture_features()
    if mutation == "target":
        features["objetivo_semana_siguiente"] = 1
    elif mutation == "future_offset":
        definitions[SHORT[0]]["source_week_offsets"] = [1]
    elif mutation == "catalog":
        definitions.pop("poblacion")
    elif mutation == "duplicate_label":
        panel = pd.concat([panel, panel.iloc[:1]])
    else:
        panel = panel.iloc[1:]
    with pytest.raises(ValueError):
        audit_columns(features, panel, definitions)


def test_optional_support_never_reads_validation_or_test_values_or_labels():
    panel, features, _ = fixture_features({radio: [None, 1, 0, 2] * 4 for radio in RADIOS})
    assignments, _ = prepare_splits(panel, PLANS)
    first, _ = training_support(features, panel, assignments)
    changed_features, changed_labels = features.copy(), panel.copy()
    outside = ~assignments.partition.eq("train")
    changed_features.loc[outside.to_numpy(), SHORT] = 999
    changed_labels.loc[outside.to_numpy(), "objetivo_semana_siguiente"] = 0
    second, _ = training_support(changed_features, changed_labels, assignments)
    pd.testing.assert_frame_equal(first, second)
    assert not first.selection_applied.any()
    assert first.decision.eq("block_if_required_else_drop_optional").all()


def test_unsupported_classes_remain_blocked_even_if_features_are_present():
    panel, features, _ = fixture_features()
    assignments, _ = prepare_splits(panel, PLANS)
    support, partitions = training_support(features, panel, assignments)
    assert not support.passes_future_support_rule.any()
    assert partitions.negative.eq(0).all() and not partitions.fit_for_training.any()


def test_missing_values_zeros_and_temporal_unavailability_are_distinct_and_immutable():
    selected = ["poblacion", SHORT[0]]
    frame = pd.DataFrame({"poblacion": [100, 200, 300], SHORT[0]: [0., None, 5.]})
    original = frame.copy(deep=True)
    evidence = pd.DataFrame({"poblacion": [False, False, False], SHORT[0]: [True, True, False]})
    retrospective, flags, states = numeric_view(frame, selected, available_at_origin=evidence)
    assert retrospective.loc[0, SHORT[0]] == 0 and pd.isna(retrospective.loc[1, SHORT[0]])
    assert states.loc[0, SHORT[0]] == "supported_observation_zero"
    assert states.loc[1, SHORT[0]] == "unknown_value"
    assert retrospective.loc[2, SHORT[0]] == 5 and not flags.loc[2, SHORT[0] + "_missing"]
    operational, flags, states = numeric_view(frame, selected, mode="point_in_time", available_at_origin=evidence)
    assert operational.poblacion.isna().all() and pd.isna(operational.loc[2, SHORT[0]])
    assert operational.loc[0, SHORT[0]] == 0
    assert states.loc[2, SHORT[0]] == "temporally_unavailable_or_unverified"
    pd.testing.assert_frame_equal(frame, original)


def test_numeric_zero_of_calendar_is_not_an_epidemiological_zero():
    frame = pd.DataFrame({"estacionalidad_seno": [0.]})
    _, _, states = numeric_view(frame, ["estacionalidad_seno"], available_at_origin=pd.DataFrame({"estacionalidad_seno": [True]}))
    assert states.iloc[0, 0] == "known_numeric_zero_not_an_epidemiological_label"


@pytest.mark.parametrize("mutation", ["target", "infinity", "evidence_index", "evidence_columns", "mode"])
def test_missingness_view_rejects_invalid_inputs(mutation):
    frame = pd.DataFrame({SHORT[0]: [None, 1.]})
    selected, mode, evidence = [SHORT[0]], "retrospective", None
    if mutation == "target":
        frame["target"] = 0
        selected = ["target"]
    elif mutation == "infinity":
        frame.loc[1, SHORT[0]] = float("inf")
    elif mutation == "evidence_index":
        evidence = pd.DataFrame({SHORT[0]: [True]}, index=[9])
    elif mutation == "evidence_columns":
        evidence = pd.DataFrame({"wrong": [True, True]})
    else:
        mode = "invent_zeros"
    with pytest.raises(ValueError):
        numeric_view(frame, selected, mode=mode, available_at_origin=evidence)


def declaration(**changes):
    template = declaration_template({"fixture"})["interval_template"]
    return {**template, "responsible_ref": "fictional_responsible", "declared_on": "2024-04-01",
        "declaration_ref": "fictional_declaration", "start": "2024-01-07", "end": "2024-01-27",
        "source_ids": ["fixture"], "date_panels": ["expanded"], "justification": "fictional",
        "provenance_ref": "fictional", "confidence": "low", "case_definition_ref": "fictional",
        "manual_filter_reconciliation_ref": "fictional", "temporal_basis_statement": "fictional",
        "experimental_approximation_acknowledged": True,
        "source_extractions": [{"source_id": "fixture", "requested_start": "2024-01-01", "requested_end": "2024-02-29",
            "extraction_date_field": "fictional_reference", "extraction_cutoff": "2024-03-31",
            "original_export_ref": "fictional", "confirmation_filter_column": "fictional",
            "confirmation_filter_values": ["fictional"], "geographic_filter_columns_and_values": {"fictional": ["fictional"]}}], **changes}


def test_no_declaration_means_no_experimental_candidates_or_labels():
    panel = fixture_panel({radio: [None] * 16 for radio in RADIOS})
    before = panel.copy(deep=True)
    preview, report = declared_coverage_preview(panel, [], {"fixture"}, date_policy="expanded")
    assert not preview.candidate_observation_if_separately_authorized.any()
    assert not preview.candidate_target_if_separately_authorized.any()
    assert not report["assumed_zeros_materialized"]
    pd.testing.assert_frame_equal(panel, before)


def test_explicit_intervals_preserve_pending_partial_positive_and_date_scope():
    panel = fixture_panel({radio: [None] * 16 for radio in RADIOS})
    panel.loc[3, "registros_pendientes_posibles"] = 1  # Jan 7.
    panel.loc[4, "ventana_semanal_parcial"] = True  # Jan 14.
    panel.loc[5, "casos_observados"] = 1  # Jan 21.
    preserved = panel.copy(deep=True)
    preview, report = declared_coverage_preview(panel, [declaration()], {"fixture"}, date_policy="expanded")
    assert report["candidate_observations"] == 3  # Only the other radio.
    assert not preview.materialization_authorized.any()
    assert not preview.loc[panel.radio_censal.eq(RADIOS[0]), "candidate_observation_if_separately_authorized"].any()
    assert not preview.loc[panel.fecha_inicio_semana.lt(date(2024, 1, 7)), "candidate_observation_if_separately_authorized"].any()
    strict = panel.assign(panel_fechas="strict")
    _, strict_report = declared_coverage_preview(strict, [declaration()], {"fixture"}, date_policy="strict")
    assert strict_report["candidate_observations"] == 0
    pd.testing.assert_frame_equal(panel, preserved)


def test_target_preview_uses_exact_next_week_without_jumping_a_gap():
    panel = fixture_panel({radio: [None] * 16 for radio in RADIOS})
    panel = panel[panel.fecha_inicio_semana.ne(date(2024, 1, 7))].reset_index(drop=True)
    preview, _ = declared_coverage_preview(panel, [declaration()], {"fixture"}, date_policy="expanded")
    assert not preview.loc[preview.fecha_inicio_semana.eq(date(2023, 12, 31)), "candidate_target_if_separately_authorized"].any()


@pytest.mark.parametrize("entry", [None, {"responsible_ref": ""}, {"pending_policy": "ignore"}, {"start": "2025-01-05", "end": "2025-01-11"}])
def test_incomplete_or_unsafe_declaration_is_rejected(entry):
    panel = fixture_panel()
    entries = [declaration(**entry)] if entry is not None else [declaration_template({"fixture"})["interval_template"]]
    with pytest.raises((ValueError, TypeError)):
        declared_coverage_preview(panel, entries, {"fixture"}, date_policy="expanded")


def test_declared_interval_cannot_extend_past_documented_extractions_or_materialize():
    panel = fixture_panel()
    with pytest.raises(ValueError, match="extracción"):
        declared_coverage_preview(panel, [declaration(end="2024-03-30")], {"fixture"}, date_policy="expanded")
    with pytest.raises(ValueError, match="materializar"):
        declared_coverage_preview(panel, [declaration()], {"fixture"}, date_policy="expanded", materialize=True)


def test_unvalidated_classification_is_not_called_confirmed():
    audit = pd.DataFrame({"source_id": ["delivery_2022"] * 3, "classification": ["confirmado", "sospechoso", "confirmado"],
        "processing_outcome": ["included", "excluded", "included"], "analysis_eligibility": ["eligible_provisional"] * 3,
        "epidemiological_eligibility_validated": [False, False, True], "epidemiological_identity_validated": [False, False, True]})
    preserved = audit.copy(deep=True)
    inventory, report = eligibility_review(audit)
    assert report["included_records_provisional"] == 2
    assert report["confirmed_under_existing_validation_flags"] == 1
    assert not report["source_2022"]["universe_and_clinical_criterion_resolved"]
    assert inventory.records.sum() == 3
    pd.testing.assert_frame_equal(audit, preserved)


def test_protocol_validates_parameters_without_fitting_and_disables_actions(monkeypatch):
    def no_fit(*args, **kwargs):
        pytest.fail("Fase 5B no puede entrenar ni ajustar imputadores")
    monkeypatch.setattr("sklearn.ensemble.RandomForestClassifier.fit", no_fit)
    monkeypatch.setattr("sklearn.ensemble.RandomForestRegressor.fit", no_fit)
    monkeypatch.setattr("sklearn.impute.SimpleImputer.fit", no_fit)
    protocol = experiment_protocol()
    assert protocol["parameters"] == RF_PARAMETERS
    assert not protocol["training_performed"] and not protocol["environment"]["estimator_fitted"]
    assert protocol["environment"]["native_nan_supported"]
    assert not protocol["imputation"]["parameters_fitted"]
    assert protocol["parameters"]["random_state"] == protocol["future_replicate_seeds"][0]
    assert protocol["calibration"]["applied"] is False


def rewrite_manifest(directory):
    name = "integrity_manifest.private.json"
    data = {"outputs_sha256": {path.relative_to(directory).as_posix(): digest_path(path) for path in directory.rglob("*") if path.is_file() and path.name != name}}
    (directory / name).write_text(json.dumps(data), encoding="utf-8")


def rewrite_observed_manifest(directory):
    filename = directory / "integrity_manifest.json"
    filename.write_text(json.dumps({"outputs_sha256": {path.relative_to(directory).as_posix(): digest_path(path) for path in directory.rglob("*") if path.is_file() and path != filename}}), encoding="utf-8")


@pytest.fixture
def fictional_experiment(fictional_preparation, monkeypatch):
    root, phase5a, registry = fictional_preparation
    universe = root / phase5a["universe_dir"]
    review = json.loads((universe / "review.private.json").read_text())
    review["statistics"] = {policy: {"overall": {"next_week_labels": {"positive": 30, "negative": 0, "unknown": 2},
        "potential_next_week_negatives_conditional": 0}} for policy in ("strict", "expanded")}
    (universe / "review.private.json").write_text(json.dumps(review), encoding="utf-8")
    (universe / "configuration.private.json").write_text(json.dumps({"coverage_declarations": [], "training_enabled": False, "generate_assumed_zeros": False}), encoding="utf-8")
    rewrite_manifest(universe)
    for policy in ("strict", "expanded"):
        prior = root / phase5a["observed_dir"] / policy / "exploratory"
        audit = pd.read_parquet(prior / "records_audit.parquet")
        audit["analysis_eligibility"] = "eligible_provisional"
        audit["epidemiological_eligibility_validated"] = False
        audit["epidemiological_identity_validated"] = False
        audit.to_parquet(prior / "records_audit.parquet", index=False)
        rewrite_observed_manifest(prior)
    rewrite_observed_manifest(root / phase5a["observed_dir"])
    run_preparation(root, phase5a)
    monkeypatch.setattr("sigard_ml.official.spatial_ml.experiment_pipeline.require_branch", lambda root: None)
    monkeypatch.setattr("sigard_ml.official.spatial_ml.experiment_pipeline.load_configuration", lambda *args: ({}, registry))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.experiment_pipeline.EXPECTED_RADIOS", 2)
    for target in ("sklearn.ensemble.RandomForestClassifier.fit", "sklearn.ensemble.RandomForestRegressor.fit", "sklearn.impute.SimpleImputer.fit", "sigard_ml.official.excel.open_authorized_workbook"):
        monkeypatch.setattr(target, lambda *args, **kwargs: pytest.fail("Fase 5B intentó fit o abrir Excel"))
    return root, {**DEFAULTS, "source_2022_id": "fixture"}, registry


def test_complete_private_preparation_reproduces_audits_and_preserves_prior_outputs(fictional_experiment):
    root, options, _ = fictional_experiment
    output = root / options["output_dir"]
    before = protected_snapshot(root, output)
    first = run_experiment_preparation(root, options)
    assert first["datasets"]["expanded/conservative"]["positive"] == 30
    assert first["datasets"]["expanded/conservative"]["negative"] == 0
    assert not first["negatives_materialized"] and not first["training_performed"]
    require_preserved(before, protected_snapshot(root, output))
    for name in ("A", "B", "C"):
        assert not json.loads((output / f"experiment_{name}.private.json").read_text())["training_enabled"]
    with pytest.raises(ValueError, match="nuevo"):
        run_experiment_preparation(root, options)
    repeated_options = {**options, "output_dir": "data/interim/official/fictional_05b_repeat"}
    second = run_experiment_preparation(root, repeated_options)
    assert first == second
    for path in output.rglob("*.parquet"):
        assert digest_path(path) == digest_path(root / repeated_options["output_dir"] / path.relative_to(output))


def test_denied_authorization_precedes_private_reads(fictional_experiment, monkeypatch):
    root, options, registry = fictional_experiment
    denied = SourceRegistry((replace(registry.sources[0], enabled=False),))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.experiment_pipeline.load_configuration", lambda *args: ({}, denied))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.experiment_pipeline.protected_snapshot", lambda *args: pytest.fail("Lectura sin permiso"))
    with pytest.raises(AccessDenied):
        run_experiment_preparation(root, options)


def test_tampered_phase5a_artifact_blocks_experiment(fictional_experiment):
    root, options, _ = fictional_experiment
    path = root / options["phase5a_dir"] / "expanded/conservative/labels.private.parquet"
    path.write_bytes(b"FICTIONAL_CORRUPTION")
    with pytest.raises(ValueError, match="manifiesto"):
        run_experiment_preparation(root, options)
    assert not (root / options["output_dir"]).exists()


@pytest.mark.parametrize("field,value", [("training_enabled", True), ("materialize_assumed_zeros", True),
    ("output_dir", "frontend/public/data"), ("output_dir", "data/interim/official/observed"),
    ("phase5a_dir", "data/raw/not_private"), ("output_dir", "../outside")])
def test_actions_and_unsafe_directories_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        experiment_paths(tmp_path, {**DEFAULTS, field: value})


def test_date_policy_comparison_preserves_unknown_not_equal_negative():
    strict = fixture_panel({radio: [None] * 16 for radio in RADIOS})
    expanded = strict.copy()
    expanded.loc[1, "objetivo_semana_siguiente"] = 1
    result = label_policy_comparison(strict, expanded)
    assert result["expanded_positive_strict_unknown"] == 1
    assert result["positive_negative_disagreements"] == 0
