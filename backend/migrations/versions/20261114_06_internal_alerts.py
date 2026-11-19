"""Internal alerts: rules, weekly evaluations, candidates with human review, audit.

Schema only. Candidates have no published state (CHECK): citizen publication of
alerts is outside the prototype scope. Only protected values are stored.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261114_06"
down_revision = "20261114_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internal_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("capability", sa.String(20), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("radio_ids", sa.JSON(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("consecutive_weeks", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("capability IN ('presence', 'quantity')", name="internal_alert_rules_capability_check"),
        sa.CheckConstraint("consecutive_weeks >= 1 AND consecutive_weeks <= 4", name="internal_alert_rules_consecutive_check"),
        sa.CheckConstraint("(capability = 'presence' AND threshold IS NULL) OR (capability = 'quantity' AND threshold >= 5)",
                           name="internal_alert_rules_threshold_check"),
    )
    op.create_table(
        "internal_alert_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_week", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("triggered_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('completed', 'no_data')", name="internal_alert_evaluations_status_check"),
    )
    op.create_index("ix_internal_alert_evaluations_target_week", "internal_alert_evaluations", ["target_week"])
    op.create_table(
        "internal_alert_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("internal_alert_rules.id"), nullable=False),
        sa.Column("rule_revision", sa.Integer(), nullable=False),
        sa.Column("rule_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), sa.ForeignKey("internal_alert_evaluations.id"), nullable=False),
        sa.Column("target_week", sa.Date(), nullable=False),
        sa.Column("radio_id", sa.String(16), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("discard_reason", sa.String(30), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('pending', 'approved_internal', 'discarded')", name="internal_alert_candidates_status_check"),
        sa.CheckConstraint("discard_reason IS NULL OR discard_reason IN ('false_alarm', 'insufficient_context', 'duplicate', 'other')",
                           name="internal_alert_candidates_reason_check"),
        sa.UniqueConstraint("rule_id", "rule_revision", "target_week", "radio_id", name="uq_internal_alert_candidate"),
    )
    op.create_index("ix_internal_alert_candidates_rule_id", "internal_alert_candidates", ["rule_id"])
    op.create_index("ix_internal_alert_candidates_target_week", "internal_alert_candidates", ["target_week"])
    op.create_index("ix_internal_alert_candidates_status", "internal_alert_candidates", ["status"])
    op.create_table(
        "internal_alert_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("entity", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_internal_alert_audit_created_at", "internal_alert_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_internal_alert_audit_created_at", table_name="internal_alert_audit")
    op.drop_table("internal_alert_audit")
    for index in ("status", "target_week", "rule_id"):
        op.drop_index(f"ix_internal_alert_candidates_{index}", table_name="internal_alert_candidates")
    op.drop_table("internal_alert_candidates")
    op.drop_index("ix_internal_alert_evaluations_target_week", table_name="internal_alert_evaluations")
    op.drop_table("internal_alert_evaluations")
    op.drop_table("internal_alert_rules")
