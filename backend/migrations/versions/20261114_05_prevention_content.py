"""Editable preventive content with published snapshot and before/after audit.

Schema only. The initial content is loaded with ``python -m app.prevention_seed``
(idempotent by slug), so the migration never reads frontend files.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261114_05"
down_revision = "20261020_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prevention_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_label", sa.String(200), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("published_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'published')", name="prevention_sections_status_check"),
        sa.CheckConstraint("position >= 0 AND position <= 1000", name="prevention_sections_position_check"),
        sa.CheckConstraint("version >= 0", name="prevention_sections_version_check"),
    )
    op.create_index("ix_prevention_sections_status", "prevention_sections", ["status"])
    op.create_table(
        "prevention_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("prevention_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_prevention_audit_section_id", "prevention_audit", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_prevention_audit_section_id", table_name="prevention_audit")
    op.drop_table("prevention_audit")
    op.drop_index("ix_prevention_sections_status", table_name="prevention_sections")
    op.drop_table("prevention_sections")
