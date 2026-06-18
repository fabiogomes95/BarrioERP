"""
app/api/v1/endpoints/cash.py

Controle de Caixa: abrir, sangria/suprimento, fechar e histórico.
"""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.cash import (
    CashClose,
    CashMovementCreate,
    CashOpen,
    CashSessionResponse,
)
from app.services.cash_service import CashService

router = APIRouter()


def _service(session: DBSession, user: CurrentUser) -> CashService:
    return CashService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


@router.get(
    "/current",
    response_model=CashSessionResponse | None,
    summary="Caixa aberto atual",
    description="Retorna o caixa aberto (com movimentos e esperado até agora) ou null.",
)
async def current(session: DBSession, current_user: CurrentUser) -> CashSessionResponse | None:
    return await _service(session, current_user).get_current()


@router.post(
    "/open",
    response_model=CashSessionResponse,
    status_code=201,
    summary="Abrir caixa",
)
async def open_cash(
    data: CashOpen, session: DBSession, current_user: CurrentUser
) -> CashSessionResponse:
    return await _service(session, current_user).open(data)


@router.post(
    "/movement",
    response_model=CashSessionResponse,
    summary="Sangria / Suprimento",
)
async def add_movement(
    data: CashMovementCreate, session: DBSession, current_user: CurrentUser
) -> CashSessionResponse:
    return await _service(session, current_user).add_movement(data)


@router.post(
    "/close",
    response_model=CashSessionResponse,
    summary="Fechar caixa",
)
async def close_cash(
    data: CashClose, session: DBSession, current_user: CurrentUser
) -> CashSessionResponse:
    return await _service(session, current_user).close(data)


@router.get(
    "/history",
    response_model=list[CashSessionResponse],
    summary="Histórico de caixas fechados",
)
async def history(
    session: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[CashSessionResponse]:
    return await _service(session, current_user).history(limit=limit)
