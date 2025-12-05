"""Workshop-specific dependencies for multi-tenant isolation."""

import logging
import uuid
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.workshops import Workshop, WorkshopMember, WorkshopCRUD, WorkshopMemberCRUD


logger = logging.getLogger("app.dependencies.workshop")


def _check_workshop_membership(
    workshop_id: uuid.UUID,
    min_role: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkshopMember:
    """
    Internal function to check workshop membership.
    
    Args:
        workshop_id: UUID of the workshop
        min_role: Minimum required role (viewer, member, technician, admin, owner)
        current_user: Current authenticated user (injected)
        db: Database session (injected)
    
    Returns:
        WorkshopMember: The user's membership record
    
    Raises:
        HTTPException: 403 if user is not a member or lacks required role
    """
    # Verify workshop exists and is active
    workshop = (
        db.query(Workshop)
        .filter(
            Workshop.id == workshop_id,
            Workshop.is_active.is_(True),
            Workshop.is_deleted.is_(False),
        )
        .first()
    )
    
    if not workshop:
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
    membership = (
        db.query(WorkshopMember)
        .filter(
            WorkshopMember.workshop_id == workshop_id,
            WorkshopMember.user_id == current_user.id,
            WorkshopMember.is_active.is_(True),
            WorkshopMember.is_deleted.is_(False),
        )
        .first()
    )
    
    if not membership:
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


def require_workshop_membership(
    min_role: str = "member",
) -> Callable:
    """
    Factory function to create a FastAPI dependency for workshop membership.
    
    Usage:
        @router.get("/threads")
        def list_threads(
            workshop_id: UUID = Query(...),
            membership: WorkshopMember = Depends(require_workshop_membership()),
        ):
            # Use membership.workshop_id for queries
            ...
    """
    def dependency(
        workshop_id: Annotated[uuid.UUID, Query(...)],
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> WorkshopMember:
        return _check_workshop_membership(workshop_id, min_role, current_user, db)
    
    return dependency


def get_workshop_context(
    workshop_id: uuid.UUID,
    membership: Annotated[WorkshopMember, Depends(require_workshop_membership())] = None,
    db: Annotated[Session, Depends(get_db)] = None,
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
    
    workshop = (
        db.query(Workshop)
        .filter(
            Workshop.id == workshop_id,
            Workshop.is_active.is_(True),
            Workshop.is_deleted.is_(False),
        )
        .first()
    )
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop
