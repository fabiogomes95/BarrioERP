"""
app/services/cash_service.py

Controle de caixa: abertura, sangria/suprimento e fechamento com conferência.

Esperado em caixa = fundo de troco + vendas em dinheiro + suprimentos - sangrias.
"vendas em dinheiro" = pagamentos method=cash, status=confirmed, registrados
entre a abertura e o fechamento da sessão, no estabelecimento.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, TenantError
from app.models.cash import CashMovement, CashMovementKind, CashSession, CashSessionStatus
from app.models.order import Order
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.cash import (
    CashClose,
    CashMovementCreate,
    CashMovementResponse,
    CashOpen,
    CashSessionResponse,
)
from app.services.base import BaseService


class CashService(BaseService):
    def _require_establishment(self) -> UUID:
        if self.establishment_id is None:
            raise TenantError("Usuário não está vinculado a um estabelecimento.")
        return self.establishment_id

    async def _current(self) -> CashSession | None:
        establishment_id = self._require_establishment()
        stmt = (
            select(CashSession)
            .where(
                CashSession.establishment_id == establishment_id,
                CashSession.status == CashSessionStatus.OPEN,
            )
            .options(selectinload(CashSession.movements))
            .order_by(CashSession.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _cash_sales(self, session_obj: CashSession) -> Decimal:
        establishment_id = self._require_establishment()
        end = session_obj.closed_at or datetime.now(UTC)
        stmt = (
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Order, Order.id == Payment.order_id)
            .where(
                Order.establishment_id == establishment_id,
                Payment.method == PaymentMethod.CASH,
                Payment.status == PaymentStatus.CONFIRMED,
                Payment.created_at >= session_obj.opened_at,
                Payment.created_at <= end,
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(result.scalar() or 0)

    async def _to_response(self, s: CashSession) -> CashSessionResponse:
        cash_sales = await self._cash_sales(s)
        suprimentos = sum(
            (m.amount for m in s.movements if m.kind == CashMovementKind.SUPRIMENTO),
            Decimal("0.00"),
        )
        sangrias = sum(
            (m.amount for m in s.movements if m.kind == CashMovementKind.SANGRIA),
            Decimal("0.00"),
        )
        expected_so_far = s.opening_amount + cash_sales + suprimentos - sangrias
        return CashSessionResponse(
            id=s.id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            status=s.status,
            opening_amount=s.opening_amount,
            opened_at=s.opened_at,
            closed_at=s.closed_at,
            counted_amount=s.counted_amount,
            expected_amount=s.expected_amount,
            difference=s.difference,
            notes=s.notes,
            movements=[CashMovementResponse.model_validate(m) for m in s.movements],
            cash_sales=cash_sales,
            suprimentos=suprimentos,
            sangrias=sangrias,
            expected_so_far=expected_so_far,
        )

    async def get_current(self) -> CashSessionResponse | None:
        s = await self._current()
        return await self._to_response(s) if s else None

    async def open(self, data: CashOpen) -> CashSessionResponse:
        establishment_id = self._require_establishment()
        if await self._current() is not None:
            raise BusinessRuleError("Já existe um caixa aberto. Feche-o antes de abrir outro.")
        s = CashSession(
            establishment_id=establishment_id,
            opened_by=self.user_id,
            status=CashSessionStatus.OPEN,
            opening_amount=data.opening_amount,
            opened_at=datetime.now(UTC),
            notes=data.notes,
        )
        self.session.add(s)
        await self.session.flush()
        await self.session.refresh(s, attribute_names=["movements"])
        return await self._to_response(s)

    async def add_movement(self, data: CashMovementCreate) -> CashSessionResponse:
        s = await self._current()
        if s is None:
            raise BusinessRuleError("Nenhum caixa aberto.")
        m = CashMovement(
            session_id=s.id,
            kind=data.kind,
            amount=data.amount,
            reason=data.reason,
            created_by=self.user_id,
        )
        self.session.add(m)
        await self.session.flush()
        await self.session.refresh(s, attribute_names=["movements"])
        return await self._to_response(s)

    async def close(self, data: CashClose) -> CashSessionResponse:
        s = await self._current()
        if s is None:
            raise BusinessRuleError("Nenhum caixa aberto.")
        cash_sales = await self._cash_sales(s)
        suprimentos = sum(
            (m.amount for m in s.movements if m.kind == CashMovementKind.SUPRIMENTO),
            Decimal("0.00"),
        )
        sangrias = sum(
            (m.amount for m in s.movements if m.kind == CashMovementKind.SANGRIA),
            Decimal("0.00"),
        )
        expected = s.opening_amount + cash_sales + suprimentos - sangrias

        s.counted_amount = data.counted_amount
        s.expected_amount = expected
        s.difference = data.counted_amount - expected
        s.closed_at = datetime.now(UTC)
        s.closed_by = self.user_id
        s.status = CashSessionStatus.CLOSED
        if data.notes:
            s.notes = data.notes
        await self.session.flush()
        return await self._to_response(s)

    async def history(self, *, limit: int = 30) -> list[CashSessionResponse]:
        establishment_id = self._require_establishment()
        stmt = (
            select(CashSession)
            .where(
                CashSession.establishment_id == establishment_id,
                CashSession.status == CashSessionStatus.CLOSED,
            )
            .options(selectinload(CashSession.movements))
            .order_by(CashSession.closed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [await self._to_response(s) for s in result.scalars().all()]
