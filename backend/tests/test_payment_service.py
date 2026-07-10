"""Testes do PaymentService — regras de negócio de pagamentos."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from decimal import Decimal

import pytest

from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.table import Table, TableStatus
from app.models.establishment import Establishment
from app.schemas.payment import PaymentCreate, OrderFinish
from app.services.payment_service import PaymentService
from app.core.exceptions import BusinessRuleError, NotFoundError, OptimisticLockError, TenantError


@pytest.fixture
def service(mock_session, company_id, establishment_id, user_id):
    return PaymentService(
        session=mock_session,
        company_id=UUID(company_id),
        establishment_id=UUID(establishment_id),
        user_id=UUID(user_id),
    )


def make_order(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000005"),
        company_id=UUID("00000000-0000-0000-0000-000000000001"),
        establishment_id=UUID("00000000-0000-0000-0000-000000000002"),
        table_id=None,
        waiter_id=UUID("00000000-0000-0000-0000-000000000003"),
        customer_name="Cliente",
        status=OrderStatus.OPEN,
        total=Decimal("100.00"),
        subtotal=Decimal("100.00"),
        service_fee=Decimal("0"),
        service_fee_percent=Decimal("0"),
        discount=Decimal("0"),
        notes=None,
        order_type="counter",
        guest_count=1,
        closed_at=None,
        version=1,
        items=[],
        payments=[],
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Order)


def make_payment(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        order_id=UUID("00000000-0000-0000-0000-000000000005"),
        cashier_id=UUID("00000000-0000-0000-0000-000000000003"),
        method="pix",
        amount=Decimal("50.00"),
        amount_tendered=None,
        change_given=None,
        reference=None,
        status=PaymentStatus.CONFIRMED,
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Payment)


def make_establishment(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        service_fee_percent=Decimal("0"),
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Establishment)


def make_table(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        establishment_id=UUID("00000000-0000-0000-0000-000000000002"),
        status=TableStatus.OCCUPIED,
        version=1,
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Table)


class TestRegister:
    async def test_register_payment_success(self, service, mock_session):
        order = make_order(total=Decimal("100.00"))
        payment = make_payment(amount=Decimal("50.00"))

        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("0"))
        svc._payment_repo.add = AsyncMock(return_value=payment)

        result = await svc.register(PaymentCreate(
            order_id=order.id, method="pix", amount=Decimal("50.00"),
        ))

        assert result.amount == Decimal("50.00")
        assert result.method == "pix"

    async def test_register_order_not_found(self, service, mock_session):
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.register(PaymentCreate(
                order_id=UUID("00000000-0000-0000-0000-000000000099"),
                method="cash", amount=Decimal("10.00"),
            ))

    async def test_register_order_cancelled(self, service, mock_session):
        order = make_order(status=OrderStatus.CANCELLED)
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)

        with pytest.raises(BusinessRuleError, match="registrar pagamento"):
            await svc.register(PaymentCreate(
                order_id=order.id, method="cash", amount=Decimal("10.00"),
            ))

    async def test_register_already_fully_paid(self, service, mock_session):
        order = make_order(total=Decimal("100.00"))
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("100.00"))

        with pytest.raises(BusinessRuleError, match="totalmente paga"):
            await svc.register(PaymentCreate(
                order_id=order.id, method="cash", amount=Decimal("10.00"),
            ))

    async def test_register_payment_exceeds_balance(self, service, mock_session):
        order = make_order(total=Decimal("50.00"))
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("0"))

        with pytest.raises(BusinessRuleError, match="excede o saldo devedor"):
            await svc.register(PaymentCreate(
                order_id=order.id, method="cash", amount=Decimal("60.00"),
            ))

    async def test_register_allows_closed_order_for_fiado(self, service, mock_session):
        """Fiado: permite pagamento em comanda CLOSED."""
        order = make_order(status=OrderStatus.CLOSED, total=Decimal("100.00"))
        payment = make_payment(amount=Decimal("50.00"))

        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("0"))
        svc._payment_repo.add = AsyncMock(return_value=payment)

        result = await svc.register(PaymentCreate(
            order_id=order.id, method="pix", amount=Decimal("50.00"),
        ))
        assert result.amount == Decimal("50.00")


class TestListForOrder:
    async def test_list_for_order_success(self, service, mock_session):
        order = make_order()
        payment = make_payment(amount=Decimal("50.00"))

        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.list_by_order = AsyncMock(return_value=[payment])

        result = await svc.list_for_order(order.id)
        assert len(result) == 1
        assert result[0].amount == Decimal("50.00")

    async def test_list_for_order_empty(self, service, mock_session):
        order = make_order()
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.list_by_order = AsyncMock(return_value=[])

        result = await svc.list_for_order(order.id)
        assert result == []

    async def test_list_for_order_not_found(self, service, mock_session):
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.list_for_order(UUID("00000000-0000-0000-0000-000000000099"))


class TestFinish:
    async def test_finish_success(self, service, mock_session):
        order = make_order(table_id=UUID("00000000-0000-0000-0000-000000000004"),
                           total=Decimal("100.00"))
        table = make_table()
        fresh = make_order(table_id=UUID("00000000-0000-0000-0000-000000000004"),
                           total=Decimal("100.00"), status=OrderStatus.CLOSED)

        svc = service
        svc._order_repo.get_with_items = AsyncMock(side_effect=[order, fresh])
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("100.00"))
        svc._table_repo.get_by_establishment = AsyncMock(return_value=table)
        mock_session.flush = AsyncMock()

        result = await svc.finish(order.id, OrderFinish(version=1))
        assert result.total == Decimal("100.00")

    async def test_finish_not_found(self, service, mock_session):
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.finish(UUID("00000000-0000-0000-0000-000000000099"),
                             OrderFinish(version=1))

    async def test_finish_invalid_status(self, service, mock_session):
        order = make_order(status=OrderStatus.CANCELLED)
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)

        with pytest.raises(BusinessRuleError, match="possível finalizar"):
            await svc.finish(order.id, OrderFinish(version=1))

    async def test_finish_version_conflict(self, service, mock_session):
        order = make_order(version=2)
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)

        with pytest.raises(OptimisticLockError):
            await svc.finish(order.id, OrderFinish(version=1))

    async def test_finish_insufficient_payment(self, service, mock_session):
        order = make_order(total=Decimal("100.00"), version=1)
        svc = service
        svc._order_repo.get_with_items = AsyncMock(return_value=order)
        svc._payment_repo.sum_confirmed_by_order = AsyncMock(return_value=Decimal("30.00"))

        with pytest.raises(BusinessRuleError, match="Pagamento insuficiente"):
            await svc.finish(order.id, OrderFinish(version=1))

    async def test_finish_no_establishment(self, mock_session):
        svc = PaymentService(session=mock_session, company_id=UUID("00000000-0000-0000-0000-000000000001"))

        with pytest.raises(TenantError):
            await svc.finish(UUID("00000000-0000-0000-0000-000000000005"),
                             OrderFinish(version=1))

    async def test_register_no_establishment(self, mock_session):
        svc = PaymentService(session=mock_session, company_id=UUID("00000000-0000-0000-0000-000000000001"))

        with pytest.raises(TenantError):
            await svc.register(PaymentCreate(
                order_id=UUID("00000000-0000-0000-0000-000000000005"),
                method="cash", amount=Decimal("10.00"),
            ))
