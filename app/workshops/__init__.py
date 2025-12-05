"""Multi-tenant workshop management module."""

from .models import Workshop, WorkshopMember
from .schemas import WorkshopCreate, WorkshopUpdate, WorkshopMemberCreate, WorkshopMemberUpdate
from .crud import WorkshopCRUD, WorkshopMemberCRUD
from .tenant_context import (
    TenantContext,
    get_tenant_context,
    require_tenant_role,
    filter_by_workshop,
    get_current_workshop_id,
)

__all__ = [
    "Workshop",
    "WorkshopMember",
    "WorkshopCreate",
    "WorkshopUpdate",
    "WorkshopMemberCreate",
    "WorkshopMemberUpdate",
    "WorkshopCRUD",
    "WorkshopMemberCRUD",
    "TenantContext",
    "get_tenant_context",
    "require_tenant_role",
    "filter_by_workshop",
    "get_current_workshop_id",
]

