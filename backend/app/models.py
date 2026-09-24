import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortableGeometry(UserDefinedType):
    """PostGIS en ejecución y texto GeoJSON en las pruebas SQLite aisladas."""

    cache_ok = True

    def get_col_spec(self, **_kwargs) -> str:
        return "geometry(GEOMETRY,4326)"


@compiles(PortableGeometry, "sqlite")
def compile_portable_geometry_sqlite(_type, _compiler, **_kwargs) -> str:
    return "TEXT"


class User(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="user")
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
        String(36), ForeignKey("citizen_reports.id", ondelete="SET NULL"), nullable=True
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


class PublicationBatch(Base):
    __tablename__ = "publication_batches"
    __table_args__ = (
        CheckConstraint("status IN ('staged', 'published', 'retired')", name="publication_batches_status_check"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="staged", index=True)
    default_cutoff_date: Mapped[date] = mapped_column(Date, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_evaluation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PublicationWeek(Base):
    __tablename__ = "publication_weeks"

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publication_batches.id", ondelete="CASCADE"), primary_key=True
    )
    cutoff_date: Mapped[date] = mapped_column(Date, primary_key=True)
    target_week_start: Mapped[date] = mapped_column(Date, nullable=False)
    target_week_end: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_label: Mapped[str] = mapped_column(String(40), nullable=False)
    target_week_label: Mapped[str] = mapped_column(String(80), nullable=False)
    has_temporal_prediction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_experimental_spatial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TemporalPrediction(Base):
    __tablename__ = "temporal_predictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "cutoff_date"],
            ["publication_weeks.batch_id", "publication_weeks.cutoff_date"],
            ondelete="CASCADE",
        ),
        CheckConstraint("predicted_cases >= 0", name="temporal_predictions_nonnegative_check"),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cutoff_date: Mapped[date] = mapped_column(Date, primary_key=True)
    target_week_start: Mapped[date] = mapped_column(Date, nullable=False)
    target_week_end: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_cases: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_cases_rounded: Mapped[int] = mapped_column(Integer, nullable=False)
    official_cases: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence_prediction: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence_absolute_error: Mapped[float | None] = mapped_column(Float, nullable=True)


class TerritorialRadio(Base):
    __tablename__ = "territorial_radios"
    __table_args__ = (
        UniqueConstraint("batch_id", "radio_id", name="uq_territorial_radios_batch_radio"),
        CheckConstraint("population >= 0", name="territorial_radios_population_check"),
        CheckConstraint("households >= 0", name="territorial_radios_households_check"),
        CheckConstraint("dwellings >= 0", name="territorial_radios_dwellings_check"),
        CheckConstraint("area_km2 > 0", name="territorial_radios_area_check"),
        CheckConstraint("percentile >= 0 AND percentile <= 100", name="territorial_radios_percentile_check"),
        CheckConstraint(
            "relative_level IN ('very_low', 'low', 'medium', 'high')",
            name="territorial_radios_level_check",
        ),
    )

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publication_batches.id", ondelete="CASCADE"), primary_key=True
    )
    radio_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    population_density: Mapped[float] = mapped_column(Float, nullable=False)
    households: Mapped[int] = mapped_column(Integer, nullable=False)
    dwellings: Mapped[int] = mapped_column(Integer, nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    demographic_residential_component: Mapped[float] = mapped_column(Float, nullable=False)
    density_component: Mapped[float] = mapped_column(Float, nullable=False)
    territorial_context_score: Mapped[float] = mapped_column(Float, nullable=False)
    percentile: Mapped[float] = mapped_column(Float, nullable=False)
    relative_level: Mapped[str] = mapped_column(String(20), nullable=False)
    geom: Mapped[object] = mapped_column(PortableGeometry(), nullable=False)


class ExperimentalSpatialResult(Base):
    __tablename__ = "experimental_spatial_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "cutoff_date"],
            ["publication_weeks.batch_id", "publication_weeks.cutoff_date"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["batch_id", "radio_id"],
            ["territorial_radios.batch_id", "territorial_radios.radio_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("experimental_spatial_score >= 0", name="experimental_spatial_score_check"),
        CheckConstraint("percentile >= 0 AND percentile <= 100", name="experimental_spatial_percentile_check"),
        CheckConstraint(
            "relative_level IN ('very_low', 'low', 'medium', 'high')",
            name="experimental_spatial_level_check",
        ),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cutoff_date: Mapped[date] = mapped_column(Date, primary_key=True)
    radio_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    target_week_start: Mapped[date] = mapped_column(Date, nullable=False)
    target_week_end: Mapped[date] = mapped_column(Date, nullable=False)
    experimental_spatial_score: Mapped[float] = mapped_column(Float, nullable=False)
    percentile: Mapped[float] = mapped_column(Float, nullable=False)
    relative_level: Mapped[str] = mapped_column(String(20), nullable=False)
    synthetic_scenario: Mapped[str] = mapped_column(String(80), nullable=False)
