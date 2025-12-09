"""Token management and accounting endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.tokens import TokenAccountingService
from app.services.token_notifications import TokenNotificationService
from app.api.v1 import workshops


router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("/remaining")
def get_remaining_tokens(
    workshop_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get remaining tokens for current user in current or specified workshop."""
    if not workshop_id:
        # Get from current workshop context (would need workshop store)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workshop_id is required",
        )
    
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Ensure user is member of workshop
    workshops._ensure_workshop_member(db, current_user.id, workshop_uuid)
    
    accounting_service = TokenAccountingService(db)
    remaining = accounting_service.get_user_remaining_tokens(current_user.id, workshop_uuid)
    
    # Get notifications
    notification_service = TokenNotificationService(db)
    notifications = notification_service.check_and_notify(current_user.id, workshop_uuid)
    
    return {
        "remaining": remaining,
        "notifications": notifications,
    }


@router.post("/validate")
async def validate_tokens(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pre-validate token availability for estimated usage."""
    workshop_id_str = payload.get("workshop_id")
    estimated_tokens = payload.get("estimated_tokens", 0)
    
    if not workshop_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workshop_id is required",
        )
    
    try:
        workshop_uuid = uuid.UUID(workshop_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Ensure user is member of workshop
    workshops._ensure_workshop_member(db, current_user.id, workshop_uuid)
    
    accounting_service = TokenAccountingService(db)
    
    # Check limits
    workshop_ok = accounting_service.check_workshop_limits(workshop_uuid, estimated_tokens)
    user_ok = accounting_service.check_user_limits(current_user.id, workshop_uuid, estimated_tokens)
    
    remaining = accounting_service.get_user_remaining_tokens(current_user.id, workshop_uuid)
    
    return {
        "is_allowed": workshop_ok and user_ok,
        "workshop_ok": workshop_ok,
        "user_ok": user_ok,
        "remaining": remaining,
    }


@router.get("/workshops/{workshop_id}/usage")
def get_workshop_token_usage(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workshop token usage and limits (admin/owner only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Ensure user is admin or owner
    workshops._ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    accounting_service = TokenAccountingService(db)
    remaining = accounting_service.get_user_remaining_tokens(current_user.id, workshop_uuid)
    
    return {
        "workshop": remaining["workshop"],
        "user": remaining["user"],
    }

