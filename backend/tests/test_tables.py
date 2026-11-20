"""
Mesas: cadastro (número repetido, edição ao mesmo tempo, desativar) e a mesa
nas operações de comanda que ainda não tinham teste — abrir numa mesa já
ocupada ou desativada e mesclar (as mesas das comandas de origem ficam livres).

Abrir/fechar/cancelar/reabrir liberando a mesa já estão em test_order_service.py.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError, OptimisticLockError
from app.models.order import OrderStatus
from app.models.table import Table, TableStatus
from app.schemas.order import OrderCreate
from app.schemas.table import TableCreate, TableUpdate
from app.services.table_service import TableService
from tests.test_order_service import make_order, make_table, service  # noqa: F401 (fixture)

EST = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def tables(mock_session):
    svc = TableService(mock_session, UUID("00000000-0000-0000-0000-000000000001"), EST,
                       UUID("00000000-0000-0000-0000-000000000003"))
    svc._repo = MagicMock()
    svc._repo.get_by_number = AsyncMock(return_value=None)
    svc._repo.add = AsyncMock(side_effect=lambda t: _saved(t))
    mock_session.refresh = AsyncMock()
    return svc


def _saved(t: Table) -> Table:
    """O que o banco preencheria no INSERT."""
    from datetime import UTC, datetime
    t.id, t.version = uuid4(), 1
    t.created_at = t.updated_at = datetime.now(UTC)
    t.is_active = True
    return t


# ── Cadastro ──────────────────────────────────────────────────────────────────

async def test_mesa_nova_sempre_comeca_livre(tables):
    resp = await tables.create(TableCreate(number=21, label="Mesa 21", capacity=4))
    assert resp.status == TableStatus.FREE and resp.number == 21


async def test_numero_repetido_e_recusado(tables):
    tables._repo.get_by_number = AsyncMock(return_value=make_table(number=5))
    with pytest.raises(ConflictError, match="número 5"):
        await tables.create(TableCreate(number=5, label="Mesa 5", capacity=4))
    tables._repo.add.assert_not_called()


async def test_dois_cadastrando_o_mesmo_numero_ao_mesmo_tempo(tables):
    """Os dois passam pela checagem; o banco barra o segundo e vira mensagem amigável."""
    tables._repo.add = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    with pytest.raises(ConflictError, match="em uso"):
        await tables.create(TableCreate(number=5, label="Mesa 5", capacity=4))


async def test_editar_com_versao_antiga_e_recusado(tables):
    """Dois aparelhos editando a mesma mesa: quem chega com versão velha não sobrescreve."""
    mesa = make_table(version=4, label="Mesa 5")
    tables._repo.get_by_establishment = AsyncMock(return_value=mesa)
    with pytest.raises(OptimisticLockError):
        await tables.update(mesa.id, TableUpdate(label="Varanda", version=3))
    assert mesa.label == "Mesa 5"


async def test_editar_muda_so_o_que_foi_enviado(tables):
    mesa = make_table(version=4, label="Mesa 5", capacity=4)
    tables._repo.get_by_establishment = AsyncMock(return_value=mesa)
    with patch("app.services.table_service.TableResponse.model_validate"):
        await tables.update(mesa.id, TableUpdate(label="Varanda", version=4))
    assert (mesa.label, mesa.capacity) == ("Varanda", 4)


async def test_nao_edita_mesa_desativada(tables):
    mesa = make_table(is_active=False)
    tables._repo.get_by_establishment = AsyncMock(return_value=mesa)
    with pytest.raises(BusinessRuleError, match="desativada"):
        await tables.update(mesa.id, TableUpdate(label="x", version=1))


async def test_mesa_de_outro_estabelecimento_nao_aparece(tables):
    tables._repo.get_by_establishment = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await tables.get(uuid4())
    with pytest.raises(NotFoundError):
        await tables.deactivate(uuid4())


async def test_nao_desativa_mesa_com_comanda_aberta(tables):
    mesa = make_table(status=TableStatus.OCCUPIED)
    tables._repo.get_by_establishment = AsyncMock(return_value=mesa)
    with pytest.raises(BusinessRuleError, match="comanda aberta"):
        await tables.deactivate(mesa.id)
    assert mesa.is_active is True


async def test_desativa_mesa_livre(tables):
    mesa = make_table(status=TableStatus.FREE)
    tables._repo.get_by_establishment = AsyncMock(return_value=mesa)
    await tables.deactivate(mesa.id)
    assert mesa.is_active is False


async def test_nao_desativa_duas_vezes(tables):
    tables._repo.get_by_establishment = AsyncMock(return_value=make_table(is_active=False))
    with pytest.raises(BusinessRuleError, match="já está desativada"):
        await tables.deactivate(uuid4())


# ── Mesa nas comandas ─────────────────────────────────────────────────────────

async def test_nao_abre_segunda_comanda_na_mesma_mesa(service):
    mesa = make_table(status=TableStatus.OCCUPIED)
    service._table_repo.get_by_establishment = AsyncMock(return_value=mesa)
    service._order_repo.get_open_by_table = AsyncMock(return_value=make_order())
    service._order_repo.add = AsyncMock()
    with pytest.raises(BusinessRuleError, match="já possui uma comanda aberta"):
        await service.open_order(OrderCreate(table_id=mesa.id))
    service._order_repo.add.assert_not_called()


async def test_nao_abre_comanda_em_mesa_desativada(service):
    mesa = make_table(is_active=False)
    service._table_repo.get_by_establishment = AsyncMock(return_value=mesa)
    with pytest.raises(BusinessRuleError, match="desativada"):
        await service.open_order(OrderCreate(table_id=mesa.id))


async def _merge(service, target, sources, mesas: dict):
    orders = {o.id: o for o in [target, *sources]}
    service.session.scalar = AsyncMock(return_value=Decimal("0"))
    service.session.execute = AsyncMock()
    service.session.flush = AsyncMock()
    service.session.refresh = AsyncMock()
    service._table_repo.get_by_establishment = AsyncMock(side_effect=lambda tid, _e: mesas.get(tid))
    with patch.object(service, "_get_or_raise", AsyncMock(side_effect=lambda oid, _e: orders[oid])), \
         patch.object(service, "_order_label", AsyncMock(return_value="x")), \
         patch.object(service, "_log_audit", AsyncMock()):
        await service.merge_orders(target.id, [s.id for s in sources])


async def test_mesclar_libera_as_mesas_das_comandas_de_origem(service):
    m1, m2, m3 = (make_table(id=uuid4(), status=TableStatus.OCCUPIED) for _ in range(3))
    target = make_order(id=uuid4(), table_id=m1.id)
    a, b = make_order(id=uuid4(), table_id=m2.id), make_order(id=uuid4(), table_id=m3.id)
    await _merge(service, target, [a, b], {m.id: m for m in (m1, m2, m3)})
    assert m1.status == TableStatus.OCCUPIED                  # a mesa que ficou com tudo continua ocupada
    assert (m2.status, m3.status) == (TableStatus.FREE, TableStatus.FREE)
    assert (a.status, b.status) == (OrderStatus.CANCELLED, OrderStatus.CANCELLED)


async def test_mesclar_duas_comandas_da_mesma_mesa_nao_libera_a_mesa(service):
    mesa = make_table(id=uuid4(), status=TableStatus.OCCUPIED)
    target, src = make_order(id=uuid4(), table_id=mesa.id), make_order(id=uuid4(), table_id=mesa.id)
    await _merge(service, target, [src], {mesa.id: mesa})
    assert mesa.status == TableStatus.OCCUPIED


async def test_mesclar_comanda_de_balcao_numa_mesa(service):
    mesa = make_table(id=uuid4(), status=TableStatus.OCCUPIED)
    target, balcao = make_order(id=uuid4(), table_id=mesa.id), make_order(id=uuid4(), table_id=None)
    await _merge(service, target, [balcao], {mesa.id: mesa})
    assert mesa.status == TableStatus.OCCUPIED


async def test_nao_mescla_comanda_com_pagamento(service):
    """O dinheiro ficaria preso numa comanda cancelada."""
    mesa = make_table(id=uuid4(), status=TableStatus.OCCUPIED)
    target, src = make_order(id=uuid4(), table_id=None), make_order(id=uuid4(), table_id=mesa.id)
    service.session.scalar = AsyncMock(return_value=Decimal("20"))
    orders = {target.id: target, src.id: src}
    with patch.object(service, "_get_or_raise", AsyncMock(side_effect=lambda oid, _e: orders[oid])), \
         patch.object(service, "_order_label", AsyncMock(return_value="gabi")), \
         pytest.raises(BusinessRuleError, match="pagamento"):
        await service.merge_orders(target.id, [src.id])
    assert src.status == OrderStatus.OPEN and mesa.status == TableStatus.OCCUPIED


@pytest.mark.parametrize("motivo,kwargs", [
    ("destino na lista", "self"), ("lista vazia", "empty"),
])
async def test_mesclar_pedido_sem_sentido_e_recusado(service, motivo, kwargs):
    target = make_order(id=uuid4())
    ids = [target.id] if kwargs == "self" else []
    with pytest.raises(BusinessRuleError):
        await service.merge_orders(target.id, ids)
