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
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.database.session import AsyncSessionLocal
from app.models.company import Company
from app.models.order import Order, OrderItemStatus, OrderType
from app.models.payment import Payment, PaymentStatus
from app.models.table import Table
from app.repositories.order_repository import OrderRepository
from app.services import thermal_printer

logger = logging.getLogger(__name__)

PrintKind = Literal["comanda", "cozinha"]

_METHOD_LABEL = {
    "cash": "Dinheiro", "credit_card": "Credito", "debit_card": "Debito",
    "pix": "Pix", "voucher": "Voucher", "other": "Outro",
}
_TYPE_LABEL = {OrderType.DELIVERY: "Delivery", OrderType.PICKUP: "Retirada"}


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


async def print_receipt(session: AsyncSession, company_id: UUID, establishment_id: UUID, order_id: UUID) -> None:
    order = await _load(session, establishment_id, order_id)
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
    data = thermal_printer.kitchen_ticket(
        where=await _where(session, order, receipt=False), items=items, notes=order.notes,
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
