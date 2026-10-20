"""Integración de etapa 9: sólo fixtures y permisos/evidencias simulados."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
import json

import pandas as pd
import pytest

from sigard_ml.official.access import AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.epidemiological_preflight import ACCREDITED, EXPERIMENTAL, dataset_digest
from sigard_ml.official.preparation_pipeline import run_preparation
from sigard_ml.official.weekly_targets import attach_next_week_target
from test_epidemiological_preflight import approvals, bundle


def authorization(data, tmp_path, **changes):
    source = SourceAuthorization(
        source_id=data["dataset_id"], source_version=data["dataset_version"],
        path=tmp_path / "fictional_in_memory_extract.json", sheets=("records", "weeks", "labels"),
        subset_ref=dataset_digest(data), approved_extract=True, enabled=True,
        uses=frozenset({AuthorizedUse.PROCESSING}), evidence_ref="fictional-context-evidence",
        custodian_ref="fictional-custodian", confidentiality_ref="fictional-confidentiality",
        storage_policy_ref="fictional-in-memory-only")
    return SourceRegistry((replace(source, **changes),))


def execute(data, tmp_path, *, uses=(EXPERIMENTAL, ACCREDITED), **options):
    artifacts, decisions = approvals(data, uses=uses)
    return run_preparation(data, registry=authorization(data, tmp_path), artifacts=artifacts,
                           decision_refs=decisions, **options)


def blocker(result, control):
    assert result.status == "blocked"
    assert any(check.control_id == control for check in result.blockers)
    assert all(check.reason for check in result.blockers)
    assert not result.to_dict()["permitted_uses"]


def test_complete_authorized_fixture_executes_validation_preflight_and_decision(tmp_path):
    result = execute(bundle(accredited=True), tmp_path)
    output = result.to_dict()
    assert result.status == "prepared_simulation_only"
    assert output["validation_executed"] and output["preflight_executed"]
    assert output["technical_consistent"]
    assert output["permitted_uses"] == ["simulation_epidemiological_accredited"]
    assert output["passed_controls"] and output["warnings"] and output["pending_evidence"]
    assert not output["blockers"]
    assert not output["training_enabled"] and not output["training_authorized"] and not output["evaluation_authorized"]
    assert not output["datasets_written"]
    assert sum(output["validation_counts"].values()) == len(result.preflight.findings)
    assert all(item["count"] >= 1 for item in output["passed_controls"])
    assert "fictional-reviewer" not in json.dumps(output)
    assert "fictional_row" not in json.dumps(output)


def test_unaccredited_classification_blocks_accredited_preparation(tmp_path):
    data = bundle(accredited=True)
    data["records"][0].update(epidemiological_eligibility_validated=False, classification_evidence_ref=None)
    result = execute(data, tmp_path)
    assert result.preflight.technical_consistent
    blocker(result, "eligibility.P1")


def test_insufficient_coverage_preserves_unknown_states_and_blocks(tmp_path):
    data = bundle()
    before = deepcopy(data)
    result = execute(data, tmp_path)
    blocker(result, "eligibility.coverage")
    assert result.preflight.technical_consistent
    assert any(item.result.control_id == "label.unknown" for item in result.preflight.findings)
    assert data["weeks"][1]["casos_observados"] is None
    assert data["labels"][0]["objetivo_semana_siguiente"] is None
    assert data == before


def test_experimental_route_must_be_selected_explicitly_and_never_enables_official_use(tmp_path):
    data = bundle(assumed=True)
    blocker(execute(data, tmp_path, uses=(EXPERIMENTAL,)), "decision.scope")
    result = execute(data, tmp_path, uses=(EXPERIMENTAL,), requested_use=EXPERIMENTAL)
    assert result.status == "prepared_simulation_only"
    assert result.to_dict()["permitted_uses"] == ["simulation_retrospective_experimental"]
    assert data["weeks"][1]["casos_observados"] is None
    assert result.to_dict()["training_authorized"] is False


def test_external_processing_permission_is_not_epidemiological_approval(tmp_path):
    data = bundle(accredited=True)
    result = run_preparation(data, registry=authorization(data, tmp_path))
    assert result.preflight.technical_consistent
    blocker(result, "decision.scope")


@pytest.mark.parametrize("requirement", ["P1", "P3"])
def test_declared_confirmation_or_coverage_cannot_replace_missing_evidence(tmp_path, requirement):
    data = bundle(accredited=True)
    artifacts, refs = approvals(data)
    del artifacts["proof:" + requirement]
    result = run_preparation(data, registry=authorization(data, tmp_path), artifacts=artifacts, decision_refs=refs)
    assert result.preflight.technical_consistent
    blocker(result, "evidence." + requirement)


def test_unknown_use_does_not_fall_back_to_experimental_preparation(tmp_path):
    blocker(run_preparation(bundle(accredited=True), requested_use="skip_approval"), "preparation.use")


def test_dataset_cannot_grant_itself_permission(tmp_path, monkeypatch):
    data = bundle(accredited=True)
    data["processing_authorized"] = True
    artifacts, refs = approvals(bundle(accredited=True))
    monkeypatch.setattr("sigard_ml.official.preparation_pipeline.run_preflight",
                        lambda *args, **kwargs: pytest.fail("Preflight sin autorización externa"))
    result = run_preparation(data, artifacts=artifacts, decision_refs=refs)
    blocker(result, "preparation.authorization")
    assert not result.to_dict()["validation_executed"]


@pytest.mark.parametrize("changes", [{"enabled": False}, {"approved_extract": False}, {"uses": frozenset()},
    {"sheets": ("records", "weeks")}, {"subset_ref": "fictional-other-scope"}, {"source_version": "fictional-v2"},
    {"evidence_ref": None}, {"custodian_ref": None}, {"confidentiality_ref": None}, {"storage_policy_ref": None}])
def test_existing_source_registry_denies_missing_context_before_validation(tmp_path, monkeypatch, changes):
    data = bundle(accredited=True)
    registry = authorization(data, tmp_path, **changes)
    monkeypatch.setattr("sigard_ml.official.preparation_pipeline.run_preflight",
                        lambda *args, **kwargs: pytest.fail("Se omitió el permiso externo"))
    blocker(run_preparation(data, registry=registry), "preparation.authorization")


def test_changed_fixture_scope_is_rejected_before_preflight(tmp_path, monkeypatch):
    data = bundle(accredited=True)
    registry = authorization(data, tmp_path)
    data["records"][0]["record_ref"] = "fictional-changed-row"
    monkeypatch.setattr("sigard_ml.official.preparation_pipeline.run_preflight",
                        lambda *args, **kwargs: pytest.fail("Se aceptó una huella ajena"))
    blocker(run_preparation(data, registry=registry), "preparation.authorization")


@pytest.mark.parametrize("operation", [AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION, AuthorizedUse.PUBLICATION,
                                        AuthorizedUse.INSPECTION, "processing", "train", True])
def test_no_operation_can_continue_to_training_or_evaluation(tmp_path, monkeypatch, operation):
    data = bundle(accredited=True)
    registry = authorization(data, tmp_path, uses=frozenset(AuthorizedUse))
    artifacts, refs = approvals(data)
    monkeypatch.setattr("sigard_ml.official.preparation_pipeline.run_preflight",
                        lambda *args, **kwargs: pytest.fail("Operación no admitida"))
    result = run_preparation(data, registry=registry, artifacts=artifacts, decision_refs=refs, operation=operation)
    blocker(result, "preparation.operation")
    assert not result.to_dict()["training_authorized"] and not result.to_dict()["evaluation_authorized"]


def test_real_data_context_is_never_processed_even_with_access_permission(tmp_path, monkeypatch):
    data = bundle(accredited=True)
    data["data_kind"] = "official_observed"
    registry = authorization(data, tmp_path)
    monkeypatch.setattr("sigard_ml.official.preparation_pipeline.run_preflight",
                        lambda *args, **kwargs: pytest.fail("Se intentó procesar datos reales"))
    blocker(run_preparation(data, registry=registry), "preparation.fictional_only")


def test_validator_is_called_once_through_preflight_and_after_authorization(tmp_path, monkeypatch):
    import sigard_ml.official.epidemiological_preflight as preflight
    import sigard_ml.official.preparation_pipeline as preparation

    data = bundle(accredited=True)
    artifacts, refs = approvals(data)
    registry = authorization(data, tmp_path)
    calls = []

    def spy(name, function):
        def wrapper(*args, **kwargs):
            calls.append(name)
            return function(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(SourceRegistry, "authorize", spy("authorize", SourceRegistry.authorize))
    monkeypatch.setattr(preparation, "run_preflight", spy("preflight", preparation.run_preflight))
    for name in ("validate_records", "validate_week", "validate_label"):
        monkeypatch.setattr(preflight, name, spy(name, getattr(preflight, name)))
    result = run_preparation(data, registry=registry, artifacts=artifacts, decision_refs=refs)
    assert result.status == "prepared_simulation_only"
    assert calls == ["authorize"] * 3 + ["preflight", "validate_records", "validate_week", "validate_week", "validate_label"]


def test_inputs_models_and_files_are_not_modified_or_opened(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Se intentó IO, entrenamiento o pipeline de datos reales")

    data = bundle(accredited=True)
    artifacts, refs = approvals(data)
    registry = authorization(data, tmp_path)
    before = deepcopy((data, artifacts, refs, registry))
    monkeypatch.setattr("sklearn.ensemble.RandomForestClassifier.fit", forbidden)
    monkeypatch.setattr("sklearn.ensemble.RandomForestRegressor.fit", forbidden)
    monkeypatch.setattr("sigard_ml.official.observed_pipeline.run_observed_pipeline", forbidden)
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.run_preparation", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("pathlib.Path.open", forbidden)
    result = run_preparation(data, registry=registry, artifacts=artifacts, decision_refs=refs)
    assert result.status == "prepared_simulation_only"
    assert (data, artifacts, refs, registry) == before


def test_existing_weekly_preparation_output_is_compatible_without_relabeling(tmp_path):
    data = bundle(accredited=True)
    weeks = pd.DataFrame(data["weeks"])
    for field in ("fecha_inicio_semana", "fecha_fin_semana"):
        weeks[field] = weeks[field].map(date.fromisoformat)
    weeks["registros_fecha_aproximada"] = 0
    before = weeks.copy(deep=True)
    panel = attach_next_week_target(weeks)
    columns = list(data["labels"][0])
    origin = panel.iloc[[0]].copy()
    origin["tipo_etiqueta"] = "cero_heredado_bajo_politica_origen"
    data["labels"] = origin[columns].to_dict("records")
    result = execute(data, tmp_path)
    assert result.status == "prepared_simulation_only"
    assert result.preflight.technical_consistent
    pd.testing.assert_frame_equal(weeks, before)
    assert panel.apto_entrenamiento.eq(False).all()


@pytest.mark.parametrize("flag", ["skip_preflight", "skip_validation", "training_enabled", "prevalidated_results"])
def test_no_bypass_configuration_is_exposed(flag):
    with pytest.raises(TypeError):
        run_preparation(bundle(accredited=True), **{flag: True})
