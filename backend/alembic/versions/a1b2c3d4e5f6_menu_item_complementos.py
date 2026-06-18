"""menu_item complementos

Adiciona a coluna `complementos` (JSONB) em menu_items — lista de opções
obrigatórias na hora do pedido (ex: cortes do churrasco, sabores de suco).

Revision ID: a1b2c3d4e5f6
Revises: 12586000cd36
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "12586000cd36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menu_items",
        sa.Column(
            "complementos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("menu_items", "complementos")
