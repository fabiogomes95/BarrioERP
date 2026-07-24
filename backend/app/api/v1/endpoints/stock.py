"""
app/api/v1/endpoints/stock.py

Endpoints HTTP para o módulo de estoque/insumos.
Todos exigem role owner/manager — controle de insumos é decisão gerencial.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, require_roles
from app.models.user import UserRole
from app.schemas.stock import (
    MenuItemIngredientResponse,
    MenuItemIngredientSet,
    StockItemCreate,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementResponse,
)
from app.services.stock_service import StockService

router = APIRouter()


def _service(session: DBSession, user: CurrentUser) -> StockService:
    return StockService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


# ══════════════════════════════════════════════════════════════
# INSUMOS
# ══════════════════════════════════════════════════════════════


@router.post(
    "/items",
    response_model=StockItemResponse,
    status_code=201,
    summary="Criar insumo",
)
async def create_item(
    data: StockItemCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).create_item(data)


@router.get(
    "/items",
    response_model=list[StockItemResponse],
    summary="Listar insumos",
)
async def list_items(
    session: DBSession,
    current_user: CurrentUser,
    active_only: bool = Query(default=True),
) -> list[StockItemResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).list_items(active_only=active_only)


@router.get(
    "/low",
    response_model=list[StockItemResponse],
    summary="Listar insumos com estoque baixo",
)
async def list_low_stock(
    session: DBSession,
    current_user: CurrentUser,
) -> list[StockItemResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).list_low_stock()


@router.get(
    "/items/{item_id}",
    response_model=StockItemResponse,
    summary="Buscar insumo",
)
async def get_item(
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).get_item(item_id)


@router.patch(
    "/items/{item_id}",
    response_model=StockItemResponse,
    summary="Atualizar insumo",
)
async def update_item(
    item_id: UUID,
    data: StockItemUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).update_item(item_id, data)


@router.delete(
    "/items/{item_id}",
    status_code=204,
    summary="Remover insumo",
)
async def delete_item(
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    await _service(session, current_user).delete_item(item_id)


# ══════════════════════════════════════════════════════════════
# MOVIMENTAÇÕES
# ══════════════════════════════════════════════════════════════


@router.post(
    "/items/{item_id}/movements",
    response_model=StockMovementResponse,
    status_code=201,
    summary="Registrar movimentação manual (compra, ajuste ou perda)",
)
async def create_movement(
    item_id: UUID,
    data: StockMovementCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> StockMovementResponse:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).record_movement(item_id, data)


@router.get(
    "/items/{item_id}/movements",
    response_model=list[StockMovementResponse],
    summary="Histórico de movimentações de um insumo",
)
async def list_movements(
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[StockMovementResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).list_movements(item_id, limit=limit, offset=offset)


# ══════════════════════════════════════════════════════════════
# RECEITA (ingredientes de um item do cardápio)
# ══════════════════════════════════════════════════════════════


@router.get(
    "/menu-items/{menu_item_id}/ingredients",
    response_model=list[MenuItemIngredientResponse],
    summary="Listar ingredientes (receita) de um item do cardápio",
)
async def get_ingredients(
    menu_item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> list[MenuItemIngredientResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).get_ingredients(menu_item_id)


@router.put(
    "/menu-items/{menu_item_id}/ingredients",
    response_model=list[MenuItemIngredientResponse],
    summary="Substituir a receita completa de um item do cardápio",
)
async def set_ingredients(
    menu_item_id: UUID,
    data: MenuItemIngredientSet,
    session: DBSession,
    current_user: CurrentUser,
) -> list[MenuItemIngredientResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).set_ingredients(menu_item_id, data)
