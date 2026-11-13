"""Alertas de dinheiro, resumo da noite e limpeza de logs (app/alerts.py) — regras puras."""

import os
import time as _time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.alerts import (
    CashClose, Event, NightData, anomaly_messages, night_summary, night_window, prune_logs, summary_due,
)

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 11, 14, 1, 30, tzinfo=TZ)
D20, R20 = Decimal("20"), Decimal("20")


def ev(action, role="waiter", nome="Zé", before=None, after=None, where="Mesa 5"):
    return Event(action, nome, role, AGORA, before or {}, after or {}, where)


def cancel(status, role="waiter", total_antes="100.00", total_depois="70.00", nome="Zé"):
    return ev("order_item.cancel", role, nome,
              before={"item": {"item_name": "Picanha", "status": status, "quantity": 1}, "order": {"total": total_antes}},
              after={"item": {"reason": "cliente desistiu"}, "order": {"total": total_depois}})


def test_cancelar_item_que_ja_foi_pra_cozinha_alerta_com_valor_e_motivo():
    [m] = anomaly_messages([cancel("preparing")], [], D20, R20)
    assert "Zé cancelou 1x Picanha (preparando) — Mesa 5 — R$ 30,00" in m and "cliente desistiu" in m


def test_valor_do_item_vem_da_auditoria_nova():
    e = cancel("ready")
    e.before["item"]["subtotal"] = "89.90"
    e.before["order"]["total"] = e.after["order"]["total"] = "60.00"   # registro antigo bugado: antes == depois
    [m] = anomaly_messages([e], [], D20, R20)
    assert "R$ 89,90" in m


def test_paga_mas_nao_finalizada_nao_aparece_como_dinheiro_faltando():
    txt = night_summary(dados(received_by_method={"cash": Decimal("27")}, paid_not_closed=1))
    assert "Pagas mas não finalizadas: 1" in txt and "Ainda abertas" not in txt


def test_diminuir_item_que_foi_pra_cozinha_alerta():
    e = ev("order_item.quantity_change", "cashier", "Ana",
           before={"item_name": "Caipirinha", "quantity": 5, "status": "preparing", "unit_price": "18.00"},
           after={"item_name": "Caipirinha", "quantity": 2})
    [m] = anomaly_messages([e], [], D20, R20)
    assert "Ana tirou 3x Caipirinha (preparando, era 5, ficou 2) — Mesa 5 — R$ 54,00" in m


def test_aumentar_ou_diminuir_pendente_nao_alerta():
    mais = ev("order_item.quantity_change", before={"quantity": 1, "status": "sent"}, after={"quantity": 3})
    pendente = ev("order_item.quantity_change", before={"quantity": 5, "status": "pending"}, after={"quantity": 3})
    assert anomaly_messages([mais, pendente], [], D20, R20) == []


def test_cancelar_item_pendente_e_rotina():
    assert anomaly_messages([cancel("pending")], [], D20, R20) == []


def test_acao_do_dono_nao_gera_alerta():
    assert anomaly_messages([cancel("served", role="owner"),
                             ev("payment.void", "owner", before={"amount": "50"})], [], D20, R20) == []


def test_estorno_sempre_alerta():
    [m] = anomaly_messages([ev("payment.void", "cashier", "Ana", before={"amount": "48.50", "method": "pix"})], [], D20, R20)
    assert m == "↩️ Ana estornou um pagamento de R$ 48,50 (Pix) — Mesa 5"


def test_desconto_so_a_partir_do_limite():
    pequeno = ev("order.discount_change", "manager", after={"discount": "10", "order": {"subtotal": "100"}})
    grande = ev("order.discount_change", "manager", after={"discount": "25", "order": {"subtotal": "100"}})
    assert anomaly_messages([pequeno], [], D20, R20) == []
    [m] = anomaly_messages([grande], [], D20, R20)
    assert "desconto de R$ 25,00 (25% da conta de R$ 100,00)" in m


def test_comanda_cancelada_alerta():
    [m] = anomaly_messages([ev("order.cancel", "manager", "Gerente", after={"total": "80.00"})], [], D20, R20)
    assert "Gerente cancelou a comanda inteira — Mesa 5 (R$ 80,00)" in m


def test_diferenca_de_caixa_avisa_ate_do_dono_e_ignora_troco_miudo():
    closes = [CashClose("Dono", Decimal("-35"), Decimal("465"), Decimal("500")),
              CashClose("Ana", Decimal("2.50"), Decimal("502.50"), Decimal("500"))]
    [m] = anomaly_messages([], closes, D20, R20)
    assert "R$ 35,00 FALTANDO" in m and "Dono" in m


def test_evento_com_dados_quebrados_nao_derruba():
    estranho = ev("order_item.cancel", before={"item": {"status": "sent"}, "order": {"total": "abc"}}, after={})
    [m] = anomaly_messages([estranho], [], D20, R20)
    assert "cancelou" in m


# ── resumo da noite ──

def dados(**kw):
    base = dict(night=date(2026, 11, 13), received_by_method={}, orders_closed=0, closed_total=Decimal("0"),
                fiado_count=0, fiado_open=Decimal("0"), still_open=0, still_open_remaining=Decimal("0"),
                closes=[], item_cancels=[], voids=[], discounts_total=Decimal("0"), order_cancels=[],
                online_accepted=0, online_rejected=0)
    base.update(kw)
    return NightData(**base)


def test_noite_sem_movimento_nao_manda_nada():
    assert night_summary(dados()) is None


def test_resumo_completo():
    txt = night_summary(dados(
        received_by_method={"pix": Decimal("820"), "cash": Decimal("430.50")},
        orders_closed=25, closed_total=Decimal("1250.50"), fiado_count=1, fiado_open=Decimal("60"),
        still_open=1, still_open_remaining=Decimal("45"),
        closes=[CashClose("Ana", Decimal("-5"), Decimal("425.50"), Decimal("430.50"))],
        item_cancels=[cancel("sent"), cancel("pending", nome="Bia")],
        voids=[ev("payment.void", before={"amount": "20"})], discounts_total=Decimal("15"),
        online_accepted=4, online_rejected=1,
    ))
    assert txt.startswith("📊 Resumo da noite — sex 13/11")
    for trecho in ["Recebido: R$ 1.250,50", "• Pix: R$ 820,00", "• Dinheiro: R$ 430,50",
                   "Comandas fechadas: 25 · ticket médio R$ 50,02", "4 aceitos, 1 recusados",
                   "Fiado novo: 1 conta(s), R$ 60,00", "Ainda abertas: 1 comanda(s), faltando R$ 45,00",
                   "Caixa (Ana): R$ 5,00 faltando", "Itens cancelados: Bia (1), Zé (1)",
                   "Estornos: 1 · R$ 20,00 (Zé)", "Descontos dados: R$ 15,00"]:
        assert trecho in txt, trecho
    assert txt.index("Pix") < txt.index("Dinheiro")  # maior primeiro


def test_janela_da_noite_e_hora_de_mandar():
    start, end = night_window(date(2026, 11, 13), TZ)
    assert start == datetime(2026, 11, 13, 6, tzinfo=TZ) and end == datetime(2026, 11, 14, 6, tzinfo=TZ)
    assert summary_due(datetime(2026, 11, 14, 6, 3, tzinfo=TZ), None) == date(2026, 11, 13)
    assert summary_due(datetime(2026, 11, 14, 6, 3, tzinfo=TZ), "2026-11-13") is None   # já mandou
    assert summary_due(datetime(2026, 11, 14, 5, 59, tzinfo=TZ), None) is None           # cedo
    assert summary_due(datetime(2026, 11, 14, 7, 0, tzinfo=TZ), None) is None            # passou da hora


# ── limpeza de logs ──

def test_limpeza_apaga_so_rotacionados_velhos_e_encurta_os_que_crescem(tmp_path):
    agora = datetime.now(UTC)
    velho = tmp_path / "service_out-20260901T010203.456.log"
    novo = tmp_path / "service_out-20261110T010203.456.log"
    em_uso = tmp_path / "service_out.log"
    for f in (velho, novo, em_uso):
        f.write_text("x")
    antigo = _time.time() - 40 * 86400
    os.utime(velho, (antigo, antigo))
    os.utime(em_uso, (antigo, antigo))   # em uso nunca é apagado, mesmo velho
    (tmp_path / "monitor.log").write_text("\n".join(f"linha {i}" for i in range(2500)))

    apagados, encurtados = prune_logs(tmp_path, agora)

    assert (apagados, encurtados) == (1, 1)
    assert not velho.exists() and novo.exists() and em_uso.exists()
    linhas = (tmp_path / "monitor.log").read_text().splitlines()
    assert len(linhas) == 2000 and linhas[-1] == "linha 2499"
