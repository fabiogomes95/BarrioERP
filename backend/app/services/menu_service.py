"""
app/services/menu_service.py

Regras de negócio para o módulo de cardápio.

═══════════════════════════════════════════════════════════════
CONCEITO — Como ERP mantém histórico consistente
═══════════════════════════════════════════════════════════════

Um ERP (Enterprise Resource Planning) precisa responder perguntas
sobre o passado, o presente e às vezes o futuro.

PASSADO: "Qual foi o faturamento com hamburgueres em março?"
    Resposta correta: precisa dos preços NAQUELE MOMENTO
    Solução: OrderItem armazena snapshot (item_name, unit_price)

PRESENTE: "Qual é o preço atual do hamburguer?"
    Resposta simples: MenuItem.price

FUTURO: "Se eu mudar o preço, quanto impacta a receita?"
    Não implementado — analytics avançado

A SEPARAÇÃO que permite isso:
    MenuItem → estado ATUAL do produto
    OrderItem → estado no MOMENTO DO PEDIDO (snapshot imutável)

Quando o gerente muda o preço do hamburguer de R$25 para R$28:
    MenuItem.price = 28.00  ← muda aqui
    Todos os OrderItems históricos → continuam com unit_price=25.00

Essa separação é FUNDAMENTAL para integridade histórica.

═══════════════════════════════════════════════════════════════
CONCEITO — Relacionamento Categoria → Itens no ORM
═══════════════════════════════════════════════════════════════

No model MenuCategory:
    items: Mapped[list["MenuItem"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

No model MenuItem:
    category: Mapped[MenuCategory] = relationship(back_populates="items")

Isso define:
    - Uma categoria TEM MUITOS itens (1:N)
    - Cada item PERTENCE A UMA categoria (N:1)
    - cascade="all, delete-orphan" → se a categoria for deletada FISICAMENTE,
      os itens dela também são deletados. (Não afeta soft delete.)

NO NOSSO CASO (soft delete):
    Não usamos essa cascata automática do ORM.
    Fazemos a cascata MANUALMENTE no service (soft_delete_all_in_category).
    Motivo: precisamos controlar exatamente quando e como os itens desaparecem.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que não há VersionMixin no cardápio?
═══════════════════════════════════════════════════════════════

VersionMixin foi usado em Order e Table porque:
    - Ordens são editadas FREQUENTEMENTE (items adicionados, status alterado)
    - Mesas são editadas CONCORRENTEMENTE (múltiplos garçons)
    - Um conflito de edição tem impacto financeiro ou operacional imediato

MenuCategory e MenuItem NÃO têm VersionMixin porque:
    - Cardápios são editados RARAMENTE (uma vez por dia, no máximo)
    - Raramente há edição concorrente (um gerente edita por vez)
    - Um conflito de edição tem impacto baixo (preço atualizado por quem?)

Se dois gerentes editassem o preço do hamburguer ao mesmo tempo:
    Último a salvar vence (last-write-wins).
    Não é ideal, mas é aceitável para dados de catálogo.

Para um sistema enterprise com múltiplos gerentes editando o cardápio
simultaneamente: adicionar VersionMixin à migração e ao model.
Para nosso caso: não é necessário agora.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    TenantError,
)
from app.models.menu import MenuCategory, MenuItem
from app.repositories.menu_repository import MenuCategoryRepository, MenuItemRepository
from app.schemas.common import PaginatedResponse
from app.schemas.menu import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from app.services.base import BaseService


class MenuService(BaseService):
    """
    Service do cardápio — gerencia categorias e itens.

    Usa dois repositories:
        _category_repo → operações em menu_categories
        _item_repo     → operações em menu_items (com JOINs)

    Ambos compartilham a mesma `session` → mesma transação.
    """

    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        self._category_repo = MenuCategoryRepository(session)
        self._item_repo = MenuItemRepository(session)

    # ── Helper ────────────────────────────────────────────────────────────────

    def _require_establishment(self) -> UUID:
        """Exige que o usuário esteja vinculado a um estabelecimento."""
        if self.establishment_id is None:
            raise TenantError(
                "Usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário para gerenciar o cardápio."
            )
        return self.establishment_id

    # ══════════════════════════════════════════════════════════════
    # CATEGORIAS
    # ══════════════════════════════════════════════════════════════

    async def create_category(self, data: CategoryCreate) -> CategoryResponse:
        """
        Cria uma nova categoria no cardápio.

        REGRAS:
            - Usuário deve ter establishment_id no JWT
            - Nome deve ser único no estabelecimento (não deletado)

        Por que verificar unicidade de nome?
            "Bebidas" e "Bebidas" na mesma lista confundem clientes e garçons.
            O gerente provavelmente fez um cadastro duplicado por engano.
            → ConflictError com mensagem clara.
        """
        establishment_id = self._require_establishment()

        # Verifica nome único neste estabelecimento
        existing = await self._category_repo.get_by_name(data.name, establishment_id)
        if existing is not None:
            raise ConflictError(
                f"Já existe uma categoria com o nome '{data.name}' neste cardápio."
            )

        category = MenuCategory(
            establishment_id=establishment_id,
            name=data.name,
            description=data.description,
            sort_order=data.sort_order,
            is_active=True,
        )
        category = await self._category_repo.add(category)
        return CategoryResponse.model_validate(category)

    async def list_categories(
        self,
        *,
        active_only: bool = True,
    ) -> list[CategoryResponse]:
        """
        Lista categorias do estabelecimento.

        Por padrão, retorna apenas categorias ATIVAS.
        Para ver categorias inativas: active_only=False (útil para o gerente).

        Por que retornar lista simples (não paginada)?
            Restaurantes raramente têm mais de 20-30 categorias.
            Paginação aqui seria over-engineering.
            A lista completa é carregada de uma vez — simples e eficiente.

        ORDENAÇÃO: sort_order ASC, depois name ASC.
        """
        establishment_id = self._require_establishment()
        categories = await self._category_repo.list_by_establishment(
            establishment_id,
            active_only=active_only,
        )
        return [CategoryResponse.model_validate(c) for c in categories]

    async def update_category(
        self,
        category_id: UUID,
        data: CategoryUpdate,
    ) -> CategoryResponse:
        """
        Atualiza campos de uma categoria.

        PATCH parcial: só atualiza campos enviados (exclude_unset=True).
        Sem locking otimista — catálogos não têm VersionMixin.

        CONCEITO — last-write-wins:
            Sem VersionMixin, se dois usuários editarem ao mesmo tempo:
            O último a salvar prevalece. Para catálogos, isso é aceitável.
            Para transações financeiras, isso seria perigoso (daí o VersionMixin).
        """
        establishment_id = self._require_establishment()

        category = await self._category_repo.get_by_establishment(
            category_id, establishment_id
        )
        if category is None:
            raise NotFoundError("MenuCategory", category_id)

        # Se o nome está sendo alterado, verifica unicidade
        if data.name is not None and data.name != category.name:
            existing = await self._category_repo.get_by_name(
                data.name, establishment_id
            )
            if existing is not None:
                raise ConflictError(
                    f"Já existe uma categoria com o nome '{data.name}' neste cardápio."
                )

        # Aplica apenas os campos que foram enviados
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(category, field, value)

        await self.session.flush()
        await self.session.refresh(category)
        return CategoryResponse.model_validate(category)

    async def delete_category(self, category_id: UUID) -> None:
        """
        Soft-deleta uma categoria e TODOS os seus itens ativos (cascade).

        FLUXO:
            1. Busca a categoria (verifica tenant)
            2. Soft-deleta todos os itens da categoria (cascade)
            3. Soft-deleta a categoria em si
            4. Flush — tudo na mesma transação

        CONCEITO — Por que não apenas desativar?
            is_active=False → item inativo mas ainda existe no banco
            deleted_at=now() → item "removido" do sistema

            Deletar (soft) é definitivo — o gerente decidiu remover.
            Desativar é temporário — o gerente vai reativar depois.
            Semanticamente diferentes, tratados diferente.

        CONCEITO — Cascade manual:
            O banco tem ON DELETE CASCADE para delete físico.
            Soft delete não ativa o CASCADE do banco.
            Fazemos a cascata manualmente via soft_delete_all_in_category().
            Tudo na mesma transação — ou tudo é deletado, ou nada.

        LANÇA:
            NotFoundError (404) → categoria não encontrada
        """
        establishment_id = self._require_establishment()

        category = await self._category_repo.get_by_establishment(
            category_id, establishment_id
        )
        if category is None:
            raise NotFoundError("MenuCategory", category_id)

        # Cascade: soft-deleta os itens da categoria ANTES da categoria
        items_deleted = await self._item_repo.soft_delete_all_in_category(category_id)

        # Soft-deleta a categoria
        category.soft_delete()
        await self.session.flush()

        # Log para debugging/auditoria (não persiste, só para visibilidade)
        # Em produção: registrar no AuditLog com items_deleted count
        _ = items_deleted  # suprime warning de variável não usada

    # ══════════════════════════════════════════════════════════════
    # ITENS DO CARDÁPIO
    # ══════════════════════════════════════════════════════════════

    async def create_item(self, data: MenuItemCreate) -> MenuItemResponse:
        """
        Cria um novo item no cardápio.

        REGRAS:
            - Categoria deve existir e pertencer ao estabelecimento
            - Nome deve ser único dentro da categoria
            - Preço deve ser positivo (validado no schema)

        Por que verificar que a categoria pertence ao establishment?
            Multi-tenancy: o usuário não pode criar itens numa categoria
            de outro restaurante, mesmo que conheça o UUID dela.

        CONCEITO — Preço imutável histórico:
            O preço cadastrado aqui é o preço ATUAL.
            Mudar o preço no futuro (PATCH) não altera pedidos passados.
            Isso é garantido pelo snapshot no OrderItem.
        """
        establishment_id = self._require_establishment()

        # Verifica que a categoria existe e pertence ao establishment
        category = await self._category_repo.get_by_establishment(
            data.category_id, establishment_id
        )
        if category is None:
            raise NotFoundError("MenuCategory", data.category_id)

        if not category.is_active:
            raise BusinessRuleError(
                f"A categoria '{category.name}' está inativa. "
                "Ative a categoria antes de adicionar itens."
            )

        # Verifica unicidade de nome dentro da categoria
        existing = await self._item_repo.get_by_name_in_category(
            data.name, data.category_id
        )
        if existing is not None:
            raise ConflictError(
                f"Já existe um item com o nome '{data.name}' nesta categoria."
            )

        item = MenuItem(
            category_id=data.category_id,
            name=data.name,
            description=data.description,
            price=data.price,
            sort_order=data.sort_order,
            is_active=True,
            is_available=True,  # novo item começa disponível por padrão
        )
        item = await self._item_repo.add(item)
        return MenuItemResponse.model_validate(item)

    async def list_items(
        self,
        *,
        category_id: UUID | None = None,
        active_only: bool = True,
        available_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse:
        """
        Lista itens do cardápio com filtros e paginação.

        FILTROS COMBINADOS:
            category_id  → filtra por categoria específica
            active_only  → só itens ativos (padrão: True)
            available_only → só itens disponíveis (padrão: False — ver todos)
            page/page_size → paginação

        CASO DE USO TÍPICO (garçom tomando pedido):
            GET /menu/items?active_only=true&available_only=true
            → Só itens que existem E estão disponíveis agora

        CASO DE USO GERENTE (editando cardápio):
            GET /menu/items?active_only=false
            → Todos os itens, inclusive inativos

        CASO DE USO POR CATEGORIA:
            GET /menu/items?category_id=X
            → Só itens da categoria X

        Para listar todos os itens sem paginação:
            Use page_size=1000 (ou implemente um endpoint específico).
            Para cardápios de restaurante (< 200 itens), isso é aceitável.

        RETORNA: PaginatedResponse com lista de MenuItemResponse.
        """
        establishment_id = self._require_establishment()
        offset = (page - 1) * page_size

        # Se category_id for fornecido, verifica que pertence ao establishment
        if category_id is not None:
            category = await self._category_repo.get_by_establishment(
                category_id, establishment_id
            )
            if category is None:
                raise NotFoundError("MenuCategory", category_id)

        items = await self._item_repo.list_by_establishment(
            establishment_id,
            category_id=category_id,
            active_only=active_only,
            available_only=available_only,
            limit=page_size,
            offset=offset,
        )
        total = await self._item_repo.count_by_establishment(
            establishment_id,
            category_id=category_id,
            active_only=active_only,
        )
        pages = max(1, (total + page_size - 1) // page_size)

        return PaginatedResponse(
            items=[MenuItemResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_item(self, item_id: UUID) -> MenuItemResponse:
        """
        Retorna um item específico do cardápio.

        Multi-tenancy: item só é retornado se pertencer ao estabelecimento
        do usuário logado (verificado via JOIN com MenuCategory).

        RETORNA: MenuItemResponse.
        LANÇA: NotFoundError (404) se não encontrado ou de outro tenant.
        """
        establishment_id = self._require_establishment()

        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("MenuItem", item_id)

        return MenuItemResponse.model_validate(item)

    async def update_item(
        self,
        item_id: UUID,
        data: MenuItemUpdate,
    ) -> MenuItemResponse:
        """
        Atualiza campos de um item do cardápio.

        PATCH parcial: só atualiza campos enviados (exclude_unset=True).

        CASOS ESPECIAIS:
            1. Renomear item: verifica unicidade na categoria atual
            2. Mover de categoria: verifica que nova categoria é do mesmo tenant
            3. Renomear E mover: verifica na nova categoria

        ATUALIZAÇÃO DE PREÇO:
            Muda apenas o preço ATUAL do item.
            Não retroativo — pedidos passados mantêm o preço da época (snapshot).
            Este é o comportamento CORRETO para sistemas financeiros.

        ATIVAR/DESATIVAR:
            is_active=False → item some do cardápio (não pode ser pedido)
            is_active=True  → item volta ao cardápio
            is_available=False → item existe mas está esgotado hoje
        """
        establishment_id = self._require_establishment()

        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("MenuItem", item_id)

        # Determina a categoria alvo (atual ou nova)
        target_category_id = data.category_id if data.category_id else item.category_id

        # Se estiver mudando de categoria, verifica que a nova pertence ao tenant
        if data.category_id is not None and data.category_id != item.category_id:
            new_category = await self._category_repo.get_by_establishment(
                data.category_id, establishment_id
            )
            if new_category is None:
                raise NotFoundError("MenuCategory", data.category_id)

        # Se o nome está sendo alterado (ou movendo de categoria), verifica unicidade
        new_name = data.name if data.name is not None else item.name
        name_changed = data.name is not None and data.name != item.name
        category_changed = data.category_id is not None and data.category_id != item.category_id

        if name_changed or category_changed:
            existing = await self._item_repo.get_by_name_in_category(
                new_name, target_category_id
            )
            # Só conflita se existir outro item (não o próprio item sendo editado)
            if existing is not None and existing.id != item.id:
                raise ConflictError(
                    f"Já existe um item com o nome '{new_name}' nesta categoria."
                )

        # Aplica apenas os campos que foram enviados
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        await self.session.flush()
        await self.session.refresh(item)
        return MenuItemResponse.model_validate(item)

    async def delete_item(self, item_id: UUID) -> None:
        """
        Soft-deleta um item do cardápio.

        COMPORTAMENTO:
            item.deleted_at = now()
            item some das listagens (deleted_at IS NULL nas queries)
            item NÃO é apagado fisicamente do banco

        SEGURANÇA HISTÓRICA:
            OrderItems existentes que referenciam este item:
                menu_item_id → ainda aponta para o registro (não nulo)
            O snapshot (item_name, unit_price) no OrderItem é preservado.
            Mesmo que o item seja deletado, o histórico de pedidos está intacto.

        Se o item fosse deletado FISICAMENTE:
            ON DELETE SET NULL → menu_item_id vira NULL nos OrderItems
            O snapshot ainda preserva nome/preço — sem perda financeira.
            Mas a referência ao cardápio seria perdida.
            Por isso, SOFT DELETE é a escolha certa.

        LANÇA:
            NotFoundError (404) → item não encontrado ou de outro tenant
        """
        establishment_id = self._require_establishment()

        item = await self._item_repo.get_by_establishment(item_id, establishment_id)
        if item is None:
            raise NotFoundError("MenuItem", item_id)

        item.soft_delete()  # método do SoftDeleteMixin: deleted_at = now()
        await self.session.flush()
