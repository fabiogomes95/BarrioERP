import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class TableStatus(str, enum.Enum):
    FREE = "free"
    OCCUPIED = "occupied"
    BILL_REQUESTED = "bill_requested"
    RESERVED = "reserved"
    BLOCKED = "blocked"


class Table(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """Mesa física ou ponto de atendimento (balcão, delivery)."""

    __tablename__ = "tables"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[TableStatus] = mapped_column(
        Enum(TableStatus, name="table_status_enum"),
        nullable=False,
        default=TableStatus.FREE,
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    establishment: Mapped["Establishment"] = relationship(back_populates="tables")  # noqa: F821
    # Relacionamento viewonly: carrega apenas comandas abertas (closed_at IS NULL).
    # Não use para writes — para criar uma Order use Order.table_id diretamente.
    open_orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        primaryjoin="and_(foreign(Order.table_id) == Table.id, Order.closed_at == None)",
        viewonly=True,
        lazy="noload",
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        back_populates="table",
        foreign_keys="Order.table_id",
    )

    __table_args__ = (
        Index("ix_tables_establishment_number", "establishment_id", "number", unique=True),
        Index("ix_tables_establishment_status", "establishment_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Table id={self.id} number={self.number} status={self.status}>"
