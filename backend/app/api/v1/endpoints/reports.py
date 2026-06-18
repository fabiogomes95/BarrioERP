"""
app/api/v1/endpoints/reports.py

Relatórios: faturamento do dia e histórico de comandas fechadas.
"""

from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.order import OrderResponse
from app.schemas.report import DailyReport
from app.services.order_service import OrderService

router = APIRouter()


def _service(session: DBSession, user: CurrentUser) -> OrderService:
    return OrderService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


@router.get(
    "/daily",
    response_model=DailyReport,
    summary="Relatório do dia",
    description=(
        "Faturamento, nº de comandas, ticket médio, faturamento por forma de "
        "pagamento e itens mais vendidos das comandas FECHADAS no dia."
    ),
)
async def daily_report(
    session: DBSession,
    current_user: CurrentUser,
    day: date | None = Query(
        default=None,
        description="Dia do relatório (YYYY-MM-DD). Padrão: hoje.",
    ),
) -> DailyReport:
    return await _service(session, current_user).daily_report(day)


@router.get(
    "/history",
    response_model=list[OrderResponse],
    summary="Histórico de comandas fechadas",
    description="Lista as comandas fechadas mais recentes (com itens).",
)
async def history(
    session: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OrderResponse]:
    return await _service(session, current_user).list_history(limit=limit, offset=offset)
