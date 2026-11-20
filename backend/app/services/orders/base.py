"""
app/services/orders/base.py

Base das comandas: __init__ e helpers usados pelas outras partes.

Código movido sem mudança de order_service.py (lá está a explicação geral
e a classe OrderService, que junta todas as partes).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo


from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError, TenantError
from app.models.user import UserRole
from app.models.order import Order, OrderItem, OrderItemStatus
from app.repositories.order_repository import OrderRepository
from app.repositories.table_repository import TableRepository
from app.services.base import BaseService
from app.services.stock_service import StockService
from sqlalchemy.ext.asyncio import AsyncSession


# Quem cancela/diminui item que já saiu de PENDENTE (foi pra cozinha)
_CAN_CANCEL_SENT_ITEMS = (UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)


class OrderServiceBase(BaseService):
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
        self._stock_service = StockService(session, company_id, establishment_id, user_id)

    # ── Helper: contexto de tenant ────────────────────────────────────────────

    async def _next_order_number(self, establishment_id: UUID) -> str:
        """Retorna o próximo número sequencial do dia para pedidos sem mesa."""
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()
        start = datetime.combine(today, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        count = await self._order_repo.count_non_table_today(establishment_id, start, end)
        return str(count + 1)

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

    @staticmethod
    def _require_can_reduce(item: OrderItem, actor_role: UserRole | None) -> None:
        """
        Garçom/cozinha só cancelam (ou diminuem) item ainda PENDENTE — lançado
        errado, não foi pra cozinha. Depois disso, só caixa/gerente/dono:
        evita "lança, cobra, cancela" sem ninguém do caixa ver.
        actor_role=None = chamada interna (sem usuário), não restringe.
        """
        if actor_role is None or actor_role in _CAN_CANCEL_SENT_ITEMS:
            return
        if item.status != OrderItemStatus.PENDING:
            raise ForbiddenError(
                f"'{item.item_name}' já foi pra cozinha — só o caixa ou o gerente pode cancelar."
            )

    async def _ensure_total_covers_payments(self, order: Order) -> None:
        """
        Barra mudanças que deixariam o total da comanda abaixo do que já foi
        pago (desconto, item cancelado, quantidade menor, tirar os 10%) — o
        dinheiro a mais sumiria do controle. Também barra total negativo
        (desconto maior que o que sobrou depois de cancelar itens).

        Trava a comanda antes de somar os pagamentos: um pagamento sendo
        registrado ao mesmo tempo termina antes e entra na conta
        (mesma trava do PaymentService.register).
        """
        if order.total < 0:
            raise BusinessRuleError(
                f"Essa mudança deixa o total negativo (R$ {order.total:.2f}). "
                f"Diminua o desconto antes."
            )
        await self._order_repo.lock(order.id, order.establishment_id)
        pago = await self._order_repo.sum_confirmed_payments(order.id)
        if order.total < pago:
            raise BusinessRuleError(
                f"Essa mudança deixa o total (R$ {order.total:.2f}) menor que o já pago "
                f"(R$ {pago:.2f}). Estorne um pagamento antes."
            )

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

    def _order_snapshot(self, order: Order) -> dict:
        """Extrai um snapshot dos campos relevantes da order para audit log."""
        return {
            "order_id": str(order.id),
            "status": order.status.value if order.status else None,
            "subtotal": str(order.subtotal),
            "discount": str(order.discount),
            "service_fee": str(order.service_fee),
            "total": str(order.total),
            "customer_name": order.customer_name,
            "guest_count": order.guest_count,
        }

    async def _order_label(self, order: Order) -> str:
        """Como a comanda aparece pro usuário: nome do cliente ou a mesa."""
        if order.customer_name:
            return order.customer_name
        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(order.table_id, order.establishment_id)
            if table is not None:
                return f"Mesa {table.number}"
        return "sem nome"
