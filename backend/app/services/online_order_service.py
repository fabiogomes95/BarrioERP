"""
app/services/online_order_service.py

Fila de aceite dos pedidos do cardápio público (ver app/models/online_order.py).

Aceitar = abrir uma comanda delivery/retirada e lançar os itens pelo próprio
OrderService — o pedido online passa pelas MESMAS regras de um pedido de
balcão (KDS, baixa de estoque, auditoria, taxa de serviço zerada pra
delivery/retirada). Nada aqui duplica regra de comanda.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError, TenantError
from app.models.online_order import OnlineOrder, OnlineOrderStatus
from app.models.order import OrderType
from app.schemas.online_order import OnlineOrderResponse, OnlineOrdersReport, OnlineTopItem
from app.schemas.order import OrderCreate, OrderItemAdd
from app.services.base import BaseService
from app.services.order_service import OrderService


def format_phone(digits: str) -> str:
    d = digits[2:] if digits.startswith("55") and len(digits) > 11 else digits
    if len(d) < 10:
        return d
    return f"({d[:2]}) {d[2:-4]}-{d[-4:]}"


PAYMENT_LABELS = {"cash": "Dinheiro", "pix": "Pix", "credit": "Crédito", "debit": "Débito"}


def payment_label(method: str, change_for: Decimal | None = None) -> str:
    label = PAYMENT_LABELS.get(method, method)
    if method == "cash" and change_for:
        label += f" (troco p/ R$ {change_for:.2f})".replace(".", ",")
    return label


class OnlineOrderService(BaseService):

    def _require_establishment(self) -> UUID:
        if self.establishment_id is None:
            raise TenantError("Usuário não está vinculado a um estabelecimento.")
        return self.establishment_id

    async def _get_pending_for_update(self, online_order_id: UUID) -> OnlineOrder:
        # FOR UPDATE: dois aparelhos tocando "Aceitar" juntos não viram duas comandas
        online_order = await self.session.scalar(
            select(OnlineOrder)
            .where(
                OnlineOrder.id == online_order_id,
                OnlineOrder.establishment_id == self._require_establishment(),
            )
            .with_for_update()
        )
        if online_order is None:
            raise NotFoundError("OnlineOrder", online_order_id)
        if online_order.status != OnlineOrderStatus.PENDING:
            raise BusinessRuleError("Esse pedido já foi aceito ou recusado.")
        return online_order

    async def list(self, status: OnlineOrderStatus = OnlineOrderStatus.PENDING) -> list[OnlineOrderResponse]:
        rows = await self.session.scalars(
            select(OnlineOrder)
            .where(
                OnlineOrder.establishment_id == self._require_establishment(),
                OnlineOrder.status == status,
            )
            .order_by(OnlineOrder.created_at)
            .limit(100)
        )
        return [OnlineOrderResponse.model_validate(o) for o in rows]

    async def accept(self, online_order_id: UUID) -> UUID:
        online_order = await self._get_pending_for_update(online_order_id)
        establishment_id = self._require_establishment()
        orders = OrderService(self.session, self.company_id, establishment_id, self.user_id)

        kind = "Entrega" if online_order.fulfillment == OrderType.DELIVERY else "Retirada"
        notes = f"Pedido online #{online_order.number} · {kind} · Tel {format_phone(online_order.customer_phone)}"
        if online_order.delivery_location:
            notes += f" · Entregar em: {online_order.delivery_location}"
        if online_order.payment_method:
            notes += f" · Pagamento: {payment_label(online_order.payment_method, online_order.change_for)}"
        if online_order.notes:
            notes += f" · Obs: {online_order.notes}"

        order = await orders.open_order(OrderCreate(
            order_type=online_order.fulfillment,
            customer_name=f"{online_order.customer_name} · online #{online_order.number}",
            notes=notes[:500],
        ))

        for line in online_order.items:
            manual = OrderItemAdd(
                item_name=line["item_name"],
                unit_price=Decimal(line["unit_price"]),
                quantity=line["quantity"],
            )
            # Mesmo caminho do balcão (cozinha + estoque): meio a meio e
            # complemento vão com a origem, não como item manual
            if line.get("half_first") and line.get("half_with"):
                data = OrderItemAdd(menu_item_id=UUID(line["half_first"]),
                                    half_with=UUID(line["half_with"]), quantity=line["quantity"])
            elif line.get("menu_item_id"):
                data = OrderItemAdd(menu_item_id=UUID(line["menu_item_id"]),
                                    complemento=line.get("complemento"), quantity=line["quantity"])
            else:
                await orders.add_item(order.id, manual)
                continue
            try:
                await orders.add_item(order.id, data)
            except (NotFoundError, BusinessRuleError):
                # Item/opção ficou indisponível entre o pedido e o aceite — lança
                # com o nome/preço que o cliente viu, em vez de travar o aceite.
                await orders.add_item(order.id, manual)

        online_order.status = OnlineOrderStatus.ACCEPTED
        online_order.order_id = order.id
        online_order.handled_by_id = self.user_id
        online_order.handled_at = datetime.now(UTC)
        await self.session.flush()

        await self._log_audit(
            action="online_order.accept",
            resource_type="online_order",
            resource_id=str(online_order.id),
            after={"number": online_order.number, "order_id": str(order.id)},
        )
        # O ticket da cozinha é impresso pelo endpoint DEPOIS do commit
        # (direct_print.print_or_fallback) — aceite que falhou não imprime nada.
        return order.id

    async def report(self, start: datetime, end: datetime) -> OnlineOrdersReport:
        """Resumo dos pedidos do cardápio num intervalo (pela hora em que chegaram)."""
        tz = ZoneInfo(settings.TIMEZONE)
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        if start >= end:
            raise BusinessRuleError("O início precisa ser antes do fim.")

        rows = list(await self.session.scalars(
            select(OnlineOrder).where(
                OnlineOrder.establishment_id == self._require_establishment(),
                OnlineOrder.created_at >= start,
                OnlineOrder.created_at < end,
            )
        ))
        accepted = [o for o in rows if o.status == OnlineOrderStatus.ACCEPTED]
        accepted_total = sum((o.total for o in accepted), Decimal("0.00"))

        qty: dict[str, int] = {}
        money: dict[str, Decimal] = {}
        for o in accepted:
            for line in o.items:
                name = line["item_name"]
                qty[name] = qty.get(name, 0) + line["quantity"]
                money[name] = money.get(name, Decimal("0")) + Decimal(line["unit_price"]) * line["quantity"]
        top = sorted(qty, key=lambda n: (-qty[n], -money[n]))[:8]

        return OnlineOrdersReport(
            received=len(rows),
            accepted=len(accepted),
            rejected=sum(1 for o in rows if o.status == OnlineOrderStatus.REJECTED),
            pending=sum(1 for o in rows if o.status == OnlineOrderStatus.PENDING),
            accepted_total=accepted_total,
            average_ticket=(accepted_total / len(accepted)).quantize(Decimal("0.01")) if accepted else Decimal("0.00"),
            delivery=sum(1 for o in accepted if o.fulfillment == OrderType.DELIVERY),
            pickup=sum(1 for o in accepted if o.fulfillment == OrderType.PICKUP),
            top_items=[OnlineTopItem(name=n, quantity=qty[n], total=money[n]) for n in top],
        )

    async def reject(self, online_order_id: UUID) -> None:
        online_order = await self._get_pending_for_update(online_order_id)
        online_order.status = OnlineOrderStatus.REJECTED
        online_order.handled_by_id = self.user_id
        online_order.handled_at = datetime.now(UTC)
        await self.session.flush()

        await self._log_audit(
            action="online_order.reject",
            resource_type="online_order",
            resource_id=str(online_order.id),
            after={"number": online_order.number},
        )
