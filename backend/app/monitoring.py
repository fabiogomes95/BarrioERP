"""
app/monitoring.py — "algo caiu?" a cada 5 minutos.

Roda pela tarefa agendada BarrioERP-Monitor:
    backend\\.venv\\Scripts\\python.exe -m app.monitoring

Cada verificação devolve um Check (ok ou problema). O estado fica em
logs/monitor_state.json pra não virar spam:
  - avisa quando um problema COMEÇA,
  - repete a cada REMIND_AFTER enquanto continuar,
  - avisa quando VOLTA ao normal.

Avisos vão pro Telegram (ALERT_TELEGRAM_* no .env); sem isso configurado,
só ficam em logs/monitor.log. Um check que quebra (exceção) vira problema
— monitor que falha calado é pior que nenhum.

`python -m app.monitoring --test` manda uma mensagem de teste.
"""

import asyncio
import ctypes
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[2]       # raiz do repositório
LOGS = ROOT / "logs"
STATE_FILE = LOGS / "monitor_state.json"
LOG_FILE = LOGS / "monitor.log"

REMIND_AFTER = timedelta(hours=2)
PENDING_ORDER_MINUTES = 10
BACKUP_MAX_AGE = timedelta(hours=30)
DISK_MIN_FREE_GB = 10


@dataclass
class Check:
    key: str            # identificador estável (vira chave no estado)
    ok: bool
    problem: str = ""   # texto do aviso quando não está ok
    recovered: str = ""  # texto quando volta ao normal


# ── Verificações ──────────────────────────────────────────────────────────────

def _http_ok(url: str, timeout: float = 8) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (URL fixa da config)
            return 200 <= r.status < 300, f"HTTP {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def check_barrio() -> Check:
    ok, why = _http_ok("http://127.0.0.1:8000/health")
    return Check("barrio", ok, f"Barrio fora do ar ({why}). Comandas e caixa param.", "Barrio voltou.")


def check_public_menu() -> list[Check]:
    ok, why = _http_ok("http://127.0.0.1:8090/api/cardapio/matriz")
    checks = [Check("cardapio_local", ok, f"Serviço do cardápio online parado ({why}). Pedidos só pelo WhatsApp.",
                    "Cardápio online voltou.")]
    if settings.MONITOR_PUBLIC_MENU_URL:
        ok2, why2 = _http_ok(settings.MONITOR_PUBLIC_MENU_URL, timeout=15)
        checks.append(Check("cardapio_publico", ok2,
                            f"Cardápio não abre pelo link público ({why2}) — Tailscale Funnel?",
                            "Link público do cardápio voltou."))
    return checks


async def _pending_online_orders() -> int:
    from sqlalchemy import func, select

    from app.database.session import AsyncSessionLocal
    from app.models.online_order import OnlineOrder, OnlineOrderStatus

    limit = datetime.now(UTC) - timedelta(minutes=PENDING_ORDER_MINUTES)
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count()).select_from(OnlineOrder).where(
                OnlineOrder.status == OnlineOrderStatus.PENDING, OnlineOrder.created_at < limit,
            )
        ) or 0


def check_pending_orders() -> Check:
    n = asyncio.run(_pending_online_orders())
    return Check("pedido_parado", n == 0,
                 f"{n} pedido(s) online esperando aceite há mais de {PENDING_ORDER_MINUTES} min. "
                 "O Barrio está aberto no caixa?",
                 "Pedidos online em dia.")


def check_printer() -> Check | None:
    if not settings.THERMAL_PRINTER or sys.platform != "win32":
        return None
    import win32print

    # Status/atributos do spooler do Windows (impressoras USB genéricas nem
    # sempre informam "sem papel"; offline/erro elas informam)
    OFFLINE, ERROR, PAPER_OUT, PAPER_PROBLEM = 0x80, 0x2, 0x10, 0x40
    WORK_OFFLINE = 0x400
    try:
        h = win32print.OpenPrinter(settings.THERMAL_PRINTER)
        try:
            info = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        return Check("impressora", False, f"Impressora {settings.THERMAL_PRINTER} não encontrada ({type(e).__name__}).",
                     "Impressora voltou.")
    status, attrs = info["Status"], info["Attributes"]
    if status & (PAPER_OUT | PAPER_PROBLEM):
        why = "sem papel"
    elif status & OFFLINE or attrs & WORK_OFFLINE:
        why = "desligada ou desconectada"
    elif status & ERROR:
        why = "com erro"
    else:
        return Check("impressora", True, recovered="Impressora voltou.")
    return Check("impressora", False, f"Impressora térmica {why}. Tickets da cozinha não vão sair.",
                 "Impressora voltou.")


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def check_power() -> Check | None:
    if sys.platform != "win32":
        return None
    ps = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps)):
        return None
    on_battery = ps.ACLineStatus == 0
    pct = ps.BatteryLifePercent if 0 <= ps.BatteryLifePercent <= 100 else None
    msg = "Notebook do Barrio na BATERIA — a luz caiu ou o carregador soltou?"
    if pct is not None:
        msg += f" Carga: {pct}%."
    return Check("energia", not on_battery, msg, "Notebook de volta na tomada.")


def check_backup() -> list[Check]:
    checks = []
    f = Path(settings.MONITOR_BACKUP_FILE)
    if f.exists():
        age = datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)
        checks.append(Check("backup_velho", age <= BACKUP_MAX_AGE,
                            f"Backup do banco parado: o último tem {int(age.total_seconds() // 3600)}h.",
                            "Backup do banco em dia."))
    else:
        checks.append(Check("backup_velho", False, f"Arquivo de backup não encontrado: {f}", "Backup encontrado."))
    test_log = LOGS / "testar_backup.log"
    if test_log.exists():
        last = [l for l in test_log.read_text(encoding="utf-8-sig", errors="replace").splitlines() if "RESULTADO" in l]
        if last:
            checks.append(Check("backup_teste", "FALHOU" not in last[-1],
                                "O teste mensal do backup REPROVOU — ver logs\\testar_backup.log.",
                                "Teste do backup voltou a passar."))
    return checks


def check_publish() -> Check | None:
    log = LOGS / "publicar_cardapio.log"
    if not log.exists():
        return None
    lines = [l for l in log.read_text(encoding="utf-8-sig", errors="replace").splitlines() if l.strip()]
    if not lines:
        return None
    return Check("publicacao", "ERRO" not in lines[-1],
                 "Publicação do cardápio no GitHub falhando — a cópia do GitHub pode estar desatualizada.",
                 "Publicação do cardápio voltou.")


def check_disk() -> Check:
    free_gb = shutil.disk_usage(ROOT).free / 1024**3
    return Check("disco", free_gb >= DISK_MIN_FREE_GB, f"Disco quase cheio: {free_gb:.1f} GB livres.",
                 "Espaço em disco ok.")


CHECKS = [check_barrio, check_public_menu, check_pending_orders, check_printer,
          check_power, check_backup, check_publish, check_disk]


def run_checks() -> list[Check]:
    results: list[Check] = []
    for fn in CHECKS:
        name = fn.__name__.removeprefix("check_")
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = Check(f"falha_{name}", False, f"O monitor não conseguiu verificar '{name}': {type(e).__name__}: {e}",
                      f"Verificação '{name}' voltou a funcionar.")
        if r is None:
            continue
        results.extend(r if isinstance(r, list) else [r])
    return results


# ── Estado e avisos ───────────────────────────────────────────────────────────

def decide(results: list[Check], state: dict, now: float) -> tuple[list[str], dict]:
    """Quais mensagens mandar agora + novo estado. Puro (testado)."""
    messages: list[str] = []
    new_state: dict = {}
    for c in results:
        prev = state.get(c.key)
        if c.ok:
            if prev:  # estava com problema → voltou
                mins = int((now - prev["since"]) // 60)
                messages.append(f"✅ {c.recovered} (ficou {mins} min com problema)")
            continue
        if not prev:
            messages.append(f"🚨 {c.problem}")
            new_state[c.key] = {"since": now, "last_sent": now}
        elif now - prev["last_sent"] >= REMIND_AFTER.total_seconds():
            mins = int((now - prev["since"]) // 60)
            messages.append(f"⏰ Continua: {c.problem} (há {mins} min)")
            new_state[c.key] = {"since": prev["since"], "last_sent": now}
        else:
            new_state[c.key] = prev
    # Check que sumiu (ex: impressora removida da config) não fica preso no estado
    return messages, new_state


def send_telegram(text: str) -> bool:
    token, chat = settings.ALERT_TELEGRAM_BOT_TOKEN, settings.ALERT_TELEGRAM_CHAT_ID
    if not token or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _log(msg: str) -> None:
    LOGS.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def main() -> int:
    if "--test" in sys.argv:
        sent = send_telegram("🔔 Teste do monitor do Barrio: os avisos estão chegando.")
        print("Mensagem enviada." if sent else "Não enviou: confira ALERT_TELEGRAM_BOT_TOKEN/CHAT_ID no .env.")
        return 0 if sent else 1

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    results = run_checks()
    messages, new_state = decide(results, state, time.time())
    problems = [c.key for c in results if not c.ok]

    if messages:
        text = "Barrio — Recanto da Barra\n\n" + "\n\n".join(messages)
        sent = send_telegram(text)
        for m in messages:
            _log(("[enviado] " if sent else "[só log] ") + m)
    if "--verbose" in sys.argv:
        for c in results:
            print(("OK      " if c.ok else "PROBLEMA") + f"  {c.key:<18} {'' if c.ok else c.problem}")

    LOGS.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(new_state), encoding="utf-8")

    # Dinheiro (alertas, resumo da noite) e limpeza de logs — ver app/alerts.py.
    # Isolado: se quebrar, o monitor de "algo caiu?" continua valendo.
    try:
        from app import alerts
        alerts.run(send_telegram, _log)
    except Exception as e:  # noqa: BLE001
        _log(f"[erro] alerts: {type(e).__name__}: {e}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
