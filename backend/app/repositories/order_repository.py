"""
app/repositories/order_repository.py

Acesso ao banco para Order e OrderItem.

═══════════════════════════════════════════════════════════════
CONCEITO — Lazy Loading vs Eager Loading
═══════════════════════════════════════════════════════════════

Este é um dos conceitos mais importantes do SQLAlchemy.

LAZY LOADING (carregamento preguiçoso — padrão):
    O SQLAlchemy só carrega o relacionamento quando você ACESSA.

    order = await session.get(Order, order_id)
    # Até aqui: apenas a linha da tabela `orders` foi carregada

    print(order.items)  # AQUI ocorreria uma nova query ao banco!
    # → "SELECT * FROM order_items WHERE order_id = ?"

    PROBLEMA no async: o SQLAlchemy async NÃO suporta lazy loading!
    Tentar acessar order.items fora de um contexto async vai falhar
    com MissingGreenlet ou um AttributeError misterioso.

EAGER LOADING (carregamento antecipado — o que usamos aqui):
    Carregamos os relacionamentos na MESMA query, ou em query separada
    mas ainda dentro do mesmo bloco async.

    Existem duas estratégias:

    1. selectinload(Order.items):
        Faz DUAS queries:
            SELECT * FROM orders WHERE id = ?          ← query 1
            SELECT * FROM order_items WHERE order_id IN (ids)  ← query 2

        Vantagem: não faz JOIN, melhor para listas de muitos itens.
        Desvantagem: sempre 2 queries, mesmo que não haja itens.

    2. joinedload(Order.items):
        Faz UMA query com JOIN:
            SELECT orders.*, order_items.* FROM orders
            LEFT OUTER JOIN order_items ON order_items.order_id = orders.id
            WHERE orders.id = ?

        Vantagem: uma única query.
        Desvantagem: retorna linhas duplicadas para orders (N×M rows).
        Melhor para relacionamentos 1:1 ou poucos itens.

    REGRA GERAL:
        - 1:N com potencialmente muitos itens → selectinload
        - 1:1 ou N:1 → joinedload ou joined()

    Usamos selectinload(Order.items) porque uma comanda pode ter
    muitos itens (10, 20, 50 itens) e joinedload multiplicaria as linhas.

═══════════════════════════════════════════════════════════════
CONCEITO — Como o SQLAlchemy faz JOINs via relacionamentos
═══════════════════════════════════════════════════════════════

No model Order, declaramos:
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

E no OrderItem:
    order: Mapped[Order] = relationship(back_populates="items")

Com isso, o SQLAlchemy sabe:
    - Order tem uma lista de OrderItems
    - Cada OrderItem tem um Order pai
    - A chave de ligação é OrderItem.order_id → Order.id

Quando escrevemos `.options(selectinload(Order.items))`, estamos dizendo:
    "Ao carregar esta Order, também carregue os OrderItems relacionados
     fazendo uma segunda query automática."

═══════════════════════════════════════════════════════════════
CONCEITO — Por que verificamos o tenant em cada query?
═══════════════════════════════════════════════════════════════

Multi-tenancy: cada estabelecimento vê apenas seus próprios dados.

Em `get_with_items(order_id, establishment_id)`:
    WHERE orders.id = ? AND orders.establishment_id = ?

Se um garçom do Restaurante A enviar o UUID de uma comanda do Restaurante B:
    → O WHERE retorna 0 linhas → None → NotFoundError → HTTP 404
    → Ele não sabe que a comanda existe → segurança por obscuridade

NUNCA faça: get(order_id) e depois cheque order.establishment_id == establishment_id
    → Isso é inseguro porque você leu o dado antes de verificar a permissão

SEMPRE faça: inclua a verificação de tenant no WHERE da query.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.menu import MenuCategory, MenuItem
from app.models.order import Order, OrderItem, OrderStatus
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """
    Repository para Order e operações relacionadas a comandas.

    Herda CRUD genérico de BaseRepository[Order].
    Adiciona queries específicas que precisam de:
        - eager loading (selectinload para order.items)
        - filtro por tenant (establishment_id)
        - lógica de "comanda aberta" (closed_at IS NULL)
    """

    model = Order

    # ── Queries de Order ──────────────────────────────────────────────────────

    async def get_open_by_table(self, table_id: UUID) -> Order | None:
        """
        Busca a comanda ABERTA de uma mesa.

        Uma mesa pode ter no máximo UMA comanda aberta (closed_at IS NULL).
        Se a mesa tiver comanda aberta, não podemos abrir outra.

        Por que filtrar por closed_at IS NULL e não por status?
            closed_at é mais confiável: é um timestamp imutável.
            Status poderia ser alterado incorretamente, mas closed_at só
            recebe valor quando a comanda é fechada de verdade.

        Não carregamos itens aqui — só precisamos saber se EXISTE
        uma comanda aberta. Os itens não importam para essa verificação.

        RETORNA: Order se houver comanda aberta, None se a mesa estiver livre.
        """
        stmt = (
            select(Order)
            .where(
                Order.table_id == table_id,
                Order.closed_at.is_(None),          # comanda não fechada
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_items(
        self,
        order_id: UUID,
        establishment_id: UUID,
    ) -> Order | None:
        """
        Busca uma comanda específica com todos os seus itens carregados.

        MULTI-TENANCY: filtra por establishment_id para garantir isolamento.

        EAGER LOADING: uses selectinload para carregar order.items em
        uma segunda query automática dentro da mesma transação.

        Essa função é usada sempre que precisamos retornar um OrderResponse,
        porque o schema precisa acessar order.items.

        RETORNA: Order com items carregados, ou None se não encontrado/sem permissão.
        """
        stmt = (
            select(Order)
            .where(
                Order.id == order_id,
                Order.establishment_id == establishment_id,
            )
            .options(selectinload(Order.items))     # carrega items em query separada
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_open(
        self,
        establishment_id: UUID,
        *,
        table_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """
        Lista comandas abertas de um estabelecimento com filtro opcional por mesa.

        FILTRO table_id (opcional):
            None        → retorna todas as comandas abertas do estabelecimento
            UUID válido → retorna apenas a comanda aberta daquela mesa

        CASO DE USO DO FILTRO:
            O garçom se aproxima da mesa 5 e quer ver o pedido em andamento.
            GET /orders/open?table_id=uuid-da-mesa-5
            → Retorna lista com 0 ou 1 item (mesa tem no máximo 1 comanda aberta)

            Sem o filtro, o frontend baixaria todas as comandas abertas do salão
            e filtraria no cliente — desnecessário quando só precisa de uma.

        Carrega os itens de cada comanda via selectinload (2 queries no total,
        independente da quantidade de comandas retornadas).

        ORDENAÇÃO por created_at: as mais antigas aparecem primeiro —
        o garçom vê as mesas que esperaram mais no topo da lista.
        """
        filters = [
            Order.establishment_id == establishment_id,
            Order.closed_at.is_(None),
        ]

        # Filtro opcional: se informado, restringe a uma mesa específica
        if table_id is not None:
            filters.append(Order.table_id == table_id)

        stmt = (
            select(Order)
            .where(*filters)
            .options(selectinload(Order.items))
            .order_by(Order.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_closed_between(
        self,
        establishment_id: UUID,
        start,
        end,
    ) -> list[Order]:
        """
        Comandas FECHADAS (closed_at no intervalo [start, end)) com itens e
        pagamentos carregados — base do relatório diário.
        """
        stmt = (
            select(Order)
            .where(
                Order.establishment_id == establishment_id,
                Order.closed_at.is_not(None),
                Order.closed_at >= start,
                Order.closed_at < end,
            )
            .options(selectinload(Order.items), selectinload(Order.payments))
            .order_by(Order.closed_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_closed(
        self,
        establishment_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """Histórico: comandas fechadas mais recentes primeiro (com itens)."""
        stmt = (
            select(Order)
            .where(
                Order.establishment_id == establishment_id,
                Order.closed_at.is_not(None),
            )
            .options(selectinload(Order.items))
            .order_by(Order.closed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self, establishment_id: UUID) -> int:
        """
        Conta comandas abertas para metadados de paginação.

        Separado do list_open para evitar carregar todos os dados
        só para contar — COUNT(*) com índice é muito rápido.
        """
        return await self.count(
            Order.establishment_id == establishment_id,
            Order.closed_at.is_(None),
        )

    # ── Queries de MenuItem (para validação ao adicionar itens) ───────────────

    async def get_available_menu_item(
        self,
        menu_item_id: UUID,
        establishment_id: UUID,
    ) -> MenuItem | None:
        """
        Busca um item do cardápio, validando que:
            1. Existe e não foi deletado (deleted_at IS NULL)
            2. Está ativo (is_active = True)
            3. Está disponível (is_available = True)
            4. Pertence ao estabelecimento correto (JOIN com MenuCategory)

        POR QUE FAZER JOIN COM MENUCAREGORY?
            MenuItem não tem establishment_id diretamente.
            O vínculo é: MenuItem → MenuCategory → Establishment

            Então para verificar se o MenuItem pertence ao estabelecimento,
            precisamos: JOIN menu_categories ON menu_items.category_id = menu_categories.id
            E então: WHERE menu_categories.establishment_id = ?

            Sem esse JOIN, um garçom poderia adicionar pratos de outro restaurante!

        COLOCADO NO OrderRepository porque é uma query de suporte à criação de itens.
        Em um projeto maior, existiria um MenuItemRepository separado.

        RETORNA: MenuItem se válido e disponível, None caso contrário.
        """
        stmt = (
            select(MenuItem)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(
                MenuItem.id == menu_item_id,
                MenuItem.is_active.is_(True),
                MenuItem.is_available.is_(True),
                MenuItem.deleted_at.is_(None),
                MenuCategory.establishment_id == establishment_id,
                MenuCategory.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Queries de OrderItem ───────────────────────────────────────────────────

    async def get_item(self, item_id: UUID, order_id: UUID) -> OrderItem | None:
        """
        Busca um item específico de uma comanda.

        POR QUE FILTRAR POR order_id E NÃO SÓ POR item_id?
            Segurança: um item pertence a uma comanda específica.
            Se filtrarmos só por item_id, um garçom autenticado poderia
            tentar acessar itens de outras comandas com um UUID arbitrário.

            Ao exigir que o item pertença à comanda informada, garantimos
            que o acesso ao item está limitado ao mesmo escopo de acesso
            à comanda — que já foi validada pelo service (pertence ao
            estabelecimento correto) antes deste método ser chamado.

        QUERY GERADA:
            SELECT * FROM order_items
            WHERE id = :item_id
              AND order_id = :order_id
        """
        stmt = (
            select(OrderItem)
            .where(
                OrderItem.id == item_id,
                OrderItem.order_id == order_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
