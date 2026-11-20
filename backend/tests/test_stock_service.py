"""
Testes do StockService — baixa de estoque pelas vendas.

O banco é simulado: `FakeSession` guarda os movimentos criados (session.add)
e devolve eles na consulta "movimentos de venda deste item" — é o que
restore/scale usam. Assim dá pra testar a conta de verdade: vende, muda a
quantidade, cancela, e o insumo tem que voltar exatamente ao que era.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.models.stock import StockMovement, StockMovementKind
from app.schemas.stock import StockMovementCreate
from app.services.stock_service import StockService

EST = UUID("00000000-0000-0000-0000-000000000002")
PIZZA = UUID("00000000-0000-0000-0000-0000000000b1")
CALABRESA = UUID("00000000-0000-0000-0000-0000000000b2")


class FakeSession:
    """Só o que o StockService usa: add, flush, refresh e o select de movimentos."""

    def __init__(self):
        self.added: list = []
        self.flush = AsyncMock()
        self.refresh = AsyncMock()

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)

    @property
    def movements(self) -> list[StockMovement]:
        return [m for m in self.added if isinstance(m, StockMovement)]

    async def execute(self, stmt):
        # Única consulta do serviço: movimentos SALE de um order_item.
        # Pega o order_item_id do WHERE compilado.
        params = stmt.compile().params
        oid = next(v for k, v in params.items() if k.startswith("order_item_id"))
        found = [m for m in self.movements if m.order_item_id == oid and m.kind == StockMovementKind.SALE]
        result = MagicMock()
        result.scalars.return_value.all.return_value = found
        return result


def insumo(nome: str, qtd: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), name=nome, quantity_on_hand=Decimal(qtd), min_quantity=Decimal("0"))


@pytest.fixture
def estoque():
    """Queijo 5 kg e calabresa 3 kg; Pizza usa 0,3 kg de queijo; Calabresa usa 0,2 de cada."""
    queijo, calab = insumo("Queijo", "5"), insumo("Calabresa", "3")
    receitas = {
        PIZZA: [SimpleNamespace(stock_item=queijo, quantity_per_unit=Decimal("0.300"))],
        CALABRESA: [SimpleNamespace(stock_item=queijo, quantity_per_unit=Decimal("0.200")),
                    SimpleNamespace(stock_item=calab, quantity_per_unit=Decimal("0.200"))],
    }
    session = FakeSession()
    svc = StockService(session, UUID("00000000-0000-0000-0000-000000000001"), EST,
                       UUID("00000000-0000-0000-0000-000000000003"))
    svc._ingredient_repo.list_for_menu_item = AsyncMock(side_effect=lambda mid: receitas.get(mid, []))
    por_id = {queijo.id: queijo, calab.id: calab}
    svc._item_repo.get = AsyncMock(side_effect=lambda i: por_id.get(i))
    svc._item_repo.get_by_establishment = AsyncMock(side_effect=lambda i, _e: por_id.get(i))
    svc._log_audit = AsyncMock()
    return SimpleNamespace(svc=svc, session=session, queijo=queijo, calab=calab)


# ── Venda ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_venda_baixa_a_receita_vezes_a_quantidade(estoque):
    item = uuid4()
    await estoque.svc.deduct_for_sale(PIZZA, 2, item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("4.4")          # 5 - 2 × 0,3
    [m] = estoque.session.movements
    assert (m.kind, m.quantity_change, m.order_item_id) == (StockMovementKind.SALE, Decimal("-0.6"), item)


@pytest.mark.asyncio
async def test_item_sem_receita_nao_mexe_no_estoque(estoque):
    await estoque.svc.deduct_for_sale(uuid4(), 3, uuid4(), EST)
    assert estoque.session.movements == []
    assert estoque.queijo.quantity_on_hand == Decimal("5")


@pytest.mark.asyncio
async def test_estoque_pode_ficar_negativo_sem_bloquear_a_venda(estoque):
    await estoque.svc.deduct_for_sale(PIZZA, 20, uuid4(), EST)        # precisa 6 kg, tem 5
    assert estoque.queijo.quantity_on_hand == Decimal("-1")


# ── Cancelar item ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelar_devolve_exatamente_o_que_baixou(estoque):
    item = uuid4()
    await estoque.svc.deduct_for_sale(CALABRESA, 3, item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("4.4")
    assert estoque.calab.quantity_on_hand == Decimal("2.4")
    await estoque.svc.restore_for_item(item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("5")
    assert estoque.calab.quantity_on_hand == Decimal("3")


@pytest.mark.asyncio
async def test_cancelar_depois_de_mudar_quantidade_volta_ao_original(estoque):
    item = uuid4()
    await estoque.svc.deduct_for_sale(PIZZA, 1, item, EST)
    await estoque.svc.adjust_for_quantity_change(PIZZA, item, 1, 4, EST)   # 1 → 4
    assert estoque.queijo.quantity_on_hand == Decimal("3.8")              # 5 - 4 × 0,3
    await estoque.svc.adjust_for_quantity_change(PIZZA, item, 4, 2, EST)   # 4 → 2
    assert estoque.queijo.quantity_on_hand == Decimal("4.4")
    await estoque.svc.restore_for_item(item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("5")


@pytest.mark.asyncio
async def test_cancelar_um_item_nao_devolve_o_de_outro(estoque):
    a, b = uuid4(), uuid4()
    await estoque.svc.deduct_for_sale(PIZZA, 1, a, EST)
    await estoque.svc.deduct_for_sale(PIZZA, 2, b, EST)
    await estoque.svc.restore_for_item(a, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("4.4")              # só o b continua baixado


@pytest.mark.asyncio
async def test_mudar_para_a_mesma_quantidade_nao_cria_movimento(estoque):
    item = uuid4()
    await estoque.svc.deduct_for_sale(PIZZA, 2, item, EST)
    await estoque.svc.adjust_for_quantity_change(PIZZA, item, 2, 2, EST)
    assert len(estoque.session.movements) == 1


# ── Pizza meio a meio (sem menu_item único) ───────────────────────────────────

@pytest.mark.asyncio
async def test_meio_a_meio_mudar_quantidade_escala_a_baixa(estoque):
    item = uuid4()
    # meia pizza + meia calabresa
    await estoque.svc.deduct_for_sale(PIZZA, Decimal("0.5"), item, EST)
    await estoque.svc.deduct_for_sale(CALABRESA, Decimal("0.5"), item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("4.75")             # 5 - 0,15 - 0,1
    assert estoque.calab.quantity_on_hand == Decimal("2.9")
    await estoque.svc.scale_for_quantity_change(item, 1, 3, EST)           # 1 → 3 pizzas
    assert estoque.queijo.quantity_on_hand == Decimal("4.25")             # 3 × 0,25
    assert estoque.calab.quantity_on_hand == Decimal("2.7")
    await estoque.svc.restore_for_item(item, EST)
    assert estoque.queijo.quantity_on_hand == Decimal("5")
    assert estoque.calab.quantity_on_hand == Decimal("3")


@pytest.mark.asyncio
async def test_meio_a_meio_sem_baixa_anterior_nao_faz_nada(estoque):
    await estoque.svc.scale_for_quantity_change(uuid4(), 1, 3, EST)
    assert estoque.session.movements == []


# ── Movimentos manuais (compra, perda, ajuste) ────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,negativo,esperado", [
    (StockMovementKind.PURCHASE, False, Decimal("7")),
    (StockMovementKind.LOSS, False, Decimal("3")),
    (StockMovementKind.ADJUSTMENT, False, Decimal("7")),
    (StockMovementKind.ADJUSTMENT, True, Decimal("3")),
])
async def test_movimento_manual_soma_ou_subtrai_pelo_tipo(estoque, kind, negativo, esperado):
    data = StockMovementCreate(kind=kind, quantity=Decimal("2"), is_negative_adjustment=negativo, reason="teste")
    estoque.session.refresh = AsyncMock(side_effect=lambda m: _preenche_resposta(m))
    await estoque.svc.record_movement(estoque.queijo.id, data)
    assert estoque.queijo.quantity_on_hand == esperado


@pytest.mark.asyncio
async def test_movimento_manual_em_insumo_de_outro_estabelecimento_e_recusado(estoque):
    data = StockMovementCreate(kind=StockMovementKind.PURCHASE, quantity=Decimal("1"))
    with pytest.raises(NotFoundError):
        await estoque.svc.record_movement(uuid4(), data)


def _preenche_resposta(m: StockMovement) -> None:
    """Campos que o banco preencheria (created_at etc.) pra resposta validar."""
    from datetime import UTC, datetime
    m.created_at = m.updated_at = datetime.now(UTC)
