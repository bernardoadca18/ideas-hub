"""add explicit duration intent and durable generation runs

Revision ID: 0005_editorial_runs
Revises: 0004_duration_contract
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_editorial_runs"
down_revision: str | None = "0004_duration_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ideias", sa.Column("duration_mode", sa.String(32), nullable=True))
    op.add_column("ideias", sa.Column("duration_target_source", sa.String(32), nullable=True))
    op.create_check_constraint(
        "ck_ideia_duration_mode",
        "ideias",
        "duration_mode IS NULL OR duration_mode IN ('explicit_target','profile_default','content_driven')",
    )
    op.create_table(
        "script_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ideia_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roteiro_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("generation_strategy", sa.String(48), nullable=False),
        sa.Column("strategy_identity", sa.String(64), nullable=False),
        sa.Column("production_profile", sa.String(64), nullable=False),
        sa.Column("duration_mode", sa.String(32), nullable=False),
        sa.Column("duration_target_source", sa.String(32), nullable=False),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("target_words", sa.Integer(), nullable=True),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_dossier", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("continuity_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("call_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_sections", sa.Integer(), nullable=False),
        sa.Column("completed_sections", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ideia_id"], ["ideias.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roteiro_id"], ["roteiros.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_script_generation_runs_ideia_id", "script_generation_runs", ["ideia_id"])
    op.create_index("ix_script_generation_runs_status", "script_generation_runs", ["status"])
    op.create_table(
        "script_generation_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_key", sa.String(64), nullable=False),
        sa.Column("section_order", sa.Integer(), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("section_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("local_validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_identity", sa.String(64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["script_generation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "section_key", name="uq_generation_run_section"),
    )
    op.create_index("ix_script_generation_sections_run_id", "script_generation_sections", ["run_id"])
    op.create_index("ix_script_generation_sections_status", "script_generation_sections", ["status"])


def downgrade() -> None:
    op.drop_index("ix_script_generation_sections_status", table_name="script_generation_sections")
    op.drop_index("ix_script_generation_sections_run_id", table_name="script_generation_sections")
    op.drop_table("script_generation_sections")
    op.drop_index("ix_script_generation_runs_status", table_name="script_generation_runs")
    op.drop_index("ix_script_generation_runs_ideia_id", table_name="script_generation_runs")
    op.drop_table("script_generation_runs")
    op.drop_constraint("ck_ideia_duration_mode", "ideias", type_="check")
    op.drop_column("ideias", "duration_target_source")
    op.drop_column("ideias", "duration_mode")
