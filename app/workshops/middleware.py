"""Workshop context middleware for multi-tenant isolation."""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from .models import Workshop, WorkshopMember
from .crud import WorkshopCRUD, WorkshopMemberCRUD


logger = logging.getLogger("app.workshops.middleware")


def require_workshop_membership(
    workshop_id: uuid.UUID,
    min_role: str = "member",
) -> type[Depends]:
    """
    Factory function to create a FastAPI dependency for workshop membership.
    
    Usage:
        @router.get("/threads")
        def list_threads(
            workshop_id: UUID,
            membership: WorkshopMember = Depends(require_workshop_membership(workshop_id)),
        ):
            ...
    """
    def _check_membership(
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> WorkshopMember:
        """Ensure user is a member of the workshop with required role."""
        if current_user is None or db is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Dependency injection failed",
            )
        
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
        
        # Check role hierarchy
        role_hierarchy = {
            "viewer": 0,
            "member": 1,
            "technician": 2,
            "admin": 3,
            "owner": 4,
        }
        
        user_role_level = role_hierarchy.get(membership.role, 0)
        required_level = role_hierarchy.get(min_role, 0)
        
        if user_role_level < required_level:
            logger.warning(
                "User %s (role: %s) attempted to access workshop %s requiring %s",
                current_user.id,
                membership.role,
                workshop_id,
                min_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role} role or higher. Your role: {membership.role}",
            )
        
        return membership
    
    return Depends(_check_membership)


def get_workshop_context(
    workshop_id: uuid.UUID,
    membership: Optional[WorkshopMember] = None,
    db: Optional[Session] = None,
) -> Workshop:
    """
    Get workshop context with membership verification.
    
    Returns the Workshop object after verifying user membership.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session not available",
        )
    
    workshop = WorkshopCRUD.get_by_id(db, workshop_id)
    
    if not workshop or not workshop.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop

