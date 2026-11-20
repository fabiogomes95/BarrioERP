"""
app/services/orders/lifecycle.py

Ciclo da comanda: abrir, listar, detalhar, fechar, pedir conta, desconto/taxa,
nome do cliente, reabrir, cancelar e juntar comandas.

Código movido sem mudança de order_service.py (lá está a explicação geral
e a classe OrderService, que junta todas as partes).
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm.exc import StaleDataError

from app.core import events
from app.core.exceptions import BusinessRuleError, NotFoundError, OptimisticLockError
from app.models.establishment import Establishment
from app.models.order import Order, OrderItem, OrderStatus, OrderType
from app.models.payment import Payment, PaymentStatus
from app.models.table import TableStatus
from app.schemas.order import OrderClose, OrderCreate, OrderResponse
from app.services.orders.base import OrderServiceBase


class OrderLifecycleMixin(OrderServiceBase):
    """Ciclo da comanda: abrir, listar, detalhar, fechar, pedir conta, desconto/taxa,"""

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

        # Auto-numera pedidos sem mesa e sem nome
        customer_name = data.customer_name
        if data.table_id is None and not customer_name:
            customer_name = await self._next_order_number(establishment_id)

        # Snapshot da taxa de serviço — delivery e retirada não pagam taxa
        establishment = await self.session.get(Establishment, establishment_id)
        if data.order_type in (OrderType.DELIVERY, OrderType.PICKUP):
            fee_percent = Decimal("0")
        else:
            fee_percent = establishment.service_fee_percent if establishment else Decimal("0")

        # 3. Cria a comanda
        order = Order(
            establishment_id=establishment_id,
            table_id=data.table_id,
            waiter_id=self.user_id,         # quem abriu (do JWT)
            status=OrderStatus.OPEN,
            order_type=data.order_type,
            guest_count=data.guest_count,
            customer_name=customer_name,
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

        # 5. Audit log
        await self._log_audit(
            action="order.open",
            resource_type="order",
            resource_id=str(order.id),
            after=self._order_snapshot(order),
        )

        # 6. Retorna a comanda recém-criada (com items — vazia por enquanto)
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
        paid = await self._order_repo.sum_confirmed_payments_by_order([o.id for o in orders])
        return [
            OrderResponse.model_validate(o).model_copy(update={"paid": paid.get(o.id, Decimal("0"))})
            for o in orders
        ]

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

        # Audit log do fechamento
        await self._log_audit(
            action="order.close",
            resource_type="order",
            resource_id=str(order.id),
            before={"status": "open"},
            after=self._order_snapshot(order),
        )

        # Retorna estado final da comanda
        return await self._get_or_raise(order.id, establishment_id)

    async def request_bill(self, order_id: UUID) -> OrderResponse:
        """
        Marca a comanda como CONTA SOLICITADA (garçom avisando que o cliente
        quer pagar) e notifica o caixa em tempo real (SSE).

        Por que na Order e não só na Table?
            Comandas de balcão (sem mesa — table_id None) também precisam
            pedir a conta; e nem toda mesa tem uma única comanda (mesas com
            várias pessoas podem ter comandas separadas por pessoa). O status
            "conta pedida" é da COMANDA — quando ela está ligada a uma mesa,
            espelhamos o status na mesa também, só para o card colorir
            corretamente na tela de Mesas.

        LANÇA:
            NotFoundError (404)      → comanda não encontrada
            BusinessRuleError (422)  → comanda não está aberta
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status != OrderStatus.OPEN:
            raise BusinessRuleError(
                f"Não é possível solicitar a conta de uma comanda com status "
                f"'{order.status.value}'. Apenas comandas ABERTAS podem solicitar a conta."
            )

        order.status = OrderStatus.BILL_REQUESTED

        table = None
        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(
                order.table_id, establishment_id
            )
            if table is not None:
                table.status = TableStatus.BILL_REQUESTED

        await self.session.flush()

        await events.publish(
            self.session,
            "table.bill_requested",
            company_id=str(self.company_id),
            establishment_id=str(establishment_id),
            order_id=str(order.id),
            table_id=str(table.id) if table else None,
            table_number=table.number if table else None,
            table_label=table.label if table else (order.customer_name or "Balcão"),
        )

        await self._log_audit(
            action="order.bill_requested",
            resource_type="order",
            resource_id=str(order.id),
            after=self._order_snapshot(order),
        )

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

        old_discount = order.discount
        order.discount = discount
        self._recalculate_total(order)
        await self._ensure_total_covers_payments(order)

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        await self._log_audit(
            action="order.discount_change",
            resource_type="order",
            resource_id=str(order.id),
            before={"discount": str(old_discount), "order": self._order_snapshot(order)},
            after={"discount": str(discount), "order": self._order_snapshot(order)},
        )

        return await self._get_or_raise(order.id, establishment_id)

    async def set_service_fee(self, order_id: UUID, apply: bool) -> OrderResponse:
        """Ativa ou desativa a taxa de serviço nesta comanda."""
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar a taxa de serviço de uma comanda com status "
                f"'{order.status.value}'."
            )

        old_percent = order.service_fee_percent
        if apply:
            establishment = await self.session.get(Establishment, establishment_id)
            order.service_fee_percent = establishment.service_fee_percent if establishment else Decimal("0")
        else:
            order.service_fee_percent = Decimal("0")

        self._recalculate_total(order)
        await self._ensure_total_covers_payments(order)

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        await self._log_audit(
            action="order.service_fee_change",
            resource_type="order",
            resource_id=str(order.id),
            before={"service_fee_percent": str(old_percent), "order": self._order_snapshot(order)},
            after={"service_fee_percent": str(order.service_fee_percent), "order": self._order_snapshot(order)},
        )

        return await self._get_or_raise(order.id, establishment_id)

    async def update_customer_name(self, order_id: UUID, name: str | None) -> OrderResponse:
        """Atualiza o nome do cliente de uma comanda."""
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)
        if order.status == OrderStatus.CANCELLED:
            raise BusinessRuleError("Não é possível editar uma comanda cancelada.")
        order.customer_name = name
        await self.session.flush()
        return await self._get_or_raise(order.id, establishment_id)

    async def reopen_order(self, order_id: UUID) -> OrderResponse:
        """
        Reabre uma comanda fechada que possui fiado (pagamento parcial).

        Útil quando o cliente volta para adicionar mais itens à conta.
        A comanda volta ao status OPEN para receber novos itens/pagamentos.
        Os pagamentos já registrados permanecem como crédito.
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status != OrderStatus.CLOSED:
            raise BusinessRuleError(
                "Apenas comandas FECHADAS podem ser reabertas."
            )

        # Verifica se já foi totalmente paga — se sim, não faz sentido reabrir
        total_paid = await self._order_repo.sum_confirmed_payments(order_id)
        if total_paid >= order.total:
            raise BusinessRuleError(
                "Esta comanda já foi totalmente paga. Não é possível reabrir."
            )

        # Mesa já ocupada por outra comanda (outro cliente sentou lá depois):
        # a conta reaberta vira de balcão em vez de ficar duas na mesma mesa
        # (a tela de Mesas só enxerga uma, e a outra "sumia").
        old_table_id = order.table_id
        if order.table_id is not None and await self._order_repo.list_open(
            establishment_id, table_id=order.table_id,
        ):
            order.table_id = None

        order.status = OrderStatus.OPEN
        order.closed_at = None

        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(
                order.table_id, establishment_id
            )
            if table is not None:
                table.status = TableStatus.OCCUPIED

        await self.session.flush()

        await self._log_audit(
            action="order.reopen",
            resource_type="order",
            resource_id=str(order.id),
            before={"status": "closed", "table_id": str(old_table_id) if old_table_id else None},
            after=self._order_snapshot(order),
        )

        return await self._get_or_raise(order.id, establishment_id)

    async def cancel_order(self, order_id: UUID) -> None:
        """Cancela (apaga) uma comanda, liberando a mesa se houver."""
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status == OrderStatus.CANCELLED:
            raise BusinessRuleError("Comanda já está cancelada.")
        # Comanda com dinheiro recebido não some dos relatórios: estorna antes
        await self._order_repo.lock(order.id, establishment_id)
        if await self._order_repo.sum_confirmed_payments(order.id) > 0:
            raise BusinessRuleError(
                "Essa comanda tem pagamento registrado. Estorne os pagamentos antes de cancelar."
            )

        order.status = OrderStatus.CANCELLED
        order.closed_at = datetime.now(UTC)

        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(
                order.table_id, establishment_id
            )
            if table is not None:
                table.status = TableStatus.FREE

        await self.session.flush()

        await self._log_audit(
            action="order.cancel",
            resource_type="order",
            resource_id=str(order.id),
            before={"status": "open"},
            after=self._order_snapshot(order),
        )

    async def merge_orders(self, target_id: UUID, source_ids: list[UUID]) -> OrderResponse:
        """
        Mescla outras comandas na comanda `target_id` (ex: duas mesas que viraram
        uma só, ou o cliente que abriu uma comanda nova sem querer).

        Os itens MUDAM de comanda (UPDATE order_items.order_id) — não são
        recriados: mantêm preço, status de cozinha e a baixa de estoque já feita.
        As comandas de origem ficam CANCELLED com nota "Itens movidos para a comanda X"
        (os itens agora contam na receita da comanda destino) e as mesas delas
        são liberadas. Desconto das origens é somado no destino.

        POR QUE NÃO `target.items.append(item)`:
            items tem cascade "delete-orphan" — tirar o item da coleção da
            comanda de origem faria o SQLAlchemy APAGAR o item.

        Comanda de origem com pagamento registrado é recusada: o dinheiro ficaria
        preso numa comanda cancelada. O caixa estorna primeiro (ou mescla ao contrário).
        Tudo numa transação: ou mescla tudo, ou nada muda.
        """
        establishment_id = self._require_establishment()
        source_ids = list(dict.fromkeys(source_ids))  # sem repetidos, mantém a ordem
        if not source_ids:
            raise BusinessRuleError("Escolha ao menos uma comanda para mesclar.")
        if target_id in source_ids:
            raise BusinessRuleError("A comanda de destino não pode estar entre as que serão mescladas.")

        mergeable = (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED)
        target = await self._get_or_raise(target_id, establishment_id)
        if target.status not in mergeable:
            raise BusinessRuleError("A comanda de destino não está aberta.")
        target_label = await self._order_label(target)

        sources = [await self._get_or_raise(sid, establishment_id) for sid in source_ids]
        for src in sources:
            label = await self._order_label(src)
            if src.status not in mergeable:
                raise BusinessRuleError(f"A comanda '{label}' não está aberta.")
            paid = await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.order_id == src.id, Payment.status == PaymentStatus.CONFIRMED,
                )
            )
            if paid > 0:
                raise BusinessRuleError(
                    f"A comanda '{label}' já tem pagamento registrado (R$ {paid:.2f}). "
                    "Estorne o pagamento antes de mesclar, ou mescle as outras nela."
                )

        before = {"target": self._order_snapshot(target),
                  "sources": [self._order_snapshot(s) for s in sources]}

        await self.session.execute(
            update(OrderItem)
            .where(OrderItem.order_id.in_([s.id for s in sources]))
            .values(order_id=target.id)
        )

        now = datetime.now(UTC)
        for src in sources:
            target.discount += src.discount
            src.status = OrderStatus.CANCELLED
            src.closed_at = now
            note = f"Itens movidos para a comanda {target_label}"
            src.notes = f"{src.notes} · {note}"[:500] if src.notes else note
            if src.table_id is not None and src.table_id != target.table_id:
                table = await self._table_repo.get_by_establishment(src.table_id, establishment_id)
                if table is not None:
                    table.status = TableStatus.FREE

        # Recarrega os itens do destino (agora com os que vieram) e recalcula total
        await self.session.flush()
        await self.session.refresh(target, ["items"])
        self._recalculate_total(target)
        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        await self._log_audit(
            action="order.merge",
            resource_type="order",
            resource_id=str(target.id),
            before=before,
            after=self._order_snapshot(target),
        )
        return await self._get_or_raise(target.id, establishment_id)
