"""
app/services/thermal_printer.py

Impressão DIRETA na térmica (POS-80C, USB) ligada ao PC que roda o backend —
sem navegador, sem janela de impressão, sem pop-up.

POR QUE NO SERVIDOR (e não window.print() no navegador)?
    O pedido de impressão chega no PC do caixa por SSE (celular do garçom,
    aceite de pedido online). O Chrome bloqueia a janela de impressão aberta
    sem clique do usuário ("Permita pop-ups...") e o alert() ainda travava a
    tela do Barrio até alguém clicar OK. Aqui o backend manda os bytes direto
    pro spooler do Windows (RAW), em ESC/POS — a "língua" das térmicas.

Formatação (recibo e ticket de cozinha) são funções puras, testadas em
tests/test_thermal_printer.py; só send_raw() fala com a impressora.

Sem impressora configurada (THERMAL_PRINTER vazio) ou fora do Windows,
is_configured() é False e quem chama cai no caminho antigo (evento SSE →
impressão pelo navegador do PC marcado como "impressora do bar").
"""

import sys
import unicodedata
from datetime import datetime
from decimal import Decimal

from app.core.config import settings

WIDTH = 48  # colunas na fonte padrão em papel de 80mm

INIT = b"\x1b@"
BOLD_ON, BOLD_OFF = b"\x1bE\x01", b"\x1bE\x00"
CENTER, LEFT = b"\x1ba\x01", b"\x1ba\x00"
NORMAL, DOUBLE, TALL = b"\x1d!\x00", b"\x1d!\x11", b"\x1d!\x01"  # TALL = só altura dupla
FEED_AND_CUT = b"\n\n\n\n\x1dVB\x00"


def _ascii(text: str) -> bytes:
    """Sem acento: as térmicas genéricas variam de página de código e imprimem
    lixo no lugar de 'ç/ã'. 'Coracao' é sempre legível; 'CoraÃ§Ã£o' não."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
    return plain.replace(b"\r", b"")


def _money(v: Decimal | float | int) -> str:
    s = f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        while len(w) > width:  # palavra maior que a linha
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _two_cols(left: str, right: str, width: int = WIDTH) -> list[str]:
    """'2x Brahma 600ml ............ R$ 20,00' — valor alinhado à direita."""
    room = width - len(right) - 1
    lines = _wrap(left, room)
    lines[-1] = lines[-1].ljust(room) + " " + right
    return lines


def _line(ch: str = "-") -> bytes:
    return (ch * WIDTH).encode() + b"\n"


def _text(s: str) -> bytes:
    return _ascii(s) + b"\n"


def kitchen_ticket(where: str, items: list[tuple[int, str, str | None]],
                   subtitle: str | None = None, notes: str | None = None,
                   now: datetime | None = None) -> bytes:
    """Ticket da cozinha: onde/quem, itens GRANDES, observações. Sem preço."""
    now = now or datetime.now()
    out = [INIT, CENTER, BOLD_ON, DOUBLE]
    out += [_text(l) for l in _wrap(where.upper(), WIDTH // 2)]
    out += [NORMAL, BOLD_OFF]
    if subtitle:
        out.append(_text(subtitle))
    out.append(_text(now.strftime("%H:%M")))
    out += [LEFT, _line("=")]
    for qty, name, item_notes in items:
        out += [BOLD_ON, TALL]
        out += [_text(l) for l in _wrap(f"{qty}x {name}", WIDTH)]
        out += [NORMAL, BOLD_OFF]
        if item_notes:
            out += [_text(f"   > {l}") for l in _wrap(item_notes, WIDTH - 5)]
        out.append(_line())
    if notes:
        out += [BOLD_ON, _text("OBS:"), BOLD_OFF]
        out += [_text(l) for l in _wrap(notes, WIDTH)]
    out.append(FEED_AND_CUT)
    return b"".join(out)


def receipt(bar_name: str, where: str, items: list[tuple[int, str, Decimal]],
            subtotal: Decimal, service_fee: Decimal, service_fee_percent: Decimal,
            discount: Decimal, total: Decimal, payments: list[tuple[str, Decimal]],
            now: datetime | None = None) -> bytes:
    """Recibo da comanda — mesmo conteúdo do printComanda() do navegador."""
    now = now or datetime.now()
    out = [INIT, CENTER, BOLD_ON, TALL, _text(bar_name), NORMAL, BOLD_OFF,
           _text(where), _text(now.strftime("%d/%m/%Y %H:%M")), LEFT, _line()]
    if not items:
        out.append(_text("(sem itens)"))
    for qty, name, line_total in items:
        out += [_text(l) for l in _two_cols(f"{qty}x {name}", _money(line_total))]
    out.append(_line())
    if service_fee > 0:
        out += [_text(l) for l in _two_cols("Subtotal", _money(subtotal))]
        pct = f"{Decimal(service_fee_percent).normalize():f}"  # 10.00 → "10", 12.50 → "12.5"
        out += [_text(l) for l in _two_cols(f"Taxa de servico ({pct}%)", _money(service_fee))]
    if discount > 0:
        out += [_text(l) for l in _two_cols("Desconto", "-" + _money(discount))]
    out += [BOLD_ON, TALL, _text(_two_cols("TOTAL", _money(total))[0]), NORMAL, BOLD_OFF]
    paid = sum((amount for _, amount in payments), Decimal("0"))
    for label, amount in payments:
        out += [_text(l) for l in _two_cols(f"Pago ({label})", "-" + _money(amount))]
    if paid > 0:
        remaining = max(Decimal("0"), total - paid)
        out += [BOLD_ON, _text(_two_cols("FALTA PAGAR", _money(remaining))[0]), BOLD_OFF]
    out += [_line(), CENTER, _text("Obrigado pela preferencia!"), FEED_AND_CUT]
    return b"".join(out)


def is_configured() -> bool:
    return bool(settings.THERMAL_PRINTER) and sys.platform == "win32"


def send_raw(data: bytes, printer: str | None = None) -> None:
    """Manda os bytes pro spooler do Windows sem passar pelo driver gráfico (RAW)."""
    import win32print  # só existe no Windows (pywin32)

    handle = win32print.OpenPrinter(printer or settings.THERMAL_PRINTER)
    try:
        win32print.StartDocPrinter(handle, 1, ("Barrio", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
