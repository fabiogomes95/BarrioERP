from datetime import datetime
from uuid import UUID

from app.schemas.common import BaseSchema


class AuditLogEntry(BaseSchema):
    id: UUID
    action: str
    resource_type: str
    resource_id: str | None = None
    before: str | None = None
    after: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
