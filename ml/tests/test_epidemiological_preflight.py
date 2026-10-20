"""Escenarios íntegramente ficticios y evidencia simulada; no accede a entregas."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json

import pytest

from sigard_ml.official.epidemiological_validator.results import VERSION as VALIDATOR_VERSION
from sigard_ml.official.epidemiological_preflight import (
    ACCREDITED, EXPERIMENTAL, SimulatedArtifact, dataset_digest, run_preflight,
)
from sigard_ml.official.epidemiological_preflight.evidence import REQUIREMENTS, canonical_bytes
from test_epidemiological_validator import record, week, label


def bundle(*, accredited=False, assumed=False):
    row = record()
    if accredited:
        row.update(epidemiological_eligibility_validated=True, classification_evidence_ref="proof:P1",
                   epidemiological_identity_validated=True, identity_evidence_ref="proof:P2",
                   epidemiological_precision_validated=True, spatial_evidence_ref="proof:P5")
    origin = week(raw=1, verified="complete" if accredited else "unknown")
    target = week(verified="complete" if accredited else "unknown", semana_epidemiologica=2,
                  fecha_inicio_semana="2024-01-07", fecha_fin_semana="2024-01-13")
    if accredited:
        origin["verificacion_cobertura_ref"] = target["verificacion_cobertura_ref"] = "proof:P3"
    objective = {"radio_censal": "fictional_radio_a", "fecha_inicio_semana": "2023-12-31",
                 "fecha_inicio_semana_objetivo": "2024-01-07", "apto_entrenamiento": False,
                 "tipo_etiqueta": "cero_heredado_bajo_politica_origen", "objetivo_semana_siguiente": 0,
                 "objetivo_valido": True}
    if assumed:
        objective.update(label(autorizacion_cobertura_ref="decision:experimental"))
    elif not accredited:
        objective.update(tipo_etiqueta="desconocida", objetivo_semana_siguiente=None, objetivo_valido=False)
    result = {"data_kind": "fictional", "dataset_id": "fictional-dataset", "dataset_version": "fictional-v1",
              "records": [row], "weeks": [origin, target], "labels": [objective]}
    return json.loads(canonical_bytes(result))


def artifact(document):
    content = canonical_bytes(document)
    return SimulatedArtifact(content, hashlib.sha256(content).hexdigest())


def approvals(data, *, uses=(EXPERIMENTAL, ACCREDITED)):
    """Sólo fixture: representa al revisor ficticio, no existe en la API productiva."""
    report = run_preflight(data)
    keys = [item.key for item in report.findings if item.result.status in ("advertencia", "pendiente_acreditacion")]
    digest = dataset_digest(data)
    registry, refs = {}, {}
    for requirement in REQUIREMENTS:
        reference = "proof:" + requirement
        registry[reference] = artifact({"reference": reference, "simulation": True, "dataset_sha256": digest,
            "requirement": requirement, "uses": list(uses), "review_state": "reviewed",
            "reviewer_ref": "fictional-reviewer", "basis": "Fictional reviewed evidence for " + requirement})
    for use in uses:
        reference = "decision:experimental" if use == EXPERIMENTAL else "decision:accredited"
        refs[use] = reference
        registry[reference] = artifact({"reference": reference, "simulation": True, "dataset_sha256": digest,
            "use": use, "status": "approved", "reviewer_ref": "fictional-reviewer", "rule_version": "fictional-rule-v1",
            "decided_on": "2026-10-20", "validator_version": VALIDATOR_VERSION,
            "evidence_refs": {requirement: "proof:" + requirement for requirement in REQUIREMENTS},
            "accepted_findings": keys})
    return registry, refs


def assessment(report, use):
    return next(item for item in report.eligibility if item.use == use)


def blocked(report, use, control=None):
    result = assessment(report, use)
    assert result.status == "blocked" and result.blockers
    if control:
        assert any(item.control_id == control for item in result.blockers)


def test_structurally_correct_without_accredited_confirmation_is_not_epidemiologically_eligible():
    data = bundle(accredited=True)
    data["records"][0].update(epidemiological_eligibility_validated=False, classification_evidence_ref=None)
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    blocked(report, ACCREDITED, "eligibility.P1")


def test_unknown_temporal_coverage_blocks_even_with_declared_review():
    data = bundle()
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    for use in (EXPERIMENTAL, ACCREDITED):
        blocked(report, use, "eligibility.coverage")


def test_experimental_negative_without_resolved_authorization_is_blocked():
    report = run_preflight(bundle(assumed=True))
    assert report.technical_consistent and not report.permitted_uses
    blocked(report, EXPERIMENTAL, "decision.scope")
    blocked(report, ACCREDITED, "eligibility.experimental_negative")


def test_missing_reference_dates_are_not_waived_by_approved_simulated_decision():
    data = bundle(accredited=True)
    data["records"][0].update(symptom_onset=None, symptom_onset_status="missing", reference_date=None,
                             week_start=None, week_end=None, epidemiological_year=None, epidemiological_week=None)
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    for use in (EXPERIMENTAL, ACCREDITED):
        blocked(report, use, "eligibility.unresolved")


def test_ambiguous_radio_is_not_assigned_or_waived():
    data = bundle(accredited=True)
    data["records"][0].update(assignment_state="ambiguous", geometry_status="multiple_matches",
                             matching_radios=["fictional_radio_a", "fictional_radio_b"], radio_candidate=None)
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    blocked(report, EXPERIMENTAL, "eligibility.unresolved")
    blocked(report, ACCREDITED, "eligibility.unresolved")
    assert data["records"][0]["radio_candidate"] is None


@pytest.mark.parametrize("requirement", REQUIREMENTS)
def test_missing_evidence_for_any_required_rule_blocks_its_use(requirement):
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    del registry["proof:" + requirement]
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    blocked(report, ACCREDITED, "evidence." + requirement)


def test_explicitly_authorized_experiment_has_only_simulated_retrospective_eligibility():
    data = bundle(assumed=True)
    registry, refs = approvals(data, uses=(EXPERIMENTAL,))
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    assert assessment(report, EXPERIMENTAL).status == "eligible_simulation_only"
    assert report.permitted_uses == ("simulation_retrospective_experimental",)
    blocked(report, ACCREDITED)
    assert report.training_authorized is False and report.evaluation_authorized is False


@pytest.mark.parametrize("action", ["train", "evaluate", "unknown", True])
def test_request_to_train_or_evaluate_is_blocked_even_with_complete_simulated_evidence(action):
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs, requested_action=action)
    assert report.technical_consistent and report.training_authorized is False
    assert not report.permitted_uses
    for use in (EXPERIMENTAL, ACCREDITED):
        blocked(report, use, "execution.disabled")


def test_complete_simulated_evidence_can_pass_the_dry_assessment_but_never_authorizes_real_work():
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    before = deepcopy((data, registry, refs))
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert report.technical_consistent
    assert assessment(report, ACCREDITED).status == "eligible_simulation_only"
    assert len(report.permitted_uses) == 2
    output = report.to_dict()
    assert output["passed_controls"] and output["warnings"] and output["pending_evidence"]
    assert all(item["key"] for item in output["warnings"] + output["pending_evidence"])
    assert output["training_authorized"] is False and output["evaluation_authorized"] is False
    assert (data, registry, refs) == before
    assert report == run_preflight(data, artifacts=registry, decision_refs=refs)


@pytest.mark.parametrize("change", ["hash", "body", "reviewer", "review_state", "scope", "requirement", "uses", "basis", "simulation"])
def test_declared_evidence_is_not_sufficient_without_integrity_scope_and_review(change):
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    original = registry["proof:P1"]
    if change == "hash":
        registry["proof:P1"] = replace(original, sha256="0" * 64)
    elif change == "body":
        registry["proof:P1"] = replace(original, content=b"fictional-tamper")
    else:
        document = json.loads(original.content)
        field, value = {"reviewer": ("reviewer_ref", ""), "scope": ("dataset_sha256", "0" * 64),
                        "review_state": ("review_state", "declared"), "requirement": ("requirement", "P3"),
                        "uses": ("uses", [EXPERIMENTAL]), "basis": ("basis", ""), "simulation": ("simulation", False)}[change]
        document[field] = value
        registry["proof:P1"] = artifact(document)
    blocked(run_preflight(data, artifacts=registry, decision_refs=refs), ACCREDITED, "evidence.P1")


@pytest.mark.parametrize("change", ["scope", "status", "reviewer", "date", "version", "use", "accepted", "missing_rule", "extra_finding"])
def test_decision_must_be_explicit_approved_scoped_and_linked_to_all_rules(change):
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    decision = json.loads(registry[refs[ACCREDITED]].content)
    if change == "missing_rule":
        del decision["evidence_refs"]["P6"]
    else:
        field, value = {"scope": ("dataset_sha256", "wrong"), "status": ("status", "pending"),
                        "reviewer": ("reviewer_ref", ""), "date": ("decided_on", None),
                        "version": ("validator_version", "old"), "use": ("use", EXPERIMENTAL),
                        "accepted": ("accepted_findings", []), "extra_finding": ("accepted_findings", ["unrelated-finding"])}[change]
        decision[field] = value
    registry[refs[ACCREDITED]] = artifact(decision)
    blocked(run_preflight(data, artifacts=registry, decision_refs=refs), ACCREDITED,
            "eligibility.review" if change == "accepted" else "decision.scope")


def test_changed_data_invalidates_previous_simulated_approval():
    data = bundle(accredited=True)
    registry, refs = approvals(data)
    data["dataset_version"] = "fictional-v2"
    blocked(run_preflight(data, artifacts=registry, decision_refs=refs), ACCREDITED, "decision.scope")


@pytest.mark.parametrize("group,field,control", [("records", "classification_evidence_ref", "eligibility.P1"),
    ("records", "identity_evidence_ref", "eligibility.P2"), ("records", "spatial_evidence_ref", "eligibility.P5"),
    ("weeks", "verificacion_cobertura_ref", "eligibility.coverage")])
def test_declared_verifications_must_resolve_to_the_reviewed_evidence_in_both_uses(group, field, control):
    data = bundle(accredited=True)
    data[group][0][field] = "fictional-unresolved-reference"
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    for use in (EXPERIMENTAL, ACCREDITED):
        blocked(report, use, control)


@pytest.mark.parametrize("change", ["ambiguous_week", "horizon", "duplicate_cell", "target_link", "unknown_kind"])
def test_technical_failure_cannot_be_overridden_by_decision(change):
    data = bundle(accredited=True)
    if change == "ambiguous_week":
        data["records"][0]["epidemiological_week"] = 9
    elif change == "horizon":
        data["labels"][0]["fecha_inicio_semana"] = "2024-01-07"
    elif change == "duplicate_cell":
        data["weeks"].append(deepcopy(data["weeks"][0]))
    elif change == "target_link":
        data["labels"][0].update(tipo_etiqueta="positivo_provisional", objetivo_semana_siguiente=1)
    else:
        data["labels"][0]["tipo_etiqueta"] = "invented"
    registry, refs = approvals(data)
    report = run_preflight(data, artifacts=registry, decision_refs=refs)
    assert not report.technical_consistent and not report.permitted_uses
    blocked(report, EXPERIMENTAL, "eligibility.technical")


@pytest.mark.parametrize("payload", [{}, {"data_kind": "fictional"}, [], None])
def test_empty_or_malformed_dataset_cannot_pass_vacuously(payload):
    report = run_preflight(payload)
    assert not report.technical_consistent and not report.permitted_uses


def test_real_data_kind_is_rejected_before_validator_or_evidence_access(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Se intentó procesar datos fuera del alcance ficticio")

    monkeypatch.setattr("sigard_ml.official.epidemiological_preflight.validate_records", forbidden)
    data = bundle(accredited=True)
    data["data_kind"] = "official"
    report = run_preflight(data)
    blocked(report, ACCREDITED, "execution.fictional_only")


def test_no_files_training_or_effective_evaluation_are_invoked(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("El preflight intentó IO o entrenamiento")

    data = bundle(accredited=True)
    registry, refs = approvals(data)
    monkeypatch.setattr("sklearn.ensemble.RandomForestClassifier.fit", forbidden)
    monkeypatch.setattr("sklearn.ensemble.RandomForestRegressor.fit", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("pathlib.Path.open", forbidden)
    assert assessment(run_preflight(data, artifacts=registry, decision_refs=refs), ACCREDITED).status == "eligible_simulation_only"


@pytest.mark.parametrize("payload", [{"bundle": {}}, {"bundle": {"data_kind": "fictional"}}])
def test_cli_reports_blocked_and_never_authorizes_empty_input(monkeypatch, payload):
    from sigard_ml.official.epidemiological_preflight.__main__ import main

    stdout = io.StringIO()
    monkeypatch.setattr("sys.argv", ["preflight"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.stdout", stdout)
    assert main() == 1
    output = json.loads(stdout.getvalue())
    assert not output["training_authorized"] and not output["evaluation_authorized"]
    assert not output["permitted_uses"]


def test_cli_complete_simulation_has_no_effective_authorization(monkeypatch):
    from sigard_ml.official.epidemiological_preflight.__main__ import main

    data = bundle(accredited=True)
    registry, refs = approvals(data)
    payload = {"bundle": data, "decision_refs": refs,
               "artifacts": {key: {"content": item.content.decode("utf-8"), "sha256": item.sha256}
                             for key, item in registry.items()}}
    stdout = io.StringIO()
    monkeypatch.setattr("sys.argv", ["preflight"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.stdout", stdout)
    assert main() == 0
    output = json.loads(stdout.getvalue())
    assert output["permitted_uses"] and not output["training_authorized"]
    assert "fictional-reviewer" not in stdout.getvalue()


@pytest.mark.parametrize("payload,args", [("invalid-json", []), ('{"path":"fictional-private-path"}', []),
    ('{"bundle":{},"artifacts":{"ref":{"content":3}}}', []), ('{"bundle":{}}', ["fictional-private-path"])])
def test_cli_rejects_malformed_input_and_file_arguments_without_echoing_values(monkeypatch, payload, args):
    from sigard_ml.official.epidemiological_preflight.__main__ import main

    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.argv", ["preflight", *args])
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    assert main() == 2
    assert "fictional-private-path" not in stdout.getvalue() + stderr.getvalue()
