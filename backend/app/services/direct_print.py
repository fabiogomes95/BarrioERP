"""
app/services/direct_print.py

Imprime recibo/ticket de cozinha de uma comanda direto na térmica do PC
(app/services/thermal_printer.py). Se a impressão direta não estiver
configurada ou falhar (impressora desligada, sem papel, driver), cai no
caminho antigo: evento SSE "print.request" pro navegador do PC marcado
como "impressora do bar" — o pedido de impressão não se perde.

print_or_fallback() abre a PRÓPRIA sessão: é chamado depois do commit da
requisição (BackgroundTasks no aceite de pedido online), quando a sessão da
requisição já foi fechada.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.database.session import AsyncSessionLocal
from app.models.company import Company
from app.models.online_order import OnlineOrder
from app.models.order import Order, OrderItemStatus, OrderType
from app.models.payment import Payment, PaymentStatus
from app.models.table import Table
from app.repositories.order_repository import OrderRepository
from app.services import thermal_printer
from app.services.online_order_service import format_phone, payment_label

logger = logging.getLogger(__name__)

PrintKind = Literal["comanda", "cozinha"]

_METHOD_LABEL = {
    "cash": "Dinheiro", "credit_card": "Credito", "debit_card": "Debito",
    "pix": "Pix", "voucher": "Voucher", "other": "Outro",
}
_TYPE_LABEL = {OrderType.DELIVERY: "Entrega", OrderType.PICKUP: "Retirada"}


async def _where(session: AsyncSession, order: Order, *, receipt: bool) -> str:
    if order.table_id is not None:
        table = await session.get(Table, order.table_id)
        if table is not None:
            base = f"Mesa {table.number}"
            return f"{base} - {order.customer_name}" if order.customer_name else base
    base = _TYPE_LABEL.get(order.order_type, "Consumo no local" if receipt else "Balcao")
    return f"{base} - {order.customer_name}" if order.customer_name else base


async def _load(session: AsyncSession, establishment_id: UUID, order_id: UUID) -> Order:
    order = await OrderRepository(session).get_with_items(order_id, establishment_id)
    if order is None:
        raise LookupError(f"comanda {order_id} não encontrada")
    return order


async def _online(session: AsyncSession, order: Order) -> OnlineOrder | None:
    """Pedido do cardápio que virou esta comanda (None = comanda lançada na casa)."""
    return await session.scalar(select(OnlineOrder).where(OnlineOrder.order_id == order.id))


def delivery_lines(online: OnlineOrder, total: Decimal) -> list[tuple[str, str]]:
    """O que o entregador precisa no papel: onde, quem, como recebe, quanto de troco."""
    lines: list[tuple[str, str]] = []
    if online.fulfillment == OrderType.DELIVERY:
        lines.append(("ENTREGAR EM", online.delivery_location or "(nao informado - ligar pro cliente)"))
    lines.append(("Telefone", format_phone(online.customer_phone)))
    if online.payment_method:
        lines.append(("Pagamento", payment_label(online.payment_method)))
        if online.payment_method == "cash" and online.change_for:
            troco = online.change_for - total
            if troco > 0:
                lines.append(("LEVAR TROCO",
                              f"{thermal_printer._money(troco)} (paga com {thermal_printer._money(online.change_for)})"))
            else:
                lines.append(("Troco", f"paga com {thermal_printer._money(online.change_for)}"))
    if online.notes:
        lines.append(("Obs do cliente", online.notes))
    return lines


async def print_receipt(session: AsyncSession, company_id: UUID, establishment_id: UUID, order_id: UUID) -> None:
    order = await _load(session, establishment_id, order_id)
    online = await _online(session, order)
    company = await session.get(Company, company_id)
    payments = (await session.scalars(
        select(Payment).where(Payment.order_id == order.id, Payment.status == PaymentStatus.CONFIRMED)
        .order_by(Payment.created_at)
    )).all()
    method = lambda p: _METHOD_LABEL.get(getattr(p.method, "value", str(p.method)).lower(), str(p.method))  # noqa: E731
    data = thermal_printer.receipt(
        bar_name=company.name if company else "Barrio",
        where=await _where(session, order, receipt=True),
        items=[(i.quantity, i.item_name, i.subtotal) for i in order.items if i.status != OrderItemStatus.CANCELLED],
        subtotal=order.subtotal, service_fee=order.service_fee,
        service_fee_percent=order.service_fee_percent, discount=order.discount, total=order.total,
        payments=[(method(p), p.amount) for p in payments],
        delivery=delivery_lines(online, order.total) if online else None,
    )
    await asyncio.to_thread(thermal_printer.send_raw, data)


async def print_kitchen(session: AsyncSession, establishment_id: UUID, order_id: UUID,
                        items: list[tuple[int, str, str | None]] | None = None) -> bool:
    """
    Ticket da cozinha. `items` = os escolhidos na tela (qtd, nome, obs);
    sem lista = itens da comanda que vão pra cozinha (status SENT).
    False = nada pra imprimir (ex: pedido só de bebida).
    """
    order = await _load(session, establishment_id, order_id)
    if items is None:
        items = [(i.quantity, i.item_name, i.notes) for i in order.items if i.status == OrderItemStatus.SENT]
    if not items:
        return False
    # Pedido online: order.notes carrega telefone/pagamento/local pro caixa —
    # a cozinha só precisa da observação que o cliente escreveu.
    online = await _online(session, order)
    data = thermal_printer.kitchen_ticket(
        where=await _where(session, order, receipt=False), items=items,
        notes=online.notes if online else order.notes,
    )
    await asyncio.to_thread(thermal_printer.send_raw, data)
    return True


async def print_or_fallback(kind: PrintKind, company_id: UUID, establishment_id: UUID, order_id: UUID,
                            items: list[tuple[int, str, str | None]] | None = None) -> bool:
    """True = saiu direto na térmica. False = mandado pro navegador do PC (caminho antigo)."""
    async with AsyncSessionLocal() as session:
        if thermal_printer.is_configured():
            try:
                if kind == "cozinha":
                    await print_kitchen(session, establishment_id, order_id, items)
                else:
                    await print_receipt(session, company_id, establishment_id, order_id)
                return True
            except Exception:
                logger.exception("Impressão direta (%s) falhou — mandando pro navegador do PC", kind)
        await events.publish(
            session, "print.request",
            company_id=str(company_id), establishment_id=str(establishment_id),
            order_id=str(order_id), print_type=kind,
            items=[{"name": n, "qty": q, "notes": o} for q, n, o in items] if items else None,
        )
        await session.commit()
        return False
