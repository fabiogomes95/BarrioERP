"""
app/repositories/reservation_repository.py

Acesso ao banco para Reservation.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.reservation import Reservation, ReservationStatus
from app.repositories.base import BaseRepository


class ReservationRepository(BaseRepository[Reservation]):
    model = Reservation

    async def get_by_establishment(self, reservation_id: UUID, establishment_id: UUID) -> Reservation | None:
        stmt = (
            select(Reservation)
            .where(
                Reservation.id == reservation_id,
                Reservation.establishment_id == establishment_id,
            )
            .options(selectinload(Reservation.table))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_establishment(
        self,
        establishment_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: ReservationStatus | None = None,
        table_id: UUID | None = None,
    ) -> list[Reservation]:
        filters = [Reservation.establishment_id == establishment_id]
        if start is not None:
            filters.append(Reservation.reserved_at >= start)
        if end is not None:
            filters.append(Reservation.reserved_at < end)
        if status is not None:
            filters.append(Reservation.status == status)
        if table_id is not None:
            filters.append(Reservation.table_id == table_id)

        stmt = (
            select(Reservation)
            .where(*filters)
            .options(selectinload(Reservation.table))
            .order_by(Reservation.reserved_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_overlapping(
        self,
        table_id: UUID,
        window_start: datetime,
        window_end: datetime,
        *,
        exclude_id: UUID | None = None,
    ) -> list[Reservation]:
        """Reservas CONFIRMED/SEATED da mesma mesa cujo horário cai dentro da janela dada."""
        filters = [
            Reservation.table_id == table_id,
            Reservation.status.in_([ReservationStatus.CONFIRMED, ReservationStatus.SEATED]),
            Reservation.reserved_at >= window_start,
            Reservation.reserved_at < window_end,
        ]
        if exclude_id is not None:
            filters.append(Reservation.id != exclude_id)

        stmt = select(Reservation).where(*filters)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_confirmed_starting_by(self, establishment_id: UUID, deadline: datetime) -> list[Reservation]:
        """CONFIRMED cujo horário já chegou (ou está a caminho) até `deadline`."""
        stmt = select(Reservation).where(
            Reservation.establishment_id == establishment_id,
            Reservation.status == ReservationStatus.CONFIRMED,
            Reservation.reserved_at <= deadline,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_overdue_confirmed(self, establishment_id: UUID, before: datetime) -> list[Reservation]:
        """CONFIRMED cujo horário passou de `before` (grace period vencido) sem check-in."""
        stmt = select(Reservation).where(
            Reservation.establishment_id == establishment_id,
            Reservation.status == ReservationStatus.CONFIRMED,
            Reservation.reserved_at < before,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
