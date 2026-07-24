import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class ReservationStatus(str, enum.Enum):
    CONFIRMED = "confirmed"  # reservada, aguardando o cliente
    SEATED = "seated"        # cliente chegou, check-in feito
    CANCELLED = "cancelled"  # cancelada
    NO_SHOW = "no_show"      # ninguém apareceu — marcado automaticamente


class Reservation(Base, UUIDMixin, TimestampMixin):
    """Reserva de mesa com data/hora marcada."""

    __tablename__ = "reservations"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ReservationStatus.CONFIRMED,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    seated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    establishment: Mapped["Establishment"] = relationship(back_populates="reservations")  # noqa: F821
    table: Mapped["Table"] = relationship(back_populates="reservations")  # noqa: F821

    __table_args__ = (
        Index("ix_reservations_establishment_reserved_at", "establishment_id", "reserved_at"),
        Index("ix_reservations_table_reserved_at", "table_id", "reserved_at"),
    )

    def __repr__(self) -> str:
        return f"<Reservation id={self.id} table_id={self.table_id} reserved_at={self.reserved_at} status={self.status}>"
