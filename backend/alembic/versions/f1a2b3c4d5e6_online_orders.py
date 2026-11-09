"""online_orders

Pedidos feitos pelo cardápio público, pendentes de aceite.

Revision ID: f1a2b3c4d5e6
Revises: 9434c9420e4f
Create Date: 2026-11-06 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '9434c9420e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status_enum = postgresql.ENUM('pending', 'accepted', 'rejected', name='online_order_status_enum')
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'online_orders',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('establishment_id', sa.UUID(), nullable=False),
        sa.Column('number', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('status', postgresql.ENUM(name='online_order_status_enum', create_type=False), nullable=False),
        sa.Column('fulfillment', postgresql.ENUM(name='order_type_enum', create_type=False), nullable=False),
        sa.Column('customer_name', sa.String(length=80), nullable=False),
        sa.Column('customer_phone', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('client_ip', sa.String(length=64), nullable=True),
        sa.Column('order_id', sa.UUID(), nullable=True),
        sa.Column('handled_by_id', sa.UUID(), nullable=True),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['establishment_id'], ['establishments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['handled_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('number'),
    )
    op.create_index('ix_online_orders_establishment_status', 'online_orders', ['establishment_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_online_orders_establishment_status', table_name='online_orders')
    op.drop_table('online_orders')
    postgresql.ENUM(name='online_order_status_enum').drop(op.get_bind(), checkfirst=True)
