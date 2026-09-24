"""Agrega lotes versionados para publicación epidemiológica."""

from alembic import op
from geoalchemy2 import Geometry
import sqlalchemy as sa


revision = "20260924_03"
down_revision = "20260923_02"
branch_labels = None
depends_on = None


LEVEL_CHECK = "relative_level IN ('very_low', 'low', 'medium', 'high')"


def upgrade() -> None:
    op.create_table(
        "publication_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("input_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="staged"),
        sa.Column("default_cutoff_date", sa.Date(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("model_evaluation_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('staged', 'published', 'retired')",
            name="publication_batches_status_check",
        ),
    )
    op.create_index("ix_publication_batches_status", "publication_batches", ["status"])
    op.create_index(
        "uq_publication_batches_one_published",
        "publication_batches",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "publication_weeks",
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("target_week_start", sa.Date(), nullable=False),
        sa.Column("target_week_end", sa.Date(), nullable=False),
        sa.Column("cutoff_label", sa.String(40), nullable=False),
        sa.Column("target_week_label", sa.String(80), nullable=False),
        sa.Column("has_temporal_prediction", sa.Boolean(), nullable=False),
        sa.Column("has_experimental_spatial", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["publication_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("batch_id", "cutoff_date"),
        sa.CheckConstraint("target_week_start <= target_week_end", name="publication_weeks_date_order_check"),
    )

    op.create_table(
        "temporal_predictions",
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("target_week_start", sa.Date(), nullable=False),
        sa.Column("target_week_end", sa.Date(), nullable=False),
        sa.Column("predicted_cases", sa.Float(), nullable=False),
        sa.Column("predicted_cases_rounded", sa.Integer(), nullable=False),
        sa.Column("official_cases", sa.Float(), nullable=True),
        sa.Column("absolute_error", sa.Float(), nullable=True),
        sa.Column("persistence_prediction", sa.Float(), nullable=True),
        sa.Column("persistence_absolute_error", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id", "cutoff_date"],
            ["publication_weeks.batch_id", "publication_weeks.cutoff_date"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("batch_id", "cutoff_date"),
        sa.CheckConstraint("predicted_cases >= 0", name="temporal_predictions_nonnegative_check"),
    )

    op.create_table(
        "territorial_radios",
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("radio_id", sa.String(32), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False),
        sa.Column("population_density", sa.Float(), nullable=False),
        sa.Column("households", sa.Integer(), nullable=False),
        sa.Column("dwellings", sa.Integer(), nullable=False),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("demographic_residential_component", sa.Float(), nullable=False),
        sa.Column("density_component", sa.Float(), nullable=False),
        sa.Column("territorial_context_score", sa.Float(), nullable=False),
        sa.Column("percentile", sa.Float(), nullable=False),
        sa.Column("relative_level", sa.String(20), nullable=False),
        sa.Column("geom", Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["publication_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("batch_id", "radio_id"),
        sa.CheckConstraint("population >= 0", name="territorial_radios_population_check"),
        sa.CheckConstraint("households >= 0", name="territorial_radios_households_check"),
        sa.CheckConstraint("dwellings >= 0", name="territorial_radios_dwellings_check"),
        sa.CheckConstraint("area_km2 > 0", name="territorial_radios_area_check"),
        sa.CheckConstraint("percentile >= 0 AND percentile <= 100", name="territorial_radios_percentile_check"),
        sa.CheckConstraint(LEVEL_CHECK, name="territorial_radios_level_check"),
    )
    op.create_index("ix_territorial_radios_geom", "territorial_radios", ["geom"], postgresql_using="gist")

    op.create_table(
        "experimental_spatial_results",
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("radio_id", sa.String(32), nullable=False),
        sa.Column("target_week_start", sa.Date(), nullable=False),
        sa.Column("target_week_end", sa.Date(), nullable=False),
        sa.Column("experimental_spatial_score", sa.Float(), nullable=False),
        sa.Column("percentile", sa.Float(), nullable=False),
        sa.Column("relative_level", sa.String(20), nullable=False),
        sa.Column("synthetic_scenario", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "cutoff_date"],
            ["publication_weeks.batch_id", "publication_weeks.cutoff_date"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "radio_id"],
            ["territorial_radios.batch_id", "territorial_radios.radio_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("batch_id", "cutoff_date", "radio_id"),
        sa.CheckConstraint("experimental_spatial_score >= 0", name="experimental_spatial_score_check"),
        sa.CheckConstraint("percentile >= 0 AND percentile <= 100", name="experimental_spatial_percentile_check"),
        sa.CheckConstraint(LEVEL_CHECK, name="experimental_spatial_level_check"),
    )


def downgrade() -> None:
    op.drop_table("experimental_spatial_results")
    op.drop_index("ix_territorial_radios_geom", table_name="territorial_radios", postgresql_using="gist")
    op.drop_table("territorial_radios")
    op.drop_table("temporal_predictions")
    op.drop_table("publication_weeks")
    op.drop_index("uq_publication_batches_one_published", table_name="publication_batches")
    op.drop_index("ix_publication_batches_status", table_name="publication_batches")
    op.drop_table("publication_batches")
