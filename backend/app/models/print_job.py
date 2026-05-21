import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class PrintJobType(str, enum.Enum):
    KITCHEN = "kitchen"      # comanda de cozinha
    BAR = "bar"              # comanda de bar
    RECEIPT = "receipt"      # cupom do cliente


class PrintJobStatus(str, enum.Enum):
    PENDING = "pending"
    PRINTED = "printed"
    FAILED = "failed"


class PrintJob(Base, UUIDMixin, TimestampMixin):
    """Fila de impressão para cozinha, bar e caixa."""

    __tablename__ = "print_jobs"

    order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[PrintJobType] = mapped_column(
        Enum(PrintJobType, name="print_job_type_enum"),
        nullable=False,
        index=True,
    )
    status: Mapped[PrintJobStatus] = mapped_column(
        Enum(PrintJobStatus, name="print_job_status_enum"),
        nullable=False,
        default=PrintJobStatus.PENDING,
        index=True,
    )
    printer_target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON com dados de impressão
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="print_jobs")  # noqa: F821

    __table_args__ = (
        Index("ix_print_jobs_status_type", "status", "type"),
        Index("ix_print_jobs_establishment_pending", "establishment_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<PrintJob id={self.id} type={self.type} status={self.status}>"
