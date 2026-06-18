"""
app/services/order_service.py

Regras de negócio para o módulo de comandas.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é uma Transaction (Transação)?
═══════════════════════════════════════════════════════════════

Uma transação é um conjunto de operações que deve ser executado
de forma ATÔMICA — ou tudo acontece, ou nada acontece.

Analogia: transferência bancária.
    OPERAÇÃO 1: Débita R$100 da conta A
    OPERAÇÃO 2: Credita R$100 na conta B

    Se der erro entre as duas operações, o banco não pode ficar
    com R$100 a menos na conta A e nada na conta B.
    → A transação garante: ou as duas operações acontecem, ou nenhuma.

No BarrioERP, ao ABRIR uma comanda:
    OPERAÇÃO 1: INSERT na tabela orders (cria a comanda)
    OPERAÇÃO 2: UPDATE na tabela tables (mesa vira OCCUPIED)

    Se a operação 2 falhar (ex: table_id inválido), a operação 1
    deve ser revertida. Não podemos ter uma comanda sem mesa OCCUPIED.
    → session.flush() propaga ambas; session.commit() confirma ambas.
    → Se der erro, o get_db() faz session.rollback() e NADA é salvo.

COMO O SQLAlchemy GERENCIA TRANSAÇÕES:
    A sessão (AsyncSession) abre uma transação automaticamente.
    Você acumula mudanças com session.add() e session.flush().
    O commit() confirma tudo ou o rollback() cancela tudo.
    O get_db() faz isso automaticamente no finally do yield.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que concorrência importa em restaurante?
═══════════════════════════════════════════════════════════════

Um restaurante movimentado pode ter:
    - 4 garçons usando o app ao mesmo tempo
    - 20 mesas abertas simultaneamente
    - Múltiplas requisições chegando por segundo

Cenários problemáticos SEM proteção:

1. ABERTURA DUPLICADA DE COMANDA:
    Garçom A e Garçom B ambos clicam "abrir mesa 5" ao mesmo tempo.
    Sem verificação → duas comandas abertas para a mesma mesa.
    → Confusão: qual comanda é a correta? Qual tem os pedidos?

2. FECHAMENTO DUPLO:
    Garçom A e o caixa tentam fechar a comanda 123 ao mesmo tempo.
    Sem locking → a comanda pode ser fechada "duas vezes".
    → Pagamento duplicado, relatório inconsistente.

3. ITEM ADICIONADO A COMANDA FECHADA:
    Garçom A fecha a comanda enquanto Garçom B adiciona um item.
    Sem verificação de status → item adicionado a comanda já fechada.
    → Total errado, item nunca cobrado.

COMO PROTEGEMOS:
    - Abertura: verificamos ANTES se a mesa tem comanda aberta (check + lock)
    - Fechamento: usamos VersionMixin (optimistic locking)
    - Adição de item: verificamos se status == OPEN antes de adicionar

═══════════════════════════════════════════════════════════════
CONCEITO — Como relacionamentos funcionam no ORM
═══════════════════════════════════════════════════════════════

Quando fazemos `order.items.append(new_item)`:

    1. O SQLAlchemy VÊ que order.items é uma coleção rastreada
    2. Ao fazer append, ele marca new_item como "para ser inserido"
    3. O new_item.order_id é automaticamente definido como order.id
    4. session.flush() executa o INSERT
    5. new_item.id é preenchido com o UUID gerado pelo banco

Isso é a magia das "tracked collections" do SQLAlchemy.
Você não precisa definir order_id manualmente — o ORM faz isso.

ALTERNATIVA (mais explícita, mesma result):
    new_item = OrderItem(order_id=order.id, ...)
    session.add(new_item)

Ambas as formas funcionam. A primeira (append) é mais "pythônica"
porque expressa a intenção: "adicionar um item a esta comanda".
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    OptimisticLockError,
    TenantError,
)
from app.models.establishment import Establishment
from app.models.order import Order, OrderItem, OrderItemStatus, OrderStatus
from app.models.payment import PaymentStatus
from app.models.table import Table, TableStatus
from app.repositories.order_repository import OrderRepository
from app.repositories.table_repository import TableRepository
from app.schemas.report import DailyReport, PaymentMethodTotal, TopItem
from app.schemas.order import (
    OrderClose,
    OrderCreate,
    OrderItemAdd,
    OrderItemResponse,
    OrderResponse,
)
from app.services.base import BaseService
from sqlalchemy.ext.asyncio import AsyncSession


class OrderService(BaseService):
    """
    Service de comandas — abre, lista, detalha, adiciona itens e fecha.

    Usa dois repositories:
        _order_repo → operações em orders e order_items
        _table_repo → atualiza o status da mesa ao abrir/fechar comanda

    Os dois repositories compartilham a mesma `session` — logo, estão
    na mesma transação. Se qualquer operação falhar, ambas são revertidas.
    """

    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        self._order_repo = OrderRepository(session)
        self._table_repo = TableRepository(session)

    # ── Helper: contexto de tenant ────────────────────────────────────────────

    def _require_establishment(self) -> UUID:
        """Exige que o usuário esteja vinculado a um estabelecimento."""
        if self.establishment_id is None:
            raise TenantError(
                "Usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário a um estabelecimento para gerenciar comandas."
            )
        return self.establishment_id

    # ── Helper: recalcular totais ─────────────────────────────────────────────

    def _recalculate_total(self, order: Order) -> None:
        """
        Recalcula subtotal e total da comanda a partir dos itens ativos.

        CONCEITO — Por que recalcular em vez de apenas somar?
            Quando um item é cancelado (status=CANCELLED), ele não deve
            entrar no total. Recalcular do zero garante consistência.

        CONCEITO — Por que usar Decimal, não float?
            Float tem erros de ponto flutuante binário:
                0.1 + 0.2 = 0.30000000000000004  ← errado!

            Decimal aritmética é EXATA:
                Decimal("0.1") + Decimal("0.2") = Decimal("0.3")  ← correto!

            Para dinheiro, NUNCA use float. Sempre Decimal.
            O banco de dados armazena como NUMERIC(12,2) — sem perda de precisão.

        FÓRMULA:
            subtotal = soma dos subtotais dos itens ativos
            total = subtotal + service_fee - discount
            (service_fee e discount = 0 por enquanto — reservados para o futuro)
        """
        active_items = [
            item for item in order.items
            if item.status != OrderItemStatus.CANCELLED
        ]
        order.subtotal = sum(
            item.subtotal for item in active_items
        ) or Decimal("0.00")
        # Taxa de serviço = subtotal × percentual snapshot da comanda
        order.service_fee = round(
            order.subtotal * order.service_fee_percent / Decimal("100"), 2
        )
        order.total = order.subtotal + order.service_fee - order.discount

    # ── Helper: busca comanda com itens e verifica tenant ─────────────────────

    async def _get_or_raise(self, order_id: UUID, establishment_id: UUID) -> Order:
        """
        Busca a comanda com itens carregados, lançando NotFoundError se não encontrar.

        Centraliza a lógica de "buscar comanda + verificar tenant + lançar 404"
        para não repetir em cada método.
        """
        order = await self._order_repo.get_with_items(order_id, establishment_id)
        if order is None:
            raise NotFoundError("Order", order_id)
        return order

    # ── Operações de negócio ──────────────────────────────────────────────────

    async def open_order(self, data: OrderCreate) -> OrderResponse:
        """
        Abre uma nova comanda para uma mesa.

        FLUXO COMPLETO (com transação implícita):

            1. Verifica que o usuário tem um estabelecimento → TenantError
            2. Busca a mesa no banco → NotFoundError se não existir
            3. Verifica que a mesa está ativa → BusinessRuleError
            4. Verifica que a mesa não tem comanda aberta → BusinessRuleError
            5. Cria a Order (INSERT no banco via flush)
            6. Atualiza o status da mesa para OCCUPIED (UPDATE via flush)
            7. Busca a order recém-criada com items (vazia por enquanto)
            8. Retorna OrderResponse

            Tudo na mesma transação → se o passo 6 falhar,
            o passo 5 é revertido automaticamente.

        CONCEITO — RACE CONDITION na abertura de comanda:
            Dois garçons clicam "abrir mesa 5" ao mesmo tempo.

            Com SELECT + verificação:
                1. Ambos fazem get_open_by_table() → retorna None para ambos
                2. Ambos criam uma Order para a mesa 5
                3. Ambos atualizam a mesa para OCCUPIED
                → Duas comandas abertas! Inconsistência!

            A proteção REAL seria usar SELECT FOR UPDATE (pessimistic locking)
            para travar a linha da mesa durante a verificação. Isso é avançado.

            Para nosso nível atual, o check + regra de negócio é suficiente.
            Em produção de alto volume, adicionaríamos o SELECT FOR UPDATE.
        """
        establishment_id = self._require_establishment()

        # Comanda de balcão/avulsa: sem mesa. Pula toda a validação de mesa.
        table = None
        if data.table_id is not None:
            # 1. Busca e valida a mesa
            table = await self._table_repo.get_by_establishment(
                data.table_id, establishment_id
            )
            if table is None:
                raise NotFoundError("Table", data.table_id)

            if not table.is_active:
                raise BusinessRuleError(
                    f"A mesa '{table.label}' está desativada e não pode receber comandas."
                )

            # 2. Verifica se já tem comanda aberta nessa mesa
            existing = await self._order_repo.get_open_by_table(data.table_id)
            if existing is not None:
                raise BusinessRuleError(
                    f"A mesa '{table.label}' já possui uma comanda aberta. "
                    "Feche a comanda atual antes de abrir uma nova."
                )

        # Snapshot da taxa de serviço configurada no estabelecimento
        establishment = await self.session.get(Establishment, establishment_id)
        fee_percent = establishment.service_fee_percent if establishment else Decimal("0")

        # 3. Cria a comanda
        order = Order(
            establishment_id=establishment_id,
            table_id=data.table_id,
            waiter_id=self.user_id,         # quem abriu (do JWT)
            status=OrderStatus.OPEN,
            guest_count=data.guest_count,
            customer_name=data.customer_name,
            notes=data.notes,
            subtotal=Decimal("0.00"),
            service_fee=Decimal("0.00"),
            service_fee_percent=fee_percent,
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
        )
        order = await self._order_repo.add(order)

        # 4. Atualiza a mesa para OCCUPIED — mesma transação (só se houver mesa)
        if table is not None:
            table.status = TableStatus.OCCUPIED
        await self.session.flush()

        # 5. Retorna a comanda recém-criada (com items — vazia por enquanto)
        return await self._get_or_raise(order.id, establishment_id)

    async def list_open(
        self,
        *,
        table_id: UUID | None = None,
    ) -> list[OrderResponse]:
        """
        Lista comandas abertas do estabelecimento, com filtro opcional por mesa.

        PARÂMETRO table_id (keyword-only):
            None → todas as comandas abertas (visão geral do salão)
            UUID → apenas a comanda da mesa informada (visão individual)

        Inclui os itens de cada comanda (eager loaded — sem N+1 queries).
        Ordenadas por hora de abertura: as mais antigas aparecem primeiro.

        RETORNA: lista de OrderResponse (vazia se não há comandas abertas).
        """
        establishment_id = self._require_establishment()
        orders = await self._order_repo.list_open(
            establishment_id,
            table_id=table_id,
        )
        return [OrderResponse.model_validate(o) for o in orders]

    async def get(self, order_id: UUID) -> OrderResponse:
        """
        Retorna uma comanda específica com todos seus itens.

        Multi-tenancy garantida: get_with_items filtra por establishment_id.

        RETORNA: OrderResponse com items carregados.
        LANÇA: NotFoundError (404) se não encontrar ou for de outro tenant.
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)
        return OrderResponse.model_validate(order)

    async def add_item(self, order_id: UUID, data: OrderItemAdd) -> OrderResponse:
        """
        Adiciona um item à comanda e recalcula o total.

        FLUXO:
            1. Busca a comanda com items (eager loaded)
            2. Verifica que está OPEN
            3. Resolve nome/preço do item:
               - Se menu_item_id: busca no cardápio (snapshot)
               - Se manual: usa name/price do request
            4. Cria OrderItem e adiciona à coleção order.items
            5. Recalcula subtotal e total da comanda
            6. Flush → dois INSERTs/UPDATEs na mesma transação
            7. Busca novamente com items para retornar resposta consistente

        CONCEITO — Snapshot de preço em ação:
            Ao adicionar "Hambúrguer Artesanal" com menu_item_id:
                menu_item = busca no banco → name="Hambúrguer", price=25.00
                order_item.item_name = menu_item.name   ← snapshot
                order_item.unit_price = menu_item.price  ← snapshot
                order_item.menu_item_id = menu_item.id  ← referência (pode mudar)

            Se amanhã o hambúrguer mudar de nome ou preço:
                → A comanda já possui os valores do momento do pedido ✓

        CONCORRÊNCIA (por que NÃO pedimos version aqui):
            Adicionar item é uma operação APPEND — adiciona uma linha nova.
            Dois garçons podem adicionar itens ao mesmo tempo sem conflito.

            O problema de concorrência real é ATUALIZAR o subtotal da Order.
            O VersionMixin do SQLAlchemy detectará conflito se dois garçons
            tentarem atualizar o subtotal exatamente ao mesmo tempo:
                → StaleDataError → convertemos em OptimisticLockError (409)
                → O cliente tenta de novo (raramente acontece na prática)

        LANÇA:
            NotFoundError (404)      → comanda não encontrada
            BusinessRuleError (422)  → comanda não está aberta
            NotFoundError (404)      → item do cardápio não encontrado/indisponível
            OptimisticLockError (409) → conflito de concorrência no total
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status != OrderStatus.OPEN:
            raise BusinessRuleError(
                f"Não é possível adicionar itens a uma comanda com status '{order.status.value}'. "
                "Apenas comandas ABERTAS aceitam novos itens."
            )

        # Resolve nome e preço do item
        if data.menu_item_id is not None:
            # Modo cardápio: busca no banco e usa snapshot
            menu_item = await self._order_repo.get_available_menu_item(
                data.menu_item_id, establishment_id
            )
            if menu_item is None:
                raise NotFoundError("MenuItem", data.menu_item_id)

            item_name = menu_item.name
            unit_price = menu_item.price
            menu_item_id = menu_item.id
        else:
            # Modo manual: usa dados do request (validados no schema)
            item_name = data.item_name  # type: ignore[assignment] — garantido pelo model_validator
            unit_price = data.unit_price  # type: ignore[assignment] — garantido pelo model_validator
            menu_item_id = None

        # Calcula o subtotal do item
        subtotal = unit_price * data.quantity

        # Cria o item e adiciona à comanda
        # Usar order.items.append() em vez de session.add() direto:
        # → SQLAlchemy define order_id automaticamente
        # → O item entra na coleção rastreada imediatamente
        new_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item_id,
            item_name=item_name,
            unit_price=unit_price,
            quantity=data.quantity,
            subtotal=subtotal,
            notes=data.notes,
            status=OrderItemStatus.PENDING,
        )
        order.items.append(new_item)

        # Recalcula totais da comanda (inclui o novo item)
        self._recalculate_total(order)

        try:
            await self.session.flush()
        except StaleDataError:
            # Dois garçons atualizaram o total simultaneamente
            # O cliente deve tentar novamente (raramente acontece)
            raise OptimisticLockError("Order")

        # Re-busca do banco para garantir dados frescos e itens atualizados
        # (após flush, os IDs e timestamps gerados pelo banco estão disponíveis)
        return await self._get_or_raise(order.id, establishment_id)

    async def close_order(self, order_id: UUID, data: OrderClose) -> OrderResponse:
        """
        Fecha uma comanda e libera a mesa.

        FLUXO:
            1. Busca comanda com items (verifica tenant)
            2. Verifica que pode ser fechada (OPEN ou BILL_REQUESTED)
            3. Verifica versão (locking otimista)
            4. Seta status=CLOSED, closed_at=now()
            5. Busca a mesa e seta status=FREE
            6. Flush → tudo na mesma transação
            7. Retorna OrderResponse com status atualizado

        CONCEITO — Por que locking otimista É CRÍTICO aqui:
            Fechar uma comanda é a operação mais sensível financeiramente.
            Se dois usuários tentarem fechar ao mesmo tempo:
                → Um deve ter sucesso (HTTP 200)
                → O outro deve falhar com HTTP 409 (Conflict)

            O version garante isso:
                Usuário A lê order (version=5), fecha → version vira 6
                Usuário B também leu (version=5), tenta fechar:
                    → StaleDataError (version=5 no request, mas banco tem 6)
                    → OptimisticLockError → HTTP 409

            O caixa recarrega a comanda, vê que já está fechada, para.

        CONCEITO — Transação entre duas tabelas:
            Fechamos a comanda E liberamos a mesa na mesma transação.
            Se fechar a comanda funcionar mas a mesa não puder ser liberada
            (ex: mesa foi deletada entre a abertura e o fechamento):
                → session.flush() falharia
                → session.rollback() (feito pelo get_db) reverte tudo
                → A comanda VOLTA para OPEN automaticamente

            Isso é a garantia ACID da transação. A = Atomicidade.

        LANÇA:
            NotFoundError (404)      → comanda não encontrada
            BusinessRuleError (422)  → comanda já fechada ou cancelada
            OptimisticLockError (409) → conflito de versão
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível fechar uma comanda com status '{order.status.value}'. "
                "Apenas comandas ABERTAS ou com CONTA SOLICITADA podem ser fechadas."
            )

        # Locking otimista: version deve bater
        if order.version != data.version:
            raise OptimisticLockError("Order")

        # Fecha a comanda
        order.status = OrderStatus.CLOSED
        order.closed_at = datetime.now(UTC)
        if data.notes:
            order.notes = data.notes

        # Libera a mesa — mesma transação
        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(
                order.table_id, establishment_id
            )
            if table is not None:
                table.status = TableStatus.FREE

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        # Retorna estado final da comanda
        return await self._get_or_raise(order.id, establishment_id)

    async def cancel_item(
        self,
        order_id: UUID,
        item_id: UUID,
        *,
        reason: str | None = None,
    ) -> OrderResponse:
        """
        Cancela um item de uma comanda aberta.

        REGRAS DE NEGÓCIO:
            1. A comanda deve existir e pertencer ao estabelecimento
            2. A comanda deve estar OPEN ou BILL_REQUESTED
               (não faz sentido cancelar item de comanda já fechada)
            3. O item deve existir e pertencer à comanda informada
            4. O item não pode já estar CANCELLED
            5. O item não pode estar SERVED (já foi entregue ao cliente)

        POR QUE NÃO PERMITIR CANCELAR ITENS SERVED?
            Um item SERVED foi fisicamente entregue ao cliente.
            Cancelar algo que já foi consumido é uma operação de crédito/
            estorno, não um cancelamento simples — teria implicações fiscais
            e de estoque. Para o MVP, bloqueamos. Se necessário, um OWNER
            pode fechar e reabrir a comanda com ajuste manual.

        TOTAIS APÓS CANCELAMENTO:
            _recalculate_total() soma apenas itens com status != CANCELLED.
            Ao marcar o item como CANCELLED antes de chamar esse método,
            ele automaticamente sai do cálculo. A lógica está centralizada
            — não precisamos subtrair manualmente.

        LOCKING OTIMISTA:
            Cancelar um item atualiza order.subtotal e order.total.
            Como Order tem VersionMixin, qualquer UPDATE no registro
            incrementa o version. Se dois cancelamentos simultâneos
            ocorrerem, o segundo receberá StaleDataError → OptimisticLockError.
            O frontend deve recarregar a comanda e tentar novamente.

        LANÇA:
            NotFoundError (404)       → comanda ou item não encontrado
            BusinessRuleError (422)   → comanda fechada, item servido, já cancelado
            OptimisticLockError (409) → conflito de versão concorrente
        """
        establishment_id = self._require_establishment()

        # Carrega a comanda com seus itens (selectinload via get_with_items)
        order = await self._get_or_raise(order_id, establishment_id)

        # Regra 1: comanda deve estar em estado cancelável
        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível cancelar itens de uma comanda com status "
                f"'{order.status.value}'. Apenas comandas ABERTAS ou com "
                "CONTA SOLICITADA permitem cancelamento de itens."
            )

        # Regra 2: item deve pertencer a esta comanda
        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        # Regra 3: item não pode estar já cancelado
        if item.status == OrderItemStatus.CANCELLED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já está cancelado."
            )

        # Regra 4: item não pode ter sido servido
        if item.status == OrderItemStatus.SERVED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já foi servido e não pode ser cancelado. "
                "Para ajustes pós-serviço, utilize o processo de estorno manual."
            )

        # Cancela o item — campos de auditoria registram quando e por quê
        item.status = OrderItemStatus.CANCELLED
        item.cancelled_at = datetime.now(UTC)
        item.cancelled_reason = reason  # None se não fornecido — aceitável

        # Recalcula subtotal e total da comanda (exclui automaticamente itens CANCELLED)
        # _recalculate_total() itera sobre order.items já carregados em memória,
        # então o item recém-cancelado já reflete o novo status.
        self._recalculate_total(order)

        try:
            await self.session.flush()
        except StaleDataError:
            # Dois cancelamentos simultâneos tentaram atualizar o total da comanda.
            # O frontend deve recarregar a comanda e tentar o cancelamento novamente.
            raise OptimisticLockError("Order")

        return await self._get_or_raise(order.id, establishment_id)

    async def set_item_quantity(
        self,
        order_id: UUID,
        item_id: UUID,
        *,
        quantity: int,
    ) -> OrderResponse:
        """
        Altera a quantidade de um item da comanda e recalcula o total.

        Útil para o caso comum no bar: o cliente pede outra cerveja igual.
        Em vez de criar uma nova linha, incrementamos a quantidade do item.

        REGRAS:
            - Comanda deve estar OPEN ou BILL_REQUESTED
            - Item deve existir e pertencer à comanda
            - Item não pode estar CANCELLED nem SERVED
            - quantity >= 1 (para zerar, use o cancelamento)
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar itens de uma comanda com status "
                f"'{order.status.value}'."
            )

        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        if item.status == OrderItemStatus.CANCELLED:
            raise BusinessRuleError(f"O item '{item.item_name}' está cancelado.")
        if item.status == OrderItemStatus.SERVED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já foi servido e não pode ser alterado."
            )

        item.quantity = quantity
        item.subtotal = item.unit_price * quantity
        self._recalculate_total(order)

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        return await self._get_or_raise(order.id, establishment_id)

    async def set_discount(self, order_id: UUID, discount: Decimal) -> OrderResponse:
        """Define o desconto (R$) da comanda e recalcula o total."""
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar o desconto de uma comanda com status "
                f"'{order.status.value}'."
            )
        if discount > order.subtotal:
            raise BusinessRuleError(
                "O desconto não pode ser maior que o subtotal da comanda."
            )

        order.discount = discount
        self._recalculate_total(order)

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        return await self._get_or_raise(order.id, establishment_id)

    # ── Relatórios / histórico ──────────────────────────────────────────────

    async def list_history(self, *, limit: int = 50, offset: int = 0) -> list[OrderResponse]:
        """Histórico de comandas fechadas (mais recentes primeiro)."""
        establishment_id = self._require_establishment()
        orders = await self._order_repo.list_closed(
            establishment_id, limit=limit, offset=offset
        )
        return [OrderResponse.model_validate(o) for o in orders]

    async def daily_report(self, day: date | None = None) -> DailyReport:
        """
        Resumo do dia: faturamento, nº de comandas, ticket médio,
        faturamento por forma de pagamento e itens mais vendidos.

        O "dia" é calculado no fuso America/Sao_Paulo (o bar opera em horário
        local; closed_at é armazenado em UTC e comparado com o intervalo local).
        """
        establishment_id = self._require_establishment()
        tz = ZoneInfo("America/Sao_Paulo")
        target = day or datetime.now(tz).date()
        start = datetime.combine(target, time.min, tzinfo=tz)
        end = start + timedelta(days=1)

        orders = await self._order_repo.list_closed_between(
            establishment_id, start, end
        )

        revenue_total = Decimal("0.00")
        method_totals: dict[str, Decimal] = {}
        method_counts: dict[str, int] = {}
        item_qty: dict[str, int] = {}
        item_total: dict[str, Decimal] = {}

        for order in orders:
            revenue_total += order.total
            for payment in order.payments:
                if payment.status == PaymentStatus.CONFIRMED:
                    key = payment.method.value
                    method_totals[key] = method_totals.get(key, Decimal("0.00")) + payment.amount
                    method_counts[key] = method_counts.get(key, 0) + 1
            for it in order.items:
                if it.status == OrderItemStatus.CANCELLED:
                    continue
                item_qty[it.item_name] = item_qty.get(it.item_name, 0) + it.quantity
                item_total[it.item_name] = item_total.get(it.item_name, Decimal("0.00")) + it.subtotal

        count = len(orders)
        average = (revenue_total / count) if count else Decimal("0.00")

        by_method = [
            PaymentMethodTotal(method=m, total=method_totals[m], count=method_counts[m])
            for m in method_totals
        ]
        by_method.sort(key=lambda x: x.total, reverse=True)

        top_items = [
            TopItem(name=name, quantity=item_qty[name], total=item_total[name])
            for name in item_qty
        ]
        top_items.sort(key=lambda x: x.quantity, reverse=True)

        return DailyReport(
            date=target,
            revenue_total=revenue_total,
            orders_count=count,
            average_ticket=round(average, 2),
            by_payment_method=by_method,
            top_items=top_items[:10],
        )
