"""add durable script revision metadata

Revision ID: 0006_revision_runs
Revises: 0005_editorial_runs
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_revision_runs"
down_revision: str | None = "0005_editorial_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_generation_runs",
        sa.Column(
            "parent_roteiro_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "script_generation_runs",
        sa.Column(
            "generation_intent",
            sa.String(32),
            server_default="initial",
            nullable=False,
        ),
    )
    op.add_column(
        "script_generation_runs",
        sa.Column("revision_feedback", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_generation_run_parent_roteiro",
        "script_generation_runs",
        "roteiros",
        ["parent_roteiro_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_script_generation_runs_parent_roteiro_id",
        "script_generation_runs",
        ["parent_roteiro_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_script_generation_runs_parent_roteiro_id",
        table_name="script_generation_runs",
    )
    op.drop_constraint(
        "fk_generation_run_parent_roteiro",
        "script_generation_runs",
        type_="foreignkey",
    )
    op.drop_column("script_generation_runs", "revision_feedback")
    op.drop_column("script_generation_runs", "generation_intent")
    op.drop_column("script_generation_runs", "parent_roteiro_id")
