import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class OrderStatus(str, enum.Enum):
    OPEN = "open"
    BILL_REQUESTED = "bill_requested"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class OrderItemStatus(str, enum.Enum):
    PENDING = "pending"          # aguardando envio à cozinha
    SENT = "sent"                # enviado à cozinha
    PREPARING = "preparing"      # em preparo
    READY = "ready"              # pronto para servir
    SERVED = "served"            # servido
    CANCELLED = "cancelled"


class Order(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """
    Comanda de uma mesa.
    Uma mesa pode ter no máximo uma Order com status != CLOSED/CANCELLED.
    """

    __tablename__ = "orders"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tables.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    waiter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum"),
        nullable=False,
        default=OrderStatus.OPEN,
        index=True,
    )
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    service_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    establishment: Mapped["Establishment"] = relationship(back_populates="orders")  # noqa: F821
    table: Mapped["Table | None"] = relationship(back_populates="orders")  # noqa: F821
    waiter: Mapped["User | None"] = relationship(back_populates="orders", foreign_keys=[waiter_id])  # noqa: F821
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        back_populates="order", cascade="all, delete-orphan"
    )
    print_jobs: Mapped[list["PrintJob"]] = relationship(  # noqa: F821
        back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_orders_establishment_status", "establishment_id", "status"),
        Index("ix_orders_table_open", "table_id", "closed_at"),
        Index("ix_orders_establishment_closed_at", "establishment_id", "closed_at"),
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} status={self.status} total={self.total}>"


class OrderItem(Base, UUIDMixin, TimestampMixin):
    """Item de uma comanda — snapshot do preço no momento do pedido."""

    __tablename__ = "order_items"

    order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    menu_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("menu_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Snapshot imutável do momento do pedido
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OrderItemStatus] = mapped_column(
        Enum(OrderItemStatus, name="order_item_status_enum"),
        nullable=False,
        default=OrderItemStatus.PENDING,
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem | None"] = relationship(back_populates="order_items")  # noqa: F821

    __table_args__ = (
        Index("ix_order_items_order_status", "order_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<OrderItem id={self.id} name={self.item_name} qty={self.quantity}>"
