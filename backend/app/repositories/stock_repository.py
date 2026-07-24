"""
app/repositories/stock_repository.py

Acesso ao banco para StockItem, StockMovement e MenuItemIngredient.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.stock import MenuItemIngredient, StockItem, StockMovement
from app.repositories.base import BaseRepository


class StockItemRepository(BaseRepository[StockItem]):
    model = StockItem

    async def get_by_establishment(self, item_id: UUID, establishment_id: UUID) -> StockItem | None:
        stmt = select(StockItem).where(
            StockItem.id == item_id,
            StockItem.establishment_id == establishment_id,
            StockItem.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_establishment(
        self, establishment_id: UUID, *, active_only: bool = True
    ) -> list[StockItem]:
        filters = [
            StockItem.establishment_id == establishment_id,
            StockItem.deleted_at.is_(None),
        ]
        if active_only:
            filters.append(StockItem.is_active.is_(True))

        stmt = select(StockItem).where(*filters).order_by(StockItem.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_low_stock(self, establishment_id: UUID) -> list[StockItem]:
        """Insumos ativos com quantity_on_hand <= min_quantity."""
        stmt = select(StockItem).where(
            StockItem.establishment_id == establishment_id,
            StockItem.deleted_at.is_(None),
            StockItem.is_active.is_(True),
            StockItem.quantity_on_hand <= StockItem.min_quantity,
        ).order_by(StockItem.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str, establishment_id: UUID) -> StockItem | None:
        stmt = select(StockItem).where(
            StockItem.name == name,
            StockItem.establishment_id == establishment_id,
            StockItem.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class StockMovementRepository(BaseRepository[StockMovement]):
    model = StockMovement

    async def list_by_item(
        self, stock_item_id: UUID, establishment_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[StockMovement]:
        stmt = (
            select(StockMovement)
            .where(
                StockMovement.stock_item_id == stock_item_id,
                StockMovement.establishment_id == establishment_id,
            )
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MenuItemIngredientRepository(BaseRepository[MenuItemIngredient]):
    model = MenuItemIngredient

    async def list_for_menu_item(self, menu_item_id: UUID) -> list[MenuItemIngredient]:
        stmt = (
            select(MenuItemIngredient)
            .where(MenuItemIngredient.menu_item_id == menu_item_id)
            .options(selectinload(MenuItemIngredient.stock_item))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace_for_menu_item(
        self, menu_item_id: UUID, ingredients: list[tuple[UUID, Decimal]]
    ) -> list[MenuItemIngredient]:
        """Apaga a receita atual do item e grava a nova lista (substituição total)."""
        existing = await self.list_for_menu_item(menu_item_id)
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()

        created = []
        for stock_item_id, quantity_per_unit in ingredients:
            row = MenuItemIngredient(
                menu_item_id=menu_item_id,
                stock_item_id=stock_item_id,
                quantity_per_unit=quantity_per_unit,
            )
            self.session.add(row)
            created.append(row)
        await self.session.flush()
        for row in created:
            await self.session.refresh(row)
        return created
