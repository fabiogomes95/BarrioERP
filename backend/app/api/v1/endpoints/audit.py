from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.audit import AuditLogEntry
from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditService

router = APIRouter()


@router.get(
    "/",
    response_model=PaginatedResponse,
    summary="Listar logs de auditoria",
    description=(
        "Retorna o histórico de ações registradas no sistema, "
        "com filtros opcionais por ação, tipo de recurso e paginação."
    ),
)
async def list_audit_logs(
    session: DBSession,
    current_user: CurrentUser,
    action: str | None = Query(default=None, description="Filtrar por ação (ex: order.close)"),
    resource_type: str | None = Query(default=None, description="Filtrar por tipo de recurso (ex: order)"),
    resource_id: str | None = Query(default=None, description="Filtrar por ID do recurso"),
    page: int = Query(default=1, ge=1, description="Número da página"),
    page_size: int = Query(default=50, ge=1, le=200, description="Itens por página (máx 200)"),
) -> PaginatedResponse:
    svc = AuditService(session)
    items, total = await svc.list_logs(
        company_id=current_user.company_id,
        establishment_id=current_user.establishment_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return PaginatedResponse(
        items=[
            AuditLogEntry(
                id=item.id,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                before=item.before,
                after=item.after,
                ip_address=item.ip_address,
                user_agent=item.user_agent,
                user_id=item.user_id,
                user_name=item.user.name if item.user else None,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=-( -total // page_size ),  # ceil division
    )
