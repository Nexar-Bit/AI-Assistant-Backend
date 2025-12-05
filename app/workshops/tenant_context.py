"""Tenant context management for automatic data isolation."""

import logging
import uuid
from typing import Annotated, Optional, TypeVar, Generic

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session, Query
from sqlalchemy import Column

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from .models import Workshop, WorkshopMember

from app.core.database import get_db
from .crud import WorkshopCRUD, WorkshopMemberCRUD


logger = logging.getLogger("app.workshops.tenant_context")


class TenantContext:
    """Context manager for tenant isolation."""
    
    def __init__(
        self,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
        membership: "WorkshopMember",
        workshop: "Workshop",
    ):
        self.workshop_id = workshop_id
        self.user_id = user_id
        self.membership = membership
        self.workshop = workshop
    
    @property
    def role(self) -> str:
        """Get user's role in this workshop."""
        return self.membership.role
    
    def has_role(self, min_role: str) -> bool:
        """Check if user has required role or higher."""
        role_hierarchy = {
            "viewer": 0,
            "member": 1,
            "technician": 2,
            "admin": 3,
            "owner": 4,
        }
        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(min_role, 0)
        return user_level >= required_level


def get_tenant_context(
    workshop_id: uuid.UUID,
    current_user: "User",  # Will be injected via Depends
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    """
    Get tenant context with automatic membership verification.
    
    This dependency should be used in endpoints that require workshop context.
    It automatically verifies membership and returns a TenantContext object.
    """
    # Verify workshop exists and is active
    workshop = WorkshopCRUD.get_by_id(db, workshop_id)
    
    if not workshop or not workshop.is_active:
        logger.warning(
            "Workshop not found or inactive: %s (user: %s)",
            workshop_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found or inactive",
        )
    
    # Get user's membership
    membership = WorkshopMemberCRUD.get_membership(db, workshop_id, current_user.id)
    
    if not membership or not membership.is_active:
        logger.warning(
            "User %s attempted to access workshop %s without membership",
            current_user.id,
            workshop_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this workshop",
        )
    
    return TenantContext(workshop_id, current_user.id, membership, workshop)


def require_tenant_role(min_role: str = "member"):
    """
    Factory function to create a dependency that requires a specific role.
    
    Usage:
        @router.get("/admin")
        def admin_endpoint(
            context: TenantContext = Depends(require_tenant_role("admin")),
        ):
            ...
    """
    def _check_role(
        workshop_id: uuid.UUID,
        context: Annotated[TenantContext, Depends(get_tenant_context)],
    ) -> TenantContext:
        if not context.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role} role or higher. Your role: {context.role}",
            )
        return context
    
    return Depends(_check_role)


def filter_by_workshop(query: Query, workshop_id: uuid.UUID, model_class) -> Query:
    """
    Automatically filter a query by workshop_id if the model has that column.
    
    This is a helper function for automatic tenant isolation in queries.
    """
    if hasattr(model_class, 'workshop_id'):
        return query.filter(model_class.workshop_id == workshop_id)
    return query


def get_current_workshop_id(
    current_user: "User",  # Will be injected via Depends
    db: Annotated[Session, Depends(get_db)],
    workshop_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    """
    Get the current workshop ID from context or user's default workshop.
    
    If workshop_id is provided, verify user is a member.
    Otherwise, return user's first active workshop.
    """
    if workshop_id:
        # Verify membership
        membership = WorkshopMemberCRUD.get_membership(db, workshop_id, current_user.id)
        if membership and membership.is_active:
            return workshop_id
        return None
    
    # Get user's first active workshop
    workshops = WorkshopCRUD.get_user_workshops(db, current_user.id)
    if workshops:
        return workshops[0].id
    
    return None

