from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Company(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Tenant raiz — cada empresa cliente do SaaS."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="starter")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    establishments: Mapped[list["Establishment"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_companies_slug_active", "slug", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} slug={self.slug}>"
