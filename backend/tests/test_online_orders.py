"""
Pedidos online — as barreiras do lado do cliente (cardápio público) e o
aceite no app (pedido vira comanda).

O preço do carrinho já tem testes próprios (test_online_order_pricing.py);
aqui ele é trocado por um valor fixo pra testar só as regras em volta.
"""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import public_menu
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.online_order import OnlineOrder, OnlineOrderStatus
from app.models.order import OrderType
from app.services.online_order_pricing import PricedLine
from app.services.online_order_service import OnlineOrderService, format_phone, payment_label

EST = UUID("00000000-0000-0000-0000-000000000002")
PIZZA = UUID("00000000-0000-0000-0000-0000000000c1")
CALAB = UUID("00000000-0000-0000-0000-0000000000c2")


# ══════════════════════════════════════════════════════════════════════════════
# Lado do cliente: POST /api/cardapio/{slug}/pedidos
# ══════════════════════════════════════════════════════════════════════════════

def pedido(**over) -> dict:
    body = dict(customer_name="  Gabi   Souza ", customer_phone="(71) 99999-1234", fulfillment="pickup",
                payment_method="pix", items=[{"menu_item_id": str(PIZZA), "quantity": 1}])
    body.update(over)
    return body


class Cenario:
    """Monta o cardápio público com banco simulado. Ajuste os campos e chame post()."""

    def __init__(self):
        self.aberto = True
        self.pausado = False
        self.aviso = None                      # SimpleNamespace(no_delivery=True) = sem entrega hoje
        self.pendentes = 0
        self.total_carrinho = Decimal("48.00")
        self.adicionados: list = []

    def post(self, body: dict):
        session = MagicMock()
        session.scalar = AsyncMock(return_value=self.pendentes)
        session.add = lambda o: (setattr(o, "number", 12), self.adicionados.append(o))
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield session

        est = SimpleNamespace(id=EST, company_id=uuid4())
        linha = PricedLine(menu_item_id=PIZZA, item_name="Pizza Frango", unit_price=self.total_carrinho, quantity=1)
        repo = MagicMock()
        repo.return_value.list_by_establishment = AsyncMock(return_value=[])
        with patch.object(public_menu, "_open_now", return_value=self.aberto), \
             patch.object(public_menu, "AsyncSessionLocal", fake_session), \
             patch.object(public_menu, "_get_establishment", AsyncMock(return_value=est)), \
             patch.object(public_menu, "online_orders_paused", return_value=self.pausado), \
             patch.object(public_menu, "active_day_notice", return_value=self.aviso), \
             patch.object(public_menu, "MenuCategoryRepository", repo), \
             patch.object(public_menu, "MenuItemRepository", repo), \
             patch.object(public_menu, "price_cart", return_value=[linha]), \
             patch.object(public_menu.events, "publish", AsyncMock()):
            public_menu.limiter.enabled = False   # 4/min por IP atrapalharia os testes
            try:
                return TestClient(public_menu.app).post("/api/cardapio/matriz/pedidos", json=body)
            finally:
                public_menu.limiter.enabled = True


@pytest.fixture
def c() -> Cenario:
    return Cenario()


def test_pedido_ok_fica_pendente_com_nome_e_telefone_limpos(c):
    r = c.post(pedido())
    assert r.status_code == 201, r.text
    assert r.json() == {"number": 12, "total": 48.0}
    [o] = c.adicionados
    assert isinstance(o, OnlineOrder) and o.status == OnlineOrderStatus.PENDING
    assert o.customer_name == "Gabi Souza"
    assert o.customer_phone == "71999991234"
    assert o.total == Decimal("48.00")


def test_bar_fechado_recusa(c):
    c.aberto = False
    r = c.post(pedido())
    assert r.status_code == 409 and "fechados" in r.json()["detail"]
    assert c.adicionados == []


def test_pedidos_pausados_recusa(c):
    c.pausado = True
    r = c.post(pedido())
    assert r.status_code == 409 and "pausados" in r.json()["detail"]
    assert c.adicionados == []


def test_dia_sem_entrega_recusa_entrega_mas_aceita_retirada(c):
    c.aviso = SimpleNamespace(no_delivery=True)
    r = c.post(pedido(fulfillment="delivery"))
    assert r.status_code == 409 and "entrega" in r.json()["detail"]
    assert c.post(pedido(fulfillment="pickup")).status_code == 201


def test_fila_cheia_manda_pro_whatsapp(c):
    c.pendentes = public_menu.MAX_PENDING_ONLINE_ORDERS
    r = c.post(pedido())
    assert r.status_code == 429 and "WhatsApp" in r.json()["detail"]


def test_troco_menor_que_o_total_recusa(c):
    r = c.post(pedido(payment_method="cash", change_for="40"))
    assert r.status_code == 422 and "48,00" in r.json()["detail"]
    assert c.adicionados == []


def test_troco_so_vale_pra_dinheiro(c):
    r = c.post(pedido(payment_method="pix", change_for="100"))
    assert r.status_code == 201
    assert c.adicionados[0].change_for is None


def test_endereco_so_fica_guardado_na_entrega(c):
    c.post(pedido(fulfillment="pickup", delivery_location="Rua A, 10"))
    c.post(pedido(fulfillment="delivery", delivery_location="Rua A, 10"))
    assert [o.delivery_location for o in c.adicionados] == [None, "Rua A, 10"]


@pytest.mark.parametrize("tel", ["1234", "71 9999", "+55 71 99999-1234 ramal 22"])
def test_telefone_sem_ddd_ou_estranho_recusa(c, tel):
    assert c.post(pedido(customer_phone=tel)).status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Lado do app: aceitar / recusar
# ══════════════════════════════════════════════════════════════════════════════

def online(**over) -> OnlineOrder:
    o = OnlineOrder(
        id=uuid4(), establishment_id=EST, number=12, status=OnlineOrderStatus.PENDING,
        fulfillment=OrderType.DELIVERY, customer_name="Gabi", customer_phone="71999991234",
        delivery_location="Rua A, 10", payment_method="cash", change_for=Decimal("100"),
        notes="sem cebola", total=Decimal("0"), items=[],
    )
    for k, v in over.items():
        setattr(o, k, v)
    return o


@pytest.fixture
def app_side(mock_session):
    svc = OnlineOrderService(mock_session, UUID("00000000-0000-0000-0000-000000000001"), EST,
                             UUID("00000000-0000-0000-0000-000000000003"))
    svc._log_audit = AsyncMock()
    orders = MagicMock()
    orders.open_order = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    orders.add_item = AsyncMock()
    with patch("app.services.online_order_service.OrderService", return_value=orders):
        yield SimpleNamespace(svc=svc, session=mock_session, orders=orders)


@pytest.mark.asyncio
async def test_aceitar_abre_comanda_com_tudo_que_o_entregador_precisa(app_side):
    o = online()
    app_side.session.scalar = AsyncMock(return_value=o)
    order_id = await app_side.svc.accept(o.id)

    data = app_side.orders.open_order.call_args.args[0]
    assert data.order_type == OrderType.DELIVERY
    assert data.customer_name == "Gabi · online #12"
    assert data.notes == ("Pedido online #12 · Entrega · Tel (71) 99999-1234 · Entregar em: Rua A, 10"
                          " · Pagamento: Dinheiro (troco p/ R$ 100,00) · Obs: sem cebola")
    assert o.status == OnlineOrderStatus.ACCEPTED and o.order_id == order_id
    assert o.handled_at is not None


@pytest.mark.asyncio
async def test_aceitar_lanca_cada_tipo_de_item_pelo_caminho_certo(app_side):
    o = online(items=[
        {"menu_item_id": str(PIZZA), "item_name": "Pizza Frango", "unit_price": "48", "quantity": 1,
         "complemento": "borda", "half_first": None, "half_with": None},
        {"menu_item_id": None, "item_name": "Pizza ½ Frango ½ Calabresa", "unit_price": "50", "quantity": 1,
         "complemento": None, "half_first": str(PIZZA), "half_with": str(CALAB)},
        {"menu_item_id": None, "item_name": "Taxa de entrega", "unit_price": "5", "quantity": 1,
         "complemento": None, "half_first": None, "half_with": None},
    ])
    app_side.session.scalar = AsyncMock(return_value=o)
    await app_side.svc.accept(o.id)

    a, b, c = [call.args[1] for call in app_side.orders.add_item.call_args_list]
    assert (a.menu_item_id, a.complemento) == (PIZZA, "borda")                 # do cardápio: baixa estoque
    assert (b.menu_item_id, b.half_with) == (PIZZA, CALAB)                     # meio a meio: os dois sabores
    assert (c.menu_item_id, c.item_name, c.unit_price) == (None, "Taxa de entrega", Decimal("5"))


@pytest.mark.asyncio
async def test_item_que_acabou_antes_do_aceite_entra_com_o_preco_que_o_cliente_viu(app_side):
    o = online(items=[{"menu_item_id": str(PIZZA), "item_name": "Pizza Frango", "unit_price": "48",
                       "quantity": 2, "complemento": None, "half_first": None, "half_with": None}])
    app_side.session.scalar = AsyncMock(return_value=o)
    app_side.orders.add_item = AsyncMock(side_effect=[BusinessRuleError("indisponível"), None])
    await app_side.svc.accept(o.id)

    fallback = app_side.orders.add_item.call_args_list[1].args[1]
    assert (fallback.menu_item_id, fallback.item_name, fallback.unit_price, fallback.quantity) == \
        (None, "Pizza Frango", Decimal("48"), 2)
    assert o.status == OnlineOrderStatus.ACCEPTED


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [OnlineOrderStatus.ACCEPTED, OnlineOrderStatus.REJECTED])
async def test_pedido_ja_resolvido_nao_aceita_de_novo(app_side, status):
    """Dois aparelhos tocando "Aceitar": o segundo vê o pedido já aceito e não abre outra comanda."""
    o = online(status=status)
    app_side.session.scalar = AsyncMock(return_value=o)
    with pytest.raises(BusinessRuleError):
        await app_side.svc.accept(o.id)
    with pytest.raises(BusinessRuleError):
        await app_side.svc.reject(o.id)
    app_side.orders.open_order.assert_not_called()


@pytest.mark.asyncio
async def test_pedido_de_outro_estabelecimento_nao_aparece(app_side):
    app_side.session.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await app_side.svc.accept(uuid4())


@pytest.mark.asyncio
async def test_recusar_nao_abre_comanda(app_side):
    o = online()
    app_side.session.scalar = AsyncMock(return_value=o)
    await app_side.svc.reject(o.id)
    assert o.status == OnlineOrderStatus.REJECTED
    app_side.orders.open_order.assert_not_called()


# ── Formatação ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("digits,esperado", [
    ("71999991234", "(71) 99999-1234"),
    ("7133331234", "(71) 3333-1234"),
    ("5571999991234", "(71) 99999-1234"),
])
def test_telefone_formatado(digits, esperado):
    assert format_phone(digits) == esperado


def test_pagamento_formatado():
    assert payment_label("cash", Decimal("50")) == "Dinheiro (troco p/ R$ 50,00)"
    assert payment_label("cash") == "Dinheiro"
    assert payment_label("pix", Decimal("50")) == "Pix"
