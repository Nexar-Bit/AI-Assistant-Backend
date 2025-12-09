"""Admin endpoints for managing user registrations."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_superuser
from app.core.database import get_db
from app.models.user import User
from app.services.email_service import email_service


router = APIRouter(prefix="/admin/registrations", tags=["admin", "registrations"])


class RegistrationResponse(BaseModel):
    """Schema for registration response."""
    id: uuid.UUID
    username: str
    email: str
    registration_message: Optional[str]
    registration_approved: bool
    email_verified: bool
    is_active: bool
    role: str
    created_at: str

    class Config:
        from_attributes = True


class ApproveRegistrationRequest(BaseModel):
    """Schema for approving a registration."""
    approved: bool


@router.get("/pending", response_model=List[RegistrationResponse])
def list_pending_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """List all pending user registrations (superuser only)."""
    users = db.query(User).filter(
        User.registration_approved == False,
        User.is_active == False,
    ).order_by(User.created_at.desc()).all()
    
    return [
        RegistrationResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            registration_message=u.registration_message,
            registration_approved=u.registration_approved,
            email_verified=u.email_verified,
            is_active=u.is_active,
            role=u.role,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.post("/{user_id}/approve", status_code=status.HTTP_200_OK)
def approve_registration(
    user_id: uuid.UUID,
    payload: ApproveRegistrationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Approve or reject a user registration (superuser only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if payload.approved:
        user.registration_approved = True
        # Only activate if email is also verified
        if user.email_verified:
            user.is_active = True
        
        # Send approval email
        if email_service.is_available():
            email_service.send_approval_email(
                to_email=user.email,
                username=user.username,
                approved=True,
            )
        
        db.commit()
        return {"message": "Registro aprobado exitosamente", "user_id": str(user.id)}
    else:
        # Reject registration
        if email_service.is_available():
            email_service.send_approval_email(
                to_email=user.email,
                username=user.username,
                approved=False,
            )
        
        # Optionally delete the user or mark as rejected
        db.delete(user)
        db.commit()
        return {"message": "Registro rechazado", "user_id": str(user_id)}


@router.get("/", response_model=List[RegistrationResponse])
def list_all_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
    include_approved: bool = True,
    limit: int = 100,
):
    """List all registrations with optional filtering (superuser only)."""
    query = db.query(User)
    
    if not include_approved:
        query = query.filter(User.registration_approved == False)
    
    users = query.order_by(User.created_at.desc()).limit(limit).all()
    
    return [
        RegistrationResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            registration_message=u.registration_message,
            registration_approved=u.registration_approved,
            email_verified=u.email_verified,
            is_active=u.is_active,
            role=u.role,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]

