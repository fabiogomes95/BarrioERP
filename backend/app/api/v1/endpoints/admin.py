"""
app/api/v1/endpoints/admin.py

Administração do bar: editar dados (nome, telefone, endereço) e taxa de serviço.
Apenas OWNER e MANAGER podem alterar.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.core.exceptions import ForbiddenError, NotFoundError, TenantError
from app.models.company import Company
from app.models.establishment import Establishment
from app.models.user import UserRole
from app.schemas.admin import SettingsResponse, SettingsUpdate

router = APIRouter()


async def _load(session: DBSession, user: CurrentUser) -> tuple[Company, Establishment]:
    if user.establishment_id is None:
        raise TenantError("Usuário não está vinculado a um estabelecimento.")
    company = await session.get(Company, user.company_id)
    establishment = await session.get(Establishment, user.establishment_id)
    if company is None or establishment is None:
        raise NotFoundError("Establishment", user.establishment_id)
    return company, establishment


def _to_response(company: Company, est: Establishment) -> SettingsResponse:
    return SettingsResponse(
        company_name=company.name,
        company_phone=company.phone,
        establishment_name=est.name,
        address=est.address,
        service_fee_percent=est.service_fee_percent,
    )


@router.get(
    "/settings",
    response_model=SettingsResponse,
    summary="Configurações do bar",
)
async def get_settings(session: DBSession, current_user: CurrentUser) -> SettingsResponse:
    company, est = await _load(session, current_user)
    return _to_response(company, est)


@router.patch(
    "/settings",
    response_model=SettingsResponse,
    summary="Atualizar configurações do bar",
    description="Edita nome/telefone/endereço do bar e a taxa de serviço (%). OWNER/MANAGER.",
)
async def update_settings(
    data: SettingsUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> SettingsResponse:
    if current_user.role not in (UserRole.OWNER, UserRole.MANAGER):
        raise ForbiddenError("Apenas o dono ou gerente pode alterar as configurações.")

    company, est = await _load(session, current_user)

    if data.company_name is not None:
        company.name = data.company_name.strip()
    if data.company_phone is not None:
        company.phone = data.company_phone.strip() or None
    if data.address is not None:
        est.address = data.address.strip() or None
    if data.service_fee_percent is not None:
        est.service_fee_percent = data.service_fee_percent

    await session.flush()
    return _to_response(company, est)
