"""
app/services/stock_service.py

Regras de negócio do módulo de estoque/insumos.

CONCEITO — Quando o estoque é deduzido:
    O único evento confiável no fluxo atual de comandas é "item adicionado"
    (`OrderService.add_item`) — o enum OrderItemStatus tem um fluxo completo
    (pending → sent → preparing → ready → served), mas nada no sistema hoje
    transiciona por esses estados. Por isso a dedução acontece na
    ADIÇÃO do item, não no "servido". Reverte no cancelamento do item, e
    ajusta a diferença quando a quantidade muda.

CONCEITO — Estoque negativo não bloqueia venda:
    Divergência de estoque é comum (contagem errada, insumo usado fora do
    sistema). Bloquear o garçom por causa disso pararia a operação do bar.
    A dedução acontece sempre; o alerta de estoque baixo/negativo é
    só visual, na tela de Estoque.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError, TenantError
from app.models.stock import StockItem, StockMovement, StockMovementKind
from app.repositories.menu_repository import MenuItemRepository
from app.repositories.stock_repository import (
    MenuItemIngredientRepository,
    StockItemRepository,
    StockMovementRepository,
)
from app.schemas.stock import (
    MenuItemIngredientResponse,
    MenuItemIngredientSet,
    StockItemCreate,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementResponse,
)
from app.services.base import BaseService


class StockService(BaseService):
    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        self._item_repo = StockItemRepository(session)
        self._movement_repo = StockMovementRepository(session)
        self._ingredient_repo = MenuItemIngredientRepository(session)
        self._menu_item_repo = MenuItemRepository(session)

    def _require_establishment(self) -> UUID:
        if self.establishment_id is None:
            raise TenantError(
                "Usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário para gerenciar o estoque."
            )
        return self.establishment_id

    def _to_response(self, item: StockItem) -> StockItemResponse:
        resp = StockItemResponse.model_validate(item)
        resp.is_low = item.quantity_on_hand <= item.min_quantity
        return resp

    # ══════════════════════════════════════════════════════════════
    # CRUD de StockItem
    # ══════════════════════════════════════════════════════════════

    async def create_item(self, data: StockItemCreate) -> StockItemResponse:
        establishment_id = self._require_establishment()

        item = StockItem(
            establishment_id=establishment_id,
            name=data.name,
            unit=data.unit,
            quantity_on_hand=data.quantity_on_hand,
            min_quantity=data.min_quantity,
            is_active=True,
            notes=data.notes,
        )
        item = await self._item_repo.add(item)

        await self._log_audit(
            action="stock_item.create",
            resource_type="stock_item",
            resource_id=str(item.id),
            after={"name": item.name, "quantity_on_hand": str(item.quantity_on_hand)},
        )
        return self._to_response(item)

    async def list_items(self, *, active_only: bool = True) -> list[StockItemResponse]:
        establishment_id = self._require_establishment()
        items = await self._item_repo.list_by_establishment(establishment_id, active_only=active_only)
        return [self._to_response(i) for i in items]

    async def list_low_stock(self) -> list[StockItemResponse]:
        establishment_id = self._require_establishment()
        items = await self._item_repo.list_low_stock(establishment_id)
        return [self._to_response(i) for i in items]

    async def get_item(self, item_id: UUID) -> StockItemResponse:
        establishment_id = self._require_establishment()
        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("StockItem", item_id)
        return self._to_response(item)

    async def update_item(self, item_id: UUID, data: StockItemUpdate) -> StockItemResponse:
        establishment_id = self._require_establishment()
        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("StockItem", item_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        await self.session.flush()
        await self.session.refresh(item)
        return self._to_response(item)

    async def delete_item(self, item_id: UUID) -> None:
        establishment_id = self._require_establishment()
        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("StockItem", item_id)
        item.soft_delete()
        await self.session.flush()

    # ══════════════════════════════════════════════════════════════
    # Movimentações manuais
    # ══════════════════════════════════════════════════════════════

    async def record_movement(
        self, stock_item_id: UUID, data: StockMovementCreate
    ) -> StockMovementResponse:
        establishment_id = self._require_establishment()
        item = await self._item_repo.get_by_establishment(stock_item_id, establishment_id)
        if item is None:
            raise NotFoundError("StockItem", stock_item_id)

        if data.kind == StockMovementKind.LOSS or (
            data.kind == StockMovementKind.ADJUSTMENT and data.is_negative_adjustment
        ):
            change = -data.quantity
        else:
            change = data.quantity

        movement = StockMovement(
            establishment_id=establishment_id,
            stock_item_id=stock_item_id,
            kind=data.kind,
            quantity_change=change,
            reason=data.reason,
            user_id=self.user_id,
        )
        self.session.add(movement)
        item.quantity_on_hand += change
        await self.session.flush()
        await self.session.refresh(movement)

        await self._log_audit(
            action="stock_movement.create",
            resource_type="stock_movement",
            resource_id=str(movement.id),
            after={"kind": data.kind.value, "quantity_change": str(change)},
        )
        return StockMovementResponse.model_validate(movement)

    async def list_movements(
        self, stock_item_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[StockMovementResponse]:
        establishment_id = self._require_establishment()
        item = await self._item_repo.get_by_establishment(stock_item_id, establishment_id)
        if item is None:
            raise NotFoundError("StockItem", stock_item_id)
        movements = await self._movement_repo.list_by_item(
            stock_item_id, establishment_id, limit=limit, offset=offset
        )
        return [StockMovementResponse.model_validate(m) for m in movements]

    # ══════════════════════════════════════════════════════════════
    # Receita (MenuItemIngredient)
    # ══════════════════════════════════════════════════════════════

    async def get_ingredients(self, menu_item_id: UUID) -> list[MenuItemIngredientResponse]:
        establishment_id = self._require_establishment()
        menu_item = await self._menu_item_repo.get_by_establishment(menu_item_id, establishment_id)
        if menu_item is None:
            raise NotFoundError("MenuItem", menu_item_id)

        rows = await self._ingredient_repo.list_for_menu_item(menu_item_id)
        return [
            MenuItemIngredientResponse(
                id=row.id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                menu_item_id=row.menu_item_id,
                stock_item_id=row.stock_item_id,
                quantity_per_unit=row.quantity_per_unit,
                stock_item_name=row.stock_item.name,
                stock_item_unit=row.stock_item.unit,
            )
            for row in rows
        ]

    async def set_ingredients(
        self, menu_item_id: UUID, data: MenuItemIngredientSet
    ) -> list[MenuItemIngredientResponse]:
        establishment_id = self._require_establishment()
        menu_item = await self._menu_item_repo.get_by_establishment(menu_item_id, establishment_id)
        if menu_item is None:
            raise NotFoundError("MenuItem", menu_item_id)

        for ingredient in data.ingredients:
            stock_item = await self._item_repo.get_by_establishment(
                ingredient.stock_item_id, establishment_id
            )
            if stock_item is None:
                raise NotFoundError("StockItem", ingredient.stock_item_id)

        await self._ingredient_repo.replace_for_menu_item(
            menu_item_id,
            [(i.stock_item_id, i.quantity_per_unit) for i in data.ingredients],
        )
        return await self.get_ingredients(menu_item_id)

    # ══════════════════════════════════════════════════════════════
    # Wiring com comandas (chamado por OrderService, mesma sessão/transação)
    # ══════════════════════════════════════════════════════════════

    async def deduct_for_sale(
        self, menu_item_id: UUID, quantity: int, order_item_id: UUID, establishment_id: UUID
    ) -> None:
        """Deduz o estoque dos insumos da receita de menu_item_id. Não bloqueia se ficar negativo."""
        ingredients = await self._ingredient_repo.list_for_menu_item(menu_item_id)
        for ingredient in ingredients:
            change = -(ingredient.quantity_per_unit * Decimal(quantity))
            await self._apply_sale_movement(
                stock_item=ingredient.stock_item,
                change=change,
                order_item_id=order_item_id,
                establishment_id=establishment_id,
            )

    async def restore_for_item(self, order_item_id: UUID, establishment_id: UUID) -> None:
        """Reverte (soma de volta) as deduções de venda feitas para este order_item."""
        stmt = select(StockMovement).where(
            StockMovement.order_item_id == order_item_id,
            StockMovement.kind == StockMovementKind.SALE,
        )
        result = await self.session.execute(stmt)
        original_movements = list(result.scalars().all())

        for original in original_movements:
            stock_item = await self._item_repo.get(original.stock_item_id)
            if stock_item is None:
                continue
            await self._apply_sale_movement(
                stock_item=stock_item,
                change=-original.quantity_change,
                order_item_id=order_item_id,
                establishment_id=establishment_id,
            )

    async def adjust_for_quantity_change(
        self, menu_item_id: UUID, order_item_id: UUID, old_qty: int, new_qty: int, establishment_id: UUID
    ) -> None:
        """Ajusta o estoque pela diferença quando a quantidade de um item pedido muda."""
        delta = new_qty - old_qty
        if delta == 0:
            return
        ingredients = await self._ingredient_repo.list_for_menu_item(menu_item_id)
        for ingredient in ingredients:
            change = -(ingredient.quantity_per_unit * Decimal(delta))
            await self._apply_sale_movement(
                stock_item=ingredient.stock_item,
                change=change,
                order_item_id=order_item_id,
                establishment_id=establishment_id,
            )

    async def _apply_sale_movement(
        self, *, stock_item: StockItem, change: Decimal, order_item_id: UUID, establishment_id: UUID
    ) -> None:
        if change == 0:
            return
        movement = StockMovement(
            establishment_id=establishment_id,
            stock_item_id=stock_item.id,
            kind=StockMovementKind.SALE,
            quantity_change=change,
            order_item_id=order_item_id,
            user_id=None,
        )
        self.session.add(movement)
        stock_item.quantity_on_hand += change
        await self.session.flush()
