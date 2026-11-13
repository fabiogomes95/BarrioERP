"""
app/alerts.py — de olho no dinheiro, pelo Telegram.

Roda junto com o monitor (BarrioERP-Monitor, a cada 5 min — ver
app/monitoring.py), sem tarefa agendada nova:

  1. ALERTA NA HORA: lê a auditoria desde a última rodada e avisa de
     item cancelado depois de ir pra cozinha, estorno de pagamento, desconto
     grande e comanda cancelada — com quem fez. Ações do DONO não geram
     alerta (quem recebe é ele). Diferença de caixa no fechamento avisa
     sempre, seja de quem for.
  2. RESUMO DA NOITE: às 6h (mesmo corte de "noite" dos relatórios), o que
     entrou, por forma de pagamento, caixa, cancelamentos/estornos com nome
     e o que ficou em aberto. Noite sem movimento não manda nada.
  3. LIMPEZA DE LOGS: 1x por dia, apaga arquivos rotacionados com mais de
     30 dias e encurta os logs que crescem sem rotação.

Estado próprio em logs/alerts_state.json (o monitor reescreve o dele a cada
rodada só com os checks — não dá pra dividir arquivo).

As regras de texto e de "isso merece alerta?" são funções puras, testadas em
tests/test_alerts.py; o resto só busca no banco e repassa.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
STATE_FILE = LOGS / "alerts_state.json"

NIGHT_CUTOFF_HOUR = 6        # mesma "noite" do app/services/insights.py
SUMMARY_SEND_UNTIL = time(7, 0)  # se o PC estava desligado às 6h, ainda manda até as 7h
LOG_KEEP_DAYS = 30
LOG_TRIM_LINES = 2000
ITEM_STATUS_PT = {"sent": "na cozinha", "preparing": "preparando", "ready": "pronto", "served": "servido"}
METHOD_PT = {"cash": "Dinheiro", "pix": "Pix", "credit_card": "Crédito", "debit_card": "Débito",
             "voucher": "Vale", "other": "Outro"}


def brl(v: Decimal | float | int) -> str:
    s = f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


@dataclass
class Event:
    """Uma linha da auditoria, já com nome/cargo de quem fez e onde (mesa/cliente)."""
    action: str
    user_name: str
    user_role: str | None
    at: datetime
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    where: str = ""


@dataclass
class CashClose:
    closed_by: str
    difference: Decimal
    counted: Decimal
    expected: Decimal


# ── 1. Alerta na hora (puro) ───────────────────────────────────────────────────

def _money(d: dict, *keys: str) -> Decimal:
    for k in keys:
        d = d.get(k) or {}
    try:
        return Decimal(str(d)) if not isinstance(d, dict) else Decimal("0")
    except Exception:  # noqa: BLE001
        return Decimal("0")


def anomaly_messages(events: list[Event], closes: list[CashClose],
                     discount_pct: Decimal, cash_diff: Decimal) -> list[str]:
    msgs: list[str] = []
    for e in events:
        if e.user_role == "owner":
            continue  # o dono não precisa ser avisado do que ele mesmo fez
        onde = f" — {e.where}" if e.where else ""
        if e.action == "order_item.cancel":
            item = e.before.get("item") or {}
            status = item.get("status")
            if status in (None, "pending"):
                continue  # lançou errado e cancelou na hora: rotina, não alerta
            # Valor do item (auditoria nova); registros antigos: diferença do total
            valor = _money(e.before, "item", "subtotal") or (
                _money(e.before, "order", "total") - _money(e.after, "order", "total"))
            motivo = (e.after.get("item") or {}).get("reason") or "sem motivo"
            msgs.append(f"🗑️ {e.user_name} cancelou {item.get('quantity', '?')}x {item.get('item_name', 'item')}"
                        f" ({ITEM_STATUS_PT.get(status, status)}){onde} — {brl(valor)}. Motivo: {motivo}")
        elif e.action == "order_item.quantity_change":
            antes, depois = int(e.before.get("quantity") or 0), int(e.after.get("quantity") or 0)
            status = e.before.get("status")
            if depois >= antes or status in (None, "pending"):
                continue  # aumentou, ou diminuiu item que nem foi pra cozinha
            valor = _money(e.before, "unit_price") * (antes - depois)
            msgs.append(f"➖ {e.user_name} tirou {antes - depois}x {e.before.get('item_name', 'item')}"
                        f" ({ITEM_STATUS_PT.get(status, status)}, era {antes}, ficou {depois}){onde} — {brl(valor)}")
        elif e.action == "payment.void":
            metodo = METHOD_PT.get(str(e.before.get("method", "")).lower(), e.before.get("method", ""))
            cliente = e.before.get("customer_name")
            msgs.append(f"↩️ {e.user_name} estornou um pagamento de {brl(_money(e.before, 'amount'))} ({metodo})"
                        f"{onde or (f' — {cliente}' if cliente else '')}")
        elif e.action == "order.discount_change":
            novo = _money(e.after, "discount")
            subtotal = _money(e.after, "order", "subtotal")
            if novo <= 0 or subtotal <= 0 or novo * 100 < subtotal * discount_pct:
                continue
            pct = (novo * 100 / subtotal).quantize(Decimal("1"))
            msgs.append(f"🏷️ {e.user_name} deu desconto de {brl(novo)} ({pct}% da conta de {brl(subtotal)}){onde}")
        elif e.action == "order.cancel":
            total = _money(e.after, "total")
            msgs.append(f"❌ {e.user_name} cancelou a comanda inteira{onde}" + (f" ({brl(total)})" if total > 0 else ""))
    for c in closes:
        if abs(c.difference) < cash_diff:
            continue
        lado = "SOBRANDO" if c.difference > 0 else "FALTANDO"
        msgs.append(f"💰 Caixa fechado por {c.closed_by} com {brl(abs(c.difference))} {lado} "
                    f"(contado {brl(c.counted)}, esperado {brl(c.expected)})")
    return msgs


# ── 2. Resumo da noite (puro) ──────────────────────────────────────────────────

@dataclass
class NightData:
    night: date
    received_by_method: dict[str, Decimal]
    orders_closed: int
    closed_total: Decimal
    fiado_count: int
    fiado_open: Decimal
    still_open: int                 # abertas com saldo a receber
    still_open_remaining: Decimal
    closes: list[CashClose]
    item_cancels: list[Event]
    voids: list[Event]
    discounts_total: Decimal
    order_cancels: list[Event]
    online_accepted: int
    online_rejected: int
    paid_not_closed: int = 0        # pagas, mas ninguém clicou em finalizar


def night_summary(d: NightData) -> str | None:
    received = sum(d.received_by_method.values(), Decimal("0"))
    if not (received or d.orders_closed or d.still_open or d.paid_not_closed or d.voids or d.item_cancels):
        return None  # bar fechado: não manda mensagem vazia
    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    lines = [f"📊 Resumo da noite — {dias[d.night.weekday()]} {d.night:%d/%m}", ""]
    lines.append(f"Recebido: {brl(received)}")
    for m, v in sorted(d.received_by_method.items(), key=lambda kv: -kv[1]):
        lines.append(f"  • {METHOD_PT.get(m, m)}: {brl(v)}")
    if d.orders_closed:
        ticket = d.closed_total / d.orders_closed
        lines.append(f"Comandas fechadas: {d.orders_closed} · ticket médio {brl(ticket)}")
    if d.online_accepted or d.online_rejected:
        lines.append(f"Pedidos do cardápio: {d.online_accepted} aceitos"
                     + (f", {d.online_rejected} recusados" if d.online_rejected else ""))
    if d.fiado_count:
        lines.append(f"Fiado novo: {d.fiado_count} conta(s), {brl(d.fiado_open)} a receber")
    if d.still_open:
        lines.append(f"⚠️ Ainda abertas: {d.still_open} comanda(s), faltando {brl(d.still_open_remaining)}")
    if d.paid_not_closed:
        lines.append(f"Pagas mas não finalizadas: {d.paid_not_closed} comanda(s) — finalizar pra liberar a mesa")
    for c in d.closes:
        if c.difference == 0:
            lines.append(f"Caixa ({c.closed_by}): bateu certinho")
        else:
            lado = "sobrando" if c.difference > 0 else "faltando"
            lines.append(f"Caixa ({c.closed_by}): {brl(abs(c.difference))} {lado}")

    controle: list[str] = []
    if d.item_cancels:
        por_pessoa: dict[str, int] = {}
        for e in d.item_cancels:
            por_pessoa[e.user_name] = por_pessoa.get(e.user_name, 0) + 1
        controle.append("Itens cancelados: " + ", ".join(f"{n} ({q})" for n, q in sorted(por_pessoa.items())))
    if d.voids:
        total = sum((_money(e.before, "amount") for e in d.voids), Decimal("0"))
        quem = ", ".join(sorted({e.user_name for e in d.voids}))
        controle.append(f"Estornos: {len(d.voids)} · {brl(total)} ({quem})")
    if d.discounts_total:
        controle.append(f"Descontos dados: {brl(d.discounts_total)}")
    if d.order_cancels:
        quem = ", ".join(sorted({e.user_name for e in d.order_cancels}))
        controle.append(f"Comandas canceladas: {len(d.order_cancels)} ({quem})")
    if controle:
        lines += ["", "Controle:"] + [f"  • {c}" for c in controle]
    return "\n".join(lines)


def night_window(night: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """A 'noite' D vai de D 06:00 até D+1 06:00 (hora local)."""
    start = datetime.combine(night, time(NIGHT_CUTOFF_HOUR), tzinfo=tz)
    return start, start + timedelta(days=1)


def summary_due(now_local: datetime, last_sent: str | None) -> date | None:
    """Qual noite resumir agora (ou None). Entre 6h e 7h, uma vez por noite."""
    if not (time(NIGHT_CUTOFF_HOUR) <= now_local.time() < SUMMARY_SEND_UNTIL):
        return None
    night = now_local.date() - timedelta(days=1)
    return None if last_sent == night.isoformat() else night


# ── 3. Limpeza de logs (puro o bastante pra testar com pasta temporária) ──────

def prune_logs(folder: Path, now: datetime, keep_days: int = LOG_KEEP_DAYS) -> tuple[int, int]:
    """Apaga logs rotacionados (nome com data: service_out-20261107T034432.964.log)
    mais velhos que keep_days e encurta os que crescem sem rotação. Nunca toca
    nos arquivos em uso pelos serviços. Retorna (apagados, encurtados)."""
    import re
    limite = (now - timedelta(days=keep_days)).timestamp()
    apagados = encurtados = 0
    for f in folder.glob("*.log"):
        if re.search(r"-\d{8}T\d{6}", f.name) and f.stat().st_mtime < limite:
            try:
                f.unlink()
                apagados += 1
            except OSError:
                pass
    for nome in ("monitor.log", "publicar_cardapio.log", "limpar_logs.log"):
        f = folder / nome
        if not f.exists():
            continue
        linhas = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if len(linhas) > LOG_TRIM_LINES:
            f.write_text("\n".join(linhas[-LOG_TRIM_LINES:]) + "\n", encoding="utf-8")
            encurtados += 1
    return apagados, encurtados


# ── Banco ─────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _db():
    """Sessão com engine próprio e SEM pool: o monitor roda várias vezes
    asyncio.run() no mesmo processo, e conexão guardada no pool de um loop
    que já fechou quebra no loop seguinte."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _json(s: str | None) -> dict:
    try:
        v = json.loads(s) if s else {}
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


async def _load_events(session, start: datetime, end: datetime, actions: tuple[str, ...]) -> list[Event]:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog
    from app.models.order import Order
    from app.models.table import Table
    from app.models.user import User

    rows = (await session.execute(
        select(AuditLog, User.name, User.role)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.action.in_(actions), AuditLog.created_at > start, AuditLog.created_at <= end)
        .order_by(AuditLog.created_at)
    )).all()
    events = []
    for log, name, role in rows:
        before, after = _json(log.before), _json(log.after)
        order_id = (before.get("order") or {}).get("order_id") or before.get("order_id") or after.get("order_id")
        where = ""
        if order_id:
            o = (await session.execute(
                select(Order.customer_name, Table.number).outerjoin(Table, Table.id == Order.table_id)
                .where(Order.id == order_id)
            )).first()
            if o:
                where = f"Mesa {o.number}" if o.number is not None else (o.customer_name or "Balcão")
                if o.number is not None and o.customer_name:
                    where += f" ({o.customer_name})"
        events.append(Event(log.action, name or "Alguém", getattr(role, "value", role),
                            log.created_at, before, after, where))
    return events


async def _load_closes(session, start: datetime, end: datetime) -> list[CashClose]:
    from sqlalchemy import select

    from app.models.cash import CashSession
    from app.models.user import User

    rows = (await session.execute(
        select(CashSession, User.name).outerjoin(User, User.id == CashSession.closed_by)
        .where(CashSession.closed_at > start, CashSession.closed_at <= end)
        .order_by(CashSession.closed_at)
    )).all()
    return [CashClose(name or "Alguém", s.difference or Decimal("0"), s.counted_amount or Decimal("0"),
                      s.expected_amount or Decimal("0")) for s, name in rows]


ALERT_ACTIONS = ("order_item.cancel", "order_item.quantity_change", "payment.void",
                 "order.discount_change", "order.cancel")


async def _anomalies_since(start: datetime, end: datetime) -> list[str]:
    async with _db() as session:
        events = await _load_events(session, start, end, ALERT_ACTIONS)
        closes = await _load_closes(session, start, end)
    return anomaly_messages(events, closes, Decimal(str(settings.ALERT_DISCOUNT_PERCENT)),
                            Decimal(str(settings.ALERT_CASH_DIFF)))


async def _night_data(night: date) -> NightData:
    from sqlalchemy import func, select

    from app.models.online_order import OnlineOrder, OnlineOrderStatus
    from app.models.order import Order, OrderStatus
    from app.models.payment import Payment, PaymentStatus

    tz = ZoneInfo(settings.TIMEZONE)
    start, end = night_window(night, tz)
    async with _db() as s:
        by_method = {getattr(m, "value", m): Decimal(v) for m, v in (await s.execute(
            select(Payment.method, func.sum(Payment.amount))
            .where(Payment.status == PaymentStatus.CONFIRMED, Payment.created_at >= start, Payment.created_at < end)
            .group_by(Payment.method)
        )).all()}

        paid_sub = (select(Payment.order_id, func.sum(Payment.amount).label("paid"))
                    .where(Payment.status == PaymentStatus.CONFIRMED).group_by(Payment.order_id).subquery())
        closed = (await s.execute(
            select(Order.total, func.coalesce(paid_sub.c.paid, 0))
            .outerjoin(paid_sub, paid_sub.c.order_id == Order.id)
            .where(Order.status == OrderStatus.CLOSED, Order.closed_at >= start, Order.closed_at < end)
        )).all()
        open_now = (await s.execute(
            select(Order.total, func.coalesce(paid_sub.c.paid, 0))
            .outerjoin(paid_sub, paid_sub.c.order_id == Order.id)
            .where(Order.closed_at.is_(None), Order.status != OrderStatus.CANCELLED, Order.created_at < end)
        )).all()
        fiados = [(t, p) for t, p in closed if Decimal(p) < t]

        events = await _load_events(s, start, end, ALERT_ACTIONS)
        closes = await _load_closes(s, start, end)
        online = dict((await s.execute(
            select(OnlineOrder.status, func.count())
            .where(OnlineOrder.created_at >= start, OnlineOrder.created_at < end).group_by(OnlineOrder.status)
        )).all())

    discounts = Decimal("0")
    for e in events:
        if e.action == "order.discount_change":
            discounts += max(Decimal("0"), _money(e.after, "discount") - _money(e.before, "discount"))
    return NightData(
        night=night, received_by_method=by_method,
        orders_closed=len(closed), closed_total=sum((t for t, _ in closed), Decimal("0")),
        fiado_count=len(fiados), fiado_open=sum((t - Decimal(p) for t, p in fiados), Decimal("0")),
        still_open=sum(1 for t, p in open_now if Decimal(p) < t),
        still_open_remaining=sum((t - Decimal(p) for t, p in open_now if Decimal(p) < t), Decimal("0")),
        paid_not_closed=sum(1 for t, p in open_now if Decimal(p) >= t),
        closes=closes,
        item_cancels=[e for e in events if e.action == "order_item.cancel" or (
            e.action == "order_item.quantity_change"
            and int(e.after.get("quantity") or 0) < int(e.before.get("quantity") or 0))],
        voids=[e for e in events if e.action == "payment.void"],
        discounts_total=discounts,
        order_cancels=[e for e in events if e.action == "order.cancel"],
        online_accepted=online.get(OnlineOrderStatus.ACCEPTED, 0),
        online_rejected=online.get(OnlineOrderStatus.REJECTED, 0),
    )


# ── Rodada (chamada pelo monitor) ─────────────────────────────────────────────

def run(send: Callable[[str], bool], log: Callable[[str], None], now: datetime | None = None) -> None:
    """Uma rodada: alertas desde a última, resumo se for a hora, limpeza 1x/dia.
    Cada parte é independente — se uma quebrar, as outras rodam e o erro vai pro log."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(settings.TIMEZONE)
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}

    def deliver(text: str, tag: str) -> None:
        sent = send(text)
        log(("[enviado] " if sent else "[só log] ") + f"{tag}: " + text.replace("\n", " | "))

    # 1. Alertas — o cursor só avança depois de enviar (se cair no meio, repete)
    if settings.ALERT_ANOMALIES:
        try:
            cursor = datetime.fromisoformat(state["anomaly_cursor"]) if "anomaly_cursor" in state else now
            msgs = asyncio.run(_anomalies_since(cursor, now))
            if msgs:
                deliver("Barrio — de olho no caixa\n\n" + "\n\n".join(msgs), "alerta")
            state["anomaly_cursor"] = now.isoformat()
        except Exception as e:  # noqa: BLE001
            log(f"[erro] alertas: {type(e).__name__}: {e}")

    # 2. Resumo da noite
    try:
        night = summary_due(now.astimezone(tz), state.get("summary_sent_for"))
        if night:
            text = night_summary(asyncio.run(_night_data(night)))
            if text:
                deliver(text, "resumo")
            state["summary_sent_for"] = night.isoformat()
    except Exception as e:  # noqa: BLE001
        log(f"[erro] resumo da noite: {type(e).__name__}: {e}")

    # 3. Limpeza de logs, 1x por dia
    today = now.astimezone(tz).date().isoformat()
    if state.get("logs_pruned_on") != today:
        try:
            apagados, encurtados = prune_logs(LOGS, now)
            if apagados or encurtados:
                log(f"Limpeza de logs: {apagados} arquivo(s) apagado(s), {encurtados} encurtado(s)")
            state["logs_pruned_on"] = today
        except Exception as e:  # noqa: BLE001
            log(f"[erro] limpeza de logs: {type(e).__name__}: {e}")

    LOGS.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
