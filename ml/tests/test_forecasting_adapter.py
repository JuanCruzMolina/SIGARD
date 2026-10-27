"""Integración con bytes generados: ninguna fuente, aprobación o caso real.

La condición acreditada se simula para probar denegaciones y el contrato. No
se persisten datasets, entrenan estimadores ni se interpreta cartografía.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from sigard_ml.forecasting.adapter import (
    AdapterRequest, EvidenceDocument, SCHEMA, TABLE_COLUMNS, VARIABLES,
    adapt_derived, load_derived,
)
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.forecasting.dataset import build_dataset
from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.training import FittedCounts, run_experiment, training_labels
from sigard_ml.forecasting.prediction import forecast_for_date, forecast_next_week
from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.calendar_rules import CALENDAR_VERSION
from sigard_ml.official.epidemiological_preflight.evidence import REQUIREMENTS, canonical_bytes
from sigard_ml.official.episodes import PRINCIPAL_EPISODE_POLICY

ORIGIN = date(2024, 1, 28)
REVIEW = date(2024, 4, 1)
ROOT = Path(__file__).resolve().parents[2]


def bundle_fixture():
    inputs = fictional_inputs(weeks=10)
    tables = {}
    for component in TABLE_COLUMNS:
        tables[component] = json.loads(inputs.__getattribute__(component).to_json(orient="records", date_format="iso"))
        for row in tables[component]:
            # Los objetos date se serializan explícitamente con resolución diaria.
            for key in ("week_start", "available_on"):
                if key in row:
                    row[key] = row[key][:10]
            row["source_ref"] = "fictional_" + component
            if component != "territory":
                row["partial_week"] = False
            if component == "counts":
                row["label_kind"] = "accredited_episode_count"
    return dict(schema_version=SCHEMA, data_kind="epidemiological_accredited",
                dataset_version="fictional_derived_v1", calendar_version=CALENDAR_VERSION,
                count_unit="eligible_episode_count", period_start="2023-12-31", period_end="2024-03-03",
                radios=list(inputs.radios), sources={component: dict(source_id="fictional_" + component,
                    source_version="fictional_v1", transformation_version="fictional_transform_v1",
                    provenance_ref="fictional_" + component) for component in VARIABLES},
                graph=dict(edges=[list(edge) for edge in inputs.edges], available_on="2023-12-31",
                           source_ref="fictional_graph"), **tables)


@pytest.mark.parametrize("failure", [None, "excluded_neighbor", "different_territory"])
def test_adapter_accepts_256_fictional_units_only_with_matching_context_and_graph(monkeypatch, failure):
    """Escala del nuevo universo sin cartografía, conteos ni decisiones reales."""
    monkeypatch.setattr("sigard_ml.forecasting.training._fit",
                        lambda *a, **k: pytest.fail("No entrenar en esta comprobación"))
    bundle = bundle_fixture()
    original = bundle["radios"][0]
    radios = [f"fictional_operational_{i:03d}" for i in range(256)]
    bundle["radios"] = radios
    for component in ("counts", "territory"):
        template = [row for row in bundle[component] if row["radio_id"] == original]
        bundle[component] = [dict(row, radio_id=radio) for radio in radios for row in template]
    bundle["graph"]["edges"] = [edge for a, b in zip(radios, radios[1:]) for edge in ([a, b], [b, a])]
    if failure == "excluded_neighbor":
        bundle["graph"]["edges"].extend([[radios[0], "fictional_excluded"], ["fictional_excluded", radios[0]]])
    elif failure == "different_territory":
        bundle["territory"][0]["radio_id"] = "fictional_excluded"
    if failure:
        with pytest.raises(ForecastError):
            adapt(bundle)
    else:
        inputs = adapt(bundle)
        assert len(inputs.radios) == len(panel(inputs)) == 256
        assert len(inputs.edges) == 510
        assert not inputs.training_authorized


def seal(bundle):
    """Crea decisiones ficticias vinculadas a estos bytes, sin leer archivos."""
    content = canonical_bytes(bundle)
    digest = hashlib.sha256(content).hexdigest()
    request = AdapterRequest("fictional_bundle", bundle["dataset_version"], "fictional_subset", digest,
                             "fictional_preparation", "fictional_decision", REVIEW)
    scope = {key: bundle[key] for key in ("dataset_version", "calendar_version", "count_unit", "period_start", "period_end", "radios")}
    documents = {}

    def add(reference, role, **extra):
        document = dict(reference=reference, role=role, data_kind=bundle["data_kind"], package_sha256=digest,
                        scope=scope, status="approved", reviewer_ref="fictional_reviewer", basis="Entirely fictional testing document",
                        rule_version="fictional_rule_v1", limits="Fixture only; no institutional authority",
                        decided_on="2024-04-01", **extra)
        payload = canonical_bytes(document)
        documents[reference] = EvidenceDocument(payload, hashlib.sha256(payload).hexdigest())

    add(request.preparation_ref, "count_preparation", source_id=request.source_id, subset_ref=request.subset_ref)
    add(request.decision_ref, "count_training_eligibility", evidence_refs={key: "fictional_" + key for key in REQUIREMENTS})
    inventory = []
    for component in VARIABLES:
        if component == "graph":
            rows = [bundle[component]]
        else:
            rows = bundle[component]
        for row in rows:
            key = ([row["radio_id"], row["week_start"]] if component == "counts" else
                   [row["week_start"]] if component == "climate" else
                   [row["radio_id"]] if component == "territory" else [])
            through = ((date.fromisoformat(row["week_start"]) + timedelta(days=6)).isoformat()
                       if "week_start" in row else row["available_on"])
            inventory.append(dict(component=component, key=key, available_on=row["available_on"],
                                  variables=list(VARIABLES[component]), observed_through=through, basis_ref="fictional_snapshot_receipt"))
        metadata = bundle["sources"][component]
        add(metadata["provenance_ref"], "provenance", component=component, source=metadata)
    identity_snapshots = []
    for row in bundle["counts"]:
        number = row["count"] if row["count"] is not None else 0
        reviewed = row["state"] == "complete"
        has_review = reviewed and isinstance(number, int) and number > 0
        identity_snapshots.append(dict(key=[row["radio_id"], row["week_start"]], available_on=row["available_on"],
            basis_ref="fictional_P2_scope_review", summary=dict(eligible_records=number,
                independent_episodes=number if reviewed else 0, possible_duplicate_records=0,
                unknown_identity_records=0 if reviewed else number,
                exact_episode_count=number if reviewed or number == 0 else None,
                review_refs=["fictional_episode_decision"] if has_review else [],
                review_available_on=row["available_on"] if has_review else None)))
    for key in REQUIREMENTS:
        extra = ({"snapshots": inventory} if key == "P6" else
                 {"identity_policy_version": PRINCIPAL_EPISODE_POLICY, "identity_snapshots": identity_snapshots} if key == "P2" else {})
        add("fictional_" + key, key, **extra)
    source = SourceAuthorization(request.source_id, request.source_version,
        ROOT / "data/interim/fictional_adapter_test.json", ("derived_bundle",), request.subset_ref,
        approved_extract=True, enabled=True, uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
        evidence_ref=request.preparation_ref, custodian_ref="fictional_custodian", confidentiality_ref="fictional_confidentiality",
        storage_policy_ref="fictional_storage")
    return content, SourceRegistry((source,)), request, documents


def modify_document(documents, ref, change):
    document = json.loads(documents[ref].content)
    change(document)
    content = canonical_bytes(document)
    documents[ref] = EvidenceDocument(content, hashlib.sha256(content).hexdigest())


def adapt(bundle=None):
    content, registry, request, documents = seal(bundle or bundle_fixture())
    return adapt_derived(content, registry, request, documents=documents)


def panel(inputs):
    return build_dataset(inputs, start=ORIGIN, end=ORIGIN, evaluation_as_of=REVIEW)


def test_adapter_to_existing_panel_without_training_or_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No debe leer archivos, ajustar o inferir")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    import sigard_ml.forecasting.training as training
    monkeypatch.setattr(training, "_fit", forbidden)
    monkeypatch.setattr(training, "predict", forbidden)
    inputs = adapt()
    frame = panel(inputs)
    assert len(frame) == 3 and frame.target_count.notna().all()
    assert frame.target_state.eq("complete_accredited").all()
    assert frame.data_kind.eq("epidemiological_accredited").all()
    assert frame.target_unit.eq("eligible_episode_count").all()
    assert frame.target_week.eq(ORIGIN + timedelta(weeks=1)).all()
    assert frame.provenance.iloc[0]["input_evidence"]["package_sha256"] == inputs.input_evidence["package_sha256"]
    assert not inputs.training_authorized
    with pytest.raises(ForecastError, match="Entrenamiento real deshabilitado"):
        run_experiment(inputs, start=ORIGIN, end=ORIGIN, evaluation_as_of=REVIEW,
                       validation_start=ORIGIN, test_start=ORIGIN)
    with pytest.raises(ForecastError, match="Inferencia real deshabilitada"):
        forecast_next_week(object(), inputs, as_of=REVIEW)
    with pytest.raises(ForecastError, match="Inferencia real deshabilitada"):
        forecast_for_date(SimpleNamespace(horizon_weeks=1), inputs, target_date="2024-02-04",
                          as_of=REVIEW, information_cutoff=date(2024, 3, 30))


def test_manual_date_reuses_adapter_snapshots_and_existing_prediction_without_fit():
    bundle = bundle_fixture()
    bundle["data_kind"] = "fictional"
    inputs = adapt(bundle)
    model = SimpleNamespace(predict=lambda frame: [1.0] * len(frame))
    fitted = FittedCounts(model, "fictional_stub", "fictional_stub", date(2024, 1, 20),
                          inputs.radios, inputs.dataset_version, 20261022)
    result = forecast_for_date(fitted, inputs, target_date="2024-02-06", as_of=REVIEW,
                               information_cutoff=date(2024, 3, 30))
    assert result["target_week"] == "2024-02-04"
    assert result["information_cutoff"] == "2024-02-03"
    assert result["expected_capital_count"] == len(inputs.radios)
    assert all(row["provenance"]["input_evidence"]["package_sha256"] == inputs.input_evidence["package_sha256"]
               for row in result["radios"])
    assert not inputs.training_authorized and not result["real_forecast"]


def test_next_week_needs_authorized_history_but_never_future_outcomes():
    bundle = bundle_fixture()
    bundle["data_kind"] = "fictional"
    inputs = adapt(bundle)
    origin, cutoff = date(2024, 3, 3), date(2024, 3, 9)
    with pytest.raises(ForecastError, match="objetivo t\\+1"):
        build_dataset(inputs, start=origin, end=origin, evaluation_as_of=cutoff)
    frame = build_dataset(inputs, start=origin, end=origin, evaluation_as_of=cutoff, include_outcomes=False)
    assert frame.target_count.isna().all() and frame.target_snapshot_available_on.isna().all()
    model = SimpleNamespace(predict=lambda frame: [1.0] * len(frame))
    fitted = FittedCounts(model, "fictional_stub", "fictional_stub", date(2024, 1, 20),
                          inputs.radios, inputs.dataset_version, 20261022)
    result = forecast_for_date(fitted, inputs, target_date="2024-03-11", as_of=date(2024, 3, 10),
                               information_cutoff=cutoff)
    assert result["query_mode"] == "forecast" and result["target_week"] == "2024-03-10"
    # La ruta sin desenlaces tampoco permite ampliar la historia/corte autorizados.
    with pytest.raises(ForecastError, match="período autorizado"):
        build_dataset(inputs, start=date(2024, 3, 10), end=date(2024, 3, 10),
                      evaluation_as_of=date(2024, 3, 16), include_outcomes=False)


@pytest.mark.parametrize("failure", ["missing_policy", "missing_snapshots", "missing_summary", "duplicate",
                                    "wrong_key", "pending_identity", "wrong_count", "late_review",
                                    "missing_refs", "invalid_summary", "patient_field"])
def test_p2_conciliation_cannot_promote_pending_records_to_accredited_counts(failure):
    content, registry, request, documents = seal(bundle_fixture())

    def change(document):
        if failure == "missing_policy": document.pop("identity_policy_version")
        elif failure == "missing_snapshots": document.pop("identity_snapshots")
        else:
            items = document["identity_snapshots"]
            item = next(item for item in items if item["summary"]["independent_episodes"] > 0)
            summary = item["summary"]
            if failure == "missing_summary": item.pop("summary")
            elif failure == "duplicate": items[0] = deepcopy(items[1])
            elif failure == "wrong_key": item["key"][0] = "fictional_foreign_radio"
            elif failure == "pending_identity":
                summary.update(eligible_records=summary["eligible_records"] + 1,
                               unknown_identity_records=1, exact_episode_count=None)
            elif failure == "wrong_count":
                summary.update(independent_episodes=0, exact_episode_count=0)
            elif failure == "late_review": summary["review_available_on"] = REVIEW.isoformat()
            elif failure == "missing_refs": summary["review_refs"] = []
            elif failure == "invalid_summary": summary["eligible_records"] = True
            else: summary["address"] = "fictional_forbidden_field"
    modify_document(documents, "fictional_P2", change)
    with pytest.raises(ForecastError, match="P2|episodios"):
        adapt_derived(content, registry, request, documents=documents)


def test_p2_review_result_connects_as_aggregate_and_unknown_target_is_retained():
    from test_principal_episodes import records, review, keys
    from sigard_ml.official.episodes import episode_count_summary

    bundle = bundle_fixture()
    row = next(row for row in bundle["counts"] if row["week_start"] == "2024-02-04")
    row.update(state="provisional", label_kind="provisional_record_count", count=2, pending=True,
               coverage_complete=False, mature=False)
    content, registry, request, documents = seal(bundle)
    summary = episode_count_summary(review(), record_keys=keys(records()))

    def change(document):
        item = next(item for item in document["identity_snapshots"] if item["key"] == [row["radio_id"], row["week_start"]])
        item["summary"] = summary
    modify_document(documents, "fictional_P2", change)
    inputs = adapt_derived(content, registry, request, documents=documents)
    frame = panel(inputs)
    target = frame.loc[frame.radio_id.eq(row["radio_id"])].iloc[0]
    assert pd.isna(target.target_count) and target.target_input_state == "provisional"
    assert len(training_labels(frame, inputs, REVIEW)) == len(inputs.radios) - 1
    assert not inputs.training_authorized


@pytest.mark.parametrize("state", ["complete", "provisional", "unknown"])
@pytest.mark.parametrize("value", [0, 3])
def test_accredited_zero_positive_provisional_and_unknown_remain_distinct(state, value):
    bundle = bundle_fixture()
    for row in bundle["counts"]:
        if row["week_start"] == "2024-02-04":
            row.update(state=state, count=None if state == "unknown" else value,
                       label_kind={"complete": "accredited_episode_count", "provisional": "provisional_record_count", "unknown": "unknown"}[state])
    inputs = adapt(bundle)
    frame = panel(inputs)
    if state == "complete":
        assert frame.target_count.eq(value).all() and frame.target_presence.eq(int(value > 0)).all()
        assert len(training_labels(frame, inputs, REVIEW)) == 3
    else:
        assert frame.target_count.isna().all() and frame.target_presence.isna().all()
        assert frame.target_input_state.eq(state).all()
        assert training_labels(frame, inputs, REVIEW).empty
    assert len(frame) == 3


@pytest.mark.parametrize("change", ["empty_registry", "disabled", "not_extract", "no_processing", "no_inspection", "wrong_subset", "wrong_version", "missing_evidence"])
def test_permissions_deny_before_interpreting_bytes(change):
    _, registry, request, documents = seal(bundle_fixture())
    source = registry.sources[0]
    if change == "empty_registry":
        registry = SourceRegistry()
    else:
        changes = {"disabled": {"enabled": False}, "not_extract": {"approved_extract": False},
                   "no_processing": {"uses": frozenset({AuthorizedUse.INSPECTION})},
                   "no_inspection": {"uses": frozenset({AuthorizedUse.PROCESSING})},
                   "wrong_subset": {"subset_ref": "fictional_other"}, "wrong_version": {"source_version": "fictional_v2"},
                   "missing_evidence": {"evidence_ref": None}}
        registry = SourceRegistry((replace(source, **changes[change]),))
    with pytest.raises((AccessDenied, ForecastError)):
        adapt_derived(b"unparseable", registry, request, documents=documents)


def test_package_digest_is_pinned_before_parsing():
    content, registry, request, documents = seal(bundle_fixture())
    with pytest.raises(ForecastError, match="Integridad"):
        adapt_derived(content + b" ", registry, request, documents=documents)


@pytest.mark.parametrize("requirement", REQUIREMENTS)
@pytest.mark.parametrize("failure", ["missing", "tampered", "pending", "scope", "late", "no_reviewer", "no_basis", "no_limits", "wrong_digest", "simulation_mixed"])
def test_every_p1_p6_requires_documented_scoped_decision(requirement, failure):
    content, registry, request, documents = seal(bundle_fixture())
    ref = "fictional_" + requirement
    if failure == "missing":
        del documents[ref]
    elif failure == "tampered":
        documents[ref] = replace(documents[ref], content=documents[ref].content + b" ")
    else:
        def change(doc):
            field, value = {"pending": ("status", "pending"), "scope": ("scope", {}),
                "late": ("decided_on", "2024-04-02"), "no_reviewer": ("reviewer_ref", ""),
                "no_basis": ("basis", ""), "no_limits": ("limits", ""), "wrong_digest": ("package_sha256", "0" * 64),
                "simulation_mixed": ("data_kind", "fictional")}[failure]
            doc[field] = value
        modify_document(documents, ref, change)
    with pytest.raises(ForecastError):
        adapt_derived(content, registry, request, documents=documents)


@pytest.mark.parametrize("failure", ["partial_count", "partial_climate", "climate_incomplete", "climate_null", "missing_radio_week", "missing_week", "foreign_radio", "duplicate", "coordinate", "wrong_unit", "wrong_calendar", "monday", "timestamp", "unaccredited", "unknown_nonnull", "zero_uncovered", "zero_pending", "immature", "negative", "fractional", "boolean_count", "infinite", "text_count", "wrong_provenance", "asymmetric_graph", "missing_territory", "future_period", "early_snapshot", "missing_version", "graph_coordinate"])
def test_invalid_derived_inputs_fail_closed(failure):
    bundle = bundle_fixture()
    count = bundle["counts"][0]
    if failure == "partial_count": count["partial_week"] = True
    elif failure == "partial_climate": bundle["climate"][0]["partial_week"] = True
    elif failure == "climate_incomplete": bundle["climate"][0]["complete"] = False
    elif failure == "climate_null": bundle["climate"][0]["temperature"] = None
    elif failure == "missing_radio_week": bundle["counts"].pop()
    elif failure == "missing_week": bundle["climate"].pop()
    elif failure == "foreign_radio": count["radio_id"] = "fictional_foreign"
    elif failure == "duplicate": bundle["counts"].append(deepcopy(count))
    elif failure == "coordinate": count["latitude"] = 0
    elif failure == "wrong_unit": bundle["count_unit"] = "notifications"
    elif failure == "wrong_calendar": bundle["calendar_version"] = "iso"
    elif failure == "monday": count["week_start"] = "2024-01-01"
    elif failure == "timestamp": count["available_on"] += "T00:00:00"
    elif failure == "unaccredited": count["label_kind"] = "provisional_record_count"
    elif failure == "unknown_nonnull": count.update(state="unknown", label_kind="unknown", count=0)
    elif failure == "zero_uncovered": count.update(count=0, coverage_complete=False)
    elif failure == "zero_pending": count.update(count=0, pending=True)
    elif failure == "immature": count["mature"] = False
    elif failure in ("negative", "fractional", "boolean_count", "infinite", "text_count"):
        count["count"] = {"negative": -1, "fractional": 1.5, "boolean_count": True, "infinite": "Infinity", "text_count": "0"}[failure]
    elif failure == "wrong_provenance": count["source_ref"] = "fictional_other"
    elif failure == "asymmetric_graph": bundle["graph"]["edges"].pop()
    elif failure == "missing_territory": bundle["territory"].pop()
    elif failure == "future_period": bundle["period_end"] = "2024-04-07"
    elif failure == "early_snapshot": count["available_on"] = count["week_start"]
    elif failure == "missing_version": bundle["sources"]["counts"]["transformation_version"] = ""
    elif failure == "graph_coordinate": bundle["graph"]["geometry"] = []
    with pytest.raises(ForecastError):
        adapt(bundle)


@pytest.mark.parametrize("failure", ["absent", "early", "future_observation", "variable", "key", "no_basis", "partial_observation"])
def test_p6_binds_each_snapshot_variable_and_effective_availability(failure):
    content, registry, request, documents = seal(bundle_fixture())
    def change(doc):
        items = doc["snapshots"]
        if failure == "absent": items.pop()
        elif failure == "early": items[0]["available_on"] = "2023-12-30"
        elif failure == "future_observation": items[0]["observed_through"] = "2024-01-08"
        elif failure == "variable": items[0]["variables"] = ["future_temperature"]
        elif failure == "key": items[0]["key"][0] = "fictional_foreign"
        elif failure == "no_basis": items[0]["basis_ref"] = ""
        else: items[0]["observed_through"] = "2024-01-05"
    modify_document(documents, "fictional_P6", change)
    with pytest.raises(ForecastError):
        adapt_derived(content, registry, request, documents=documents)


def test_late_revision_does_not_leak_into_features_or_historical_training_labels():
    bundle = bundle_fixture()
    before = panel(adapt(bundle))
    for component in ("counts", "climate", "territory"):
        selected = [row for row in bundle[component] if component == "territory" or row["week_start"] in ("2024-01-21", "2024-02-04")]
        for row in deepcopy(selected):
            row["available_on"] = "2024-03-20"
            row[{"counts": "count", "climate": "temperature", "territory": "population"}[component]] = 999
            bundle[component].append(row)
    inputs = adapt(bundle)
    after = panel(inputs)
    from sigard_ml.forecasting.training import matrix
    pd.testing.assert_frame_equal(matrix(before), matrix(after))
    assert after.target_count.eq(999).all()
    historical = training_labels(after, inputs, date(2024, 2, 20))
    assert historical.target_count.tolist() == before.target_count.tolist()


@pytest.mark.parametrize("provisional", [False, True])
def test_consolidated_export_is_not_historical_availability(provisional):
    """Snapshot ficticio tardío: extracción no retrodata features ni acredita etiquetas."""
    extracted = date(2026, 8, 26)
    bundle = bundle_fixture()
    for component in TABLE_COLUMNS:
        for row in bundle[component]:
            row["available_on"] = extracted.isoformat()
            if component == "counts" and provisional:
                row.update(state="provisional", label_kind="provisional_record_count",
                           coverage_complete=False, pending=True, mature=False)
    bundle["graph"]["available_on"] = extracted.isoformat()
    content, registry, request, documents = seal(bundle)
    request = replace(request, review_as_of=extracted)
    for ref in documents:
        modify_document(documents, ref, lambda doc: doc.update(decided_on=extracted.isoformat()))
    inputs = adapt_derived(content, registry, request, documents=documents)

    historical = panel(inputs)
    consolidated = build_dataset(inputs, start=ORIGIN, end=ORIGIN, evaluation_as_of=extracted)
    for frame in (historical, consolidated):
        assert frame.cases_lag_1.isna().all() and frame.cases_mean_4.isna().all()
        assert frame.temperature_lag_1.isna().all() and frame.population.isna().all()
        assert frame.neighbor_count.isna().all()
    assert historical.target_count.isna().all()
    assert historical.target_input_state.eq("missing_snapshot").all()
    assert consolidated.target_snapshot_available_on.eq(extracted).all()
    if provisional:
        assert consolidated.target_count.isna().all()
    else:
        assert consolidated.target_count.notna().all()
    assert training_labels(consolidated, inputs, REVIEW).target_count.isna().all()
    assert not inputs.training_authorized


@pytest.mark.parametrize("component", ["counts", "climate", "territory", "graph", "metadata", "document", "decision", "provenance"])
def test_mutation_after_validation_cannot_bypass_integrity(component):
    content, registry, request, documents = seal(bundle_fixture())
    inputs = adapt_derived(content, registry, request, documents=documents)
    if component in TABLE_COLUMNS:
        inputs.__getattribute__(component).loc[0, "source_ref"] = "fictional_changed"
    elif component == "graph": inputs.edges = ()
    elif component == "metadata": inputs.input_evidence["package_sha256"] = "0" * 64
    else:
        ref = {"document": "fictional_P1", "decision": "fictional_decision", "provenance": "fictional_climate"}[component]
        modify_document(documents, ref, lambda doc: doc.update(status="revoked"))
    with pytest.raises(ForecastError):
        panel(inputs)


@pytest.mark.parametrize("start,end,freeze", [(date(2024, 1, 21), ORIGIN, REVIEW), (ORIGIN, date(2024, 3, 3), REVIEW), (ORIGIN, ORIGIN, date(2024, 4, 2))])
def test_panel_cannot_exceed_authorized_period_or_freeze(start, end, freeze):
    with pytest.raises(ForecastError):
        build_dataset(adapt(), start=start, end=end, evaluation_as_of=freeze)


def test_only_exact_approved_derived_path_can_be_read(monkeypatch):
    content, registry, request, documents = seal(bundle_fixture())
    reads = []
    monkeypatch.setattr(Path, "stat", lambda self, **kwargs: SimpleNamespace(st_size=len(content)))
    monkeypatch.setattr(Path, "read_bytes", lambda self: reads.append(self) or content)
    inputs = load_derived(registry, request, documents=documents)
    assert reads == [registry.sources[0].path] and len(panel(inputs)) == 3
    for path in (ROOT / "data/raw/fictional.json", ROOT / "data/interim/fictional.xlsx", ROOT / "ml/fictional.json"):
        other = SourceRegistry((replace(registry.sources[0], path=path),))
        with pytest.raises(ForecastError):
            load_derived(other, request, documents=documents)
    assert len(reads) == 1


@pytest.mark.parametrize("raw", [b'{"duplicate":1,"duplicate":2}', b'{"value":NaN}', b'{"value":Infinity}', b'[]', b'{}'])
def test_malformed_json_is_rejected_even_if_digest_matches(raw):
    _, registry, request, documents = seal(bundle_fixture())
    request = replace(request, package_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ForecastError):
        adapt_derived(raw, registry, request, documents=documents)
