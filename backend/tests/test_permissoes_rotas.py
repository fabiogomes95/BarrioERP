"""Permissões checadas nas rotas (garçom/cozinha não alteram cadastro de mesa nem mexem em fiado)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import orders, reports, tables
from app.core.exceptions import ForbiddenError
from app.models.table import TableStatus
from app.models.user import UserRole
from app.schemas.table import TableCreate, TableUpdate


def _user(role):
    return MagicMock(role=role, company_id=uuid4(), establishment_id=uuid4(), id=uuid4())


EQUIPE = [UserRole.WAITER, UserRole.KITCHEN]


@pytest.mark.parametrize("role", EQUIPE + [UserRole.CASHIER])
async def test_so_gerente_cria_e_desativa_mesa(role):
    with pytest.raises(ForbiddenError):
        await tables.create_table(TableCreate(number=99, label="Mesa 99", capacity=4), MagicMock(), _user(role))
    with pytest.raises(ForbiddenError):
        await tables.deactivate_table(uuid4(), MagicMock(), _user(role))


@pytest.mark.parametrize("role", EQUIPE)
async def test_garcom_nao_renomeia_mesa_mas_muda_status(role):
    with pytest.raises(ForbiddenError):
        await tables.update_table(uuid4(), TableUpdate(label="VIP", version=1), MagicMock(), _user(role))
    svc = MagicMock(update=AsyncMock(return_value="ok"))
    with patch.object(tables, "_service", return_value=svc):
        assert await tables.update_table(
            uuid4(), TableUpdate(status=TableStatus.FREE, version=1), MagicMock(), _user(role)) == "ok"


@pytest.mark.parametrize("role", EQUIPE)
async def test_garcom_nao_ve_nem_reabre_fiado(role):
    with pytest.raises(ForbiddenError):
        await reports.fiado_list(MagicMock(), _user(role))
    with pytest.raises(ForbiddenError):
        await reports.fiado_grouped(MagicMock(), _user(role))
    with pytest.raises(ForbiddenError):
        await orders.reopen_order(uuid4(), MagicMock(), _user(role))
