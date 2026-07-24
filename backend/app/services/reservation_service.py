"""
app/services/reservation_service.py

Regras de negócio do módulo de reservas de mesa.

CONCEITO — Sweep "de carona" em vez de um scheduler de verdade:
    O sistema não tem nenhum processo em background (nem cron, nem worker
    assíncrono) — só os dois serviços web (HTTP/HTTPS) rodando uvicorn.
    Em vez de adicionar essa infraestrutura só para "mesa vira RESERVADA
    30 min antes / libera sozinha se não aparecer", `sync_table_statuses()`
    roda dentro de `TableService.list()` — ou seja, toda vez que a tela de
    Mesas busca a lista (que já se atualiza sozinha a cada 30s no
    frontend). Isso mantém o status "quase em tempo real" sem precisar de
    um processo novo. Limitação aceita: se ninguém abrir a tela de Mesas
    por um tempo, a transição atrasa até a próxima leitura.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError, TenantError
from app.models.reservation import Reservation, ReservationStatus
from app.models.table import TableStatus
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.table_repository import TableRepository
from app.schemas.reservation import ReservationCreate, ReservationResponse, ReservationUpdate
from app.services.base import BaseService

# Mesa vira "Reservada" a partir de X minutos antes do horário marcado
LEAD_MINUTES = 30
# Sem check-in até X minutos depois do horário marcado → NO_SHOW automático
GRACE_MINUTES = 30
# Janela de conflito: duas reservas na mesma mesa não podem cair dentro
# desse intervalo uma da outra
BLOCK_DURATION_MINUTES = 120


class ReservationService(BaseService):
    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        self._repo = ReservationRepository(session)
        self._table_repo = TableRepository(session)

    def _require_establishment(self) -> UUID:
        if self.establishment_id is None:
            raise TenantError(
                "Usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário para gerenciar reservas."
            )
        return self.establishment_id

    def _to_response(self, reservation: Reservation) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            created_at=reservation.created_at,
            updated_at=reservation.updated_at,
            establishment_id=reservation.establishment_id,
            table_id=reservation.table_id,
            customer_name=reservation.customer_name,
            customer_phone=reservation.customer_phone,
            party_size=reservation.party_size,
            reserved_at=reservation.reserved_at,
            status=reservation.status,
            notes=reservation.notes,
            created_by=reservation.created_by,
            seated_at=reservation.seated_at,
            cancelled_at=reservation.cancelled_at,
            table_number=reservation.table.number,
            table_label=reservation.table.label,
        )

    async def _check_conflict(
        self, table_id: UUID, reserved_at: datetime, *, exclude_id: UUID | None = None
    ) -> None:
        window_start = reserved_at - timedelta(minutes=BLOCK_DURATION_MINUTES)
        window_end = reserved_at + timedelta(minutes=BLOCK_DURATION_MINUTES)
        overlapping = await self._repo.list_active_overlapping(
            table_id, window_start, window_end, exclude_id=exclude_id
        )
        if overlapping:
            raise BusinessRuleError(
                "Esta mesa já tem uma reserva marcada perto desse horário. "
                "Escolha outro horário ou outra mesa."
            )

    # ══════════════════════════════════════════════════════════════
    # CRUD
    # ══════════════════════════════════════════════════════════════

    async def create(self, data: ReservationCreate) -> ReservationResponse:
        establishment_id = self._require_establishment()

        table = await self._table_repo.get_by_establishment(data.table_id, establishment_id)
        if table is None:
            raise NotFoundError("Table", data.table_id)
        if not table.is_active:
            raise BusinessRuleError("Não é possível reservar uma mesa desativada.")

        await self._check_conflict(data.table_id, data.reserved_at)

        reservation = Reservation(
            establishment_id=establishment_id,
            table_id=data.table_id,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            party_size=data.party_size,
            reserved_at=data.reserved_at,
            status=ReservationStatus.CONFIRMED,
            notes=data.notes,
            created_by=self.user_id,
        )
        reservation = await self._repo.add(reservation)
        await self.session.refresh(reservation, ["table"])

        await self._log_audit(
            action="reservation.create",
            resource_type="reservation",
            resource_id=str(reservation.id),
            after={
                "table_id": str(reservation.table_id),
                "customer_name": reservation.customer_name,
                "reserved_at": reservation.reserved_at.isoformat(),
            },
        )
        return self._to_response(reservation)

    async def list(
        self,
        *,
        day: date | None = None,
        status: ReservationStatus | None = None,
        table_id: UUID | None = None,
    ) -> list[ReservationResponse]:
        establishment_id = self._require_establishment()

        start = end = None
        if day is not None:
            tz = ZoneInfo(settings.TIMEZONE)
            start = datetime.combine(day, time.min, tzinfo=tz)
            end = start + timedelta(days=1)

        reservations = await self._repo.list_by_establishment(
            establishment_id, start=start, end=end, status=status, table_id=table_id,
        )
        return [self._to_response(r) for r in reservations]

    async def get(self, reservation_id: UUID) -> ReservationResponse:
        establishment_id = self._require_establishment()
        reservation = await self._repo.get_by_establishment(reservation_id, establishment_id)
        if reservation is None:
            raise NotFoundError("Reservation", reservation_id)
        return self._to_response(reservation)

    async def reschedule(self, reservation_id: UUID, data: ReservationUpdate) -> ReservationResponse:
        establishment_id = self._require_establishment()
        reservation = await self._repo.get_by_establishment(reservation_id, establishment_id)
        if reservation is None:
            raise NotFoundError("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CONFIRMED:
            raise BusinessRuleError(
                f"Não é possível editar uma reserva com status '{reservation.status.value}'."
            )

        update_data = data.model_dump(exclude_unset=True)
        new_table_id = update_data.get("table_id", reservation.table_id)
        new_reserved_at = update_data.get("reserved_at", reservation.reserved_at)

        if new_table_id != reservation.table_id:
            table = await self._table_repo.get_by_establishment(new_table_id, establishment_id)
            if table is None:
                raise NotFoundError("Table", new_table_id)

        if new_table_id != reservation.table_id or new_reserved_at != reservation.reserved_at:
            await self._check_conflict(new_table_id, new_reserved_at, exclude_id=reservation.id)

        for field, value in update_data.items():
            setattr(reservation, field, value)

        await self.session.flush()
        # Re-busca (em vez de refresh parcial): updated_at é server-side
        # (onupdate=func.now()) e fica expirado após o flush — um refresh()
        # com attribute_names não recarrega ele, e acessar depois quebra em
        # contexto async (MissingGreenlet). Re-fetch evita esse problema.
        reservation = await self._repo.get_by_establishment(reservation.id, establishment_id)
        return self._to_response(reservation)

    async def check_in(self, reservation_id: UUID) -> ReservationResponse:
        establishment_id = self._require_establishment()
        reservation = await self._repo.get_by_establishment(reservation_id, establishment_id)
        if reservation is None:
            raise NotFoundError("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CONFIRMED:
            raise BusinessRuleError(
                f"Não é possível fazer check-in de uma reserva com status '{reservation.status.value}'."
            )

        reservation.status = ReservationStatus.SEATED
        reservation.seated_at = datetime.now(UTC)

        # Libera a mesa (se estava marcada RESERVADA por essa reserva) para
        # o fluxo normal de abrir comanda na tela de Mesas.
        table = await self._table_repo.get_by_establishment(reservation.table_id, establishment_id)
        if table is not None and table.status == TableStatus.RESERVED:
            table.status = TableStatus.FREE

        await self.session.flush()

        await self._log_audit(
            action="reservation.check_in",
            resource_type="reservation",
            resource_id=str(reservation.id),
            after={"status": "seated"},
        )
        reservation = await self._repo.get_by_establishment(reservation.id, establishment_id)
        return self._to_response(reservation)

    async def cancel(self, reservation_id: UUID) -> None:
        establishment_id = self._require_establishment()
        reservation = await self._repo.get_by_establishment(reservation_id, establishment_id)
        if reservation is None:
            raise NotFoundError("Reservation", reservation_id)

        if reservation.status != ReservationStatus.CONFIRMED:
            raise BusinessRuleError(
                f"Não é possível cancelar uma reserva com status '{reservation.status.value}'."
            )

        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.now(UTC)

        table = await self._table_repo.get_by_establishment(reservation.table_id, establishment_id)
        if table is not None and table.status == TableStatus.RESERVED:
            table.status = TableStatus.FREE

        await self.session.flush()

        await self._log_audit(
            action="reservation.cancel",
            resource_type="reservation",
            resource_id=str(reservation.id),
            after={"status": "cancelled"},
        )

    # ══════════════════════════════════════════════════════════════
    # Sweep automático — chamado por TableService.list()
    # ══════════════════════════════════════════════════════════════

    async def sync_table_statuses(self, establishment_id: UUID) -> None:
        now = datetime.now(UTC)

        # Ativa: reservas cujo horário está a LEAD_MINUTES ou menos de distância
        # (e ainda não venceu o grace period) — mesa livre vira RESERVADA.
        upcoming = await self._repo.list_confirmed_starting_by(
            establishment_id, now + timedelta(minutes=LEAD_MINUTES)
        )
        overdue_cutoff = now - timedelta(minutes=GRACE_MINUTES)
        for reservation in upcoming:
            if reservation.reserved_at < overdue_cutoff:
                continue  # já vencida — tratada no loop abaixo
            table = await self._table_repo.get(reservation.table_id)
            if table is not None and table.status == TableStatus.FREE:
                table.status = TableStatus.RESERVED

        # Vencidas: passou do grace period sem check-in → NO_SHOW, libera mesa.
        overdue = await self._repo.list_overdue_confirmed(establishment_id, overdue_cutoff)
        for reservation in overdue:
            reservation.status = ReservationStatus.NO_SHOW
            table = await self._table_repo.get(reservation.table_id)
            if table is not None and table.status == TableStatus.RESERVED:
                table.status = TableStatus.FREE

        if upcoming or overdue:
            await self.session.flush()
