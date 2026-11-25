"""Read-only administrative audit trail (F6.6). Local administrative API only (127.0.0.1:8767).

Attached exclusively by `alerts_local` (like the predictive viewer); `app.main`, the demo and any
deployment never mount it. One GET route lists, newest first, the events already recorded by:
accounts (`admin_account_audit`), citizen reports (`citizen_report_audit`), preventive content
(`prevention_audit`), internal alerts (`internal_alert_audit`), private viewer queries
(`predictive_view_audit`) and the queries to this trail itself (`admin_audit_view`).

- Each request passes the local guard (loopback client, exact Host and Origin, no forwarded
  headers) before a DB-verified administrator JWT (role, active account, `token_version`).
- Every query is recorded first (actor, time and the filters; never results). If that row cannot
  be written the query fails (closed). By default the list leaves out that «auditoría» category.
- Responses are built from closed lists of allowed fields (allowlists): a field added tomorrow to
  an audit table does not reach the response until it is added here. Free text (report notes and
  public messages, alert comments), content bodies, viewer values, passwords, hashes and tokens
  are never returned; for report and content changes only the names of the changed fields are.
- Dates: `date_from`/`date_to` are days in Argentina time; `date_to` includes the whole day. The
  offset is fixed at UTC−3 (Argentina has no daylight saving time since 2009); the standard
  library has no time-zone database on Windows and no dependency is added for it.
- No route modifies or deletes events.
"""
from datetime import date, datetime, time, timedelta, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, func, insert, literal, select, union_all
from sqlalchemy.orm import Session

from .alert_rules import DISCARD_REASONS
from .database import get_db
from .models import (AdminAccountAudit, CitizenReport, CitizenReportAudit, InternalAlertAudit, PreventionAudit,
                     PreventionSection, User)
from .predictive_admin import AUTHORITY, ORIGIN, audit as viewer_audit, metadata as viewer_metadata
from .schemas import ReportStatus
from .security import get_current_admin

PATH = "/api/v1/admin/audit"
ARGENTINA = timezone(timedelta(hours=-3), "UTC-03:00 (Argentina)")
PAGE_SIZE, MAX_PAGE_SIZE = 25, 100

# Local-only table (own metadata, outside app.main's schema and Alembic): who looked at the trail.
metadata = MetaData()
view_log = Table(
    "admin_audit_view", metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_user_id", Integer, nullable=False),
    Column("filters", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

# Closed lists: categories and their actions.
ACTIONS = {
    "cuentas": ("created", "password_rotated", "deactivated"),
    "reportes": ("view_detail", "export_csv", "update"),
    "contenido": ("seed_import", "create", "update", "publish", "unpublish"),
    "alertas": ("rule_created", "rule_updated", "evaluation_run", "evaluation_no_data", "candidate_approved",
                "candidate_discarded", "citizen_publication_blocked", "candidates_exported"),
    "visor": ("private_query",),
    "auditoria": ("audit_viewed",),
}
DEFAULT_CATEGORIES = tuple(c for c in ACTIONS if c != "auditoria")
# Field names that may be reported as «changed» (never their values, except the report status).
REPORT_FIELDS = ("status", "public_status_message", "internal_notes", "possible_duplicate_of")
REPORT_STATUSES = {status.value for status in ReportStatus}
CONTENT_FIELDS = ("title", "body", "position", "source_label", "source_url")
RULE_FIELDS = ("name", "capability", "model", "radio_ids", "threshold", "consecutive_weeks", "enabled")
FILTER_FIELDS = ("category", "action", "actor_id", "date_from", "date_to", "page", "page_size")


def local_only(request: Request) -> None:
    """Same local criteria as the viewer guard: loopback client, exact Host and Origin."""
    headers = request.headers
    forwarded = any(key.lower().startswith(("forwarded", "x-forwarded", "x-real-ip")) for key in headers)
    local = (request.client is not None and request.client.host == "127.0.0.1" and headers.getlist("host") == [AUTHORITY]
             and request.url.scheme == "http" and not forwarded)
    trusted = headers.getlist("origin") == [ORIGIN] and headers.get("sec-fetch-site") in {None, "same-origin", "same-site"}
    if not (local and trusted):
        raise HTTPException(status_code=403, detail="local_admin_only")


router = APIRouter(prefix=PATH, tags=["admin-audit"], dependencies=[Depends(local_only)])


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ARGENTINA).astimezone(timezone.utc)


def sources():
    """One SELECT per category with the common columns (category, id, actor, action, time)."""
    view_audit_action = literal("private_query")
    return {
        "cuentas": (AdminAccountAudit.id, AdminAccountAudit.actor_user_id, AdminAccountAudit.action, AdminAccountAudit.created_at),
        "reportes": (CitizenReportAudit.id, CitizenReportAudit.actor_user_id, CitizenReportAudit.action, CitizenReportAudit.created_at),
        "contenido": (PreventionAudit.id, PreventionAudit.actor_user_id, PreventionAudit.action, PreventionAudit.created_at),
        "alertas": (InternalAlertAudit.id, InternalAlertAudit.actor_user_id, InternalAlertAudit.action, InternalAlertAudit.created_at),
        "visor": (viewer_audit.c.id, viewer_audit.c.actor_user_id, view_audit_action, viewer_audit.c.created_at),
        "auditoria": (view_log.c.id, view_log.c.actor_user_id, literal("audit_viewed"), view_log.c.created_at),
    }


def text_or_none(value, size=160):
    return value[:size] if isinstance(value, str) and value else None


def changed(before, after, fields):
    before, after = before or {}, after or {}
    return [field for field in fields if field in before or field in after if before.get(field) != after.get(field)]


def details(db: Session, rows):
    """target/summary per event, only from allowed fields."""
    by_category = {}
    for row in rows:
        by_category.setdefault(row.category, []).append(row.id)
    result = {}

    ids = by_category.get("cuentas")
    if ids:
        audits = db.execute(select(AdminAccountAudit.id, User.email).join(User, User.id == AdminAccountAudit.target_user_id)
                            .where(AdminAccountAudit.id.in_(ids))).all()
        for audit_id, email in audits:
            result[("cuentas", audit_id)] = ({"account_email": email}, {})

    ids = by_category.get("reportes")
    if ids:
        audits = db.execute(select(CitizenReportAudit.id, CitizenReportAudit.action, CitizenReportAudit.changes_json,
                                   CitizenReport.tracking_code)
                            .outerjoin(CitizenReport, CitizenReport.id == CitizenReportAudit.report_id)
                            .where(CitizenReportAudit.id.in_(ids))).all()
        for audit_id, action, changes_json, tracking_code in audits:
            try:
                changes = json.loads(changes_json) if changes_json else {}
            except ValueError:
                changes = {}
            changes = changes if isinstance(changes, dict) else {}
            summary = {}
            if action == "update":
                summary["changed_fields"] = [field for field in REPORT_FIELDS if field in changes]
                status = changes.get("status") if isinstance(changes.get("status"), dict) else None
                if status and status.get("from") in REPORT_STATUSES and status.get("to") in REPORT_STATUSES:
                    summary["status_from"], summary["status_to"] = status["from"], status["to"]
            elif action == "export_csv" and isinstance(changes.get("count"), int):
                summary["count"] = changes["count"]
            result[("reportes", audit_id)] = ({"tracking_code": tracking_code} if tracking_code else {}, summary)

    ids = by_category.get("contenido")
    if ids:
        audits = db.execute(select(PreventionAudit.id, PreventionAudit.action, PreventionAudit.before_json,
                                   PreventionAudit.after_json, PreventionSection.slug, PreventionSection.title)
                            .join(PreventionSection, PreventionSection.id == PreventionAudit.section_id)
                            .where(PreventionAudit.id.in_(ids))).all()
        for audit_id, action, before, after, slug, title in audits:
            summary = {}
            if action == "update":
                summary["changed_fields"] = changed(before, after, CONTENT_FIELDS)
            if action == "publish" and isinstance((after or {}).get("version"), int):
                summary["version"] = after["version"]
            result[("contenido", audit_id)] = ({"section_slug": slug, "section_title": text_or_none(title)}, summary)

    ids = by_category.get("alertas")
    if ids:
        for audit in db.scalars(select(InternalAlertAudit).where(InternalAlertAudit.id.in_(ids))):
            before, after = audit.before_json or {}, audit.after_json or {}
            target, summary = {}, {}
            if audit.entity == "rule":
                target["rule_name"] = text_or_none(after.get("name") or before.get("name"), 120)
                if audit.action == "rule_updated":
                    summary["changed_fields"] = changed(before, after, RULE_FIELDS)
            elif audit.entity == "evaluation":
                target["target_week"] = text_or_none(after.get("target_week"), 10)
                if isinstance(after.get("created"), int):
                    summary["created"] = after["created"]
            elif audit.entity == "candidate":
                if audit.entity_id is not None:
                    target["candidate_id"] = audit.entity_id
                if after.get("target_week"):
                    target["target_week"] = text_or_none(after.get("target_week"), 10)
                if after.get("radio_id"):
                    target["radio_id"] = text_or_none(after.get("radio_id"), 20)
                if audit.action in ("candidate_approved", "candidate_discarded"):
                    summary["has_comment"] = bool(after.get("comment"))
                    if after.get("reason") in DISCARD_REASONS:
                        summary["reason"] = after["reason"]
                if audit.action == "candidates_exported" and isinstance(after.get("count"), int):
                    summary["count"] = after["count"]
            result[("alertas", audit.id)] = ({key: value for key, value in target.items() if value is not None}, summary)

    ids = by_category.get("visor")
    if ids:
        for audit_id, route, period, radio in db.execute(select(viewer_audit.c.id, viewer_audit.c.route, viewer_audit.c.period,
                                                                viewer_audit.c.radio).where(viewer_audit.c.id.in_(ids))):
            result[("visor", audit_id)] = ({"route": route, "period": period, **({"radio_id": radio} if radio else {})}, {})

    ids = by_category.get("auditoria")
    if ids:
        for audit_id, filters in db.execute(select(view_log.c.id, view_log.c.filters).where(view_log.c.id.in_(ids))):
            try:
                stored = json.loads(filters)
            except ValueError:
                stored = {}
            result[("auditoria", audit_id)] = ({}, {"filters": {key: stored[key] for key in FILTER_FIELDS if key in stored}})
    return result


@router.get("")
def list_audit(
    request: Request,
    category: str | None = Query(default=None, max_length=20),
    action: str | None = Query(default=None, max_length=40),
    actor_id: int | None = Query(default=None, ge=1),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if category is not None and category not in ACTIONS:
        raise HTTPException(status_code=422, detail="Categoría de auditoría desconocida")
    categories = (category,) if category else DEFAULT_CATEGORIES
    if action is not None and not any(action in ACTIONS[c] for c in categories):
        raise HTTPException(status_code=422, detail="Acción de auditoría desconocida para la categoría elegida")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="La fecha Desde no puede ser posterior a Hasta")

    # The query itself is recorded first (actor, time, filters; never results). Fail closed.
    filters = {key: value for key, value in dict(category=category, action=action, actor_id=actor_id,
                                                   date_from=date_from.isoformat() if date_from else None,
                                                   date_to=date_to.isoformat() if date_to else None,
                                                   page=page, page_size=page_size).items() if value is not None}
    try:
        db.execute(insert(view_log).values(actor_user_id=admin.id, filters=json.dumps(filters, sort_keys=True),
                                           created_at=datetime.now(timezone.utc)))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="No se pudo registrar la consulta de auditoría; no se muestran eventos.") from None

    start = day_start(date_from) if date_from else None
    end = day_start(date_to + timedelta(days=1)) if date_to else None  # date_to includes the whole day
    columns = sources()
    selects = []
    for name in categories:
        if action is not None and action not in ACTIONS[name]:
            continue
        event_id, actor, act, created_at = columns[name]
        query = select(literal(name).label("category"), event_id.label("id"), actor.label("actor_user_id"),
                       act.label("action"), created_at.label("created_at"))
        if action is not None and name not in ("visor", "auditoria"):
            query = query.where(act == action)
        if actor_id is not None:
            query = query.where(actor == actor_id)
        if start is not None:
            query = query.where(created_at >= start)
        if end is not None:
            query = query.where(created_at < end)
        selects.append(query)
    if not selects:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    events = union_all(*selects).subquery() if len(selects) > 1 else selects[0].subquery()
    total = db.scalar(select(func.count()).select_from(events)) or 0
    rows = db.execute(select(events).order_by(events.c.created_at.desc(), events.c.category, events.c.id.desc())
                      .limit(page_size).offset((page - 1) * page_size)).all()
    extra = details(db, rows)
    actors = {user_id: email for user_id, email in db.execute(
        select(User.id, User.email).where(User.id.in_({row.actor_user_id for row in rows if row.actor_user_id is not None})))}
    items = []
    for row in rows:
        target, summary = extra.get((row.category, row.id), ({}, {}))
        items.append({
            "id": f"{row.category}:{row.id}", "category": row.category, "action": row.action,
            "actor": {"id": row.actor_user_id, "email": actors.get(row.actor_user_id)} if row.actor_user_id is not None else None,
            "target": target, "summary": summary, "created_at": utc(row.created_at).isoformat(),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def mount(app):
    """Attach the read-only audit route and its local tables to the local administrative app."""
    viewer_metadata.create_all(app.state.engine)  # private viewer queries (also created by the viewer mount)
    metadata.create_all(app.state.engine)
    app.include_router(router)
