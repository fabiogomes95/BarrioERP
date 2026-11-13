"""cash_sessions.cash_sales: vendas em dinheiro gravadas no fechamento

O histórico recalculava as vendas em dinheiro a cada consulta; um estorno
feito depois do fechamento mudava o número exibido, que deixava de bater com
o "esperado" gravado. Sessões já fechadas ficam com null (continua o cálculo).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-13 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cash_sessions', sa.Column('cash_sales', sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('cash_sessions', 'cash_sales')
