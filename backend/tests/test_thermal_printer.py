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
        [(2, "Brahma 600ml", Decimal("10.00"), Decimal("20.00")),
         (1, "Pizza Calabresa / Mussarela", Decimal("48.00"), Decimal("48.00"))],
        subtotal=Decimal("68.00"), service_fee=Decimal("6.80"), service_fee_percent=Decimal("10.00"),
        discount=Decimal("0"), total=Decimal("74.80"), payments=[("Pix", Decimal("50.00"))], now=NOW,
    )
    text = "\n".join(_text_lines(data))
    assert "Recanto da Barra" in text and "06/11/2026 22:30" in text
    assert "Taxa de servico (10%)" in text and "R$ 6,80" in text
    assert "R$ 74,80" in text and "Pago (Pix)" in text
    assert "FALTA PAGAR" in text and "R$ 24,80" in text
    assert "2 x R$ 10,00" in text                 # unitário quando qtd > 1
    assert "1 x R$ 48,00" not in text             # qtd 1: o total da linha já é o unitário
    assert data.startswith(b"\x1b@") and data.endswith(b"\x1dVB\x00")  # inicia e corta o papel


def test_recibo_delivery_com_local_pagamento_e_troco():
    from app.models.online_order import OnlineOrder
    from app.models.order import OrderType
    from app.services.direct_print import delivery_lines

    online = OnlineOrder(fulfillment=OrderType.DELIVERY, customer_name="Marina", customer_phone="81999998888",
                         delivery_location="Barraca 3, perto do coqueiro", payment_method="cash",
                         change_for=Decimal("100.00"), notes="sem cebola")
    data = receipt("Recanto da Barra", "Entrega - Marina", [(1, "Pizza Calabresa", Decimal("62.00"), Decimal("62.00"))],
                   subtotal=Decimal("62.00"), service_fee=Decimal("0"), service_fee_percent=Decimal("0"),
                   discount=Decimal("0"), total=Decimal("62.00"), payments=[],
                   delivery=delivery_lines(online, Decimal("62.00")), now=NOW)
    text = "\n".join(_text_lines(data))
    assert "ENTREGAR EM:" in text and "Barraca 3, perto do coqueiro" in text
    assert "(81) 99999-8888" in text and "Dinheiro" in text
    assert "LEVAR TROCO:" in text and "R$ 38,00 (paga com R$ 100,00)" in text
    assert "sem cebola" in text


def test_recibo_retirada_pix_sem_local_nem_troco():
    from app.models.online_order import OnlineOrder
    from app.models.order import OrderType
    from app.services.direct_print import delivery_lines

    online = OnlineOrder(fulfillment=OrderType.PICKUP, customer_name="Ana", customer_phone="81988887777",
                         payment_method="pix")
    labels = [l for l, _ in delivery_lines(online, Decimal("30.00"))]
    assert labels == ["Telefone", "Pagamento"]


def test_ticket_cozinha_sem_acento_e_sem_preco():
    data = kitchen_ticket("Retirada - Marina", [(3, "Churrasco - coração", None), (1, "Batata Frita P", "sem sal")],
                          notes="Obs: capricha", now=NOW)
    text = "\n".join(_text_lines(data))
    assert "RETIRADA - MARINA" in text
    assert "3x Churrasco - coracao" in text  # acento removido, sempre legível
    assert "> sem sal" in text and "capricha" in text
    assert "R$" not in text


def test_conta_junta_itens_iguais_lancados_em_horas_diferentes():
    from types import SimpleNamespace as I
    from app.models.order import OrderItemStatus as S
    from app.services.direct_print import receipt_items

    itens = [
        I(item_name="Churrasco", unit_price=Decimal("15.00"), quantity=5, subtotal=Decimal("75.00"), status=S.SERVED),
        I(item_name="Cerveja", unit_price=Decimal("12.00"), quantity=2, subtotal=Decimal("24.00"), status=S.SERVED),
        I(item_name="Churrasco ", unit_price=Decimal("15"), quantity=7, subtotal=Decimal("105.00"), status=S.READY),
        I(item_name="Churrasco", unit_price=Decimal("15.00"), quantity=3, subtotal=Decimal("45.00"), status=S.CANCELLED),
        I(item_name="Churrasco", unit_price=Decimal("12.00"), quantity=1, subtotal=Decimal("12.00"), status=S.SERVED),
    ]
    assert receipt_items(itens) == [
        (12, "Churrasco", Decimal("15.00"), Decimal("180.00")),
        (2, "Cerveja", Decimal("12.00"), Decimal("24.00")),
        (1, "Churrasco", Decimal("12.00"), Decimal("12.00")),   # preço diferente: linha própria
    ]
    text = "\n".join(_text_lines(receipt("Bar", "Mesa 1", receipt_items(itens), subtotal=Decimal("216"),
                                         service_fee=Decimal("0"), service_fee_percent=Decimal("0"),
                                         discount=Decimal("0"), total=Decimal("216"), payments=[], now=NOW)))
    assert "12x Churrasco" in text and "R$ 180,00" in text and "12 x R$ 15,00" in text
