"""Relatórios de movimento (dia da semana / horário) e de clientes do delivery."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models.online_order import OnlineOrder, OnlineOrderStatus
from app.models.order import Order, OrderItem, OrderItemStatus, OrderType
from app.models.payment import Payment, PaymentStatus
from app.services.insights import business_day, customers, movement

TZ = ZoneInfo("America/Sao_Paulo")


def _order(opened: datetime, total: str, items: list[tuple[str, int, OrderItemStatus]], paid: str | None = None) -> Order:
    o = Order(created_at=opened, total=Decimal(total))
    o.items = [OrderItem(item_name=n, quantity=q, status=s) for n, q, s in items]
    o.payments = [Payment(amount=Decimal(paid or total), status=PaymentStatus.CONFIRMED)]
    return o


def test_madrugada_conta_como_noite_anterior():
    sab_0130 = datetime(2026, 11, 7, 1, 30, tzinfo=TZ)   # sábado 01:30
    assert business_day(sab_0130, TZ) == date(2026, 11, 6)  # noite de sexta
    assert business_day(datetime(2026, 11, 7, 6, 0, tzinfo=TZ), TZ) == date(2026, 11, 7)


def test_movimento_por_dia_hora_e_itens():
    ok = OrderItemStatus.SERVED
    orders = [
        # duas sextas diferentes: média por noite = (100 + 60) / 2
        _order(datetime(2026, 10, 30, 20, 0, tzinfo=TZ), "100", [("Pizza Calabresa", 2, ok)]),
        _order(datetime(2026, 11, 7, 0, 30, tzinfo=TZ), "60", [("Brahma 600ml", 4, ok),
                                                               ("Pizza Calabresa", 1, OrderItemStatus.CANCELLED)]),
        # fiado em aberto não entra
        _order(datetime(2026, 11, 6, 21, 0, tzinfo=TZ), "80", [("Pizza Bacon", 1, ok)], paid="20"),
    ]
    rep = movement(orders, TZ)
    sexta = rep.weekdays[4]
    assert (sexta.nights, sexta.orders_count) == (2, 2)
    assert sexta.revenue_total == Decimal("160") and sexta.revenue_per_night == Decimal("80.00")
    # item cancelado não conta; Brahma (4) passa a Calabresa (2)
    assert [(t.name, t.quantity) for t in sexta.top_items] == [("Brahma 600ml", 4), ("Pizza Calabresa", 2)]
    assert {(c.weekday, c.hour, c.orders_count) for c in rep.heatmap} == {(4, 20, 1), (4, 0, 1)}
    assert len(rep.weekdays) == 7 and rep.weekdays[0].nights == 0


def _online(phone: str, name: str, when: datetime, total: str, items: list[tuple[str, int]],
            status: OnlineOrderStatus = OnlineOrderStatus.ACCEPTED) -> OnlineOrder:
    return OnlineOrder(customer_phone=phone, customer_name=name, created_at=when, total=Decimal(total),
                       status=status, fulfillment=OrderType.DELIVERY,
                       items=[{"item_name": n, "quantity": q, "unit_price": "10"} for n, q in items])


def test_clientes_frequentes_favorito_e_sumidos():
    today = date(2026, 11, 8)
    d = lambda m, dd: datetime(2026, m, dd, 20, 0, tzinfo=TZ)  # noqa: E731
    rows = [
        _online("84999990001", "Marina", d(8, 1), "50", [("Pizza Calabresa", 1)]),
        _online("84999990001", "Marina S.", d(9, 1), "70", [("Pizza Calabresa", 1), ("Coca-Cola 1L", 1)]),
        _online("84999990002", "João", d(11, 7), "30", [("Batata Frita G", 1)]),
        _online("84999990002", "João", d(11, 1), "30", [("Batata Frita G", 2)]),
        _online("84999990003", "Ana", d(11, 5), "40", [("Pizza Bacon", 1)],
                status=OnlineOrderStatus.REJECTED),  # recusado não conta
    ]
    rep = customers(rows, today, TZ)
    assert rep.customers_count == 2 and rep.returning_count == 2
    marina = next(c for c in rep.top if c.phone == "84999990001")
    assert marina.name == "Marina S." and marina.total == Decimal("120")
    assert marina.favorite_item == "Pizza Calabresa" and marina.lapsed is True
    assert [c.phone for c in rep.lapsed] == ["84999990001"]  # João pediu há 1 dia
