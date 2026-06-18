"""
app/schemas/admin.py

Schemas da área de Administração (dados do bar + taxa de serviço).
"""

from decimal import Decimal

from pydantic import Field

from app.schemas.common import BaseSchema


class SettingsResponse(BaseSchema):
    """Configurações atuais do bar."""

    company_name: str
    company_phone: str | None = None
    establishment_name: str
    address: str | None = None
    service_fee_percent: Decimal


class SettingsUpdate(BaseSchema):
    """Atualização parcial das configurações do bar."""

    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    company_phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    service_fee_percent: Decimal | None = Field(default=None, ge=0, le=100)
