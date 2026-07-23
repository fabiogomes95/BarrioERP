"""
app/schemas/report.py

Schemas de saída dos relatórios (fechamento de caixa / faturamento do dia).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.models.payment import PaymentMethod
from app.schemas.common import BaseSchema


class PaymentMethodTotal(BaseSchema):
    """Faturamento agrupado por forma de pagamento."""

    method: PaymentMethod
    total: Decimal
    count: int


class TopItem(BaseSchema):
    """Item mais vendido (agregado por nome)."""

    name: str
    quantity: int
    total: Decimal


class FiadoEntry(BaseSchema):
    """Comanda com pagamento parcial (fiado)."""

    order_id: UUID
    customer_name: str | None
    table_number: int | None
    order_type: str
    total: Decimal
    paid: Decimal
    remaining: Decimal
    created_at: datetime
    version: int


class FiadoCustomerGroup(BaseSchema):
    """Agrupamento de fiados por cliente."""

    customer_name: str
    entries: list[FiadoEntry]
    total_remaining: Decimal
    total_debt: Decimal


class DailyReport(BaseSchema):
    """
    Resumo do dia.

    Usado em: GET /api/v1/reports/daily

    `revenue_total` soma o total das comandas FECHADAS no dia.
    `by_payment_method` vem dos pagamentos confirmados dessas comandas.
    `top_items` agrega os itens (não cancelados) das comandas do dia.
    """

    date: date
    revenue_total: Decimal
    orders_count: int
    average_ticket: Decimal
    by_payment_method: list[PaymentMethodTotal]
    top_items: list[TopItem]


class DailyBreakdownEntry(BaseSchema):
    """Faturamento de um único dia dentro de um período — usado no gráfico/tabela do relatório por período."""

    date: date
    revenue_total: Decimal
    orders_count: int


class PeriodReport(BaseSchema):
    """
    Resumo de um período (intervalo de datas, inclusive nos dois extremos).

    Usado em: GET /api/v1/reports/period?start=...&end=...

    Mesma lógica do DailyReport, mas somando o intervalo inteiro, mais
    `daily_breakdown` — o total de cada dia dentro do período, pra dar pra
    ver a evolução dia a dia (gráfico ou tabela) em vez de só o agregado.
    """

    date_start: date
    date_end: date
    revenue_total: Decimal
    orders_count: int
    average_ticket: Decimal
    by_payment_method: list[PaymentMethodTotal]
    top_items: list[TopItem]
    daily_breakdown: list[DailyBreakdownEntry]
