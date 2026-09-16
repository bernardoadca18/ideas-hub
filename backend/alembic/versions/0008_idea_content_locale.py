"""Persist the selected editorial locale on ideas."""

from alembic import op
import sqlalchemy as sa

revision = "0008_idea_content_locale"
down_revision = "0007_review_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ideias",
        sa.Column(
            "content_locale", sa.String(5), nullable=False, server_default="pt-BR"
        ),
    )


def downgrade() -> None:
    op.drop_column("ideias", "content_locale")
