"""Monitor: quando avisar (começo, lembrete a cada 2h, volta ao normal)."""

from app.monitoring import REMIND_AFTER, Check, decide

T0 = 1_000_000.0
DOWN = Check("barrio", False, "Barrio fora do ar.", "Barrio voltou.")
UP = Check("barrio", True, "Barrio fora do ar.", "Barrio voltou.")


def test_avisa_quando_comeca_e_nao_repete_logo_em_seguida():
    msgs, state = decide([DOWN], {}, T0)
    assert msgs == ["🚨 Barrio fora do ar."]
    msgs2, state2 = decide([DOWN], state, T0 + 300)
    assert msgs2 == [] and state2 == state


def test_lembra_a_cada_2h_enquanto_continua():
    _, state = decide([DOWN], {}, T0)
    msgs, state = decide([DOWN], state, T0 + REMIND_AFTER.total_seconds())
    assert len(msgs) == 1 and msgs[0].startswith("⏰ Continua: Barrio fora do ar.") and "há 120 min" in msgs[0]
    assert state["barrio"]["since"] == T0  # o começo do problema não muda


def test_avisa_quando_volta_e_limpa_o_estado():
    _, state = decide([DOWN], {}, T0)
    msgs, state = decide([UP], state, T0 + 600)
    assert msgs == ["✅ Barrio voltou. (ficou 10 min com problema)"]
    assert state == {}


def test_tudo_ok_sem_mensagem():
    assert decide([UP], {}, T0) == ([], {})
