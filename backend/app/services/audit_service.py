import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditService:
    """
    Service para registrar ações no AuditLog.

    Uso:
        await AuditService(session).log(
            company_id=...,
            establishment_id=...,
            user_id=...,
            action="order.cancel",
            resource_type="order",
            resource_id=str(order_id),
            before={"status": "open"},
            after={"status": "cancelled"},
        )
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        before: object | None = None,
        after: object | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            company_id=company_id,
            establishment_id=establishment_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
            after=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(entry)
        return entry

    async def list_logs(
        self,
        company_id: UUID,
        *,
        establishment_id: UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Lista logs de auditoria com filtros opcionais e paginação."""
        conditions = [AuditLog.company_id == company_id]
        if establishment_id is not None:
            conditions.append(AuditLog.establishment_id == establishment_id)
        if action is not None:
            conditions.append(AuditLog.action == action)
        if resource_type is not None:
            conditions.append(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            conditions.append(AuditLog.resource_id == resource_id)

        # Count
        count_q = select(func.count(AuditLog.id)).where(*conditions)
        total = (await self.session.execute(count_q)).scalar_one()

        # Data
        q = (
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(q)).scalars().all()
        return list(rows), total
