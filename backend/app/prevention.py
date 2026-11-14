"""Institutional preventive content: admin editing, publication and public reading.

Content is general health guidance. It never carries individual epidemiological
records. Bodies accept plain text or a restricted Markdown subset (paragraphs,
"- " lists, **bold** and [text](https://...) links); HTML is rejected, not
rewritten, so what an administrator previews is exactly what is stored.
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from .database import get_db
from .models import PreventionAudit, PreventionSection, User
from .security import get_current_admin


CONTENT_FIELDS = ("slug", "title", "body", "position", "source_label", "source_url")
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
LIMITS = {"title": 120, "body": 4000, "source_label": 200, "source_url": 500}

HTML_TAG = re.compile(r"<\s*[A-Za-z!/?]")
HTML_ENTITY = re.compile(r"&(#\d+|#x[0-9a-f]+|[a-z]+);", re.IGNORECASE)
DANGEROUS_SCHEME = re.compile(r"(javascript|vbscript|data|file):", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DOCUMENT_NUMBER = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}\b|\b\d{7,8}\b")

FIELD_LABELS = {"title": "El título", "body": "El contenido", "source_label": "La fuente", "source_url": "El enlace de la fuente"}


def invalid(message: str) -> HTTPException:
    # Never echo the submitted value: admin validation errors stay content-free.
    return HTTPException(status_code=422, detail=message)


def clean_text(value: str | None, field: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise invalid(f"{FIELD_LABELS[field]} es obligatorio")
        return None
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if field != "body":
        value = " ".join(value.split())
    if not value:
        if required:
            raise invalid(f"{FIELD_LABELS[field]} es obligatorio")
        return None
    label = FIELD_LABELS[field]
    if len(value) > LIMITS[field]:
        raise invalid(f"{label} supera {LIMITS[field]} caracteres")
    if CONTROL.search(value):
        raise invalid(f"{label} contiene caracteres de control no permitidos")
    if HTML_TAG.search(value) or HTML_ENTITY.search(value):
        raise invalid(f"{label} no admite HTML; usá texto o el Markdown permitido")
    if DANGEROUS_SCHEME.search(re.sub(r"\s+", "", value)):
        raise invalid(f"{label} contiene un enlace o esquema no permitido")
    if field == "source_url":
        check_url(value, label)
    else:
        for _text, url in MARKDOWN_LINK.findall(value):
            check_url(url, label)
        if EMAIL.search(value) or DOCUMENT_NUMBER.search(value):
            raise invalid(f"{label} parece incluir datos personales; el contenido preventivo debe ser general")
    return value


def check_url(url: str, label: str) -> None:
    if not re.fullmatch(r"https://[^\s<>\"'`]+", url):
        raise invalid(f"{label} sólo admite enlaces https://")


def snapshot(section: PreventionSection) -> dict:
    return {field: getattr(section, field) for field in CONTENT_FIELDS}


def audit(db: Session, section: PreventionSection, actor: User | None, action: str, before, after) -> None:
    db.add(PreventionAudit(
        section_id=section.id, actor_user_id=actor.id if actor else None,
        action=action, before_json=before, after_json=after,
    ))


class PreventionDraftCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=60, pattern=SLUG_PATTERN)
    title: str = Field(max_length=LIMITS["title"] * 2)
    body: str = Field(max_length=LIMITS["body"] * 2)
    position: int = Field(default=100, ge=0, le=1000)
    source_label: str | None = Field(default=None, max_length=LIMITS["source_label"] * 2)
    source_url: str | None = Field(default=None, max_length=LIMITS["source_url"] * 2)


class PreventionDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=LIMITS["title"] * 2)
    body: str | None = Field(default=None, max_length=LIMITS["body"] * 2)
    position: int | None = Field(default=None, ge=0, le=1000)
    source_label: str | None = Field(default=None, max_length=LIMITS["source_label"] * 2)
    source_url: str | None = Field(default=None, max_length=LIMITS["source_url"] * 2)


class PreventionTransition(BaseModel):
    revision: int = Field(ge=1)


class PreventionSectionAdmin(BaseModel):
    id: int
    slug: str
    title: str
    body: str
    position: int
    source_label: str | None
    source_url: str | None
    status: str
    revision: int
    version: int
    has_pending_changes: bool
    published: dict | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    updated_by: str | None
    published_by: str | None


class PreventionAuditEntry(BaseModel):
    id: int
    action: str
    actor: str
    created_at: datetime
    before: dict | None
    after: dict | None


def emails(db: Session, ids) -> dict[int, str]:
    ids = {value for value in ids if value is not None}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.email).where(User.id.in_(ids))).all())


def admin_view(section: PreventionSection, names: dict[int, str]) -> PreventionSectionAdmin:
    published = section.published_json if section.status == "published" else None
    pending = section.status != "published" or published is None or any(
        published.get(field) != getattr(section, field) for field in CONTENT_FIELDS
    )
    return PreventionSectionAdmin(
        **snapshot(section), id=section.id, status=section.status, revision=section.revision,
        version=section.version, has_pending_changes=pending, published=published,
        created_at=section.created_at, updated_at=section.updated_at, published_at=section.published_at,
        updated_by=names.get(section.updated_by_user_id),
        published_by=names.get(section.published_by_user_id),
    )


def single_view(db: Session, section: PreventionSection) -> PreventionSectionAdmin:
    return admin_view(section, emails(db, [section.updated_by_user_id, section.published_by_user_id]))


def locked_section(db: Session, section_id: int, revision: int) -> PreventionSection:
    section = db.get(PreventionSection, section_id, populate_existing=True)
    if section is None:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    if section.revision != revision:
        raise HTTPException(status_code=409, detail="La sección cambió desde que la abriste. Recargá antes de continuar")
    return section


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(status_code=409, detail="La sección cambió desde que la abriste. Recargá antes de continuar") from None


admin_router = APIRouter(prefix="/api/v1/admin/prevention", tags=["contenido preventivo"])
public_router = APIRouter(prefix="/api/v1/public", tags=["información pública"])


@admin_router.get("", response_model=list[PreventionSectionAdmin])
def list_sections(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    sections = db.scalars(select(PreventionSection).order_by(PreventionSection.position, PreventionSection.id)).all()
    names = emails(db, [value for section in sections for value in (section.updated_by_user_id, section.published_by_user_id)])
    return [admin_view(section, names) for section in sections]


@admin_router.post("", response_model=PreventionSectionAdmin, status_code=201)
def create_draft(payload: PreventionDraftCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if db.scalar(select(PreventionSection.id).where(PreventionSection.slug == payload.slug)) is not None:
        raise HTTPException(status_code=409, detail="Ya existe una sección con ese identificador")
    section = PreventionSection(
        slug=payload.slug,
        title=clean_text(payload.title, "title", required=True),
        body=clean_text(payload.body, "body", required=True),
        position=payload.position,
        source_label=clean_text(payload.source_label, "source_label", required=False),
        source_url=clean_text(payload.source_url, "source_url", required=False),
        status="draft", created_by_user_id=admin.id, updated_by_user_id=admin.id,
    )
    db.add(section)
    db.flush()
    audit(db, section, admin, "create", None, snapshot(section))
    db.commit()
    return single_view(db, section)


@admin_router.patch("/{section_id}", response_model=PreventionSectionAdmin)
def edit_draft(section_id: int, payload: PreventionDraftUpdate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    section = locked_section(db, section_id, payload.revision)
    fields = payload.model_dump(exclude_unset=True, exclude={"revision"})
    if not fields:
        raise invalid("No se informaron cambios")
    before = snapshot(section)
    for field, value in fields.items():
        if field == "position":
            if value is None:
                raise invalid("El orden es obligatorio")
        else:
            value = clean_text(value, field, required=field in ("title", "body"))
        setattr(section, field, value)
    after = snapshot(section)
    if after == before:
        return single_view(db, section)
    section.updated_by_user_id = admin.id
    section.updated_at = datetime.now(timezone.utc)
    audit(db, section, admin, "update", before, after)
    commit_or_conflict(db)
    return single_view(db, section)


@admin_router.post("/{section_id}/publish", response_model=PreventionSectionAdmin)
def publish(section_id: int, payload: PreventionTransition, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    section = locked_section(db, section_id, payload.revision)
    if not section.source_label or not section.source_url:
        raise HTTPException(status_code=422, detail="Indicá la fuente o referencia sanitaria antes de publicar")
    current = snapshot(section)
    previous = section.published_json if section.status == "published" else None
    if previous is not None and all(previous.get(field) == current[field] for field in CONTENT_FIELDS):
        raise HTTPException(status_code=409, detail="No hay cambios pendientes para publicar")
    now = datetime.now(timezone.utc)
    section.version += 1
    section.status = "published"
    section.published_json = {**current, "version": section.version, "published_at": now.isoformat()}
    section.published_at = now
    section.published_by_user_id = admin.id
    section.updated_at = now
    audit(db, section, admin, "publish", previous, section.published_json)
    commit_or_conflict(db)
    return single_view(db, section)


@admin_router.post("/{section_id}/unpublish", response_model=PreventionSectionAdmin)
def unpublish(section_id: int, payload: PreventionTransition, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    section = locked_section(db, section_id, payload.revision)
    if section.status != "published":
        raise HTTPException(status_code=409, detail="La sección no está publicada")
    before = section.published_json
    section.status = "draft"
    section.updated_by_user_id = admin.id
    section.updated_at = datetime.now(timezone.utc)
    audit(db, section, admin, "unpublish", before, None)
    commit_or_conflict(db)
    return single_view(db, section)


@admin_router.get("/{section_id}/history", response_model=list[PreventionAuditEntry])
def history(section_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    if db.get(PreventionSection, section_id) is None:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    entries = db.scalars(
        select(PreventionAudit).where(PreventionAudit.section_id == section_id)
        .order_by(PreventionAudit.created_at.desc(), PreventionAudit.id.desc())
    ).all()
    names = emails(db, [entry.actor_user_id for entry in entries])
    return [PreventionAuditEntry(
        id=entry.id, action=entry.action, created_at=entry.created_at,
        actor=names.get(entry.actor_user_id, "Cuenta administrativa") if entry.actor_user_id else "Carga inicial del sistema",
        before=entry.before_json, after=entry.after_json,
    ) for entry in entries]


@public_router.get("/prevention")
def public_prevention(response: Response, db: Session = Depends(get_db)):
    initialized = (db.scalar(select(func.count(PreventionSection.id))) or 0) > 0
    published = db.scalars(
        select(PreventionSection).where(PreventionSection.status == "published", PreventionSection.published_json.is_not(None))
    ).all()
    sections = sorted(
        ({key: section.published_json[key] for key in (*CONTENT_FIELDS, "version", "published_at")} for section in published),
        key=lambda item: (item["position"], item["slug"]),
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    return {
        "schema_version": "prevention-sections/1",
        "initialized": initialized,
        "content_kind": "general_health_guidance",
        "sections": sections,
    }

