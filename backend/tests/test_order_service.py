"""Testes do OrderService — regras de negócio de comandas."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from decimal import Decimal

import pytest

from app.models.order import Order, OrderItem, OrderItemStatus, OrderStatus, OrderType
from app.models.table import Table, TableStatus
from app.models.establishment import Establishment
from app.models.menu import MenuItem
from app.schemas.order import OrderCreate, OrderItemAdd, OrderClose
from app.services.order_service import OrderService
from app.core.exceptions import BusinessRuleError, NotFoundError, OptimisticLockError


@pytest.fixture
def service(mock_session, company_id, establishment_id, user_id):
    return OrderService(
        session=mock_session,
        company_id=UUID(company_id),
        establishment_id=UUID(establishment_id),
        user_id=UUID(user_id),
    )


def make_table(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        establishment_id=UUID("00000000-0000-0000-0000-000000000002"),
        number=5, label="Mesa 5", capacity=4,
        status=TableStatus.FREE, is_active=True, version=1,
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Table)


def make_establishment(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        service_fee_percent=Decimal("0"),
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Establishment)


def make_order(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000005"),
        establishment_id=UUID("00000000-0000-0000-0000-000000000002"),
        table_id=UUID("00000000-0000-0000-0000-000000000004"),
        status=OrderStatus.OPEN, order_type=OrderType.COUNTER,
        guest_count=1, customer_name=None, notes=None,
        subtotal=Decimal("0"), service_fee=Decimal("0"),
        service_fee_percent=Decimal("0"),
        discount=Decimal("0"), total=Decimal("0"),
        closed_at=None, version=1,
        items=[],
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=Order)


def make_item(**kwargs) -> MagicMock:
    defaults = dict(
        id=UUID("00000000-0000-0000-0000-000000000007"),
        order_id=UUID("00000000-0000-0000-0000-000000000005"),
        item_name="Item Teste", unit_price=Decimal("10"),
        quantity=2, subtotal=Decimal("20"),
        status=OrderItemStatus.PENDING,
        notes=None, cancelled_at=None, cancelled_reason=None,
    )
    defaults.update(kwargs)
    return MagicMock(**defaults, spec=OrderItem)


def make_menu_item(**kwargs) -> MagicMock:
    mock = MagicMock()
    for k, v in dict(
        id=UUID("00000000-0000-0000-0000-000000000006"),
        name="Hamburguer", price=Decimal("25"),
        is_active=True, is_available=True,
        **kwargs,
    ).items():
        setattr(mock, k, v)
    return mock


# ── open_order ─────────────────────────────────────────────────────────────────


class TestOpenOrder:
    async def test_open_order_success(self, service, mock_session, table_id):
        table = make_table()
        establishment = make_establishment()
        service._table_repo.get_by_establishment = AsyncMock(return_value=table)
        mock_session.get = AsyncMock(return_value=establishment)
        service._order_repo.get_open_by_table = AsyncMock(return_value=None)
        service._order_repo.add = AsyncMock()
        service._get_or_raise = AsyncMock()

        data = OrderCreate(
            table_id=UUID(table_id), order_type="counter",
            guest_count=2, customer_name="Teste",
        )
        result = await service.open_order(data)

        service._order_repo.add.assert_awaited_once()
        assert table.status == TableStatus.OCCUPIED

    async def test_open_order_table_not_found(self, service, table_id):
        service._table_repo.get_by_establishment = AsyncMock(return_value=None)
        data = OrderCreate(table_id=UUID(table_id))
        with pytest.raises(NotFoundError):
            await service.open_order(data)

    async def test_open_order_table_inactive(self, service, table_id):
        table = make_table(is_active=False)
        service._table_repo.get_by_establishment = AsyncMock(return_value=table)
        data = OrderCreate(table_id=UUID(table_id))
        with pytest.raises(BusinessRuleError, match="desativada"):
            await service.open_order(data)

    async def test_open_order_table_already_occupied(self, service, table_id):
        table = make_table()
        service._table_repo.get_by_establishment = AsyncMock(return_value=table)
        service._order_repo.get_open_by_table = AsyncMock(return_value=MagicMock())
        data = OrderCreate(table_id=UUID(table_id))
        with pytest.raises(BusinessRuleError, match="já possui uma comanda"):
            await service.open_order(data)


# ── add_item ────────────────────────────────────────────────────────────────────


class TestAddItem:
    async def test_add_item_success(self, service, order_id):
        order = make_order()
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_available_menu_item = AsyncMock(
            return_value=make_menu_item()
        )

        data = OrderItemAdd(
            menu_item_id="00000000-0000-0000-0000-000000000006",
            quantity=2,
        )
        result = await service.add_item(UUID(order_id), data)

        assert order.items[0].item_name == "Hamburguer"
        assert order.items[0].quantity == 2

    async def test_add_item_order_closed(self, service, order_id):
        order = make_order(status=OrderStatus.CLOSED)
        service._get_or_raise = AsyncMock(return_value=order)
        data = OrderItemAdd(item_name="Teste", unit_price=Decimal("10"), quantity=1)
        with pytest.raises(BusinessRuleError, match="ABERTAS"):
            await service.add_item(UUID(order_id), data)

    async def test_add_item_order_cancelled(self, service, order_id):
        order = make_order(status=OrderStatus.CANCELLED)
        service._get_or_raise = AsyncMock(return_value=order)
        data = OrderItemAdd(item_name="Teste", unit_price=Decimal("10"), quantity=1)
        with pytest.raises(BusinessRuleError, match="ABERTAS"):
            await service.add_item(UUID(order_id), data)


# ── cancel_item ────────────────────────────────────────────────────────────────


class TestCancelItem:
    async def test_cancel_item_success(self, service, order_id):
        item = make_item()
        order = make_order(items=[item])
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_item = AsyncMock(return_value=item)

        result = await service.cancel_item(UUID(order_id), item.id, reason="Cliente desistiu")

        assert item.status == OrderItemStatus.CANCELLED
        assert item.cancelled_reason == "Cliente desistiu"

    async def test_cancel_item_order_closed(self, service, order_id):
        order = make_order(status=OrderStatus.CLOSED)
        service._get_or_raise = AsyncMock(return_value=order)
        with pytest.raises(BusinessRuleError, match="Apenas comandas ABERTAS"):
            await service.cancel_item(UUID(order_id), UUID("00000000-0000-0000-0000-000000000007"))

    async def test_cancel_item_already_cancelled(self, service, order_id):
        item = make_item(status=OrderItemStatus.CANCELLED)
        order = make_order(items=[item])
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_item = AsyncMock(return_value=item)
        with pytest.raises(BusinessRuleError, match="já está cancelado"):
            await service.cancel_item(UUID(order_id), item.id)

    async def test_cancel_item_served(self, service, order_id):
        item = make_item(status=OrderItemStatus.SERVED)
        order = make_order(items=[item])
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_item = AsyncMock(return_value=item)
        with pytest.raises(BusinessRuleError, match="já foi servido"):
            await service.cancel_item(UUID(order_id), item.id)


# ── close_order ────────────────────────────────────────────────────────────────


class TestCloseOrder:
    async def test_close_order_success(self, service, mock_session, order_id, table_id):
        table = make_table(status=TableStatus.OCCUPIED)
        order = make_order(table_id=UUID(table_id), version=1)
        service._get_or_raise = AsyncMock(return_value=order)
        service._table_repo.get_by_establishment = AsyncMock(return_value=table)

        data = OrderClose(version=1)
        await service.close_order(UUID(order_id), data)

        assert order.status == OrderStatus.CLOSED
        assert order.closed_at is not None
        assert table.status == TableStatus.FREE

    async def test_close_order_wrong_version(self, service, order_id):
        order = make_order(version=2)
        service._get_or_raise = AsyncMock(return_value=order)
        data = OrderClose(version=1)
        with pytest.raises(OptimisticLockError):
            await service.close_order(UUID(order_id), data)

    async def test_close_order_already_cancelled(self, service, order_id):
        order = make_order(status=OrderStatus.CANCELLED)
        service._get_or_raise = AsyncMock(return_value=order)
        data = OrderClose(version=1)
        with pytest.raises(BusinessRuleError, match="Apenas comandas ABERTAS"):
            await service.close_order(UUID(order_id), data)


# ── cancel_order ───────────────────────────────────────────────────────────────


class TestCancelOrder:
    async def test_cancel_order_success(self, service, order_id, table_id):
        table = make_table(status=TableStatus.OCCUPIED)
        order = make_order(table_id=UUID(table_id))
        service._get_or_raise = AsyncMock(return_value=order)
        service._table_repo.get_by_establishment = AsyncMock(return_value=table)

        await service.cancel_order(UUID(order_id))

        assert order.status == OrderStatus.CANCELLED
        assert table.status == TableStatus.FREE

    async def test_cancel_order_already_cancelled(self, service, order_id):
        order = make_order(status=OrderStatus.CANCELLED)
        service._get_or_raise = AsyncMock(return_value=order)
        with pytest.raises(BusinessRuleError, match="já está cancelada"):
            await service.cancel_order(UUID(order_id))


# ── _recalculate_total ─────────────────────────────────────────────────────────


class TestRecalculateTotal:
    def test_excludes_cancelled_items(self):
        order = make_order()
        active = make_item(subtotal=Decimal("50"), status=OrderItemStatus.PENDING)
        cancelled = make_item(subtotal=Decimal("30"), status=OrderItemStatus.CANCELLED)
        order.items = [active, cancelled]

        service = object.__new__(OrderService)
        service._recalculate_total(order)

        assert order.subtotal == Decimal("50")
        assert order.total == Decimal("50")

    def test_all_cancelled_zero_total(self):
        order = make_order()
        order.items = [make_item(subtotal=Decimal("30"), status=OrderItemStatus.CANCELLED)]
        service = object.__new__(OrderService)
        service._recalculate_total(order)
        assert order.subtotal == Decimal("0")
        assert order.total == Decimal("0")

    def test_service_fee_applied(self):
        order = make_order(service_fee_percent=Decimal("10"))
        order.items = [make_item(subtotal=Decimal("100"), status=OrderItemStatus.PENDING)]
        service = object.__new__(OrderService)
        service._recalculate_total(order)
        assert order.subtotal == Decimal("100")
        assert order.service_fee == Decimal("10")
        assert order.total == Decimal("110")

    def test_discount_applied(self):
        order = make_order(discount=Decimal("20"))
        order.items = [make_item(subtotal=Decimal("100"), status=OrderItemStatus.PENDING)]
        service = object.__new__(OrderService)
        service._recalculate_total(order)
        assert order.total == Decimal("80")
