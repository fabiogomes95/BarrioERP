"""
app/models/online_order.py

Pedido feito pelo cliente no cardápio público (app.public_menu).

POR QUE UMA TABELA SEPARADA (e não criar a Order direto)?
    O cardápio público fica aberto na internet. Se ele criasse comandas
    direto, um trote ou spam cairia na cozinha e no caixa sem ninguém ver.
    Aqui o pedido fica PENDENTE até alguém da casa tocar em "Aceitar" — só
    então vira uma Order normal (delivery/retirada) pelo OrderService, com
    KDS, estoque e auditoria iguais a um pedido lançado no balcão.

    O processo público só consegue INSERIR nesta tabela. Nunca lê/altera
    comandas, mesas ou caixa.

items (JSONB) guarda as linhas já precificadas pelo servidor no momento do
pedido — ver app/services/online_order_pricing.py. O preço enviado pelo
navegador nunca é usado.
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Identity, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.models.order import OrderType


class OnlineOrderStatus(str, enum.Enum):
    PENDING = "pending"    # aguardando aceite
    ACCEPTED = "accepted"  # virou comanda (order_id preenchido)
    REJECTED = "rejected"  # recusado pela casa


class OnlineOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "online_orders"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Número curto pra falar com o cliente ("pedido #42") — sequência do banco,
    # sem corrida entre dois pedidos chegando ao mesmo tempo.
    number: Mapped[int] = mapped_column(Integer, Identity(), nullable=False, unique=True)
    status: Mapped[OnlineOrderStatus] = mapped_column(
        Enum(OnlineOrderStatus, name="online_order_status_enum",
             values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OnlineOrderStatus.PENDING,
    )
    # Reaproveita o enum de tipo de pedido já existente (só delivery/pickup aqui)
    fulfillment: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type_enum", create_type=False,
             values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )
    handled_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_online_orders_establishment_status", "establishment_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<OnlineOrder #{self.number} status={self.status}>"
