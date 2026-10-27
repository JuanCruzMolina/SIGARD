"""Modalidad experimental con bytes y permisos enteramente ficticios en memoria."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sigard_ml.forecasting.adapter import (
    AdapterRequest, EvidenceDocument, PROVISIONAL_SCHEMA, adapt_derived, load_derived,
)
from sigard_ml.forecasting.contracts import ForecastError, PROVISIONAL_EXPERIMENT, known_count
from sigard_ml.forecasting.dataset import build_dataset
from sigard_ml.forecasting.evaluation import evaluate
from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.prediction import forecast_next_week
from sigard_ml.forecasting.training import predict, run_experiment
from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.calendar_rules import CALENDAR_VERSION
from sigard_ml.official.epidemiological_preflight.evidence import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
REVIEW = date(2026, 10, 24)
START, END = date(2024, 1, 28), date(2024, 5, 26)
VALIDATION, TEST = date(2024, 3, 17), date(2024, 4, 21)


def bundle():
    inputs = fictional_inputs(weeks=25)
    tables = {}
    for component in ("counts", "climate", "territory"):
        tables[component] = json.loads(getattr(inputs, component).to_json(orient="records", date_format="iso"))
        for row in tables[component]:
            row["available_on"] = None  # No disponibilidad histórica ficticiamente acreditada.
            row["source_ref"] = "fictional_" + component
            if component != "territory":
                row["week_start"] = row["week_start"][:10]
                row["partial_week"] = False
            if component == "counts":
                row.update(state="provisional", coverage_complete=False, pending=True,
                           mature=False, label_kind="provisional_record_count")
        if component == "counts":
            tables[component] = [row for row in tables[component] if row["count"] > 0]
    radios = list(inputs.radios) + [f"fictional_empty_{i}" for i in range(253)]
    tables["territory"] += [dict(tables["territory"][0], radio_id=r) for r in radios[3:]]
    return dict(schema_version=PROVISIONAL_SCHEMA, data_kind="epidemiological_provisional_records",
        dataset_version="fictional_provisional_v1", calendar_version=CALENDAR_VERSION,
        count_unit="provisional_record_count", period_start="2023-12-31", period_end="2024-06-16",
        territory_version="la-rioja-46014010-256-v1", target_definition="principal-confirmed-records-1",
        evaluation_mode="retrospective_event_time", radios=radios,
        upstream_sources=[dict(source_id="fictional_source", source_version="fictional_v1",
                               sheet="derived_bundle", subset_ref="fictional_subset")],
        sources={component: dict(source_id="fictional_source", source_version="fictional_v1",
            transformation_version="fictional_transform", provenance_ref="fictional_" + component)
                 for component in ("counts", "climate", "territory", "graph")},
        graph=dict(edges=[list(edge) for edge in inputs.edges], available_on=None, source_ref="fictional_graph"),
        **tables)


def seal(data):
    raw = canonical_bytes(data)
    sha = hashlib.sha256(raw).hexdigest()
    request = AdapterRequest("fictional_bundle", data["dataset_version"], "fictional_subset", sha,
        "fictional_preparation", "fictional_use", REVIEW, mode=PROVISIONAL_EXPERIMENT)
    scope = {key: data[key] for key in ("dataset_version", "calendar_version", "count_unit",
        "period_start", "period_end", "radios", "territory_version", "target_definition", "evaluation_mode", "upstream_sources")}
    documents = {}

    def document(reference, role, **extra):
        value = dict(reference=reference, role=role, data_kind=data["data_kind"], package_sha256=sha,
            scope=scope, status="approved", reviewer_ref="fictional_reviewer",
            basis="Entirely fictional permission for regression testing", rule_version="fictional_1",
            limits="Positive cells only; no epidemiological accreditation", decided_on=REVIEW.isoformat(), **extra)
        content = canonical_bytes(value)
        documents[reference] = EvidenceDocument(content, hashlib.sha256(content).hexdigest())

    document(request.preparation_ref, "provisional_experiment_preparation",
             source_id=request.source_id, subset_ref=request.subset_ref)
    document(request.decision_ref, "provisional_experiment_use", experiment_mode=PROVISIONAL_EXPERIMENT,
        conditional_on_observed_cells=True, production_inference_authorized=False,
        historical_availability_accredited=False, provider_permission_ref="fictional_provider_permission")
    for component, source in data["sources"].items():
        document(source["provenance_ref"], "provenance", component=component, source=source)
    sources = []
    for source_id, version in [("fictional_bundle", data["dataset_version"]), ("fictional_source", "fictional_v1")]:
        sources.append(SourceAuthorization(source_id=source_id, source_version=version,
            path=ROOT / "data/interim/official/fictional_never_open.json", sheets=("derived_bundle",),
            subset_ref="fictional_subset", enabled=True, approved_extract=True,
            uses=frozenset((AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING, AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION)),
            evidence_ref=request.preparation_ref, custodian_ref="fictional_custodian",
            confidentiality_ref="fictional_confidentiality", storage_policy_ref="fictional_storage"))
    return raw, SourceRegistry(tuple(sources)), request, documents


def adapt(data=None):
    raw, registry, request, documents = seal(data or bundle())
    return adapt_derived(raw, registry, request, documents=documents)


def panel(inputs):
    return build_dataset(inputs, start=START, end=END, evaluation_as_of=REVIEW)


@pytest.mark.parametrize("source_index", [0, 1])
@pytest.mark.parametrize("denied", [AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION])
def test_inspection_and_processing_do_not_authorize_training_or_evaluation(source_index, denied):
    raw, registry, request, documents = seal(bundle())
    sources = list(registry.sources)
    sources[source_index] = replace(sources[source_index], uses=sources[source_index].uses - {denied})
    with pytest.raises(AccessDenied):
        adapt_derived(raw, SourceRegistry(tuple(sources)), request, documents=documents)


def test_missing_permission_denies_before_parsing_or_reading(monkeypatch):
    _, registry, request, documents = seal(bundle())
    sources = tuple(replace(s, uses=frozenset((AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING))) for s in registry.sources)
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("Do not read without permission"))
    with pytest.raises(AccessDenied):
        adapt_derived(b"not json", SourceRegistry(sources), request, documents=documents)
    with pytest.raises(AccessDenied):
        load_derived(SourceRegistry(sources), request, documents=documents)


def test_mode_not_implicit_and_documents_cannot_be_missing():
    raw, registry, request, documents = seal(bundle())
    with pytest.raises(ForecastError):
        adapt_derived(raw, registry, replace(request, mode="accredited_episode_preparation"), documents=documents)
    with pytest.raises(ForecastError):
        adapt_derived(raw, registry, request, documents={})


@pytest.mark.parametrize("field,value", [("provider_permission_ref", None),
    ("historical_availability_accredited", True), ("production_inference_authorized", True),
    ("conditional_on_observed_cells", False), ("experiment_mode", "fictional_other_mode")])
def test_use_document_cannot_claim_accreditation_or_production(field, value):
    raw, registry, request, documents = seal(bundle())
    document = json.loads(documents[request.decision_ref].content)
    document[field] = value
    content = canonical_bytes(document)
    documents[request.decision_ref] = EvidenceDocument(content, hashlib.sha256(content).hexdigest())
    with pytest.raises(ForecastError):
        adapt_derived(raw, registry, request, documents=documents)


@pytest.mark.parametrize("change", ["zero", "complete", "mature", "coverage", "duplicate", "revision", "coordinate",
                                    "territory", "unit", "target", "evaluation", "component_permission"])
def test_experiment_never_accredits_or_fills_unknowns(change):
    data = bundle()
    if change == "zero": data["counts"][0]["count"] = 0
    elif change == "complete": data["counts"][0].update(state="complete", label_kind="accredited_episode_count")
    elif change == "mature": data["counts"][0]["mature"] = True
    elif change == "coverage": data["counts"][0]["coverage_complete"] = True
    elif change == "duplicate": data["counts"].append(deepcopy(data["counts"][0]))
    elif change == "revision": data["counts"].append(dict(data["counts"][0], available_on=REVIEW.isoformat()))
    elif change == "coordinate": data["counts"][0]["latitude"] = 0
    elif change == "territory": data["territory_version"] = "fictional_wrong"
    elif change == "unit": data["count_unit"] = "eligible_episode_count"
    elif change == "target": data["target_definition"] = "fictional_other_target"
    elif change == "evaluation": data["evaluation_mode"] = "operational_backtest"
    elif change == "component_permission": data["sources"]["climate"]["source_version"] = "fictional_wrong"
    with pytest.raises(ForecastError):
        adapt(data)


def test_unknown_availability_pending_and_sparse_outcomes_remain_explicit():
    inputs = adapt()
    frame = panel(inputs)
    assert inputs.training_authorized and inputs.counts.pending.all()
    assert not inputs.counts.coverage_complete.any() and not inputs.counts.mature.any()
    assert inputs.counts.available_on.isna().all()
    assert not any(known_count(row) for row in inputs.counts.itertuples())
    assert frame.target_count.isna().any() and frame.target_count.dropna().gt(0).all()
    assert frame.target_available_on.isna().all()
    assert frame.loc[frame.target_count.notna(), "target_state"].eq("observed_provisional_record_count").all()
    assert not inputs.input_evidence["historical_availability_accredited"]


def test_future_outcome_does_not_change_past_features_and_missing_lags_not_zero():
    data = bundle()
    before = panel(adapt(data))
    for row in data["counts"]:
        if date.fromisoformat(row["week_start"]) > TEST:
            row["count"] += 100
    after = panel(adapt(data))
    from sigard_ml.forecasting.dataset import FEATURES
    assert np.allclose(before.loc[before.origin_week.le(TEST), FEATURES],
                       after.loc[after.origin_week.le(TEST), FEATURES], equal_nan=True)
    assert before.cases_lag_1.isna().any() and not before.cases_lag_1.dropna().eq(0).any()


def test_mutation_and_permission_revocation_are_rechecked():
    raw, registry, request, documents = seal(bundle())
    inputs = adapt_derived(raw, registry, request, documents=documents)
    documents.clear()
    with pytest.raises(ForecastError):
        assert inputs.training_authorized
    inputs = adapt()
    inputs.experiment_mode = "fictional_bypass"
    with pytest.raises(ForecastError):
        panel(inputs)


def owner_documents(documents, request, **changes):
    document = json.loads(documents[request.decision_ref].content)
    document.pop("provider_permission_ref")
    document.update(authorization_basis="project_owner_declared_provision",
        project_owner_declaration_ref="fictional_owner_statement", institutionally_signed=False,
        local_experimental_only=True)
    document.update(changes)
    content = canonical_bytes(document)
    documents[request.decision_ref] = EvidenceDocument(content, hashlib.sha256(content).hexdigest())


def test_explicit_owner_declaration_authorizes_local_experiment_without_institutional_signature():
    raw, registry, request, documents = seal(bundle())
    owner_documents(documents, request)
    inputs = adapt_derived(raw, registry, request, documents=documents)
    assert inputs.training_authorized and inputs.evaluation_authorized
    assert inputs.input_evidence["authorization_basis"] == "project_owner_declared_provision"
    assert inputs.input_evidence["authorization_ref"] == "fictional_owner_statement"
    assert not inputs.input_evidence["evidence_refs"]  # No aprobaciones P1–P6 inventadas.
    assert not inputs.input_evidence["production_inference_authorized"]


@pytest.mark.parametrize("changes", [dict(institutionally_signed=True),
    dict(local_experimental_only=False), dict(project_owner_declaration_ref=""),
    dict(provider_permission_ref="fictional_invented_provider")])
def test_owner_declaration_cannot_expand_scope_or_claim_external_signature(changes):
    raw, registry, request, documents = seal(bundle())
    owner_documents(documents, request, **changes)
    with pytest.raises(ForecastError):
        adapt_derived(raw, registry, request, documents=documents)


def test_no_capital_totals_even_if_all_radios_have_observations():
    frame = panel(adapt()).dropna(subset=["target_count"])
    subset = frame.loc[frame.target_week.eq(frame.target_week.min())]
    report = evaluate(subset, subset.target_count, tuple(subset.radio_id), observed_only=True)
    assert report["capital"] is None and all(not row["complete"] for row in report["weekly"])


def test_existing_estimators_train_only_fictional_fixture_and_production_stays_blocked(tmp_path, monkeypatch):
    inputs = adapt()
    result = run_experiment(inputs, start=START, end=END, validation_start=VALIDATION,
                            test_start=TEST, evaluation_as_of=REVIEW)
    assert result.fitted.data_kind == "epidemiological_provisional_records"
    assert result.report["experiment_mode"] == PROVISIONAL_EXPERIMENT
    assert result.report["conditional_on_observed_cells"] and not result.report["production_inference_authorized"]
    assert result.report["poisson_presence_diagnostic"] is None
    assert all(v["territorial"]["n"] > 0 and v["capital"] is None for v in result.report["test"].values())
    assert result.report["rows"]["unknown_outcomes"] > 0
    assert len(result.evaluation_predictions) == result.report["rows"]["test"]
    assert result.evaluation_predictions.target_count.gt(0).all()
    assert set(result.evaluation_predictions) == {"radio_id", "origin_week", "target_week", "target_count",
        "model", "training_radio_mean", "lag_1_or_training_mean"}
    assert max(result.report["observed_partition_weeks"]["train"]) < VALIDATION.isoformat()
    assert max(result.report["observed_partition_weeks"]["validation"]) < TEST.isoformat()
    test = result.panel.loc[result.panel.partition.eq("test") & result.panel.target_count.notna()]
    assert np.isfinite(predict(result.fitted.model, test)).all()
    import joblib
    from sigard_ml.forecasting import artifacts
    monkeypatch.setattr(artifacts, "__file__", str(tmp_path / "ml/src/sigard_ml/forecasting/artifacts.py"))
    output = tmp_path / "ml/artifacts/official/fictional_v1"
    manifest = artifacts.save_experiment(result, output,
        configuration={"artifact_version": "fictional_v1"}, provenance={"fictional": True})
    for name, sha in manifest["outputs_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == sha
    saved = joblib.load(output / "model.private.joblib")
    assert np.array_equal(predict(saved.model, test), result.evaluation_predictions.model)
    with pytest.raises(ForecastError, match="sobrescribir"):
        artifacts.save_experiment(result, output, configuration={}, provenance={})
    with pytest.raises(ForecastError, match="privada"):
        artifacts.save_experiment(result, tmp_path / "frontend/public/fictional_v1", configuration={}, provenance={})
    incomplete = tmp_path / "ml/artifacts/official/fictional_incomplete"
    with pytest.raises(ForecastError, match="versión"):
        artifacts.save_experiment(result, incomplete, configuration={}, provenance={})
    assert not incomplete.exists()
    with pytest.raises(ForecastError, match="Inferencia real deshabilitada"):
        forecast_next_week(result.fitted, inputs, as_of=END + timedelta(days=6))


def test_test_labels_do_not_select_or_fit_the_model():
    data = bundle()
    def run(value):
        return run_experiment(adapt(value), start=START, end=END,
                              validation_start=VALIDATION, test_start=TEST, evaluation_as_of=REVIEW)
    before = run(data)
    for row in data["counts"]:
        if date.fromisoformat(row["week_start"]) > TEST:
            row["count"] += 100
    after = run(data)
    assert before.report["selected"] == after.report["selected"]
    assert before.report["candidates"] == after.report["candidates"]
    assert before.report["model_metadata"]["training_sha256"] == after.report["model_metadata"]["training_sha256"]
    # El paquete cambia de huella, pero los parámetros ajustados no usan el test.
    common = before.panel.loc[before.panel.partition.eq("train")]
    assert np.allclose(predict(before.fitted.model, common), predict(after.fitted.model, common))
