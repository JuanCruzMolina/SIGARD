import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import CitizenReport
from .schemas import CitizenReportCreate, CitizenReportCreated, PublicReportStatus
from .security import generate_tracking_code, opaque_hash, rate_limiter


router = APIRouter(prefix="/api/v1/citizen-reports", tags=["reportes ciudadanos"])
CITY_BOUNDS = {"south": -29.53, "north": -29.34, "west": -66.98, "east": -66.76}
CONFIRMATION_MESSAGE = (
    "El reporte fue registrado de manera anónima en SIGARD para su revisión. "
    "Esto no significa que haya sido recibido por el Municipio ni garantiza una intervención. "
    "Guardá el código si querés consultar su estado."
)


def inside_city(latitude: float, longitude: float) -> bool:
    return (
        CITY_BOUNDS["south"] <= latitude <= CITY_BOUNDS["north"]
        and CITY_BOUNDS["west"] <= longitude <= CITY_BOUNDS["east"]
    )


def created_response(report: CitizenReport) -> CitizenReportCreated:
    return CitizenReportCreated(
        tracking_code=report.tracking_code,
        status=report.status,
        created_at=report.created_at,
        message=CONFIRMATION_MESSAGE,
    )


def distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius = 6_371_000
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    haversine = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def find_possible_duplicate(db: Session, payload: CitizenReportCreate, now: datetime) -> str | None:
    candidates = db.scalars(
        select(CitizenReport).where(
            CitizenReport.category == payload.category.value,
            CitizenReport.created_at >= now - timedelta(days=7),
            CitizenReport.latitude.between(payload.latitude - 0.002, payload.latitude + 0.002),
            CitizenReport.longitude.between(payload.longitude - 0.002, payload.longitude + 0.002),
        ).order_by(CitizenReport.created_at.desc()).limit(20)
    ).all()
    for candidate in candidates:
        if distance_meters(payload.latitude, payload.longitude, candidate.latitude, candidate.longitude) <= 150:
            return candidate.id
    return None


@router.post("", response_model=CitizenReportCreated, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: CitizenReportCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not inside_city(payload.latitude, payload.longitude):
        raise HTTPException(status_code=422, detail="La ubicación debe estar dentro de la Ciudad de La Rioja")

    submission_hash = opaque_hash(idempotency_key, settings.secret_key) if idempotency_key else None
    if submission_hash:
        existing = db.scalar(
            select(CitizenReport).where(CitizenReport.submission_key_hash == submission_hash)
        )
        if existing:
            return created_response(existing)

    rate_limiter.check(
        request,
        settings,
        scope="citizen-report",
        limit=settings.report_rate_limit,
    )
    now = datetime.now(timezone.utc)
    possible_duplicate_of = find_possible_duplicate(db, payload, now)
    for _ in range(5):
        report = CitizenReport(
            tracking_code=generate_tracking_code(),
            submission_key_hash=submission_hash,
            category=payload.category.value,
            description=payload.description,
            latitude=payload.latitude,
            longitude=payload.longitude,
            address_reference=payload.address_reference or None,
            neighborhood=payload.neighborhood or None,
            status="recibido",
            privacy_notice_version=payload.privacy_notice_version,
            possible_duplicate_of=possible_duplicate_of,
            created_at=now,
            updated_at=now,
            retention_until=now + timedelta(days=settings.report_retention_days),
        )
        db.add(report)
        try:
            db.commit()
            db.refresh(report)
            return created_response(report)
        except IntegrityError:
            db.rollback()
            if submission_hash:
                existing = db.scalar(
                    select(CitizenReport).where(CitizenReport.submission_key_hash == submission_hash)
                )
                if existing:
                    return created_response(existing)
    raise HTTPException(status_code=503, detail="No se pudo generar un código de seguimiento")


@router.get("/status/{tracking_code}", response_model=PublicReportStatus)
def public_status(tracking_code: str, db: Session = Depends(get_db)):
    normalized = tracking_code.strip().upper()
    report = db.scalar(select(CitizenReport).where(CitizenReport.tracking_code == normalized))
    if not report:
        raise HTTPException(status_code=404, detail="No encontramos un reporte con ese código")
    return PublicReportStatus(
        tracking_code=report.tracking_code,
        status=report.status,
        created_at=report.created_at,
        updated_at=report.updated_at,
        public_status_message=report.public_status_message,
    )
