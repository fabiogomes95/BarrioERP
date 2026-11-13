"""Testes do OrderService — regras de negócio de comandas."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.order import Order, OrderItem, OrderItemStatus, OrderStatus, OrderType
from app.models.table import Table, TableStatus
from app.models.establishment import Establishment
from app.models.menu import MenuItem
from app.schemas.order import OrderCreate, OrderItemAdd, OrderClose
from app.services.order_service import OrderService
from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError, OptimisticLockError
from app.models.user import UserRole


@pytest.fixture
def service(mock_session, company_id, establishment_id, user_id):
    svc = OrderService(
        session=mock_session,
        company_id=UUID(company_id),
        establishment_id=UUID(establishment_id),
        user_id=UUID(user_id),
    )
    # Padrão: comanda sem pagamento. Testes de "total x já pago" sobrescrevem.
    svc._order_repo.lock = AsyncMock(return_value=True)
    svc._order_repo.sum_confirmed_payments = AsyncMock(return_value=Decimal("0"))
    return svc


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
        menu_item_id=None,
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
        service._stock_service.deduct_for_sale = AsyncMock()

        data = OrderItemAdd(
            menu_item_id="00000000-0000-0000-0000-000000000006",
            quantity=2,
        )
        result = await service.add_item(UUID(order_id), data)

        assert order.items[0].item_name == "Hamburguer"
        assert order.items[0].quantity == 2
        service._stock_service.deduct_for_sale.assert_awaited_once()

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


# ── total nunca abaixo do já pago ──────────────────────────────────────────────


class TestTotalNaoFicaAbaixoDoPago:
    """Desconto/cancelamento/quantidade/10% depois de pagamento parcial."""

    def _comanda_paga(self, service, pago: str, **kw):
        item = make_item(unit_price=Decimal("30"), quantity=2, subtotal=Decimal("60"))
        order = make_order(items=[item], subtotal=Decimal("60"), total=Decimal("60"), **kw)
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_item = AsyncMock(return_value=item)
        service._order_repo.sum_confirmed_payments = AsyncMock(return_value=Decimal(pago))
        return order, item

    async def test_desconto_abaixo_do_pago_e_barrado(self, service, order_id):
        self._comanda_paga(service, "50")
        with pytest.raises(BusinessRuleError, match="menor que o já pago"):
            await service.set_discount(UUID(order_id), Decimal("20"))

    async def test_desconto_que_ainda_cobre_o_pago_passa(self, service, order_id):
        order, _ = self._comanda_paga(service, "50")
        await service.set_discount(UUID(order_id), Decimal("10"))
        assert order.total == Decimal("50")

    async def test_cancelar_item_abaixo_do_pago_e_barrado(self, service, order_id):
        _, item = self._comanda_paga(service, "50")
        with pytest.raises(BusinessRuleError, match="menor que o já pago"):
            await service.cancel_item(UUID(order_id), item.id, reason="Lançado errado")

    async def test_diminuir_quantidade_abaixo_do_pago_e_barrado(self, service, order_id):
        _, item = self._comanda_paga(service, "50")
        service._stock_service = AsyncMock()  # estoque não é o assunto aqui
        with pytest.raises(BusinessRuleError, match="menor que o já pago"):
            await service.set_item_quantity(UUID(order_id), item.id, quantity=1)

    async def test_tirar_taxa_abaixo_do_pago_e_barrado(self, service, order_id):
        item = make_item(unit_price=Decimal("50"), quantity=1, subtotal=Decimal("50"))
        order = make_order(items=[item], subtotal=Decimal("50"), service_fee=Decimal("5"),
                           service_fee_percent=Decimal("10"), total=Decimal("55"))
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.sum_confirmed_payments = AsyncMock(return_value=Decimal("55"))
        with pytest.raises(BusinessRuleError, match="menor que o já pago"):
            await service.set_service_fee(UUID(order_id), apply=False)

    async def test_total_negativo_e_barrado(self, service, order_id):
        _, item = self._comanda_paga(service, "0", discount=Decimal("40"))
        with pytest.raises(BusinessRuleError, match="total negativo"):
            await service.cancel_item(UUID(order_id), item.id, reason="Lançado errado")

    async def test_cancelar_comanda_com_pagamento_e_barrado(self, service, order_id):
        order, _ = self._comanda_paga(service, "10")
        with pytest.raises(BusinessRuleError, match="Estorne os pagamentos"):
            await service.cancel_order(UUID(order_id))
        assert order.status == OrderStatus.OPEN


# ── quem pode cancelar/diminuir item ───────────────────────────────────────────


class TestPermissaoCancelarItem:
    def _setup(self, service, status):
        item = make_item(status=status)
        order = make_order(items=[item], subtotal=Decimal("20"), total=Decimal("20"))
        service._get_or_raise = AsyncMock(return_value=order)
        service._order_repo.get_item = AsyncMock(return_value=item)
        service._stock_service = AsyncMock()
        return item

    async def test_motivo_e_obrigatorio(self, service, order_id):
        item = self._setup(service, OrderItemStatus.PENDING)
        for vazio in (None, "", "  ", "ab"):
            with pytest.raises(BusinessRuleError, match="motivo"):
                await service.cancel_item(UUID(order_id), item.id, reason=vazio, actor_role=UserRole.OWNER)

    async def test_garcom_cancela_item_pendente(self, service, order_id):
        item = self._setup(service, OrderItemStatus.PENDING)
        await service.cancel_item(UUID(order_id), item.id, reason="Lançou errado", actor_role=UserRole.WAITER)
        assert item.status == OrderItemStatus.CANCELLED

    @pytest.mark.parametrize("status", [OrderItemStatus.SENT, OrderItemStatus.PREPARING, OrderItemStatus.READY])
    async def test_garcom_nao_cancela_item_que_foi_pra_cozinha(self, service, order_id, status):
        item = self._setup(service, status)
        with pytest.raises(ForbiddenError, match="só o caixa ou o gerente"):
            await service.cancel_item(UUID(order_id), item.id, reason="Cliente desistiu", actor_role=UserRole.WAITER)
        assert item.status == status

    async def test_caixa_cancela_item_que_foi_pra_cozinha(self, service, order_id):
        item = self._setup(service, OrderItemStatus.PREPARING)
        await service.cancel_item(UUID(order_id), item.id, reason="Cliente desistiu", actor_role=UserRole.CASHIER)
        assert item.status == OrderItemStatus.CANCELLED

    async def test_garcom_nao_diminui_quantidade_de_item_na_cozinha(self, service, order_id):
        item = self._setup(service, OrderItemStatus.PREPARING)
        with pytest.raises(ForbiddenError):
            await service.set_item_quantity(UUID(order_id), item.id, quantity=1, actor_role=UserRole.WAITER)

    async def test_garcom_pode_aumentar_quantidade_de_item_na_cozinha(self, service, order_id):
        item = self._setup(service, OrderItemStatus.PREPARING)
        await service.set_item_quantity(UUID(order_id), item.id, quantity=3, actor_role=UserRole.WAITER)
        assert item.quantity == 3


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


# ── list_open: quanto já foi pago (card "Falta R$ X") ──────────────────────────


AGORA = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)


class TestListOpenPago:
    async def test_lista_traz_o_pago_de_cada_comanda(self, service):
        a = make_order(id=UUID("00000000-0000-0000-0000-0000000000a1"), waiter_id=None, created_at=AGORA, updated_at=AGORA, total=Decimal("50"))
        b = make_order(id=UUID("00000000-0000-0000-0000-0000000000b2"), waiter_id=None, created_at=AGORA, updated_at=AGORA, total=Decimal("19.80"))
        service._order_repo.list_open = AsyncMock(return_value=[a, b])
        service._order_repo.sum_confirmed_payments_by_order = AsyncMock(return_value={a.id: Decimal("30")})

        result = {r.id: r for r in await service.list_open()}

        assert result[a.id].paid == Decimal("30")
        assert result[b.id].paid == Decimal("0")
        service._order_repo.sum_confirmed_payments_by_order.assert_awaited_once_with([a.id, b.id])
