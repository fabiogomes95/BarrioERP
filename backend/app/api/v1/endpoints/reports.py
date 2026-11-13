"""
app/api/v1/endpoints/reports.py

Relatórios: faturamento do dia e histórico de comandas fechadas.
"""

from datetime import date, datetime

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, require_roles
from app.models.user import UserRole
from app.schemas.order import OrderHistoryResponse
from app.schemas.report import (
    CustomersReport, DailyReport, FiadoCustomerGroup, FiadoEntry, MovementReport, PeriodReport, ShiftReport,
)
from app.services.insights import InsightsService
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
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
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
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
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
    "/period",
    response_model=PeriodReport,
    summary="Relatório por período",
    description=(
        "Faturamento, nº de comandas, ticket médio, faturamento por forma de "
        "pagamento, itens mais vendidos e detalhamento dia a dia das comandas "
        "FECHADAS entre `start` e `end` (ambos inclusos). Período máximo: 366 dias."
    ),
)
async def period_report(
    session: DBSession,
    current_user: CurrentUser,
    start: date = Query(description="Data inicial (YYYY-MM-DD), inclusa."),
    end: date = Query(description="Data final (YYYY-MM-DD), inclusa."),
) -> PeriodReport:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return await _service(session, current_user).period_report(start, end)


@router.get(
    "/shift",
    response_model=ShiftReport,
    summary="Relatório de turno (intervalo exato de data/hora)",
    description=(
        "Faturamento, nº de comandas, ticket médio, taxa de serviço (10% do "
        "garçom), faturamento por forma de pagamento e itens mais vendidos "
        "das comandas FECHADAS entre `start` e `end` (data/hora exatas, não "
        "precisa bater com meia-noite). Pensado pra turno de bar que "
        "atravessa a virada do dia, ex.: 05/09 16h até 06/09 05h. "
        "Intervalo máximo: 48 horas."
    ),
)
async def shift_report(
    session: DBSession,
    current_user: CurrentUser,
    start: datetime = Query(description="Início do turno (ISO 8601, ex.: 2026-09-05T16:00:00)."),
    end: datetime = Query(description="Fim do turno (ISO 8601, ex.: 2026-09-06T05:00:00)."),
) -> ShiftReport:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return await _service(session, current_user).shift_report(start, end)


@router.get(
    "/history",
    response_model=list[OrderHistoryResponse],
    summary="Histórico de comandas fechadas",
    description="Lista as comandas fechadas mais recentes (com itens e pagamentos). Use `day` para filtrar por data.",
)
async def history(
    session: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    day: date | None = Query(default=None, description="Filtrar por data (YYYY-MM-DD)."),
) -> list[OrderHistoryResponse]:
    require_roles(current_user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return await _service(session, current_user).list_history(limit=limit, offset=offset, day=day)


def _insights(session: DBSession, user: CurrentUser) -> InsightsService:
    require_roles(user, UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)
    return InsightsService(
        session=session, company_id=user.company_id,
        establishment_id=user.establishment_id, user_id=user.id,
    )


@router.get(
    "/movement",
    response_model=MovementReport,
    summary="Movimento por dia da semana e horário",
    description=(
        "Comandas quitadas cujas NOITES (o dia vira às 6h) caem entre `start` e "
        "`end`: média por noite de cada dia da semana, mapa de horário de pico "
        "(hora de abertura da comanda) e itens que mais saem em cada dia."
    ),
)
async def movement_report(
    session: DBSession,
    current_user: CurrentUser,
    start: date = Query(description="Primeira noite (YYYY-MM-DD), inclusa."),
    end: date = Query(description="Última noite (YYYY-MM-DD), inclusa."),
) -> MovementReport:
    return await _insights(session, current_user).movement(start, end)


@router.get(
    "/customers",
    response_model=CustomersReport,
    summary="Clientes do delivery (últimos 12 meses)",
    description=(
        "Pedidos online aceitos agrupados por telefone: quem mais pede, total, "
        "prato favorito e quem pediu 2+ vezes mas sumiu há mais de 30 dias."
    ),
)
async def customers_report(session: DBSession, current_user: CurrentUser) -> CustomersReport:
    return await _insights(session, current_user).customers()

