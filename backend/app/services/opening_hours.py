"""
app/services/opening_hours.py

Horário em que o cardápio público aceita pedido (PUBLIC_MENU_HOURS no .env).

Formato — um texto por dia, vários intervalos separados por vírgula:
    {"seg": "", "ter": "17:00-23:00", ..., "sab": "11:00-14:00,17:00-02:00"}
    - dia ausente ou "" = fechado
    - fim menor/igual ao início = vira a madrugada ("17:00-02:00" de sábado
      vale até 2h do DOMINGO, contando como expediente de sábado)
    - sem fim ("18:00-") = sem hora certa pra fechar: vale até OPEN_END_MINUTES
      da madrugada (a casa avisa o cliente se a cozinha já fechou)
    - dicionário vazio = recurso desligado: aceita pedido sempre

A página (public_menu_static/index.html) repete esta mesma regra em JS só
pra mostrar "Aberto/Fechado"; quem decide de verdade é o servidor no POST.
Módulo puro — testado em tests/test_opening_hours.py.
"""

from datetime import datetime

DAYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]  # índice = datetime.weekday()
_DAY_MINUTES = 24 * 60
# "18:00-" (sem fim): o expediente acaba às 5h da madrugada seguinte
OPEN_END_MINUTES = _DAY_MINUTES + 5 * 60


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def parse_hours(spec: dict[str, str]) -> dict[int, list[tuple[int, int]]]:
    """{"ter": "17:00-02:00"} → {1: [(1020, 1560)]} (minutos; fim > 1440 = madrugada)."""
    parsed: dict[int, list[tuple[int, int]]] = {i: [] for i in range(7)}
    for key, ranges in spec.items():
        day = DAYS.index(key.strip().lower()[:3])
        for part in filter(None, (r.strip() for r in (ranges or "").split(","))):
            start_s, end_s = part.split("-")
            start = _to_minutes(start_s)
            if not end_s.strip():
                end = OPEN_END_MINUTES
            else:
                end = _to_minutes(end_s)
                if end <= start:
                    end += _DAY_MINUTES
            parsed[day].append((start, end))
    return parsed


def is_open(spec: dict[str, str], now: datetime) -> bool:
    if not spec:
        return True
    hours = parse_hours(spec)
    minute = now.hour * 60 + now.minute
    today = now.weekday()
    if any(start <= minute < end for start, end in hours[today]):
        return True
    # Expediente de ontem que atravessou a meia-noite
    yesterday = (today - 1) % 7
    return any(end > _DAY_MINUTES and minute < end - _DAY_MINUTES for _, end in hours[yesterday])
