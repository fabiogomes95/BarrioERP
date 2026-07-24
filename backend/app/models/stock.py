import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class StockUnit(str, enum.Enum):
    UNIT = "unit"  # unidade (garrafa, lata, pacote)
    KG = "kg"
    G = "g"
    L = "l"
    ML = "ml"


class StockMovementKind(str, enum.Enum):
    PURCHASE = "purchase"      # entrada manual (compra)
    ADJUSTMENT = "adjustment"  # ajuste manual (+ ou -)
    SALE = "sale"               # dedução automática por venda
    LOSS = "loss"                # perda/quebra


class StockItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Insumo controlado em estoque (ex: carne, refrigerante, copo descartável)."""

    __tablename__ = "stock_items"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[StockUnit] = mapped_column(
        Enum(StockUnit, name="stock_unit_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    # NUMERIC(12,3) — 3 casas decimais permitem fração de kg/L
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, default=Decimal("0"), server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    establishment: Mapped["Establishment"] = relationship(back_populates="stock_items")  # noqa: F821
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="stock_item", cascade="all, delete-orphan", order_by="StockMovement.created_at"
    )
    ingredient_of: Mapped[list["MenuItemIngredient"]] = relationship(
        back_populates="stock_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_stock_items_establishment_active", "establishment_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<StockItem id={self.id} name={self.name} qty={self.quantity_on_hand}{self.unit.value}>"


class StockMovement(Base, UUIDMixin, TimestampMixin):
    """Movimento de estoque — entrada, saída ou ajuste de um insumo."""

    __tablename__ = "stock_movements"

    establishment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("stock_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[StockMovementKind] = mapped_column(
        Enum(StockMovementKind, name="stock_movement_kind_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    # Assinado: positivo = entrada, negativo = saída
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    order_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    stock_item: Mapped["StockItem"] = relationship(back_populates="movements")

    __table_args__ = (
        Index("ix_stock_movements_item_created", "stock_item_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<StockMovement id={self.id} kind={self.kind.value} change={self.quantity_change}>"


class MenuItemIngredient(Base, UUIDMixin, TimestampMixin):
    """Receita: quanto de um insumo um item do cardápio consome por unidade vendida."""

    __tablename__ = "menu_item_ingredients"

    menu_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("menu_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("stock_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    menu_item: Mapped["MenuItem"] = relationship(back_populates="ingredients")  # noqa: F821
    stock_item: Mapped["StockItem"] = relationship(back_populates="ingredient_of")

    __table_args__ = (
        UniqueConstraint("menu_item_id", "stock_item_id", name="uq_menu_item_ingredient"),
    )

    def __repr__(self) -> str:
        return f"<MenuItemIngredient menu_item_id={self.menu_item_id} stock_item_id={self.stock_item_id}>"
