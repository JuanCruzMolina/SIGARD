"""Crea reportes ciudadanos anónimos y auditoría administrativa."""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


revision = "20260819_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            email VARCHAR(150) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            rol VARCHAR(20) NOT NULL DEFAULT 'user',
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT usuarios_rol_check CHECK (rol IN ('admin', 'user'))
        )
    """))
    op.create_table(
        "citizen_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tracking_code", sa.String(20), nullable=False),
        sa.Column("submission_key_hash", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            Geometry("POINT", srid=4326, spatial_index=False),
            sa.Computed("ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)", persisted=True),
            nullable=False,
        ),
        sa.Column("address_reference", sa.String(200), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="recibido"),
        sa.Column("public_status_message", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("possible_duplicate_of", sa.String(36), nullable=True),
        sa.Column("privacy_notice_version", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["possible_duplicate_of"], ["citizen_reports.id"]),
        sa.UniqueConstraint("tracking_code"),
        sa.UniqueConstraint("submission_key_hash"),
    )
    op.create_index("ix_citizen_reports_category", "citizen_reports", ["category"])
    op.create_index("ix_citizen_reports_status", "citizen_reports", ["status"])
    op.create_index("ix_citizen_reports_neighborhood", "citizen_reports", ["neighborhood"])
    op.create_index("ix_citizen_reports_created_at", "citizen_reports", ["created_at"])
    op.create_index("ix_citizen_reports_retention_until", "citizen_reports", ["retention_until"])
    op.create_index("ix_citizen_reports_geom", "citizen_reports", ["geom"], postgresql_using="gist")

    op.create_table(
        "citizen_report_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["citizen_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["usuarios.id"]),
    )
    op.create_index("ix_citizen_report_audit_report_id", "citizen_report_audit", ["report_id"])


def downgrade() -> None:
    op.drop_table("citizen_report_audit")
    op.drop_index("ix_citizen_reports_geom", table_name="citizen_reports", postgresql_using="gist")
    op.drop_table("citizen_reports")
