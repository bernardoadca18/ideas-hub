"""production profiles: perfil_producao em nichos + novo valor de origem_ideia

Revision ID: 0002_production_profiles
Revises: 0001_initial
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002_production_profiles'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'nichos',
        sa.Column(
            'perfil_producao', sa.String(length=50), nullable=False,
            server_default='faceless_general',
        ),
    )
    # Novo valor de enum precisa rodar fora de uma transação implícita em Postgres <12;
    # em versões recentes ALTER TYPE ... ADD VALUE já funciona dentro de migration normal.
    op.execute("ALTER TYPE origem_ideia ADD VALUE IF NOT EXISTS 'notas_gameplay'")


def downgrade() -> None:
    # Não há downgrade seguro para remoção de valor de enum em Postgres sem recriar o
    # tipo; como o valor 'notas_gameplay' pode já estar em uso por linhas existentes,
    # deliberadamente não fazemos downgrade automático dessa parte.
    op.drop_column('nichos', 'perfil_producao')
