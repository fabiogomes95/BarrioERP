"""service fee percent

Adiciona service_fee_percent em establishments (configuração) e em orders
(snapshot no momento da abertura da comanda).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "establishments",
        sa.Column("service_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("service_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("orders", "service_fee_percent")
    op.drop_column("establishments", "service_fee_percent")
