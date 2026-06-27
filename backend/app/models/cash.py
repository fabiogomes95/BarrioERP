import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class CashSessionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class CashMovementKind(str, enum.Enum):
    SANGRIA = "sangria"        # retirada de dinheiro do caixa
    SUPRIMENTO = "suprimento"  # reforço/entrada de dinheiro no caixa


class CashSession(Base, UUIDMixin, TimestampMixin):
    """Sessão de caixa: abre com um fundo de troco e fecha com a contagem."""

    __tablename__ = "cash_sessions"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opened_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[CashSessionStatus] = mapped_column(
        Enum(CashSessionStatus, name="cash_session_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CashSessionStatus.OPEN,
        index=True,
    )
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    counted_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    movements: Mapped[list["CashMovement"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="CashMovement.created_at"
    )


class CashMovement(Base, UUIDMixin, TimestampMixin):
    """Movimento de caixa (sangria ou suprimento) dentro de uma sessão."""

    __tablename__ = "cash_movements"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cash_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[CashMovementKind] = mapped_column(
        Enum(CashMovementKind, name="cash_movement_kind_enum", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    session: Mapped["CashSession"] = relationship(back_populates="movements")
