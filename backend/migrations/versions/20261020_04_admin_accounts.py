"""Versioned admin sessions, normalized email uniqueness and credential-free audit."""

from alembic import op
import sqlalchemy as sa

revision = "20261020_04"
down_revision = "20260924_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    # Existing case/whitespace duplicates must be resolved by an authorized
    # operator before applying. Never merge or modify account records here.
    op.create_index("uq_usuarios_email_normalized", "usuarios", [sa.text("lower(trim(email))")], unique=True)
    op.create_table(
        "admin_account_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("admin_account_audit")
    op.drop_index("uq_usuarios_email_normalized", table_name="usuarios")
    op.drop_column("usuarios", "token_version")
