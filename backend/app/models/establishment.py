from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Establishment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Estabelecimento físico de uma empresa.
    Uma Company pode ter múltiplos (ex: filiais).
    """

    __tablename__ = "establishments"

    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Sao_Paulo")
    # Taxa de serviço padrão (%) aplicada às comandas. 0 = sem taxa.
    service_fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    company: Mapped["Company"] = relationship(back_populates="establishments")  # noqa: F821
    tables: Mapped[list["Table"]] = relationship(  # noqa: F821
        back_populates="establishment", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="establishment"
    )
    menu_categories: Mapped[list["MenuCategory"]] = relationship(  # noqa: F821
        back_populates="establishment", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        back_populates="establishment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_establishments_company_slug", "company_id", "slug", unique=True),
        Index("ix_establishments_company_active", "company_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Establishment id={self.id} slug={self.slug}>"
