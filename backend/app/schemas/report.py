"""
app/schemas/report.py

Schemas de saída dos relatórios (fechamento de caixa / faturamento do dia).
"""

from datetime import date
from decimal import Decimal

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
