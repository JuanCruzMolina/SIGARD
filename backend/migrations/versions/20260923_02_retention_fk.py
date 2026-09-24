"""Permite purgar un reporte referenciado como posible duplicado."""

from alembic import op


revision = "20260923_02"
down_revision = "20260819_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "citizen_reports_possible_duplicate_of_fkey",
        "citizen_reports",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "citizen_reports_possible_duplicate_of_fkey",
        "citizen_reports",
        "citizen_reports",
        ["possible_duplicate_of"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "citizen_reports_possible_duplicate_of_fkey",
        "citizen_reports",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "citizen_reports_possible_duplicate_of_fkey",
        "citizen_reports",
        "citizen_reports",
        ["possible_duplicate_of"],
        ["id"],
    )
