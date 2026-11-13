"""CashService — abertura de caixa concorrente."""

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessRuleError
from app.schemas.cash import CashOpen
from app.services.cash_service import CashService


@pytest.fixture
def service(mock_session, company_id, establishment_id, user_id):
    return CashService(mock_session, UUID(company_id), UUID(establishment_id), UUID(user_id))


async def test_abrir_caixa_ja_aberto_e_recusado(service):
    service._current = AsyncMock(return_value=object())
    with pytest.raises(BusinessRuleError, match="Já existe um caixa aberto"):
        await service.open(CashOpen(opening_amount=Decimal("100")))


async def test_abertura_simultanea_vira_mensagem_e_nao_erro_500(service, mock_session):
    """Os dois passaram pela checagem; o índice único recusa o segundo."""
    service._current = AsyncMock(return_value=None)
    mock_session.add = lambda obj: None
    mock_session.flush = AsyncMock(
        side_effect=IntegrityError("INSERT", {}, Exception("uq_cash_sessions_one_open"))
    )
    with pytest.raises(BusinessRuleError, match="Já existe um caixa aberto"):
        await service.open(CashOpen(opening_amount=Decimal("100")))


async def test_historico_usa_vendas_gravadas_no_fechamento(service):
    """Estorno depois do fechamento não muda o número do caixa fechado."""
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    agora = datetime.now(UTC)
    fechado = SimpleNamespace(
        id=uuid4(), created_at=agora, updated_at=agora, status="closed",
        opening_amount=Decimal("100"), opened_at=agora, closed_at=agora,
        counted_amount=Decimal("300"), expected_amount=Decimal("300"), difference=Decimal("0"),
        notes=None, movements=[], cash_sales=Decimal("200"),
    )
    service._cash_sales = AsyncMock(return_value=Decimal("150"))  # já com o estorno
    resp = await service._to_response(fechado)
    assert resp.cash_sales == Decimal("200")
    service._cash_sales.assert_not_called()
