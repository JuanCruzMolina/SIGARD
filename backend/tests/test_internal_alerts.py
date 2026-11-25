"""Internal alerts (module 4). Generated fictional source only; no private artifacts."""
import csv
from datetime import date, timedelta
import importlib.util
import io
import json
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.alert_rules import PROTECTED, disclose, disclose_split, window_outcome
from app.alert_source import FictionalSource, LocalResearchSource, SourceUnavailable
from app.models import InternalAlertCandidate, User
from test_prevention_content import add_user, auth

API = "/api/v1/admin/alerts"
START = FictionalSource.START


def week(i):
    return (START + timedelta(weeks=i)).isoformat()


@pytest.fixture
def alerts(client):
    client.app.state.alert_source = FictionalSource()
    return client, add_user(client)


def rule(**fields):
    return {"name": "Regla ficticia", "capability": "quantity", "model": "residual_v2", "threshold": 5,
            "consecutive_weeks": 1, "enabled": True, **fields}


def create(client, admin, **fields):
    response = client.post(API + "/rules", headers=auth(admin), json=rule(**fields))
    assert response.status_code == 201, response.text
    return response.json()


def evaluate(client, admin, i):
    return client.post(API + "/evaluations", headers=auth(admin), json={"target_week": week(i)})


def walk(value):
    if isinstance(value, dict):
        for v in value.values(): yield from walk(v)
    elif isinstance(value, list):
        for v in value: yield from walk(v)
    else:
        yield value


def test_shared_rule_logic():
    assert window_outcome([True, True]) == "fired"
    assert window_outcome([True, False]) == "not_met"
    assert window_outcome([True, None]) == "insufficient_data"
    assert window_outcome([]) == "insufficient_data"
    assert [disclose(v) for v in (None, 0, 4.99, 5, 7.456)] == [None, PROTECTED, PROTECTED, 5.0, 7.46]
    assert disclose_split(3, 20) == PROTECTED and disclose_split(18, 20) == PROTECTED and disclose_split(8, 20) == 8


@pytest.mark.parametrize("fields, message", [
    ({"threshold": 4.9}, "umbral entre 5"),
    ({"threshold": None}, "umbral entre 5"),
    ({"capability": "presence", "model": "rf_v2_city_propensity", "threshold": 5}, "no admite umbral"),
    ({"capability": "presence", "model": "residual_v2", "threshold": None}, "no está disponible"),
    ({"model": "unknown_model"}, "no está disponible"),
    ({"radio_ids": ["FX0000001", "FX0000001"]}, "sin repetir"),
    ({"radio_ids": []}, "al menos un radio"),
    ({"radio_ids": ["460140101"]}, "fuera del territorio"),
    ({"name": "   a  "}, "al menos 3"),
])
def test_invalid_rules_are_rejected_with_specific_messages(alerts, fields, message):
    client, admin = alerts
    response = client.post(API + "/rules", headers=auth(admin), json=rule(**fields))
    assert response.status_code == 422 and message in response.json()["detail"]


@pytest.mark.parametrize("fields", [{"consecutive_weeks": 5}, {"consecutive_weeks": 0}, {"threshold": float("inf")},
                                    {"extra": True}, {"capability": "both"}])
def test_schema_validation_rejects_out_of_range_rules(alerts, fields):
    client, admin = alerts
    assert client.post(API + "/rules", headers=auth(admin), json=rule(**fields)).status_code == 422


def test_quantity_threshold_below_five_is_rejected_by_the_database(client):
    admin = add_user(client)
    from app.models import InternalAlertRule
    with client.app.state.SessionLocal() as db:
        db.add(InternalAlertRule(name="x" * 3, capability="quantity", model="m", threshold=4, consecutive_weeks=1,
                                 created_by_user_id=admin.id, updated_by_user_id=admin.id))
        with pytest.raises(IntegrityError):
            db.commit()


def test_consecutive_weeks_fire_and_reset(alerts):
    client, admin = alerts
    one = create(client, admin, name="Una semana", radio_ids=["FX0000002"])
    two = create(client, admin, name="Dos semanas", radio_ids=["FX0000002"], consecutive_weeks=2)
    result = evaluate(client, admin, 4).json()  # FX0000002 expected 6 on even weeks, 1 otherwise
    assert [c["rule_id"] for c in result["candidates"]] == [one["id"]]
    assert evaluate(client, admin, 5).json()["candidates"] == []
    presence = create(client, admin, name="Top-3 tres semanas", capability="presence", model="rf_v2_city_propensity",
                      threshold=None, radio_ids=["FX0000003"], consecutive_weeks=3)
    fired = {i: [c for c in evaluate(client, admin, i).json()["candidates"] if c["rule_id"] == presence["id"]]
             for i in (6, 7, 8, 9)}  # FX0000003 in top-3 only on indexes 5..8
    assert [i for i, c in fired.items() if c] == [7, 8]
    evidence = fired[7][0]["evidence"]
    assert [e["target_week"] for e in evidence] == [week(5), week(6), week(7)]
    assert all(e["met"] and e["rank"] <= 3 and "expected" not in e for e in evidence)
    assert two["id"] not in {c["rule_id"] for c in client.get(API + "/candidates", headers=auth(admin)).json()}


def test_inactive_rule_never_fires_and_reevaluation_does_not_duplicate(alerts):
    client, admin = alerts
    active = create(client, admin, radio_ids=["FX0000001"])
    create(client, admin, name="Inactiva", radio_ids=["FX0000001"], enabled=False)
    first = evaluate(client, admin, 3).json()
    assert [c["rule_id"] for c in first["candidates"]] == [active["id"]]
    assert {"enabled": False}.items() <= first["evaluation"]["summary"]["rules"][1].items()
    again = evaluate(client, admin, 3).json()
    assert again["candidates"] == [] and again["evaluation"]["summary"]["rules"][0]["already_existing"] == 1
    assert first["notifications_sent"] == 0


def test_candidates_only_from_available_predictions(alerts):
    client, admin = alerts
    gap = FictionalSource.ML_GAP
    create(client, admin, radio_ids=["FX0000001"])  # expected >= 8 every week except the ML gap
    create(client, admin, name="Dos semanas", radio_ids=["FX0000001"], consecutive_weeks=2)
    at_gap = evaluate(client, admin, gap).json()
    assert at_gap["candidates"] == [] and all(r["insufficient_data"] == 1 for r in at_gap["evaluation"]["summary"]["rules"])
    after = evaluate(client, admin, gap + 1).json()["evaluation"]["summary"]["rules"]
    assert after[0]["created"] == 1 and after[1]["insufficient_data"] == 1  # window touches the gap
    first = evaluate(client, admin, 0).json()["evaluation"]["summary"]["rules"]
    assert first[1]["insufficient_data"] == 1  # no previous week: never assumed
    response = evaluate(client, admin, 200)
    assert response.status_code == 409 and "no se generan candidatas" in response.json()["detail"]
    actions = [a["action"] for a in client.get(API + "/audit", headers=auth(admin)).json()]
    assert actions[0] == "evaluation_no_data"


def test_values_below_five_are_protected_everywhere(alerts):
    """residual_v2 starts from persistence: an expected value can reveal an observed count."""
    client, admin = alerts
    source = client.app.state.alert_source
    create(client, admin, name="Persistencia", model="count_latest", radio_ids=["FX0000001"], consecutive_weeks=2)
    presence = create(client, admin, name="Top-3", capability="presence", model="rf_v2_city_propensity",
                      threshold=None, radio_ids=["FX0000001"], consecutive_weeks=2)
    quantity = create(client, admin, name="Esperados", radio_ids=["FX0000001", "FX0000002"], consecutive_weeks=1)
    i = 4  # FX0000001 observed 2 at even weeks, 7 at odd ones; expected 8+
    assert source.week(week(i))["FX0000001"]["observed"] == 2
    result = evaluate(client, admin, i).json()
    by_rule = {c["rule_id"]: c for c in result["candidates"] if c["radio_id"] == "FX0000001"}
    assert [e["observed"] for e in by_rule[presence["id"]]["evidence"]] == [7, PROTECTED]
    assert by_rule[quantity["id"]]["evidence"][0] == {"target_week": week(i), "observed": PROTECTED, "met": True, "expected": 9.0}
    # count_latest at i=5 equals the observed count 2 at i=4: must never fire nor leak below 5.
    evaluate(client, admin, 5)
    candidates = client.get(API + "/candidates", headers=auth(admin)).json()
    audit_rows = client.get(API + "/audit", headers=auth(admin)).json()
    export = client.get(API + "/candidates/export.csv", headers=auth(admin)).text
    preview = client.post(API + "/rules/preview", headers=auth(admin),
                          json=rule(radio_ids=["FX0000001", "FX0000002"])).json()
    small = [v for v in walk([candidates, audit_rows, preview]) if isinstance(v, float) and 0 <= v < 5]
    assert small == []
    observed = {e["observed"] for c in candidates for e in c["evidence"]}
    assert observed <= {PROTECTED, 7, None}
    rows = list(csv.DictReader(io.StringIO(export)))
    assert rows and all(r["observado_semana"] in (PROTECTED, "7", "") for r in rows)
    assert all(r["esperado_semana"] in ("", PROTECTED) or float(r["esperado_semana"]) >= 5 for r in rows)
    with client.app.state.SessionLocal() as db:
        stored = json.dumps([c.evidence_json for c in db.scalars(select(InternalAlertCandidate))])
    assert '"observed": 2' not in stored and PROTECTED in stored
    assert preview["label"] == "Frecuencia de activación en 2021–2024 (reconstrucción retrospectiva; 2024 ya observado)"
    assert preview["with_observed_records"] in (PROTECTED,) or preview["with_observed_records"] >= 5


def test_preview_counts_activations_without_saving(alerts):
    client, admin = alerts
    preview = client.post(API + "/rules/preview", headers=auth(admin), json=rule(radio_ids=["FX0000002"])).json()
    # Even weeks of 30 (expected 6), minus the even week without ML predictions.
    assert preview["activations"] == 14 and preview["weeks_with_activation"] == 14
    assert preview["by_year"] == {"2021": 14} and preview["fictional"] is True
    assert client.get(API + "/rules", headers=auth(admin)).json() == []
    two = client.post(API + "/rules/preview", headers=auth(admin), json=rule(radio_ids=["FX0000002"], consecutive_weeks=2)).json()
    assert two["activations"] == 0


def test_approval_and_discard_with_audit_and_stale_protection(alerts):
    client, admin = alerts
    other = add_user(client, "second-admin@example.test")
    create(client, admin, radio_ids=["FX0000001", "FX0000002"])
    a, b = evaluate(client, admin, 2).json()["candidates"]
    assert client.post(f"{API}/candidates/{a['id']}/approve", headers=auth(admin), json={"revision": 1, "comment": "x"}).status_code == 422
    approved = client.post(f"{API}/candidates/{a['id']}/approve", headers=auth(other),
                           json={"revision": a["revision"], "comment": "Revisado con el equipo de terreno"})
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved_internal" and body["decided_by"] == "second-admin@example.test"
    assert client.post(f"{API}/candidates/{a['id']}/discard", headers=auth(admin),
                       json={"revision": body["revision"], "reason": "other", "comment": "tarde"}).status_code == 409
    stale = client.post(f"{API}/candidates/{b['id']}/discard", headers=auth(admin),
                        json={"revision": b["revision"] + 1, "reason": "false_alarm", "comment": "Sin respaldo"})
    assert stale.status_code == 409
    assert client.post(f"{API}/candidates/{b['id']}/discard", headers=auth(admin),
                       json={"revision": b["revision"], "reason": "made_up", "comment": "Sin respaldo"}).status_code == 422
    discarded = client.post(f"{API}/candidates/{b['id']}/discard", headers=auth(admin),
                            json={"revision": b["revision"], "reason": "false_alarm", "comment": "Sin respaldo territorial"}).json()
    assert discarded["status"] == "discarded" and discarded["discard_reason"] == "false_alarm"
    entries = client.get(API + "/audit", headers=auth(admin)).json()
    actions = [(e["action"], e["actor"]) for e in entries]
    assert actions[:4] == [("candidate_discarded", "admin@example.test"), ("candidate_approved", "second-admin@example.test"),
                           ("evaluation_run", "admin@example.test"), ("rule_created", "admin@example.test")]
    assert entries[1]["before"] == {"status": "pending"} and entries[1]["after"]["comment"] == "Revisado con el equipo de terreno"
    assert all(e["created_at"] for e in entries)
    assert client.get(API + "/candidates?status=pending", headers=auth(admin)).json() == []


def test_rule_edit_is_audited_versioned_and_keeps_candidate_snapshot(alerts):
    client, admin = alerts
    created = create(client, admin, radio_ids=["FX0000001"])
    candidate = evaluate(client, admin, 1).json()["candidates"][0]
    edit = client.patch(f"{API}/rules/{created['id']}", headers=auth(admin),
                        json={**rule(radio_ids=["FX0000001"], threshold=9), "revision": created["revision"]})
    assert edit.status_code == 200 and edit.json()["revision"] == 2
    assert client.patch(f"{API}/rules/{created['id']}", headers=auth(admin),
                        json={**rule(threshold=7), "revision": 1}).status_code == 409
    listed = client.get(API + "/candidates", headers=auth(admin)).json()[0]
    assert listed["id"] == candidate["id"] and listed["rule"]["threshold"] == 5 and listed["rule_changed_since"] is True
    entry = client.get(API + "/audit", headers=auth(admin)).json()[0]
    assert entry["action"] == "rule_updated" and entry["before"]["threshold"] == 5 and entry["after"]["threshold"] == 9
    assert client.patch(f"{API}/rules/999", headers=auth(admin), json={**rule(), "revision": 1}).status_code == 404


def test_citizen_publication_is_blocked_in_code_and_schema(alerts):
    client, admin = alerts
    create(client, admin, radio_ids=["FX0000001"])
    candidate = evaluate(client, admin, 1).json()["candidates"][0]
    assert candidate["citizen_publication"] == "blocked_out_of_scope"
    response = client.post(f"{API}/candidates/{candidate['id']}/publish", headers=auth(admin))
    assert response.status_code == 409 and "fuera del alcance" in response.json()["detail"]
    assert client.get(API + "/audit", headers=auth(admin)).json()[0]["action"] == "citizen_publication_blocked"
    with client.app.state.SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE internal_alert_candidates SET status = 'published'"))
            db.commit()
    public_paths = [r.path for r in client.app.routes if "alert" in getattr(r, "path", "")]
    assert public_paths and all(p.startswith("/api/v1/admin/") for p in public_paths)
    status = client.get(API + "/status", headers=auth(admin)).json()
    assert status["policy"]["citizen_publication"] == "blocked_out_of_scope"
    assert status["policy"]["automatic_notifications"] is False and status["policy"]["periodicity"] == "weekly_manual"


@pytest.mark.parametrize("method, path, body", [
    ("get", "/status", None), ("get", "/rules", None), ("post", "/rules", rule()), ("post", "/rules/preview", rule()),
    ("patch", "/rules/1", {**rule(), "revision": 1}), ("post", "/evaluations", {"target_week": "2021-01-03"}),
    ("get", "/evaluations", None), ("get", "/candidates", None), ("post", "/candidates/1/approve", {"revision": 1, "comment": "abc"}),
    ("post", "/candidates/1/discard", {"revision": 1, "reason": "other", "comment": "abc"}),
    ("post", "/candidates/1/publish", None), ("get", "/audit", None), ("get", "/candidates/export.csv", None),
])
def test_every_route_requires_an_authenticated_administrator(alerts, method, path, body):
    client, _ = alerts
    user = add_user(client, "citizen@example.test", role="user")
    kwargs = {"json": body} if body is not None else {}
    assert client.request(method, API + path, **kwargs).status_code == 401
    assert client.request(method, API + path, headers={"Authorization": "Bearer invalid"}, **kwargs).status_code == 401
    assert client.request(method, API + path, headers=auth(user), **kwargs).status_code == 403


def test_without_a_prediction_source_rules_cannot_be_created(client):
    admin = add_user(client)
    status = client.get(API + "/status", headers=auth(admin)).json()
    assert status["source_available"] is False and status["policy"]["channel"] == "internal_admin_panel"
    assert client.post(API + "/rules", headers=auth(admin), json=rule()).status_code == 503
    assert client.post(API + "/evaluations", headers=auth(admin), json={"target_week": "2021-01-03"}).status_code == 503


class FakeService:
    """Records calls; mimics the in-process predictive service contract with fictional rows."""
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def catalog(self):
        self.calls.append(("catalog",))
        if self.fail:
            raise OSError("fictional unavailable bundle")
        return dict(
                training_enabled=False, operational_enabled=False, default_candidates={"presence": "rf_v2_city_propensity", "quantity": "residual_v2"},
                active_methods={"presence": "presence_seasonal", "quantity": "count_latest"},
                experimental_candidates=[
                    dict(id="rf_v2_city_propensity", capability="presence", state="experimental_not_promoted",
                         decision_rule={"type": "top_k", "k": 10}, promotion={"decision": "not_promoted"}),
                    dict(id="rf_A_epi_climate", capability="presence", state="experimental_evaluated",
                         decision_rule={"type": "threshold"}, promotion={"decision": "not_promoted"}),
                    dict(id="residual_v2", capability="quantity", state="experimental_not_promoted",
                         decision_rule={"type": "count_estimate"}, promotion={"decision": "not_promoted"})],
                weeks=[dict(target_year=2021, target_epi_week=1, target_week="2021-01-03", availability_status="available",
                            ml_availability={"rf_v2_city_propensity": "available", "residual_v2": "not_available"}),
                       dict(target_year=2025, target_epi_week=1, target_week="2025-01-05", availability_status="blocked",
                            ml_availability={})],
                **{k: "FICTIONAL" for k in ("dataset_version", "data_policy_version", "campaign_version", "territory_version",
                                            "calendar_version", "module_version")})

    def week(self, year, week, radio=None, mode="presentation"):
        self.calls.append(("week", year, week, radio, mode))
        row = lambda radio, mask: dict(radio_id=radio, common_mask=mask, observed={"quantity": 3}, predicted={"quantity": 2},
                                       ml={"rf_v2_city_propensity": {"topk_rank": 1, "quantity": None},
                                           "residual_v2": {"topk_rank": None, "quantity": 9}},
                                       ml_availability={"rf_v2_city_propensity": "available", "residual_v2": "not_available"})
        return dict(target_week="2021-01-03", dataset_version="FICTIONAL",
                    rows=[row("FX0000001", True), row("FX0000002", False)])


def test_local_research_source_reads_private_mode_and_keeps_only_top_k_and_count_models():
    fake = FakeService()
    source = LocalResearchSource(fake)
    status = source.status()
    assert [m["id"] for m in status["models"]] == ["rf_v2_city_propensity", "residual_v2", "count_latest"]
    assert [m["default"] for m in status["models"]] == [True, True, False]  # v2 by default, as in the viewer
    assert [w["target_week"] for w in status["weeks"]] == ["2021-01-03"]  # 2025 blocked, outside 2021-2024
    assert status["weeks"][0]["models"] == ["rf_v2_city_propensity", "count_latest"]
    values = source.week("2021-01-03")
    assert list(values) == ["FX0000001"]  # outside the common mask never enters
    assert values["FX0000001"]["residual_v2"] == {"rank": None, "quantity": None}  # unavailable stays unknown
    assert fake.calls[-1] == ("week", "2021", "1", None, "private")  # in process, never over HTTP
    source.week("2021-01-03")
    assert len(fake.calls) == 2  # compact process cache
    assert source.kind == "local_predictive_service" and not hasattr(source, "HEADERS")
    with pytest.raises(SourceUnavailable):
        LocalResearchSource(FakeService(fail=True)).status()
    with pytest.raises(SourceUnavailable):
        LocalResearchSource(None).status()  # predictive service not attached


def test_migration_up_down_on_isolated_sqlite(tmp_path):
    path = Path(__file__).parents[1] / "migrations/versions/20261114_06_internal_alerts.py"
    spec = importlib.util.spec_from_file_location("alerts_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261114_05"
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    tables = {"internal_alert_rules", "internal_alert_evaluations", "internal_alert_candidates", "internal_alert_audit"}
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, email VARCHAR(150) NOT NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert tables <= set(inspect(connection).get_table_names())
            migration.downgrade()
            assert not tables & set(inspect(connection).get_table_names())
