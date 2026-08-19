import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(32), default="admin")
    active: Mapped[bool] = mapped_column("activo", Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tracking_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    submission_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="recibido", index=True)
    public_status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    possible_duplicate_of: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("citizen_reports.id"), nullable=True
    )
    privacy_notice_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    audits: Mapped[list["CitizenReportAudit"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class CitizenReportAudit(Base):
    __tablename__ = "citizen_report_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("citizen_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    action: Mapped[str] = mapped_column(String(60))
    changes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[CitizenReport | None] = relationship(back_populates="audits")
