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
    service_fee_total: Decimal
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
    service_fee_total: Decimal
    by_payment_method: list[PaymentMethodTotal]
    top_items: list[TopItem]
    daily_breakdown: list[DailyBreakdownEntry]


class ShiftReport(BaseSchema):
    """
    Resumo de um intervalo exato de data/hora (ex.: turno de bar que atravessa
    a virada do dia, tipo 05/09 16h até 06/09 05h).

    Usado em: GET /api/v1/reports/shift?start=...&end=...

    Diferente do DailyReport/PeriodReport (que trabalham com dias inteiros no
    fuso local), aqui `start`/`end` são datetimes exatos — úteis pra fechar
    a conta de um turno que não bate com meia-noite.
    """

    start: datetime
    end: datetime
    revenue_total: Decimal
    orders_count: int
    average_ticket: Decimal
    service_fee_total: Decimal
    by_payment_method: list[PaymentMethodTotal]
    top_items: list[TopItem]


# ── Movimento por dia da semana / horário (Caixa → Período) ──────────────────

class WeekdayTopItem(BaseSchema):
    name: str
    quantity: int


class WeekdayEntry(BaseSchema):
    weekday: int                 # 0 = segunda ... 6 = domingo (noite do bar, vira às 6h)
    nights: int                  # quantas noites desse dia tiveram movimento no período
    orders_count: int
    revenue_total: Decimal
    revenue_per_night: Decimal   # média por noite aberta
    orders_per_night: float
    top_items: list[WeekdayTopItem]


class HourCell(BaseSchema):
    weekday: int
    hour: int                    # hora local em que a comanda foi aberta (0-23)
    orders_count: int


class MovementReport(BaseSchema):
    weekdays: list[WeekdayEntry]  # sempre 7, de segunda a domingo
    heatmap: list[HourCell]       # só as células com movimento


# ── Clientes do delivery (pedidos online aceitos, últimos 12 meses) ──────────

class CustomerEntry(BaseSchema):
    phone: str
    name: str
    orders_count: int
    total: Decimal
    first_order: date
    last_order: date
    days_since_last: int
    favorite_item: str | None
    lapsed: bool                 # pediu 2+ vezes e sumiu há mais de 30 dias


class CustomersReport(BaseSchema):
    customers_count: int
    returning_count: int         # pediram 2+ vezes
    top: list[CustomerEntry]
    lapsed: list[CustomerEntry]
