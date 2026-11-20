"""
app/services/orders/reports.py

Relatórios, histórico e fiado.

Código movido sem mudança de order_service.py (lá está a explicação geral
e a classe OrderService, que junta todas as partes).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


from app.core.config import settings
from app.core.exceptions import BusinessRuleError
from app.models.order import Order, OrderItemStatus
from app.models.payment import PaymentStatus
from app.schemas.report import (
    DailyBreakdownEntry,
    DailyReport,
    FiadoCustomerGroup,
    FiadoEntry,
    PaymentMethodTotal,
    PeriodReport,
    ShiftReport,
    TopItem,
)
from app.schemas.order import OrderHistoryResponse
from app.services.orders.base import OrderServiceBase


class OrderReportsMixin(OrderServiceBase):
    """Relatórios, histórico e fiado."""

    # ── Relatórios / histórico ──────────────────────────────────────────────

    async def list_history(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        day: date | None = None,
    ) -> list[OrderHistoryResponse]:
        """Histórico de comandas fechadas (mais recentes primeiro)."""
        establishment_id = self._require_establishment()
        start = end = None
        if day is not None:
            tz = ZoneInfo(settings.TIMEZONE)
            start = datetime.combine(day, time.min, tzinfo=tz)
            end = start + timedelta(days=1)
        orders = await self._order_repo.list_closed(
            establishment_id, limit=limit, offset=offset, start=start, end=end
        )
        responses = []
        for order in orders:
            paid_total = sum(
                (p.amount for p in order.payments if p.status == PaymentStatus.CONFIRMED),
                Decimal("0.00"),
            )
            resp = OrderHistoryResponse.model_validate(order)
            resp.is_fiado = paid_total < order.total
            responses.append(resp)
        return responses

    async def list_fiado(self) -> list[FiadoEntry]:
        """Comandas com pagamento parcial (fiado)."""
        establishment_id = self._require_establishment()
        rows = await self._order_repo.list_fiado(establishment_id)
        return [
            FiadoEntry(
                order_id=order.id,
                customer_name=order.customer_name,
                table_number=table_number,
                order_type=order.order_type.value,
                total=order.total,
                paid=paid,
                remaining=order.total - paid,
                created_at=order.created_at,
                version=order.version,
            )
            for order, paid, table_number in rows
        ]

    async def list_fiado_grouped(self) -> list[FiadoCustomerGroup]:
        """Fiados agrupados por cliente, com total consolidado."""
        entries = await self.list_fiado()
        groups: dict[str, list[FiadoEntry]] = {}
        for entry in entries:
            name = entry.customer_name or "Avulso"
            groups.setdefault(name, []).append(entry)

        return [
            FiadoCustomerGroup(
                customer_name=name,
                entries=sorted(e_list, key=lambda e: e.created_at, reverse=True),
                total_remaining=sum(e.remaining for e in e_list),
                total_debt=sum(e.total for e in e_list),
            )
            for name, e_list in sorted(groups.items())
        ]

    @staticmethod
    def _aggregate_orders(orders: list[Order]) -> tuple[
        Decimal, int, list[PaymentMethodTotal], list[TopItem], dict[date, tuple[Decimal, int]], Decimal
    ]:
        """
        Agrega uma lista de comandas fechadas em: faturamento total, nº de
        comandas, faturamento por forma de pagamento, itens mais vendidos, um
        dicionário {data_local: (faturamento, nº comandas)} — usado pelo
        relatório por período pra montar o detalhamento dia a dia — e o total
        de taxa de serviço (10% do garçom) cobrado.

        Compartilhado entre daily_report(), period_report() e shift_report()
        — a única diferença entre eles é o intervalo consultado.
        """
        tz = ZoneInfo(settings.TIMEZONE)
        revenue_total = Decimal("0.00")
        service_fee_total = Decimal("0.00")
        method_totals: dict[str, Decimal] = {}
        method_counts: dict[str, int] = {}
        item_qty: dict[str, int] = {}
        item_total: dict[str, Decimal] = {}
        by_day: dict[date, list] = {}
        count = 0

        for order in orders:
            paid_total = sum(
                (p.amount for p in order.payments if p.status == PaymentStatus.CONFIRMED),
                Decimal("0.00"),
            )
            # Comandas fechadas como FIADO (saldo em aberto) não entram no faturamento
            # — só contam quando totalmente quitadas. O saldo pendente fica visível
            # só na tela de Fiado, pra não inflar o faturamento com dinheiro que
            # ainda não entrou.
            if paid_total < order.total:
                continue

            revenue_total += order.total
            service_fee_total += order.service_fee
            count += 1

            local_day = order.closed_at.astimezone(tz).date()
            bucket = by_day.setdefault(local_day, [Decimal("0.00"), 0])
            bucket[0] += order.total
            bucket[1] += 1

            for payment in order.payments:
                if payment.status == PaymentStatus.CONFIRMED:
                    key = payment.method.value
                    method_totals[key] = method_totals.get(key, Decimal("0.00")) + payment.amount
                    method_counts[key] = method_counts.get(key, 0) + 1
            for it in order.items:
                if it.status == OrderItemStatus.CANCELLED:
                    continue
                item_qty[it.item_name] = item_qty.get(it.item_name, 0) + it.quantity
                item_total[it.item_name] = item_total.get(it.item_name, Decimal("0.00")) + it.subtotal

        by_method = [
            PaymentMethodTotal(method=m, total=method_totals[m], count=method_counts[m])
            for m in method_totals
        ]
        by_method.sort(key=lambda x: x.total, reverse=True)

        top_items = [
            TopItem(name=name, quantity=item_qty[name], total=item_total[name])
            for name in item_qty
        ]
        top_items.sort(key=lambda x: x.quantity, reverse=True)

        daily_totals = {d: (v[0], v[1]) for d, v in by_day.items()}
        return revenue_total, count, by_method, top_items, daily_totals, service_fee_total

    async def daily_report(self, day: date | None = None) -> DailyReport:
        """
        Resumo do dia: faturamento, nº de comandas, ticket médio,
        faturamento por forma de pagamento e itens mais vendidos.

        O "dia" é calculado no fuso America/Sao_Paulo (o bar opera em horário
        local; closed_at é armazenado em UTC e comparado com o intervalo local).
        """
        establishment_id = self._require_establishment()
        tz = ZoneInfo(settings.TIMEZONE)
        target = day or datetime.now(tz).date()
        start = datetime.combine(target, time.min, tzinfo=tz)
        end = start + timedelta(days=1)

        orders = await self._order_repo.list_closed_between(
            establishment_id, start, end
        )

        revenue_total, count, by_method, top_items, _, service_fee_total = self._aggregate_orders(orders)
        average = (revenue_total / count) if count else Decimal("0.00")

        return DailyReport(
            date=target,
            revenue_total=revenue_total,
            orders_count=count,
            average_ticket=round(average, 2),
            service_fee_total=service_fee_total,
            by_payment_method=by_method,
            top_items=top_items[:10],
        )

    async def period_report(self, start_day: date, end_day: date) -> PeriodReport:
        """
        Resumo de um período (start_day e end_day inclusos nos dois extremos).

        Mesma lógica do daily_report, só que soma o intervalo inteiro e ainda
        devolve o detalhamento dia a dia (daily_breakdown) — pra ver a
        evolução do faturamento ao longo do período, não só o total.

        LANÇA:
            BusinessRuleError (422) → start_day depois de end_day, ou
            período maior que 366 dias (evita relatório gigante/lento).
        """
        if start_day > end_day:
            raise BusinessRuleError("A data inicial não pode ser depois da data final.")
        if (end_day - start_day).days > 366:
            raise BusinessRuleError("O período não pode ser maior que 366 dias.")

        establishment_id = self._require_establishment()
        tz = ZoneInfo(settings.TIMEZONE)
        start = datetime.combine(start_day, time.min, tzinfo=tz)
        end = datetime.combine(end_day, time.min, tzinfo=tz) + timedelta(days=1)

        orders = await self._order_repo.list_closed_between(
            establishment_id, start, end
        )

        revenue_total, count, by_method, top_items, daily_totals, service_fee_total = self._aggregate_orders(orders)
        average = (revenue_total / count) if count else Decimal("0.00")

        breakdown = [
            DailyBreakdownEntry(date=d, revenue_total=v[0], orders_count=v[1])
            for d, v in sorted(daily_totals.items())
        ]

        return PeriodReport(
            date_start=start_day,
            date_end=end_day,
            revenue_total=revenue_total,
            orders_count=count,
            average_ticket=round(average, 2),
            service_fee_total=service_fee_total,
            by_payment_method=by_method,
            top_items=top_items[:10],
            daily_breakdown=breakdown,
        )

    async def shift_report(self, start: datetime, end: datetime) -> ShiftReport:
        """
        Resumo de um turno com data/hora exatas (não precisa bater com o dia
        de calendário) — pensado pro bar que fecha de madrugada: ex. turno de
        05/09 16h até 06/09 05h, atravessando a virada do dia.

        `start`/`end` sem fuso são tratados como horário local
        (America/Sao_Paulo, configurável via TIMEZONE).

        LANÇA:
            BusinessRuleError (422) → start >= end, ou intervalo maior que 48h
            (turno de bar não passa disso; evita relatório gigante/lento).
        """
        tz = ZoneInfo(settings.TIMEZONE)
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)

        if start >= end:
            raise BusinessRuleError("O início do turno precisa ser antes do fim.")
        if (end - start) > timedelta(hours=48):
            raise BusinessRuleError("O turno não pode ser maior que 48 horas.")

        establishment_id = self._require_establishment()
        orders = await self._order_repo.list_closed_between(establishment_id, start, end)

        revenue_total, count, by_method, top_items, _, service_fee_total = self._aggregate_orders(orders)
        average = (revenue_total / count) if count else Decimal("0.00")

        return ShiftReport(
            start=start,
            end=end,
            revenue_total=revenue_total,
            orders_count=count,
            average_ticket=round(average, 2),
            service_fee_total=service_fee_total,
            by_payment_method=by_method,
            top_items=top_items[:10],
        )
