"""cash_sessions: no máximo um caixa aberto por estabelecimento

Índice único parcial (só linhas com status 'open'). A regra já existia no
código, mas dois cliques em "Abrir caixa" ao mesmo tempo passavam os dois
pela checagem e criavam duas sessões abertas — agora o banco recusa a segunda.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-13 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'uq_cash_sessions_one_open', 'cash_sessions', ['establishment_id'],
        unique=True, postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index('uq_cash_sessions_one_open', table_name='cash_sessions')
