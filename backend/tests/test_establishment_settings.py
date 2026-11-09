"""Chaves do Establishment.settings (JSON em texto) — pausa dos pedidos online."""

import json

from app.models.establishment import Establishment
from app.services.establishment_settings import (
    ONLINE_ORDERS_PAUSED, online_orders_paused, read_settings, write_setting,
)


def test_sem_configuracao_nao_esta_pausado():
    assert online_orders_paused(Establishment(settings=None)) is False


def test_pausar_e_retomar_preserva_outras_chaves():
    est = Establishment(settings=json.dumps({"outra": 1}))
    write_setting(est, ONLINE_ORDERS_PAUSED, True)
    assert online_orders_paused(est) is True
    write_setting(est, ONLINE_ORDERS_PAUSED, False)
    assert online_orders_paused(est) is False
    assert read_settings(est)["outra"] == 1


def test_json_corrompido_volta_ao_padrao_sem_quebrar():
    for ruim in ("{nao e json", "[1, 2]", ""):
        est = Establishment(settings=ruim)
        assert read_settings(est) == {}
        assert online_orders_paused(est) is False
