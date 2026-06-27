"""tipo de pedido (balcao, delivery, retirada)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

order_type_enum = sa.Enum('counter', 'delivery', 'pickup', name='order_type_enum')


def upgrade() -> None:
    order_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('orders',
        sa.Column(
            'order_type',
            order_type_enum,
            nullable=False,
            server_default='counter',
        ),
    )


def downgrade() -> None:
    op.drop_column('orders', 'order_type')
    order_type_enum.drop(op.get_bind(), checkfirst=True)
