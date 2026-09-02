"""add review_state to script_generation_sections

Revision ID: 0007_review_state
Revises: 0006_revision_runs
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_review_state"
down_revision: str | None = "0006_revision_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_generation_sections",
        sa.Column(
            "review_state",
            sa.String(32),
            nullable=True,
            server_default="clean",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_generation_sections", "review_state")
