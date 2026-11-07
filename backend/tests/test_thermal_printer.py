"""Formatação ESC/POS do recibo e do ticket de cozinha (sem impressora)."""

from datetime import datetime
from decimal import Decimal

from app.services.thermal_printer import WIDTH, _two_cols, kitchen_ticket, receipt

NOW = datetime(2026, 11, 6, 22, 30)


def _text_lines(data: bytes) -> list[str]:
    # Remove os comandos ESC/POS usados (ESC @ = 2 bytes, GS V B n = 4, demais = 3)
    out, i = bytearray(), 0
    while i < len(data):
        if data[i] in (0x1B, 0x1D):
            cmd = data[i + 1]
            i += 2 if cmd == ord("@") else 4 if cmd == ord("V") else 3
            continue
        out.append(data[i])
        i += 1
    return [l for l in out.decode("ascii").split("\n") if l.strip()]


def test_valor_alinhado_a_direita_e_quebra_nome_longo():
    lines = _two_cols("2x Pizza Portuguesa com borda recheada de catupiry extra", "R$ 106,00")
    assert all(len(l) <= WIDTH for l in lines)
    assert lines[-1].endswith("R$ 106,00") and len(lines[-1]) == WIDTH


def test_recibo_com_taxa_pagamento_e_falta_pagar():
    data = receipt(
        "Recanto da Barra", "Mesa 4 - Marina",
        [(2, "Brahma 600ml", Decimal("20.00")), (1, "Pizza Calabresa / Mussarela", Decimal("48.00"))],
        subtotal=Decimal("68.00"), service_fee=Decimal("6.80"), service_fee_percent=Decimal("10.00"),
        discount=Decimal("0"), total=Decimal("74.80"), payments=[("Pix", Decimal("50.00"))], now=NOW,
    )
    text = "\n".join(_text_lines(data))
    assert "Recanto da Barra" in text and "06/11/2026 22:30" in text
    assert "Taxa de servico (10%)" in text and "R$ 6,80" in text
    assert "R$ 74,80" in text and "Pago (Pix)" in text
    assert "FALTA PAGAR" in text and "R$ 24,80" in text
    assert data.startswith(b"\x1b@") and data.endswith(b"\x1dVB\x00")  # inicia e corta o papel


def test_ticket_cozinha_sem_acento_e_sem_preco():
    data = kitchen_ticket("Retirada - Marina", [(3, "Churrasco - coração", None), (1, "Batata Frita P", "sem sal")],
                          notes="Obs: capricha", now=NOW)
    text = "\n".join(_text_lines(data))
    assert "RETIRADA - MARINA" in text
    assert "3x Churrasco - coracao" in text  # acento removido, sempre legível
    assert "> sem sal" in text and "capricha" in text
    assert "R$" not in text
