"""
app/services/establishment_settings.py

Leitura/escrita das chaves do `Establishment.settings` (blob JSON em texto).
Coisas que o dono liga/desliga pelo Barrio sem mexer no .env nem reiniciar
nada — ex: pausar os pedidos do cardápio online numa noite cheia.

JSON inválido ou vazio vale como {} — uma configuração corrompida nunca
derruba o cardápio nem o Barrio, só volta ao padrão.
"""

import json
from typing import Any

from app.models.establishment import Establishment

ONLINE_ORDERS_PAUSED = "online_orders_paused"


def read_settings(establishment: Establishment) -> dict[str, Any]:
    try:
        data = json.loads(establishment.settings or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_setting(establishment: Establishment, key: str, value: Any) -> None:
    data = read_settings(establishment)
    data[key] = value
    establishment.settings = json.dumps(data, ensure_ascii=False)


def online_orders_paused(establishment: Establishment) -> bool:
    return bool(read_settings(establishment).get(ONLINE_ORDERS_PAUSED, False))
