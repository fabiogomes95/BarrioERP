"""
Cozinha: o que vai pra fila ao lançar, a fila do KDS, o avanço de status
pela cozinha e o "servido" do garçom.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.order import OrderItemStatus as S, OrderStatus
from app.schemas.order import OrderItemAdd
from tests.test_order_service import make_item, make_order, service  # noqa: F401 (fixture)

T0 = datetime(2026, 11, 20, 21, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def make_menu_item(**kw) -> SimpleNamespace:
    base = dict(id=uuid4(), name="Item", price=Decimal("25"), is_active=True, is_available=True, complementos=[])
    return SimpleNamespace(**{**base, **kw})


def cat(name: str, kitchen: bool) -> SimpleNamespace:
    return SimpleNamespace(name=name, sends_to_kitchen=kitchen)


# ── Ao lançar: vai pra cozinha ou não ─────────────────────────────────────────

async def _add(service, order, *menu_items, **data):
    service._get_or_raise = AsyncMock(return_value=order)
    service._order_repo.get_available_menu_item = AsyncMock(side_effect=list(menu_items))
    service._stock_service.deduct_for_sale = AsyncMock()
    await service.add_item(order.id, OrderItemAdd(**data))
    return order.items[-1]


async def test_prato_entra_direto_na_fila_da_cozinha(service):
    churrasco = make_menu_item(name="Churrasco", category=cat("Petiscos", True), complementos=[])
    item = await _add(service, make_order(), churrasco, menu_item_id=str(churrasco.id), quantity=3)
    assert item.status == S.SENT


async def test_bebida_nao_vai_pra_cozinha(service):
    cerveja = make_menu_item(name="Brahma 600ml", category=cat("Cervejas", False), complementos=[])
    item = await _add(service, make_order(), cerveja, menu_item_id=str(cerveja.id), quantity=2)
    assert item.status == S.PENDING


async def test_item_manual_nao_vai_pra_cozinha(service):
    item = await _add(service, make_order(), item_name="Taxa rolha", unit_price=Decimal("10"), quantity=1)
    assert item.status == S.PENDING


async def test_meio_a_meio_vai_pra_cozinha(service):
    a = make_menu_item(id=uuid4(), name="Pizza Frango", price=Decimal("48"), category=cat("Pizzas", True))
    b = make_menu_item(id=uuid4(), name="Pizza Calabresa", price=Decimal("50"), category=cat("Pizzas", True))
    item = await _add(service, make_order(), a, b, menu_item_id=str(a.id), half_with=str(b.id), quantity=1)
    assert item.status == S.SENT
    assert item.unit_price == Decimal("50")          # metade mais cara


# ── Fila do KDS ───────────────────────────────────────────────────────────────

def kitem(status, minutes, name="Churrasco"):
    return make_item(id=uuid4(), item_name=name, status=status, created_at=at(minutes), quantity=1)


async def test_fila_mostra_so_o_que_esta_em_preparo(service):
    order = make_order(table=SimpleNamespace(number=5, label="Mesa 5"), created_at=at(0), items=[
        kitem(S.SERVED, 0, "Batata"), kitem(S.PENDING, 1, "Cerveja"), kitem(S.CANCELLED, 2, "Pizza"),
        kitem(S.READY, 5, "Churrasco"), kitem(S.SENT, 3, "Caldo"),
    ])
    service._order_repo.list_kitchen_orders = AsyncMock(return_value=[order])
    [ticket] = await service.list_kitchen_queue()
    assert ticket.table_number == 5
    assert [i.item_name for i in ticket.items] == ["Caldo", "Churrasco"]   # em preparo, na ordem do pedido


async def test_fila_e_pela_ordem_do_item_mais_antigo_nao_da_abertura_da_mesa(service):
    """Mesa aberta há 2h com item novo não fura a fila de quem pediu antes."""
    velha = make_order(id=uuid4(), table=None, customer_name="mesa antiga", created_at=at(-120),
                       items=[kitem(S.SENT, 30)])
    nova = make_order(id=uuid4(), table=None, customer_name="mesa nova", created_at=at(10),
                      items=[kitem(S.SENT, 15)])
    service._order_repo.list_kitchen_orders = AsyncMock(return_value=[velha, nova])
    assert [t.customer_name for t in await service.list_kitchen_queue()] == ["mesa nova", "mesa antiga"]


async def test_comanda_sem_item_em_preparo_nao_aparece(service):
    order = make_order(table=None, created_at=at(0), items=[kitem(S.SERVED, 0)])
    service._order_repo.list_kitchen_orders = AsyncMock(return_value=[order])
    assert await service.list_kitchen_queue() == []


# ── Cozinha avança o status ───────────────────────────────────────────────────

def setup_item(service, item_status, order_status=OrderStatus.OPEN):
    item = make_item(status=item_status)
    order = make_order(status=order_status, items=[item])
    service._get_or_raise = AsyncMock(return_value=order)
    service._order_repo.get_item = AsyncMock(return_value=item)
    service._log_audit = AsyncMock()
    return order, item


@pytest.mark.parametrize("de,para", [
    (S.SENT, S.PREPARING), (S.PREPARING, S.READY),
    (S.READY, S.PREPARING),                        # marcou pronto errado: pode voltar
    (S.SENT, S.READY),                             # pode pular etapa
])
async def test_cozinha_move_entre_os_status_de_preparo(service, de, para):
    order, item = setup_item(service, de)
    await service.advance_kitchen_status(order.id, item.id, para)
    assert item.status == para
    service._log_audit.assert_awaited_once()


@pytest.mark.parametrize("para", [S.SERVED, S.CANCELLED, S.PENDING])
async def test_cozinha_nao_serve_nem_cancela(service, para):
    order, item = setup_item(service, S.READY)
    with pytest.raises(BusinessRuleError, match="cozinha"):
        await service.advance_kitchen_status(order.id, item.id, para)
    assert item.status == S.READY


@pytest.mark.parametrize("atual", [S.PENDING, S.SERVED, S.CANCELLED])
async def test_cozinha_nao_mexe_em_item_fora_da_fila(service, atual):
    order, item = setup_item(service, atual)
    with pytest.raises(BusinessRuleError, match="fila da cozinha"):
        await service.advance_kitchen_status(order.id, item.id, S.READY)
    assert item.status == atual


@pytest.mark.parametrize("comanda", [OrderStatus.CLOSED, OrderStatus.CANCELLED])
async def test_cozinha_nao_mexe_em_comanda_fechada(service, comanda):
    order, item = setup_item(service, S.SENT, comanda)
    with pytest.raises(BusinessRuleError):
        await service.advance_kitchen_status(order.id, item.id, S.READY)
    assert item.status == S.SENT


async def test_cozinha_item_inexistente(service):
    order, _ = setup_item(service, S.SENT)
    service._order_repo.get_item = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.advance_kitchen_status(order.id, uuid4(), S.READY)


async def test_cozinha_funciona_com_conta_pedida(service):
    order, item = setup_item(service, S.PREPARING, OrderStatus.BILL_REQUESTED)
    await service.advance_kitchen_status(order.id, item.id, S.READY)
    assert item.status == S.READY


# ── Garçom marca servido ──────────────────────────────────────────────────────

@pytest.mark.parametrize("atual", [S.READY, S.PENDING])
async def test_garcom_serve_o_que_esta_pronto_ou_nao_precisa_de_cozinha(service, atual):
    order, item = setup_item(service, atual)
    await service.mark_item_served(order.id, item.id)
    assert item.status == S.SERVED


@pytest.mark.parametrize("atual", [S.SENT, S.PREPARING, S.SERVED, S.CANCELLED])
async def test_garcom_nao_serve_o_que_ainda_esta_na_cozinha_ou_ja_saiu(service, atual):
    order, item = setup_item(service, atual)
    with pytest.raises(BusinessRuleError, match="servido"):
        await service.mark_item_served(order.id, item.id)
    assert item.status == atual


async def test_garcom_nao_serve_em_comanda_fechada(service):
    order, item = setup_item(service, S.READY, OrderStatus.CLOSED)
    with pytest.raises(BusinessRuleError):
        await service.mark_item_served(order.id, item.id)
    assert item.status == S.READY
