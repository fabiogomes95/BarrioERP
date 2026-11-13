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
