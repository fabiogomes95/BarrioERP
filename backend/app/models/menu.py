from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class MenuCategory(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Categoria do cardápio (Bebidas, Pizzas, Petiscos…)."""

    __tablename__ = "menu_categories"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    establishment: Mapped["Establishment"] = relationship(back_populates="menu_categories")  # noqa: F821
    items: Mapped[list["MenuItem"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_menu_categories_establishment", "establishment_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<MenuCategory id={self.id} name={self.name}>"


class MenuItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Item do cardápio."""

    __tablename__ = "menu_items"

    category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("menu_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NUMERIC(12,2) — nunca float para dinheiro
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    is_available: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    category: Mapped[MenuCategory] = relationship(back_populates="items")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="menu_item")  # noqa: F821

    __table_args__ = (
        Index("ix_menu_items_category_active", "category_id", "is_active"),
        Index("ix_menu_items_category_available", "category_id", "is_available"),
    )

    def __repr__(self) -> str:
        return f"<MenuItem id={self.id} name={self.name} price={self.price}>"
