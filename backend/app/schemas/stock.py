"""
app/schemas/stock.py

Schemas Pydantic para o módulo de estoque/insumos.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.stock import StockMovementKind, StockUnit
from app.schemas.common import BaseSchema, PaginatedResponse, TimestampSchema, UUIDSchema


# ══════════════════════════════════════════════════════════════
# INSUMOS (StockItem)
# ══════════════════════════════════════════════════════════════


class StockItemCreate(BaseSchema):
    """Dados para cadastrar um novo insumo. Usado em: POST /api/v1/stock/items."""

    name: str = Field(..., min_length=1, max_length=200, description="Nome do insumo (ex: 'Carne bovina', 'Coca-Cola 350ml').")
    unit: StockUnit = Field(..., description="Unidade de medida do insumo (unit, kg, g, l, ml).")
    quantity_on_hand: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"), description="Quantidade inicial em estoque.",
    )
    min_quantity: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"), description="Limiar mínimo — abaixo disso o insumo aparece como 'estoque baixo'.",
    )
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()


class StockItemUpdate(BaseSchema):
    """Dados para atualizar um insumo. Usado em: PATCH /api/v1/stock/items/{id}. Todos os campos são opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: StockUnit | None = None
    min_quantity: Decimal | None = Field(default=None, ge=Decimal("0"))
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class StockItemResponse(UUIDSchema, TimestampSchema):
    establishment_id: UUID
    name: str
    unit: StockUnit
    quantity_on_hand: Decimal
    min_quantity: Decimal
    is_active: bool
    notes: str | None
    is_low: bool = Field(description="quantity_on_hand <= min_quantity — calculado, não vem do banco.")


PaginatedStockItemResponse = PaginatedResponse


# ══════════════════════════════════════════════════════════════
# MOVIMENTAÇÕES (StockMovement)
# ══════════════════════════════════════════════════════════════


class StockMovementCreate(BaseSchema):
    """
    Registra uma movimentação manual (compra, ajuste ou perda).

    Usado em: POST /api/v1/stock/items/{stock_item_id}/movements

    `quantity` é sempre positivo aqui — o sinal (entrada/saída) é
    decidido pelo `kind`: PURCHASE e ADJUSTMENT positivo somam ao
    estoque; LOSS e ADJUSTMENT negativo (via `is_negative_adjustment`)
    subtraem. Movimentos do tipo SALE não são criados por aqui — são
    gerados automaticamente pelo fluxo de comandas (`OrderService`).
    """

    kind: StockMovementKind = Field(..., description="purchase, adjustment ou loss. 'sale' é automático.")
    quantity: Decimal = Field(..., gt=Decimal("0"), description="Quantidade movimentada (sempre positiva).")
    is_negative_adjustment: bool = Field(
        default=False, description="Só usado com kind=adjustment: True subtrai do estoque, False soma.",
    )
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("kind")
    @classmethod
    def kind_not_sale(cls, v: StockMovementKind) -> StockMovementKind:
        if v == StockMovementKind.SALE:
            raise ValueError("Movimentos 'sale' são gerados automaticamente pela venda, não podem ser criados manualmente.")
        return v


class StockMovementResponse(UUIDSchema, TimestampSchema):
    establishment_id: UUID
    stock_item_id: UUID
    kind: StockMovementKind
    quantity_change: Decimal
    reason: str | None
    order_item_id: UUID | None
    user_id: UUID | None


PaginatedStockMovementResponse = PaginatedResponse


# ══════════════════════════════════════════════════════════════
# RECEITA (MenuItemIngredient)
# ══════════════════════════════════════════════════════════════


class MenuItemIngredientInput(BaseSchema):
    """Uma linha de receita: quanto de um insumo o item consome por unidade vendida."""

    stock_item_id: UUID
    quantity_per_unit: Decimal = Field(..., gt=Decimal("0"))


class MenuItemIngredientSet(BaseSchema):
    """
    Substitui a lista inteira de ingredientes de um item do cardápio.

    Usado em: PUT /api/v1/stock/menu-items/{menu_item_id}/ingredients
    Enviar [] remove todos os ingredientes (item volta a não afetar estoque).
    """

    ingredients: list[MenuItemIngredientInput] = Field(default_factory=list)

    @field_validator("ingredients")
    @classmethod
    def no_duplicate_stock_items(cls, v: list[MenuItemIngredientInput]) -> list[MenuItemIngredientInput]:
        ids = [i.stock_item_id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Não é possível repetir o mesmo insumo na receita de um item.")
        return v


class MenuItemIngredientResponse(UUIDSchema, TimestampSchema):
    menu_item_id: UUID
    stock_item_id: UUID
    quantity_per_unit: Decimal
    stock_item_name: str
    stock_item_unit: StockUnit
