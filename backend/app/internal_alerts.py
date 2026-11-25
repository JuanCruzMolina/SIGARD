"""Module 4 · internal alerts over already integrated predictions, with human approval.

- Channel: internal notifications in the administrator panel only. No email, SMS,
  webhook or citizen publication; publishing is blocked in code and in the schema.
- Periodicity: weekly and manual. The administrator runs the evaluation when the
  weekly data delivery arrives; automation is outside the prototype scope.
- Threshold: chosen by the administrator (minimum 5 expected records), helped by
  the retrospective activation frequency shown before saving.
- Approval: any authenticated administrator; every decision is audited.
- False alarms: consecutive weeks, mandatory human review, no automatic publication.

Exact prediction values never leave the prediction source: candidates, evidence,
previews, history, audit and exports carry `alert_rules.disclose` values only.
"""
import csv
from datetime import date, datetime, timezone
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from .alert_rules import (CITIZEN_PUBLICATION, DISCARD_REASONS, MINIMUM_COUNT, CitizenPublicationBlocked,
                          block_citizen_publication, disclose, disclose_split, meets_threshold, window_outcome)
from .alert_source import SourceUnavailable
from .database import get_db
from .models import InternalAlertAudit, InternalAlertCandidate, InternalAlertEvaluation, InternalAlertRule, User
from .security import get_current_admin

router = APIRouter(prefix="/api/v1/admin/alerts", tags=["alertas internas"])
PREVIEW_LABEL = "Frecuencia de activación en 2021–2024 (reconstrucción retrospectiva; 2024 ya observado)"
POLICY = dict(channel="internal_admin_panel", periodicity="weekly_manual", minimum_count=MINIMUM_COUNT,
              approval="authenticated_administrator", citizen_publication=CITIZEN_PUBLICATION,
              automatic_notifications=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleIn(Strict):
    name: str = Field(min_length=3, max_length=80)
    capability: Literal["presence", "quantity"]
    model: str = Field(min_length=1, max_length=64)
    radio_ids: list[str] | None = Field(default=None, max_length=256)
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    consecutive_weeks: int = Field(default=1, ge=1, le=4)
    enabled: bool = True


class RuleUpdate(RuleIn):
    revision: int = Field(ge=1)


class EvaluateIn(Strict):
    target_week: date


class ApproveIn(Strict):
    revision: int = Field(ge=1)
    comment: str = Field(min_length=3, max_length=1000)


class DiscardIn(Strict):
    revision: int = Field(ge=1)
    reason: Literal[DISCARD_REASONS]
    comment: str = Field(min_length=3, max_length=1000)


def invalid(message, status=422):
    return HTTPException(status_code=status, detail=message)


def source_of(request: Request):
    source = getattr(request.app.state, "alert_source", None)
    if source is None:
        raise invalid("Fuente de predicciones no disponible: las alertas internas se evalúan sólo en el entorno local de investigación.", 503)
    return source


def status_of(source):
    try:
        status = source.status()
        if status["radio_ids"] is None and status["weeks"]:
            source.week(status["weeks"][0]["target_week"])  # fills the common territory
        return status
    except SourceUnavailable:
        raise invalid("API predictiva local no disponible. Iniciá el entorno con npm run dev.", 503) from None


def week_values(source, target_week):
    try:
        return source.week(target_week)
    except SourceUnavailable:
        raise invalid("API predictiva local no disponible. Iniciá el entorno con npm run dev.", 503) from None


def model_of(status, model_id):
    return next((m for m in status["models"] if m["id"] == model_id), None)


def validate_rule(payload: RuleIn, status):
    name = " ".join(payload.name.split())
    if len(name) < 3:
        raise invalid("El nombre debe tener al menos 3 caracteres.")
    model = model_of(status, payload.model)
    if model is None or model["capability"] != payload.capability:
        raise invalid("El modelo elegido no está disponible para esa pregunta.")
    if payload.capability == "presence" and payload.threshold is not None:
        raise invalid("¿Dónde? usa la regla top-k del modelo y no admite umbral.")
    if payload.capability == "quantity" and (payload.threshold is None or not MINIMUM_COUNT <= payload.threshold <= 1000):
        raise invalid(f"¿Cuántos? exige un umbral entre {MINIMUM_COUNT} y 1000 registros esperados (protección de celdas pequeñas).")
    radios = None
    if payload.radio_ids is not None:
        radios = sorted(set(payload.radio_ids))
        if not radios or len(radios) != len(payload.radio_ids):
            raise invalid("Elegí al menos un radio, sin repetir.")
        if any(radio not in status["radio_ids"] for radio in radios):
            raise invalid("Hay radios fuera del territorio común evaluado.")
    return dict(name=name, capability=payload.capability, model=payload.model, radio_ids=radios,
                threshold=payload.threshold, consecutive_weeks=payload.consecutive_weeks, enabled=payload.enabled)


def emails(db, ids):
    ids = {i for i in ids if i is not None}
    return dict(db.execute(select(User.id, User.email).where(User.id.in_(ids))).all()) if ids else {}


def rule_snapshot(rule, status):
    model = model_of(status, rule.model) or {}
    return dict(name=rule.name, capability=rule.capability, model=rule.model, radio_ids=rule.radio_ids,
                threshold=rule.threshold, consecutive_weeks=rule.consecutive_weeks, enabled=rule.enabled,
                k=model.get("rule", {}).get("k"))


def rule_view(rule, names):
    return dict(id=rule.id, name=rule.name, capability=rule.capability, model=rule.model, radio_ids=rule.radio_ids,
                threshold=rule.threshold, consecutive_weeks=rule.consecutive_weeks, enabled=rule.enabled,
                revision=rule.revision, created_by=names.get(rule.created_by_user_id),
                updated_by=names.get(rule.updated_by_user_id), created_at=rule.created_at.isoformat(),
                updated_at=rule.updated_at.isoformat())


def candidate_view(c, names, current_revisions=None):
    current = (current_revisions or {}).get(c.rule_id)
    return dict(id=c.id, status=c.status, rule_id=c.rule_id, rule_revision=c.rule_revision, rule=c.rule_json,
                rule_changed_since=current is not None and current != c.rule_revision,
                evaluation_id=c.evaluation_id, target_week=c.target_week.isoformat(), radio_id=c.radio_id,
                evidence=c.evidence_json, decision_comment=c.decision_comment, discard_reason=c.discard_reason,
                decided_by=names.get(c.decided_by_user_id), decided_at=c.decided_at.isoformat() if c.decided_at else None,
                created_at=c.created_at.isoformat(), revision=c.revision, citizen_publication=CITIZEN_PUBLICATION)


def audit(db, admin, action, entity, entity_id=None, before=None, after=None):
    db.add(InternalAlertAudit(actor_user_id=admin.id, action=action, entity=entity, entity_id=entity_id,
                              before_json=before, after_json=after))


def commit_or_conflict(db):
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise invalid("Otro administrador modificó este elemento. Recargá y revisá los cambios.", 409) from None


# ---- Rule evaluation (shared by preview and weekly evaluation) ---------------------------

def window(status, target_week, n):
    weeks = status["weeks"]
    index = next((i for i, w in enumerate(weeks) if w["target_week"] == target_week), None)
    if index is None or index - n + 1 < 0:
        return None
    sequence = weeks[index - n + 1:index + 1]
    dates = [date.fromisoformat(w["target_week"]) for w in sequence]
    if any((b - a).days != 7 for a, b in zip(dates, dates[1:])):
        return None  # a gap in the calendar is never treated as consecutive
    return sequence


def condition(rule, model, entry, values, radio):
    if values is None or rule["model"] not in entry["models"] or radio not in values:
        return None
    value = values[radio].get(rule["model"]) or {}
    if rule["capability"] == "presence":
        return None if value.get("rank") is None else value["rank"] <= model["rule"]["k"]
    return meets_threshold(value.get("quantity"), rule["threshold"])


def evidence_item(rule, entry, values, radio, met):
    raw = (values or {}).get(radio) or {}
    value = raw.get(rule["model"]) or {}
    item = dict(target_week=entry["target_week"], observed=disclose(raw.get("observed")), met=met)
    if rule["capability"] == "presence":
        item["rank"] = value.get("rank")
    else:
        item["expected"] = disclose(value.get("quantity"))
    return item


def evaluate(source, status, rule, target_week, with_evidence=True):
    """{radio: (outcome, evidence | None, raw observed at target)} for one rule and week."""
    model = model_of(status, rule["model"])
    radios = rule["radio_ids"] or status["radio_ids"]
    sequence = window(status, target_week, rule["consecutive_weeks"]) if model else None
    if sequence is None:
        return {radio: ("insufficient_data", None, None) for radio in radios}
    weeks = [(entry, week_values(source, entry["target_week"])) for entry in sequence]
    result = {}
    for radio in radios:
        conditions = [condition(rule, model, entry, values, radio) for entry, values in weeks]
        outcome = window_outcome(conditions)
        evidence = [evidence_item(rule, e, v, radio, c) for (e, v), c in zip(weeks, conditions)] \
            if with_evidence and outcome == "fired" else None
        observed = ((weeks[-1][1] or {}).get(radio) or {}).get("observed")
        result[radio] = (outcome, evidence, observed)
    return result


# ---- Routes --------------------------------------------------------------------------------

@router.get("/status")
def alerts_status(request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    pending = len(db.scalars(select(InternalAlertCandidate.id).where(InternalAlertCandidate.status == "pending")).all())
    source = getattr(request.app.state, "alert_source", None)
    if source is None:
        return dict(source_available=False, policy=POLICY, pending=pending, preview_label=PREVIEW_LABEL)
    try:
        status = status_of(source)
    except HTTPException as error:
        return dict(source_available=False, reason=error.detail, policy=POLICY, pending=pending, preview_label=PREVIEW_LABEL)
    return dict(source_available=True, fictional=status["fictional"], source_kind=status["kind"], context=status["context"],
                models=status["models"], weeks=status["weeks"], radio_ids=status["radio_ids"], policy=POLICY,
                pending=pending, preview_label=PREVIEW_LABEL)


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    rules = db.scalars(select(InternalAlertRule).order_by(InternalAlertRule.id)).all()
    names = emails(db, [r.created_by_user_id for r in rules] + [r.updated_by_user_id for r in rules])
    return [rule_view(r, names) for r in rules]


@router.post("/rules/preview")
def preview_rule(payload: RuleIn, request: Request, _: User = Depends(get_current_admin)):
    source = source_of(request)
    status = status_of(source)
    rule = validate_rule(payload, status)
    activations, weeks_with, evaluable, with_records, by_year = 0, 0, 0, 0, {}
    for entry in status["weeks"]:
        result = evaluate(source, status, rule, entry["target_week"], with_evidence=False)
        fired = [observed for outcome, _, observed in result.values() if outcome == "fired"]
        if any(outcome != "insufficient_data" for outcome, _, _ in result.values()):
            evaluable += 1
        activations += len(fired)
        weeks_with += bool(fired)
        with_records += sum(1 for observed in fired if observed is not None and observed >= 1)
        year = str(entry["target_year"])
        by_year[year] = by_year.get(year, 0) + len(fired)
    return dict(label=PREVIEW_LABEL, activations=activations, weeks_with_activation=weeks_with,
                evaluable_weeks=evaluable, by_year=by_year,
                with_observed_records=disclose_split(with_records, activations),
                fictional=status["fictional"], minimum_count=MINIMUM_COUNT)


@router.post("/rules", status_code=201)
def create_rule(payload: RuleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    values = validate_rule(payload, status_of(source_of(request)))
    rule = InternalAlertRule(**values, created_by_user_id=admin.id, updated_by_user_id=admin.id)
    db.add(rule)
    db.flush()
    view = rule_view(rule, {admin.id: admin.email})
    audit(db, admin, "rule_created", "rule", rule.id, None, view)
    db.commit()
    return view


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, payload: RuleUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(get_current_admin)):
    values = validate_rule(payload, status_of(source_of(request)))
    rule = db.get(InternalAlertRule, rule_id)
    if rule is None:
        raise invalid("Regla no encontrada.", 404)
    if rule.revision != payload.revision:
        raise invalid("Otro administrador modificó esta regla. Recargá y revisá los cambios.", 409)
    names = emails(db, [rule.created_by_user_id, rule.updated_by_user_id, admin.id])
    before = rule_view(rule, names)
    for key, value in values.items():
        setattr(rule, key, value)
    rule.updated_by_user_id = admin.id
    rule.updated_at = datetime.now(timezone.utc)
    try:
        db.flush()
    except StaleDataError:
        db.rollback()
        raise invalid("Otro administrador modificó esta regla. Recargá y revisá los cambios.", 409) from None
    after = rule_view(rule, names)
    audit(db, admin, "rule_updated", "rule", rule.id, before, after)
    commit_or_conflict(db)
    return after


@router.post("/evaluations")
def run_evaluation(payload: EvaluateIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    source = source_of(request)
    status = status_of(source)
    target = payload.target_week.isoformat()
    context = dict(status["context"], kind=status["kind"], fictional=status["fictional"])
    rules = db.scalars(select(InternalAlertRule).order_by(InternalAlertRule.id)).all()
    if not any(w["target_week"] == target for w in status["weeks"]):
        evaluation = InternalAlertEvaluation(target_week=payload.target_week, status="no_data", source_json=context,
                                             summary_json=dict(rules=[], created=0), triggered_by_user_id=admin.id)
        db.add(evaluation)
        db.flush()
        audit(db, admin, "evaluation_no_data", "evaluation", evaluation.id, None, dict(target_week=target))
        db.commit()
        raise invalid("No hay predicciones disponibles para esa semana; no se generan candidatas.", 409)
    evaluation = InternalAlertEvaluation(target_week=payload.target_week, status="completed", source_json=context,
                                         summary_json={}, triggered_by_user_id=admin.id)
    db.add(evaluation)
    db.flush()
    summary, created = [], []
    for rule in rules:
        if not rule.enabled:
            summary.append(dict(rule_id=rule.id, name=rule.name, enabled=False))
            continue
        snapshot = rule_snapshot(rule, status)
        result = evaluate(source, status, snapshot, target)
        counts = dict(fired=0, created=0, already_existing=0, not_met=0, insufficient_data=0)
        for radio, (outcome, evidence, _) in sorted(result.items()):
            counts[outcome] += 1
            if outcome != "fired":
                continue
            exists = db.scalar(select(InternalAlertCandidate.id).where(
                InternalAlertCandidate.rule_id == rule.id, InternalAlertCandidate.rule_revision == rule.revision,
                InternalAlertCandidate.target_week == payload.target_week, InternalAlertCandidate.radio_id == radio))
            if exists:
                counts["already_existing"] += 1
                continue
            candidate = InternalAlertCandidate(rule_id=rule.id, rule_revision=rule.revision, rule_json=snapshot,
                                               evaluation_id=evaluation.id, target_week=payload.target_week,
                                               radio_id=radio, evidence_json=evidence, status="pending")
            db.add(candidate)
            created.append(candidate)
            counts["created"] += 1
        summary.append(dict(rule_id=rule.id, name=rule.name, enabled=True, **counts))
    evaluation.summary_json = dict(rules=summary, created=len(created))
    db.flush()
    audit(db, admin, "evaluation_run", "evaluation", evaluation.id, None,
          dict(target_week=target, created=len(created), rules=summary))
    db.commit()
    names = {admin.id: admin.email}
    return dict(evaluation=dict(id=evaluation.id, target_week=target, status=evaluation.status,
                                summary=evaluation.summary_json, fictional=status["fictional"]),
                candidates=[candidate_view(c, names) for c in created], notifications_sent=0)


@router.get("/evaluations")
def list_evaluations(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db),
                     _: User = Depends(get_current_admin)):
    rows = db.scalars(select(InternalAlertEvaluation).order_by(InternalAlertEvaluation.id.desc()).limit(limit)).all()
    names = emails(db, [r.triggered_by_user_id for r in rows])
    return [dict(id=r.id, target_week=r.target_week.isoformat(), status=r.status, summary=r.summary_json,
                 triggered_by=names.get(r.triggered_by_user_id), created_at=r.created_at.isoformat()) for r in rows]


def load_candidates(db, status_filter=None):
    query = select(InternalAlertCandidate).order_by(InternalAlertCandidate.target_week.desc(), InternalAlertCandidate.id)
    if status_filter:
        query = query.where(InternalAlertCandidate.status == status_filter)
    return db.scalars(query).all()


def current_revisions(db):
    return dict(db.execute(select(InternalAlertRule.id, InternalAlertRule.revision)).all())


@router.get("/candidates")
def list_candidates(status: Literal["pending", "approved_internal", "discarded"] | None = None,
                    db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = load_candidates(db, status)
    names = emails(db, [c.decided_by_user_id for c in rows])
    revisions = current_revisions(db)
    return [candidate_view(c, names, revisions) for c in rows]


def decide(db, admin, candidate_id, revision, new_status, comment, reason=None):
    candidate = db.get(InternalAlertCandidate, candidate_id)
    if candidate is None:
        raise invalid("Candidata no encontrada.", 404)
    if candidate.revision != revision:
        raise invalid("Otro administrador revisó esta candidata. Recargá la lista.", 409)
    if candidate.status != "pending":
        raise invalid("La candidata ya fue revisada.", 409)
    before = dict(status=candidate.status)
    candidate.status = new_status
    candidate.decision_comment = " ".join(comment.split())
    candidate.discard_reason = reason
    candidate.decided_by_user_id = admin.id
    candidate.decided_at = datetime.now(timezone.utc)
    try:
        db.flush()
    except StaleDataError:
        db.rollback()
        raise invalid("Otro administrador revisó esta candidata. Recargá la lista.", 409) from None
    after = dict(status=new_status, comment=candidate.decision_comment, reason=reason,
                 target_week=candidate.target_week.isoformat(), radio_id=candidate.radio_id, rule_id=candidate.rule_id)
    audit(db, admin, "candidate_approved" if new_status == "approved_internal" else "candidate_discarded",
          "candidate", candidate.id, before, after)
    commit_or_conflict(db)
    return candidate_view(candidate, {admin.id: admin.email}, current_revisions(db))


@router.post("/candidates/{candidate_id}/approve")
def approve(candidate_id: int, payload: ApproveIn, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return decide(db, admin, candidate_id, payload.revision, "approved_internal", payload.comment)


@router.post("/candidates/{candidate_id}/discard")
def discard(candidate_id: int, payload: DiscardIn, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return decide(db, admin, candidate_id, payload.revision, "discarded", payload.comment, payload.reason)


@router.post("/candidates/{candidate_id}/publish")
def publish_to_citizens(candidate_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    """Always refused: citizen publication of alerts is outside the prototype scope."""
    if db.get(InternalAlertCandidate, candidate_id) is None:
        raise invalid("Candidata no encontrada.", 404)
    try:
        block_citizen_publication()
    except CitizenPublicationBlocked as blocked:
        audit(db, admin, "citizen_publication_blocked", "candidate", candidate_id)
        db.commit()
        raise invalid(str(blocked), 409) from None


@router.get("/audit")
def audit_log(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db),
              _: User = Depends(get_current_admin)):
    rows = db.scalars(select(InternalAlertAudit).order_by(InternalAlertAudit.id.desc()).limit(limit)).all()
    names = emails(db, [r.actor_user_id for r in rows])
    return [dict(id=r.id, action=r.action, entity=r.entity, entity_id=r.entity_id, actor=names.get(r.actor_user_id),
                 before=r.before_json, after=r.after_json, created_at=r.created_at.isoformat()) for r in rows]


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@router.get("/candidates/export.csv")
def export_candidates(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = load_candidates(db)
    names = emails(db, [c.decided_by_user_id for c in rows])
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "estado", "semana", "radio", "regla", "pregunta", "modelo", "umbral", "semanas_consecutivas",
                     "esperado_semana", "posicion_semana", "observado_semana", "decidido_por", "decidido", "motivo", "comentario"])
    for c in rows:
        last = c.evidence_json[-1] if c.evidence_json else {}
        writer.writerow([c.id, c.status, c.target_week.isoformat(), c.radio_id, safe_cell(c.rule_json["name"]),
                         c.rule_json["capability"], c.rule_json["model"], c.rule_json["threshold"],
                         c.rule_json["consecutive_weeks"], last.get("expected"), last.get("rank"), last.get("observed"),
                         names.get(c.decided_by_user_id), c.decided_at.isoformat() if c.decided_at else None,
                         c.discard_reason, safe_cell(c.decision_comment)])
    audit(db, admin, "candidates_exported", "candidate", None, None, dict(count=len(rows)))
    db.commit()
    return Response(content=stream.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=sigard-alertas-internas.csv", "Cache-Control": "no-store"})
