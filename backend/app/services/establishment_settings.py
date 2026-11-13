"""
app/services/establishment_settings.py

Leitura/escrita das chaves do `Establishment.settings` (blob JSON em texto).
Coisas que o dono liga/desliga pelo Barrio sem mexer no .env nem reiniciar
nada — ex: pausar os pedidos do cardápio online numa noite cheia, ou o
"aviso do dia" ("Hoje sem delivery: só bebidas e churrasco na brasa").

JSON inválido ou vazio vale como {} — uma configuração corrompida nunca
derruba o cardápio nem o Barrio, só volta ao padrão.
"""

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from app.models.establishment import Establishment

ONLINE_ORDERS_PAUSED = "online_orders_paused"
DAY_NOTICE = "day_notice"

DAY_NOTICE_MAX_LEN = 280
# O aviso do dia vale até a virada do expediente: 5h da madrugada (mesmo corte
# do "18:00-" sem hora pra fechar, ver opening_hours.OPEN_END_MINUTES). Assim
# um aviso esquecido some sozinho e não aparece no cardápio de amanhã.
DAY_NOTICE_CUTOFF = time(5, 0)


def read_settings(establishment: Establishment) -> dict[str, Any]:
    try:
        data = json.loads(establishment.settings or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_setting(establishment: Establishment, key: str, value: Any) -> None:
    data = read_settings(establishment)
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    establishment.settings = json.dumps(data, ensure_ascii=False)


def online_orders_paused(establishment: Establishment) -> bool:
    return bool(read_settings(establishment).get(ONLINE_ORDERS_PAUSED, False))


# ── Aviso do dia ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DayNotice:
    text: str            # pode ser "" quando só desligou a entrega
    no_delivery: bool    # true = cardápio só oferece retirada
    until: datetime      # com fuso; depois disso o aviso não vale mais


def day_notice_expiry(now: datetime) -> datetime:
    """Próximo corte das 5h (now com fuso). 23h de sexta → 5h de sábado;
    1h da madrugada de sábado → 5h de sábado (ainda é o expediente de sexta)."""
    cutoff = datetime.combine(now.date(), DAY_NOTICE_CUTOFF, tzinfo=now.tzinfo)
    return cutoff if now < cutoff else cutoff + timedelta(days=1)


def active_day_notice(establishment: Establishment, now: datetime) -> DayNotice | None:
    raw = read_settings(establishment).get(DAY_NOTICE)
    if not isinstance(raw, dict):
        return None
    try:
        until = datetime.fromisoformat(raw["until"])
        if until.tzinfo is None or until <= now:
            return None
        text = str(raw.get("text") or "").strip()[:DAY_NOTICE_MAX_LEN]
        no_delivery = bool(raw.get("no_delivery", False))
    except (KeyError, TypeError, ValueError):
        return None
    if not text and not no_delivery:
        return None
    return DayNotice(text=text, no_delivery=no_delivery, until=until)


def set_day_notice(establishment: Establishment, text: str, no_delivery: bool, now: datetime) -> DayNotice | None:
    """Grava o aviso valendo até o próximo corte. Texto vazio e entrega ligada = apaga."""
    text = " ".join((text or "").split())[:DAY_NOTICE_MAX_LEN]
    if not text and not no_delivery:
        write_setting(establishment, DAY_NOTICE, None)
        return None
    notice = DayNotice(text=text, no_delivery=no_delivery, until=day_notice_expiry(now))
    write_setting(establishment, DAY_NOTICE, {
        "text": notice.text, "no_delivery": notice.no_delivery, "until": notice.until.isoformat(),
    })
    return notice
