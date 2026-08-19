import csv
import io
import json
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import CitizenReport, CitizenReportAudit, User
from .schemas import (
    AdminLogin,
    AdminReportDetail,
    AdminReportPage,
    AdminReportSummary,
    AdminReportUpdate,
    TokenResponse,
)
from .security import create_access_token, get_current_admin, rate_limiter, verify_password


router = APIRouter(prefix="/api/v1/admin", tags=["administración"])


@router.post("/session", response_model=TokenResponse)
def login(
    payload: AdminLogin,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    rate_limiter.check(
        request,
        settings,
        scope="admin-login",
        limit=settings.admin_login_rate_limit,
        identity=payload.email.strip().lower(),
    )
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Rol administrador requerido")
    return TokenResponse(access_token=create_access_token(user, settings))


def filtered_query(
    category: str | None,
    report_status: str | None,
    neighborhood: str | None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    query = select(CitizenReport)
    if category:
        query = query.where(CitizenReport.category == category)
    if report_status:
        query = query.where(CitizenReport.status == report_status)
    if neighborhood:
        query = query.where(CitizenReport.neighborhood.ilike(f"%{neighborhood}%"))
    if date_from:
        query = query.where(CitizenReport.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.where(CitizenReport.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    return query


@router.get("/citizen-reports", response_model=AdminReportPage)
def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    category: str | None = None,
    report_status: str | None = Query(default=None, alias="status"),
    neighborhood: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    base = filtered_query(category, report_status, neighborhood, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(
        base.order_by(CitizenReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return AdminReportPage(
        items=[AdminReportSummary.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/citizen-reports/export.csv")
def export_reports(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    reports = db.scalars(select(CitizenReport).order_by(CitizenReport.created_at.desc())).all()
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "id", "codigo", "categoria", "descripcion", "latitud", "longitud", "referencia",
        "barrio", "estado", "mensaje_publico", "notas_internas", "creado", "actualizado",
    ])
    def safe_cell(value):
        if not isinstance(value, str):
            return value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    for report in reports:
        writer.writerow([
            report.id, report.tracking_code, report.category, safe_cell(report.description), report.latitude,
            report.longitude, safe_cell(report.address_reference), safe_cell(report.neighborhood), report.status,
            safe_cell(report.public_status_message), safe_cell(report.internal_notes), report.created_at.isoformat(),
            report.updated_at.isoformat(),
        ])
    db.add(CitizenReportAudit(actor_user_id=admin.id, action="export_csv", changes_json=json.dumps({"count": len(reports)})))
    db.commit()
    return Response(
        content=stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sigard-reportes.csv", "Cache-Control": "no-store"},
    )


@router.get("/citizen-reports/{report_id}", response_model=AdminReportDetail)
def report_detail(
    report_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    report = db.get(CitizenReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return AdminReportDetail.model_validate(report)


@router.patch("/citizen-reports/{report_id}", response_model=AdminReportDetail)
def update_report(
    report_id: str,
    payload: AdminReportUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    report = db.get(CitizenReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        normalized = value.value if hasattr(value, "value") else value
        if field == "status" and normalized == "derivado" and not settings.municipal_receiver_confirmed:
            raise HTTPException(
                status_code=409,
                detail="No se puede marcar como derivado hasta confirmar un organismo receptor",
            )
        if field == "possible_duplicate_of" and normalized:
            if normalized == report.id or not db.get(CitizenReport, normalized):
                raise HTTPException(status_code=422, detail="El reporte duplicado indicado no es válido")
        previous = getattr(report, field)
        if previous != normalized:
            changes[field] = {"from": previous, "to": normalized}
            setattr(report, field, normalized)
    if changes:
        report.updated_at = datetime.now(timezone.utc)
        db.add(CitizenReportAudit(
            report_id=report.id,
            actor_user_id=admin.id,
            action="update",
            changes_json=json.dumps(changes, ensure_ascii=False),
        ))
        db.commit()
        db.refresh(report)
    return AdminReportDetail.model_validate(report)
