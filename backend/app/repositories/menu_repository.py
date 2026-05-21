"""
app/repositories/menu_repository.py

Acesso ao banco para MenuCategory e MenuItem.

Dois repositories no mesmo arquivo porque são fortemente relacionados:
    MenuCategoryRepository  → operações em menu_categories
    MenuItemRepository      → operações em menu_items (requer JOIN com categories)

═══════════════════════════════════════════════════════════════
CONCEITO — Como filtros SQL funcionam no ORM
═══════════════════════════════════════════════════════════════

SQLAlchemy constrói queries SQL de forma composicional:

    stmt = select(MenuItem)              # SELECT * FROM menu_items
    stmt = stmt.where(cond1)             # WHERE cond1
    stmt = stmt.where(cond2)             # WHERE cond1 AND cond2
    stmt = stmt.order_by(col)            # ORDER BY col
    stmt = stmt.limit(50).offset(0)      # LIMIT 50 OFFSET 0

Cada chamada retorna um novo objeto stmt (imutável).
Podemos CONSTRUIR queries condicionalmente:

    stmt = select(MenuItem).where(base_filter)
    if category_id:
        stmt = stmt.where(MenuItem.category_id == category_id)
    if active_only:
        stmt = stmt.where(MenuItem.is_active.is_(True))

Isso é mais seguro e legível do que concatenar strings SQL:
    NUNCA: f"SELECT * FROM items WHERE establishment_id = {id}"
           ↑ SQL injection! Nunca interpole valores em strings SQL.

═══════════════════════════════════════════════════════════════
CONCEITO — JOIN no SQLAlchemy para verificar tenant de MenuItem
═══════════════════════════════════════════════════════════════

MenuItem não tem `establishment_id` diretamente. O vínculo é:
    MenuItem.category_id → MenuCategory.id → MenuCategory.establishment_id

Para verificar que um MenuItem pertence a um estabelecimento:

    select(MenuItem)
    .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
    .where(
        MenuItem.id == item_id,
        MenuCategory.establishment_id == establishment_id,
    )

Isso equivale ao SQL:
    SELECT menu_items.*
    FROM menu_items
    JOIN menu_categories ON menu_items.category_id = menu_categories.id
    WHERE menu_items.id = ?
      AND menu_categories.establishment_id = ?

O JOIN garante multi-tenancy SEM precisar de uma coluna extra em MenuItem.

═══════════════════════════════════════════════════════════════
CONCEITO — Paginação com LIMIT/OFFSET
═══════════════════════════════════════════════════════════════

Como funciona paginação?

    Página 1: LIMIT 20 OFFSET 0   → itens 1-20
    Página 2: LIMIT 20 OFFSET 20  → itens 21-40
    Página 3: LIMIT 20 OFFSET 40  → itens 41-60

    Fórmula: offset = (page - 1) * page_size

Por que não é perfeito?
    Se um item for inserido entre a página 1 e a página 2,
    a página 2 vai repetir um item (ou pular um).
    Isso é o "cursor problem" — resolvido com cursor-based pagination.
    Para restaurantes com cardápios estáveis, LIMIT/OFFSET é suficiente.

Para saber o total de páginas:
    total = COUNT(*) com os mesmos filtros
    pages = ceil(total / page_size)

São DUAS queries, mas ambas rápidas com índices adequados.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from app.models.menu import MenuCategory, MenuItem
from app.repositories.base import BaseRepository


class MenuCategoryRepository(BaseRepository[MenuCategory]):
    """
    Repository para categorias do cardápio.

    Gerencia queries de MenuCategory com filtragem por tenant.
    """

    model = MenuCategory

    async def get_by_establishment(
        self,
        category_id: UUID,
        establishment_id: UUID,
    ) -> MenuCategory | None:
        """
        Busca uma categoria pelo ID, verificando que pertence ao estabelecimento.

        Multi-tenancy em ação: mesmos dois filtros que usamos em Table.
        A categoria só é retornada se pertencer ao tenant correto.
        """
        stmt = (
            select(MenuCategory)
            .where(
                MenuCategory.id == category_id,
                MenuCategory.establishment_id == establishment_id,
                MenuCategory.deleted_at.is_(None),  # não retorna deletadas
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_establishment(
        self,
        establishment_id: UUID,
        *,
        active_only: bool = True,
    ) -> list[MenuCategory]:
        """
        Lista categorias de um estabelecimento.

        Filtros:
            deleted_at IS NULL → exclui categorias soft-deletadas
            is_active = True   → (opcional) só categorias ativas

        Ordenação: sort_order ASC, depois name ASC para desempate.
        Isso garante que a ordem seja sempre previsível.
        """
        filters = [
            MenuCategory.establishment_id == establishment_id,
            MenuCategory.deleted_at.is_(None),
        ]
        if active_only:
            filters.append(MenuCategory.is_active.is_(True))

        stmt = (
            select(MenuCategory)
            .where(*filters)
            .order_by(MenuCategory.sort_order, MenuCategory.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(
        self,
        name: str,
        establishment_id: UUID,
    ) -> MenuCategory | None:
        """
        Busca categoria por nome (case-sensitive) dentro de um estabelecimento.

        Usado ANTES de criar uma nova categoria para verificar duplicidade.

        Por que incluir deleted_at IS NULL?
            Uma categoria deletada "Bebidas" não deveria bloquear a criação
            de uma nova categoria "Bebidas". O nome fica "livre" após o soft delete.
            Isso é uma decisão de negócio — alguns sistemas podem querer diferente.
        """
        stmt = (
            select(MenuCategory)
            .where(
                MenuCategory.name == name,
                MenuCategory.establishment_id == establishment_id,
                MenuCategory.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MenuItemRepository(BaseRepository[MenuItem]):
    """
    Repository para itens do cardápio.

    MenuItem não tem establishment_id diretamente — o vínculo
    é via MenuCategory. Por isso, muitos métodos fazem JOIN.
    """

    model = MenuItem

    async def get_by_establishment(
        self,
        item_id: UUID,
        establishment_id: UUID,
    ) -> MenuItem | None:
        """
        Busca um item pelo ID, verificando que pertence ao estabelecimento.

        CONCEITO — JOIN para multi-tenancy indireta:
            MenuItem não tem establishment_id.
            Para verificar o tenant, fazemos JOIN com MenuCategory:

            SELECT menu_items.*
            FROM menu_items
            JOIN menu_categories ON menu_items.category_id = menu_categories.id
            WHERE menu_items.id = ?
              AND menu_items.deleted_at IS NULL
              AND menu_categories.establishment_id = ?
              AND menu_categories.deleted_at IS NULL

            Isso é o mesmo padrão usado em order_repository.get_available_menu_item().
        """
        stmt = (
            select(MenuItem)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(
                MenuItem.id == item_id,
                MenuItem.deleted_at.is_(None),
                MenuCategory.establishment_id == establishment_id,
                MenuCategory.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_establishment(
        self,
        establishment_id: UUID,
        *,
        category_id: UUID | None = None,
        active_only: bool = True,
        available_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MenuItem]:
        """
        Lista itens do cardápio com filtros combinados.

        CONSTRUÇÃO CONDICIONAL DE QUERY:
            Começamos com os filtros base (tenant + não deletado).
            Adicionamos filtros opcionais condicionalmente.
            O SQLAlchemy vai gerar o SQL correto para cada combinação.

        FILTROS DISPONÍVEIS:
            category_id  → só itens desta categoria
            active_only  → só itens ativos (is_active=True)
            available_only → só itens disponíveis (is_available=True)

        ORDENAÇÃO: sort_order ASC dentro da categoria, depois name ASC.
        """
        filters = [
            MenuCategory.establishment_id == establishment_id,
            MenuCategory.deleted_at.is_(None),
            MenuItem.deleted_at.is_(None),
        ]

        if category_id is not None:
            filters.append(MenuItem.category_id == category_id)

        if active_only:
            filters.append(MenuItem.is_active.is_(True))

        if available_only:
            filters.append(MenuItem.is_available.is_(True))

        stmt = (
            select(MenuItem)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(*filters)
            .order_by(MenuCategory.sort_order, MenuItem.sort_order, MenuItem.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_establishment(
        self,
        establishment_id: UUID,
        *,
        category_id: UUID | None = None,
        active_only: bool = True,
    ) -> int:
        """
        Conta itens para paginação.

        Deve usar OS MESMOS filtros de list_by_establishment para que
        o total corresponda à lista retornada.
        """
        filters = [
            MenuCategory.establishment_id == establishment_id,
            MenuCategory.deleted_at.is_(None),
            MenuItem.deleted_at.is_(None),
        ]

        if category_id is not None:
            filters.append(MenuItem.category_id == category_id)

        if active_only:
            filters.append(MenuItem.is_active.is_(True))

        stmt = (
            select(func.count())
            .select_from(MenuItem)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(*filters)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_name_in_category(
        self,
        name: str,
        category_id: UUID,
    ) -> MenuItem | None:
        """
        Verifica se já existe um item com esse nome nesta categoria.

        Usado antes de criar ou renomear um item.
        Nomes duplicados na mesma categoria confundem garçons e clientes.

        Por que não verificar por establishment?
            "Coca-Cola 350ml" pode existir na categoria "Bebidas Frias"
            e também em "Bebidas do Happy Hour" — são itens diferentes.
            A unicidade é por CATEGORIA, não por estabelecimento.
        """
        stmt = (
            select(MenuItem)
            .where(
                MenuItem.name == name,
                MenuItem.category_id == category_id,
                MenuItem.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete_all_in_category(self, category_id: UUID) -> int:
        """
        Soft-deleta todos os itens ativos de uma categoria.

        Chamado quando a CATEGORIA é deletada, para garantir que
        seus itens não fiquem "órfãos" visíveis nas listagens.

        CONCEITO — Cascade Soft Delete:
            Quando deletamos a categoria "Bebidas" (soft delete):
                1. MenuCategory.deleted_at = now()
                2. Todos os seus MenuItem.deleted_at = now()

            Os itens desaparecem junto com a categoria.
            Não ficam "pendurados" sem categoria visível.

        Por que não CASCADE automático no banco?
            O banco tem ON DELETE CASCADE, mas isso é para DELETE FÍSICO.
            Soft delete é uma lógica de aplicação — o banco não sabe disso.
            Precisamos fazer o cascade manualmente no código.

        RETORNA: quantidade de itens que foram soft-deletados.
        """
        stmt = (
            select(MenuItem)
            .where(
                MenuItem.category_id == category_id,
                MenuItem.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        now = datetime.now(UTC)
        for item in items:
            item.deleted_at = now

        await self.session.flush()
        return len(items)
