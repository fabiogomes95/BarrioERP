"""
app/api/v1/endpoints/reservations.py

Endpoints HTTP para o módulo de reservas de mesa.
Sem restrição de role — operacional como Mesas/Pedidos (qualquer usuário
autenticado do estabelecimento pode ver e gerenciar reservas).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.models.reservation import ReservationStatus
from app.schemas.reservation import ReservationCreate, ReservationResponse, ReservationUpdate
from app.services.reservation_service import ReservationService

router = APIRouter()


def _service(session: DBSession, user: CurrentUser) -> ReservationService:
    return ReservationService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


@router.post("", response_model=ReservationResponse, status_code=201, summary="Criar reserva")
async def create_reservation(
    data: ReservationCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> ReservationResponse:
    return await _service(session, current_user).create(data)


@router.get("", response_model=list[ReservationResponse], summary="Listar reservas")
async def list_reservations(
    session: DBSession,
    current_user: CurrentUser,
    day: date | None = Query(default=None, description="Filtra reservas de um dia específico (fuso local)."),
    status: ReservationStatus | None = Query(default=None),
    table_id: UUID | None = Query(default=None),
) -> list[ReservationResponse]:
    return await _service(session, current_user).list(day=day, status=status, table_id=table_id)


@router.get("/{reservation_id}", response_model=ReservationResponse, summary="Buscar reserva")
async def get_reservation(
    reservation_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> ReservationResponse:
    return await _service(session, current_user).get(reservation_id)


@router.patch("/{reservation_id}", response_model=ReservationResponse, summary="Reagendar/editar reserva")
async def update_reservation(
    reservation_id: UUID,
    data: ReservationUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> ReservationResponse:
    return await _service(session, current_user).reschedule(reservation_id, data)


@router.patch("/{reservation_id}/check-in", response_model=ReservationResponse, summary="Check-in (cliente chegou)")
async def check_in_reservation(
    reservation_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> ReservationResponse:
    return await _service(session, current_user).check_in(reservation_id)


@router.patch("/{reservation_id}/cancel", status_code=204, summary="Cancelar reserva")
async def cancel_reservation(
    reservation_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    await _service(session, current_user).cancel(reservation_id)
