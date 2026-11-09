"""
app/api/v1/endpoints/online_orders.py

Fila de pedidos vindos do cardápio público. Aceitar abre a comanda
(delivery/retirada) com os itens; recusar só tira da fila.

Mesmos papéis que recebem o aviso em tempo real (owner/manager/cashier —
ver useBillRequestAlerts no frontend): é quem cuida do caixa e do telefone.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, DBSession, require_roles
from app.core.config import settings
from app.models.online_order import OnlineOrderStatus
from app.models.user import UserRole
from app.schemas.online_order import (
    OnlineOrderAccepted, OnlineOrderResponse, OnlineOrdersPause, OnlineOrdersReport,
)
from app.services import direct_print
from app.services.online_order_service import OnlineOrderService

router = APIRouter()

_ROLES = (UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER)


def _service(session: DBSession, user: CurrentUser) -> OnlineOrderService:
    require_roles(user, *_ROLES)
    return OnlineOrderService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


@router.get("/", response_model=list[OnlineOrderResponse], summary="Pedidos online (padrão: pendentes)")
async def list_online_orders(
    session: DBSession,
    current_user: CurrentUser,
    status: OnlineOrderStatus = OnlineOrderStatus.PENDING,
) -> list[OnlineOrderResponse]:
    return await _service(session, current_user).list(status)


@router.get("/report", response_model=OnlineOrdersReport, summary="Resumo dos pedidos online no intervalo")
async def online_orders_report(
    session: DBSession,
    current_user: CurrentUser,
    start: datetime = Query(description="Início (ISO 8601; sem fuso = horário local do bar)."),
    end: datetime = Query(description="Fim, exclusivo."),
) -> OnlineOrdersReport:
    return await _service(session, current_user).report(start, end)


@router.get("/pause", response_model=OnlineOrdersPause, summary="Pedidos pelo cardápio estão pausados?")
async def get_online_orders_pause(session: DBSession, current_user: CurrentUser) -> OnlineOrdersPause:
    return OnlineOrdersPause(paused=await _service(session, current_user).is_paused())


@router.put("/pause", response_model=OnlineOrdersPause, summary="Pausar/retomar pedidos pelo cardápio")
async def set_online_orders_pause(
    data: OnlineOrdersPause, session: DBSession, current_user: CurrentUser,
) -> OnlineOrdersPause:
    return OnlineOrdersPause(paused=await _service(session, current_user).set_paused(data.paused))


@router.post("/{online_order_id}/accept", response_model=OnlineOrderAccepted,
             summary="Aceitar pedido online (abre a comanda)")
async def accept_online_order(
    online_order_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
    background: BackgroundTasks,
) -> OnlineOrderAccepted:
    order_id = await _service(session, current_user).accept(online_order_id)
    # Ticket da cozinha sai sozinho na térmica. Tarefa em segundo plano roda
    # depois da resposta — e o commit (DBSession scope="function") já
    # aconteceu antes dela: aceite que falhou nunca imprime.
    if settings.AUTO_PRINT_ONLINE_ORDERS:
        background.add_task(
            direct_print.print_or_fallback, "cozinha",
            current_user.company_id, current_user.establishment_id, order_id,
        )
    return OnlineOrderAccepted(order_id=order_id)


@router.post("/{online_order_id}/reject", status_code=204, summary="Recusar pedido online")
async def reject_online_order(
    online_order_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    await _service(session, current_user).reject(online_order_id)
