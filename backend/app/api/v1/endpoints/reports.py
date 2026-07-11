"""
app/api/v1/endpoints/reports.py

Relatórios: faturamento do dia e histórico de comandas fechadas.
"""

from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, require_roles
from app.models.user import UserRole
from app.schemas.order import OrderResponse
from app.schemas.report import DailyReport, FiadoCustomerGroup, FiadoEntry
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
    "/fiado",
    response_model=list[FiadoEntry],
    summary="Contas em fiado",
    description="Comandas abertas com pagamento parcial (paid < total).",
)
async def fiado_list(
    session: DBSession,
    current_user: CurrentUser,
) -> list[FiadoEntry]:
    return await _service(session, current_user).list_fiado()


@router.get(
    "/fiado/grouped",
    response_model=list[FiadoCustomerGroup],
    summary="Fiados agrupados por cliente",
    description="Retorna os fiados agrupados por nome do cliente com total consolidado.",
)
async def fiado_grouped(
    session: DBSession,
    current_user: CurrentUser,
) -> list[FiadoCustomerGroup]:
    return await _service(session, current_user).list_fiado_grouped()


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
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return await _service(session, current_user).daily_report(day)


@router.get(
    "/history",
    response_model=list[OrderResponse],
    summary="Histórico de comandas fechadas",
    description="Lista as comandas fechadas mais recentes (com itens). Use `day` para filtrar por data.",
)
async def history(
    session: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    day: date | None = Query(default=None, description="Filtrar por data (YYYY-MM-DD)."),
) -> list[OrderResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return await _service(session, current_user).list_history(limit=limit, offset=offset, day=day)
