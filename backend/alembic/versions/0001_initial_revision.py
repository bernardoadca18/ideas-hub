"""initial revision

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema já foi aplicado via db/init/001_init.sql
    # Esta migration serve apenas para marcar o estado inicial
    pass


def downgrade() -> None:
    # Não fazemos downgrade do schema inicial
    pass
