"""
app/schemas/reservation.py

Schemas Pydantic para o módulo de reservas de mesa.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.models.reservation import ReservationStatus
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


class ReservationCreate(BaseSchema):
    """Dados para criar uma reserva. Usado em: POST /api/v1/reservations."""

    table_id: UUID
    customer_name: str = Field(..., min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=30)
    party_size: int = Field(default=1, gt=0, le=100)
    reserved_at: datetime = Field(..., description="Data/hora da reserva.")
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("customer_name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()


class ReservationUpdate(BaseSchema):
    """
    Reagenda ou edita uma reserva CONFIRMED.

    Usado em: PATCH /api/v1/reservations/{id}
    Todos os campos opcionais — PATCH parcial. Alterar `table_id` ou
    `reserved_at` refaz a checagem de conflito de horário na mesa alvo.
    """

    table_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=30)
    party_size: int | None = Field(default=None, gt=0, le=100)
    reserved_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


class ReservationResponse(UUIDSchema, TimestampSchema):
    establishment_id: UUID
    table_id: UUID
    customer_name: str
    customer_phone: str | None
    party_size: int
    reserved_at: datetime
    status: ReservationStatus
    notes: str | None
    created_by: UUID | None
    seated_at: datetime | None
    cancelled_at: datetime | None
    # Não vem do banco — preenchido pelo Service a partir do Table carregado.
    table_number: int
    table_label: str
