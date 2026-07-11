"""
app/api/v1/endpoints/menu.py

Endpoints HTTP para o módulo de cardápio.

9 endpoints organizados em dois grupos:
    CATEGORIAS (4): POST, GET, PATCH, DELETE /categories/...
    ITENS (5):      POST, GET, GET{id}, PATCH, DELETE /items/...

═══════════════════════════════════════════════════════════════
CONCEITO — Como módulos grandes são organizados no backend
═══════════════════════════════════════════════════════════════

À medida que o sistema cresce, um único arquivo de endpoints
começa a ter 500, 1000 linhas. Como organizar?

ESTRATÉGIA 1 — Um arquivo por recurso (o que usamos aqui):
    menu.py → categories + items (dois recursos, mesmo domínio)
    Funciona bem quando os recursos são pequenos e relacionados.
    Simples: um arquivo para entender o módulo inteiro.

ESTRATÉGIA 2 — Um arquivo por recurso, separados:
    categories.py → só categories
    menu_items.py → só menu items
    Melhor para recursos grandes com muitas rotas.

ESTRATÉGIA 3 — Sub-routers:
    menu_router = APIRouter(prefix="/menu")
    categories_router = APIRouter(prefix="/categories")
    items_router = APIRouter(prefix="/items")
    menu_router.include_router(categories_router)
    menu_router.include_router(items_router)

Para nosso tamanho (9 endpoints), ESTRATÉGIA 1 é adequada.

═══════════════════════════════════════════════════════════════
CONCEITO — Query parameters como filtros
═══════════════════════════════════════════════════════════════

Query parameters são passados na URL após o "?":
    GET /menu/items?category_id=uuid&is_active=true&page=2

No FastAPI, declaramos com `Query()`:
    category_id: UUID | None = Query(default=None)
    page: int = Query(default=1, ge=1)

FastAPI automaticamente:
    - Lê da URL
    - Converte para o tipo declarado (UUID, int, bool)
    - Valida (ge=1 → mínimo 1)
    - Documenta no Swagger UI

Diferença entre query params e path params:
    Path:  GET /items/{item_id}    → obrigatório, na URL
    Query: GET /items?page=2       → opcional, após o ?
    Body:  POST /items {json}      → para criação/atualização
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, require_roles
from app.models.user import UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.menu import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from app.services.menu_service import MenuService

router = APIRouter()


# ── Helper ─────────────────────────────────────────────────────────────────────


def _service(session: DBSession, user: CurrentUser) -> MenuService:
    return MenuService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


# ══════════════════════════════════════════════════════════════
# CATEGORIAS
# ══════════════════════════════════════════════════════════════


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=201,
    summary="Criar categoria",
    description="Cria uma nova categoria no cardápio do estabelecimento.",
)
async def create_category(
    data: CategoryCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> CategoryResponse:
    """
    Cria uma nova categoria (ex: 'Bebidas', 'Pratos Principais').

    O nome deve ser único no estabelecimento.
    `sort_order` controla a posição na interface (menor = primeiro).
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).create_category(data)


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="Listar categorias",
    description="Retorna todas as categorias do cardápio.",
)
async def list_categories(
    session: DBSession,
    current_user: CurrentUser,
    active_only: bool = Query(
        default=True,
        description="Se True, retorna apenas categorias ativas. False retorna todas.",
    ),
) -> list[CategoryResponse]:
    """
    Lista categorias do estabelecimento.

    Por padrão: active_only=True → só categorias ativas.
    Para o gerente ver tudo: active_only=false.

    Retorna lista simples (sem paginação) — restaurantes têm poucas categorias.
    """
    return await _service(session, current_user).list_categories(active_only=active_only)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Atualizar categoria",
    description="Atualiza campos de uma categoria. Apenas campos enviados são alterados.",
)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> CategoryResponse:
    """
    Atualiza uma categoria existente.

    Campos atualizáveis: name, description, sort_order, is_active.
    Envie apenas os campos que deseja alterar.

    Se `name` for alterado: verifica unicidade no estabelecimento.
    Sem `version` — categorias são catálogo, não transações.
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).update_category(category_id, data)


@router.delete(
    "/categories/{category_id}",
    status_code=204,
    summary="Remover categoria",
    description=(
        "Soft-deleta a categoria e TODOS os seus itens. "
        "Os itens removidos não aparecem mais no cardápio, "
        "mas o histórico de pedidos é preservado."
    ),
)
async def delete_category(
    category_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    """
    Remove uma categoria do cardápio (soft delete).

    ATENÇÃO: remove a categoria E todos os seus itens automaticamente.
    Esta ação é reversível apenas manualmente no banco de dados.

    Histórico de pedidos: preservado. OrderItems continuam com snapshot.
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    await _service(session, current_user).delete_category(category_id)


# ══════════════════════════════════════════════════════════════
# ITENS DO CARDÁPIO
# ══════════════════════════════════════════════════════════════


@router.post(
    "/items",
    response_model=MenuItemResponse,
    status_code=201,
    summary="Criar item",
    description="Cria um novo item no cardápio dentro de uma categoria.",
)
async def create_item(
    data: MenuItemCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> MenuItemResponse:
    """
    Cria um novo item no cardápio.

    A `category_id` deve pertencer ao estabelecimento do usuário logado.
    O nome deve ser único dentro da categoria.
    O preço é arredondado para 2 casas decimais.

    Novo item começa com is_active=True e is_available=True.
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).create_item(data)


@router.get(
    "/items",
    response_model=PaginatedResponse,
    summary="Listar itens",
    description="Lista itens do cardápio com filtros e paginação.",
)
async def list_items(
    session: DBSession,
    current_user: CurrentUser,
    category_id: UUID | None = Query(
        default=None,
        description="Filtra por categoria específica.",
    ),
    active_only: bool = Query(
        default=True,
        description="Se True, retorna apenas itens ativos.",
    ),
    available_only: bool = Query(
        default=False,
        description="Se True, retorna apenas itens disponíveis (is_available=True).",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse:
    """
    Lista itens do cardápio com filtros combinados.

    EXEMPLOS DE USO:
        GET /menu/items                           → todos os ativos
        GET /menu/items?available_only=true       → ativos E disponíveis agora
        GET /menu/items?category_id=uuid          → itens de uma categoria
        GET /menu/items?active_only=false         → todos (gerente)
        GET /menu/items?category_id=uuid&page=2   → paginado por categoria
    """
    return await _service(session, current_user).list_items(
        category_id=category_id,
        active_only=active_only,
        available_only=available_only,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/items/{item_id}",
    response_model=MenuItemResponse,
    summary="Buscar item",
    description="Retorna os dados de um item específico do cardápio.",
)
async def get_item(
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> MenuItemResponse:
    """
    Retorna um item específico pelo ID.

    Retorna 404 se não existir, estiver deletado, ou pertencer a outro estabelecimento.
    """
    return await _service(session, current_user).get_item(item_id)


@router.patch(
    "/items/{item_id}",
    response_model=MenuItemResponse,
    summary="Atualizar item",
    description="Atualiza campos de um item. Alterar o preço não retroage pedidos existentes.",
)
async def update_item(
    item_id: UUID,
    data: MenuItemUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> MenuItemResponse:
    """
    Atualiza um item do cardápio.

    Campos atualizáveis: name, description, price, sort_order,
                         is_active, is_available, category_id.

    SOBRE PREÇO:
        Alterar o preço muda apenas pedidos FUTUROS.
        Pedidos já feitos têm snapshot do preço da época — não são afetados.

    SOBRE MOVER DE CATEGORIA:
        Se category_id for enviado, o item é movido para a nova categoria.
        A nova categoria deve pertencer ao mesmo estabelecimento.
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    return await _service(session, current_user).update_item(item_id, data)


@router.delete(
    "/items/{item_id}",
    status_code=204,
    summary="Remover item",
    description="Soft-deleta um item do cardápio. Histórico de pedidos é preservado.",
)
async def delete_item(
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    """
    Remove um item do cardápio (soft delete).

    O item some da listagem mas continua no banco.
    Pedidos históricos que tinham este item: preservados via snapshot.
    """
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)
    await _service(session, current_user).delete_item(item_id)
