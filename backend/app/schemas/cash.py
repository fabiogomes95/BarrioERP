"""
app/schemas/cash.py

Schemas do Controle de Caixa (abertura/fechamento, sangria/suprimento).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.models.cash import CashMovementKind, CashSessionStatus
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


class CashOpen(BaseSchema):
    opening_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), description="Fundo de troco.")
    notes: str | None = Field(default=None, max_length=300)


class CashMovementCreate(BaseSchema):
    kind: CashMovementKind = Field(description="sangria (retirada) ou suprimento (reforço).")
    amount: Decimal = Field(..., gt=Decimal("0"))
    reason: str | None = Field(default=None, max_length=300)


class CashClose(BaseSchema):
    counted_amount: Decimal = Field(..., ge=Decimal("0"), description="Valor contado em dinheiro no fechamento.")
    notes: str | None = Field(default=None, max_length=300)


class CashMovementResponse(UUIDSchema, TimestampSchema):
    kind: CashMovementKind
    amount: Decimal
    reason: str | None = None


class CashSessionResponse(UUIDSchema, TimestampSchema):
    status: CashSessionStatus
    opening_amount: Decimal
    opened_at: datetime
    closed_at: datetime | None = None
    counted_amount: Decimal | None = None
    expected_amount: Decimal | None = None
    difference: Decimal | None = None
    notes: str | None = None
    movements: list[CashMovementResponse] = []
    # Calculados em tempo real:
    cash_sales: Decimal = Decimal("0")        # pagamentos em dinheiro no período
    suprimentos: Decimal = Decimal("0")
    sangrias: Decimal = Decimal("0")
    expected_so_far: Decimal = Decimal("0")   # esperado em caixa até agora
