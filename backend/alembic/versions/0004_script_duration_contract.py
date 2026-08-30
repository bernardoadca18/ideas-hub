"""add explicit editorial duration target

Revision ID: 0004_duration_contract
Revises: 0003_author_briefing
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_duration_contract"
down_revision: str | None = "0003_author_briefing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ideias", sa.Column("target_duration_seconds", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_ideia_target_duration",
        "ideias",
        "target_duration_seconds IS NULL OR "
        "(target_duration_seconds >= 60 AND target_duration_seconds <= 28800)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ideia_target_duration", "ideias", type_="check")
    op.drop_column("ideias", "target_duration_seconds")
