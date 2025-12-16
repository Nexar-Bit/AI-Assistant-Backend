"""Admin endpoints for managing user registrations."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_serializer
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_superuser
from app.core.database import get_db
from app.models.user import User
from app.services.email_service import email_service
from app.workshops.crud import WorkshopCRUD, WorkshopMemberCRUD


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
    created_at: datetime

    @field_serializer('id')
    def serialize_id(self, value: uuid.UUID) -> str:
        return str(value)

    @field_serializer('created_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat() if value else None

    class Config:
        from_attributes = True


class ApproveRegistrationRequest(BaseModel):
    """Schema for approving a registration."""
    approved: bool
    workshop_id: Optional[uuid.UUID] = None  # Workshop to assign user to
    workshop_role: Optional[str] = None  # Role in the workshop (owner, admin, technician, viewer, member)


@router.get("/pending", response_model=List[RegistrationResponse])
def list_pending_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """List all pending user registrations (superuser only)."""
    users = db.query(User).filter(
        User.registration_approved == False,
        User.is_deleted == False,
    ).order_by(User.created_at.desc()).all()
    
    return users


@router.post("/{user_id}/approve", status_code=status.HTTP_200_OK)
def approve_registration(
    user_id: uuid.UUID,
    payload: ApproveRegistrationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Approve or reject a user registration with workshop assignment (superuser only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if payload.approved:
        # Validate workshop assignment if provided
        if payload.workshop_id and not payload.workshop_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workshop role is required when assigning to a workshop",
            )
        
        # Validate workshop exists
        if payload.workshop_id:
            workshop = WorkshopCRUD.get_by_id(db, payload.workshop_id)
            if not workshop:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Workshop not found",
                )
            
            if not workshop.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot assign user to inactive workshop",
                )
        
        # Approve registration
        user.registration_approved = True
        # Activate user (email verification removed)
        user.is_active = True
        user.email_verified = True  # Mark as verified automatically
        
        db.commit()
        db.refresh(user)
        
        # Add user to workshop if specified
        if payload.workshop_id and payload.workshop_role:
            try:
                WorkshopMemberCRUD.add_member(
                    db=db,
                    workshop_id=payload.workshop_id,
                    user_id=user.id,
                    role=payload.workshop_role,
                    invited_by=current_user.id,
                    created_by=current_user.id,
                )
                db.commit()
            except Exception as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"User approved but failed to add to workshop: {str(e)}",
                )
        
        # Send approval email
        try:
            if email_service.is_available():
                email_service.send_approval_email(
                    to_email=user.email,
                    username=user.username,
                    approved=True,
                )
        except Exception as e:
            # Don't fail the request if email fails
            pass
        
        return {
            "message": "Registro aprobado exitosamente",
            "user_id": str(user.id),
            "workshop_assigned": payload.workshop_id is not None,
            "workshop_id": str(payload.workshop_id) if payload.workshop_id else None,
        }
    else:
        # Reject registration
        try:
            if email_service.is_available():
                email_service.send_approval_email(
                    to_email=user.email,
                    username=user.username,
                    approved=False,
                )
        except Exception:
            pass
        
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
    
    return users

