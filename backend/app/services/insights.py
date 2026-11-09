"""
app/services/insights.py

Relatórios de gestão (Caixa → Período):

- movement(): movimento por dia da semana e por horário — quando o bar
  enche, quanto fatura cada noite, o que mais sai em cada dia. Serve pra
  escalar equipe e planejar compra.
- customers(): clientes do delivery (pedidos online aceitos, que têm
  telefone) — quem mais pede, quanto gasta, prato favorito e quem sumiu.

"Noite" do bar: uma comanda aberta sábado 01:30 é da noite de SEXTA. O dia
de negócio vira às NIGHT_CUTOFF_HOUR (6h), não à meia-noite.

Funções puras sobre listas já carregadas — testadas sem banco em
tests/test_insights.py. O serviço só busca os dados e chama estas funções.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, TenantError
from app.models.online_order import OnlineOrder, OnlineOrderStatus
from app.models.order import Order, OrderItemStatus
from app.models.payment import PaymentStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.report import (
    CustomerEntry, CustomersReport, HourCell, MovementReport, WeekdayEntry, WeekdayTopItem,
)
from app.services.base import BaseService

NIGHT_CUTOFF_HOUR = 6
LAPSED_AFTER_DAYS = 30
CUSTOMERS_WINDOW_DAYS = 365


def business_day(moment: datetime, tz: ZoneInfo) -> date:
    """Dia da 'noite' do bar: antes das 6h ainda conta como o dia anterior."""
    return (moment.astimezone(tz) - timedelta(hours=NIGHT_CUTOFF_HOUR)).date()


def _fully_paid(order: Order) -> bool:
    # Mesma regra do faturamento (_aggregate_orders): fiado em aberto não conta
    paid = sum((p.amount for p in order.payments if p.status == PaymentStatus.CONFIRMED), Decimal("0"))
    return paid >= order.total


def movement(orders: list[Order], tz: ZoneInfo, top_per_day: int = 3) -> MovementReport:
    nights: dict[int, set[date]] = defaultdict(set)
    count: Counter[int] = Counter()
    revenue: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    cells: Counter[tuple[int, int]] = Counter()
    items: dict[int, Counter[str]] = defaultdict(Counter)

    for order in orders:
        if not _fully_paid(order):
            continue
        opened = order.created_at.astimezone(tz)
        day = business_day(order.created_at, tz)
        wd = day.weekday()  # 0 = segunda ... 6 = domingo
        nights[wd].add(day)
        count[wd] += 1
        revenue[wd] += order.total
        cells[(wd, opened.hour)] += 1
        for item in order.items:
            if item.status != OrderItemStatus.CANCELLED:
                items[wd][item.item_name] += item.quantity

    weekdays = []
    for wd in range(7):
        n = len(nights[wd])
        weekdays.append(WeekdayEntry(
            weekday=wd,
            nights=n,
            orders_count=count[wd],
            revenue_total=revenue[wd],
            revenue_per_night=(revenue[wd] / n).quantize(Decimal("0.01")) if n else Decimal("0.00"),
            orders_per_night=round(count[wd] / n, 1) if n else 0.0,
            top_items=[WeekdayTopItem(name=name, quantity=q) for name, q in items[wd].most_common(top_per_day)],
        ))
    heatmap = [HourCell(weekday=wd, hour=h, orders_count=c) for (wd, h), c in sorted(cells.items())]
    return MovementReport(weekdays=weekdays, heatmap=heatmap)


def customers(online_orders: list[OnlineOrder], today: date, tz: ZoneInfo, limit: int = 50) -> CustomersReport:
    by_phone: dict[str, list[OnlineOrder]] = defaultdict(list)
    for o in online_orders:
        if o.status == OnlineOrderStatus.ACCEPTED:
            by_phone[o.customer_phone].append(o)

    entries = []
    for phone, orders in by_phone.items():
        orders.sort(key=lambda o: o.created_at)
        last = orders[-1]
        fav: Counter[str] = Counter()
        for o in orders:
            for line in o.items:
                fav[line["item_name"]] += line["quantity"]
        last_day = last.created_at.astimezone(tz).date()
        days_since = (today - last_day).days
        entries.append(CustomerEntry(
            phone=phone,
            name=last.customer_name,  # o nome mais recente que a pessoa usou
            orders_count=len(orders),
            total=sum((o.total for o in orders), Decimal("0.00")),
            first_order=orders[0].created_at.astimezone(tz).date(),
            last_order=last_day,
            days_since_last=days_since,
            favorite_item=fav.most_common(1)[0][0] if fav else None,
            lapsed=len(orders) >= 2 and days_since > LAPSED_AFTER_DAYS,
        ))

    top = sorted(entries, key=lambda e: (-e.orders_count, -e.total))[:limit]
    lapsed = sorted((e for e in entries if e.lapsed), key=lambda e: (-e.orders_count, e.days_since_last))[:limit]
    return CustomersReport(
        customers_count=len(entries),
        returning_count=sum(1 for e in entries if e.orders_count >= 2),
        top=top,
        lapsed=lapsed,
    )


class InsightsService(BaseService):

    def _require_establishment(self):
        if self.establishment_id is None:
            raise TenantError("Usuário não está vinculado a um estabelecimento.")
        return self.establishment_id

    async def movement(self, start_day: date, end_day: date) -> MovementReport:
        if start_day > end_day:
            raise BusinessRuleError("A data inicial não pode ser depois da data final.")
        if (end_day - start_day).days > 366:
            raise BusinessRuleError("O período não pode ser maior que 366 dias.")
        tz = ZoneInfo(settings.TIMEZONE)
        # Fechamento até as 6h do dia seguinte ao fim: pega a noite inteira do último dia
        start = datetime.combine(start_day, datetime.min.time(), tzinfo=tz) + timedelta(hours=NIGHT_CUTOFF_HOUR)
        end = datetime.combine(end_day, datetime.min.time(), tzinfo=tz) + timedelta(days=1, hours=NIGHT_CUTOFF_HOUR + 6)
        orders = await OrderRepository(self.session).list_closed_between(self._require_establishment(), start, end)
        # Filtra pela NOITE em que a comanda foi aberta (não pela hora do fechamento)
        orders = [o for o in orders if start_day <= business_day(o.created_at, tz) <= end_day]
        return movement(orders, tz)

    async def customers(self) -> CustomersReport:
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()
        since = datetime.now(tz) - timedelta(days=CUSTOMERS_WINDOW_DAYS)
        rows = await self.session.scalars(
            select(OnlineOrder).where(
                OnlineOrder.establishment_id == self._require_establishment(),
                OnlineOrder.status == OnlineOrderStatus.ACCEPTED,
                OnlineOrder.created_at >= since,
            )
        )
        return customers(list(rows), today, tz)
