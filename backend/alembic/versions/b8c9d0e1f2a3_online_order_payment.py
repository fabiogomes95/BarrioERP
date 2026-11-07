"""online_orders.payment_method / change_for

Forma de pagamento escolhida no cardápio (dinheiro, pix, crédito, débito) e,
se dinheiro, troco pra quanto. Só informativo: o pagamento continua sendo
registrado na comanda pelo caixa.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-07 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('online_orders', sa.Column('payment_method', sa.String(length=20), nullable=True))
    op.add_column('online_orders', sa.Column('change_for', sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('online_orders', 'change_for')
    op.drop_column('online_orders', 'payment_method')
