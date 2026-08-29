"""author briefing and immutable script revision provenance

Revision ID: 0003_author_briefing
Revises: 0002_production_profiles
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_author_briefing"
down_revision: str | None = "0002_production_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ideias", sa.Column("author_briefing", sa.Text(), nullable=True))
    op.add_column(
        "roteiros", sa.Column("author_briefing_snapshot", sa.Text(), nullable=True)
    )
    op.add_column(
        "roteiros", sa.Column("author_briefing_identity", sa.String(length=96), nullable=True)
    )
    op.add_column(
        "roteiros",
        sa.Column("parent_roteiro_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "roteiros",
        sa.Column(
            "revision_kind",
            sa.String(length=32),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column("roteiros", sa.Column("revision_feedback", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_roteiros_parent_roteiro_id",
        "roteiros",
        "roteiros",
        ["parent_roteiro_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_roteiros_parent", "roteiros", ["parent_roteiro_id"])


def downgrade() -> None:
    op.drop_index("idx_roteiros_parent", table_name="roteiros")
    op.drop_constraint("fk_roteiros_parent_roteiro_id", "roteiros", type_="foreignkey")
    op.drop_column("roteiros", "revision_feedback")
    op.drop_column("roteiros", "revision_kind")
    op.drop_column("roteiros", "parent_roteiro_id")
    op.drop_column("roteiros", "author_briefing_identity")
    op.drop_column("roteiros", "author_briefing_snapshot")
    op.drop_column("ideias", "author_briefing")
