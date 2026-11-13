"""Chaves do Establishment.settings (JSON em texto) — pausa e aviso do dia do cardápio."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.establishment import Establishment
from app.services.establishment_settings import (
    DAY_NOTICE, ONLINE_ORDERS_PAUSED, active_day_notice, day_notice_expiry, online_orders_paused,
    read_settings, set_day_notice, write_setting,
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


# ── Aviso do dia ─────────────────────────────────────────────────────────────

TZ = ZoneInfo("America/Sao_Paulo")


def test_aviso_vence_as_5h_do_expediente():
    sexta_noite = datetime(2026, 11, 13, 20, 0, tzinfo=TZ)
    assert day_notice_expiry(sexta_noite) == datetime(2026, 11, 14, 5, 0, tzinfo=TZ)
    madrugada = datetime(2026, 11, 14, 1, 30, tzinfo=TZ)  # ainda é a noite de sexta
    assert day_notice_expiry(madrugada) == datetime(2026, 11, 14, 5, 0, tzinfo=TZ)


def test_aviso_ativo_ate_vencer_e_preserva_pausa():
    est = Establishment(settings=json.dumps({ONLINE_ORDERS_PAUSED: True}))
    agora = datetime(2026, 11, 13, 19, 0, tzinfo=TZ)
    set_day_notice(est, "  Hoje sem delivery:\n só bebidas e churrasco  ", True, agora)
    aviso = active_day_notice(est, agora + timedelta(hours=5))
    assert aviso is not None
    assert aviso.text == "Hoje sem delivery: só bebidas e churrasco"
    assert aviso.no_delivery is True
    assert online_orders_paused(est) is True
    assert active_day_notice(est, datetime(2026, 11, 14, 5, 0, tzinfo=TZ)) is None


def test_aviso_vazio_apaga():
    est = Establishment(settings=None)
    agora = datetime(2026, 11, 13, 19, 0, tzinfo=TZ)
    set_day_notice(est, "Só bebidas hoje", False, agora)
    assert set_day_notice(est, "   ", False, agora) is None
    assert DAY_NOTICE not in read_settings(est)
    assert active_day_notice(est, agora) is None


def test_aviso_corrompido_nao_quebra():
    agora = datetime(2026, 11, 13, 19, 0, tzinfo=TZ)
    for ruim in ({"text": "x"}, {"text": "x", "until": "ontem"}, "texto solto",
                 {"text": "x", "until": "2026-11-14T05:00:00"}):  # sem fuso
        est = Establishment(settings=json.dumps({DAY_NOTICE: ruim}))
        assert active_day_notice(est, agora) is None
