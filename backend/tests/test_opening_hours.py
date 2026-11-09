"""Horário de pedidos do cardápio público (inclui expediente que vira a madrugada)."""

from datetime import datetime

import pytest

from app.services.opening_hours import is_open, parse_hours

# 2026-11-03 é terça; 2026-11-07 é sábado; 2026-11-08 é domingo; 2026-11-09 é segunda
HOURS = {"seg": "", "ter": "17:00-23:00", "sab": "11:00-14:00,17:00-02:00", "dom": "17:00-23:00"}


@pytest.mark.parametrize("when, expected", [
    ("2026-11-03 16:59", False),  # terça antes de abrir
    ("2026-11-03 17:00", True),
    ("2026-11-03 22:59", True),
    ("2026-11-03 23:00", False),  # fim é exclusivo
    ("2026-11-07 12:30", True),   # sábado almoço
    ("2026-11-07 15:00", False),  # sábado entre almoço e noite
    ("2026-11-08 01:30", True),   # madrugada de domingo = expediente de sábado
    ("2026-11-08 02:00", False),
    ("2026-11-09 20:00", False),  # segunda fechado
    ("2026-11-05 20:00", False),  # quinta não configurada = fechado
])
def test_is_open(when, expected):
    assert is_open(HOURS, datetime.strptime(when, "%Y-%m-%d %H:%M")) is expected


def test_sem_horario_configurado_aceita_sempre():
    assert is_open({}, datetime(2026, 11, 9, 4, 0)) is True


@pytest.mark.parametrize("when, expected", [
    ("2026-11-06 17:59", False),  # sexta antes das 18h
    ("2026-11-06 18:00", True),
    ("2026-11-07 00:30", True),   # madrugada de sábado = expediente de sexta
    ("2026-11-07 04:59", True),
    ("2026-11-07 05:00", False),
    ("2026-11-07 10:00", False),  # sábado de manhã
    ("2026-11-09 03:00", True),   # madrugada de segunda = expediente de domingo
    ("2026-11-09 20:00", False),  # segunda fechado
    ("2026-11-05 20:00", False),  # quinta fechado
])
def test_sem_hora_de_fechar(when, expected):
    hours = {"sex": "18:00-", "sab": "18:00-", "dom": "18:00-"}
    assert is_open(hours, datetime.strptime(when, "%Y-%m-%d %H:%M")) is expected


def test_parse_madrugada_vira_minutos_alem_de_24h():
    assert parse_hours({"sab": "17:00-02:00"})[5] == [(17 * 60, 26 * 60)]
