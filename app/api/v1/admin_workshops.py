"""Workshop management endpoints for platform administrators."""

import uuid
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user, require_superuser
from app.models.user import User
from app.workshops.models import Workshop, WorkshopMember

router = APIRouter(prefix="/admin/workshops", tags=["admin-workshops"])


class WorkshopUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    monthly_token_limit: Optional[int] = Field(None, ge=0)


class WorkshopResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    owner_id: str
    monthly_token_limit: int
    tokens_used_this_month: int
    token_reset_date: Optional[date]
    token_allocation_date: Optional[date]
    token_reset_day: int
    is_active: bool
    allow_auto_invites: bool
    logo_url: Optional[str]
    primary_color: Optional[str]
    workshop_prompt: Optional[str]
    created_at: datetime
    updated_at: datetime

    @field_serializer('id')
    def serialize_id(self, value: uuid.UUID) -> str:
        return str(value)

    @field_serializer('token_reset_date', 'token_allocation_date')
    def serialize_date(self, value: Optional[date]) -> Optional[str]:
        return value.isoformat() if value else None

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat() if value else None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[WorkshopResponse])
def list_workshops(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
    is_active: Optional[bool] = None,
):
    """List all workshops (platform admin only)."""
    query = db.query(Workshop).filter(Workshop.is_deleted == False)
    
    if is_active is not None:
        query = query.filter(Workshop.is_active == is_active)
    
    workshops = query.order_by(Workshop.created_at.desc()).all()
    return workshops


@router.get("/{workshop_id}", response_model=WorkshopResponse)
def get_workshop(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get a specific workshop by ID (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop


@router.put("/{workshop_id}", response_model=WorkshopResponse)
@router.patch("/{workshop_id}", response_model=WorkshopResponse)
def update_workshop(
    workshop_id: str,
    workshop_data: WorkshopUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Update a workshop (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    # Update fields
    if workshop_data.name is not None:
        workshop.name = workshop_data.name
    if workshop_data.description is not None:
        workshop.description = workshop_data.description
    if workshop_data.is_active is not None:
        workshop.is_active = workshop_data.is_active
    if workshop_data.monthly_token_limit is not None:
        workshop.monthly_token_limit = workshop_data.monthly_token_limit
    
    workshop.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(workshop)
    
    return workshop


@router.post("/{workshop_id}/block", response_model=WorkshopResponse)
def block_workshop(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Block/deactivate a workshop (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    workshop.is_active = False
    workshop.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(workshop)
    
    return workshop


@router.post("/{workshop_id}/unblock", response_model=WorkshopResponse)
def unblock_workshop(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Unblock/activate a workshop (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    workshop.is_active = True
    workshop.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(workshop)
    
    return workshop


@router.delete("/{workshop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workshop(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Delete a workshop (soft delete, platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    # Soft delete
    workshop.is_deleted = True
    workshop.deleted_by = str(current_user.id)
    
    # Also deactivate
    workshop.is_active = False
    
    db.commit()


@router.post("/{workshop_id}/toggle-active", response_model=WorkshopResponse)
def toggle_workshop_active(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Toggle workshop active status (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    # Toggle active status
    workshop.is_active = not workshop.is_active
    workshop.updated_by = str(current_user.id)
    db.commit()
    db.refresh(workshop)
    return workshop


@router.post("/{workshop_id}/set-token-limit", response_model=WorkshopResponse)
def set_token_limit(
    workshop_id: str,
    new_limit: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Set workshop monthly token limit (platform admin only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_uuid,
        Workshop.is_deleted == False
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    # Update token limit
    workshop.monthly_token_limit = new_limit
    workshop.updated_by = str(current_user.id)
    db.commit()
    db.refresh(workshop)
    return workshop


@router.get("/memberships/all")
def get_all_workshop_memberships(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get all workshop memberships (platform admin only). Returns a mapping of workshop_id -> list of user_ids."""
    memberships = db.query(WorkshopMember).filter(
        WorkshopMember.is_deleted == False,
        WorkshopMember.is_active == True,
    ).all()
    
    # Create a mapping: workshop_id -> list of user_ids
    workshop_users_map = {}
    for membership in memberships:
        workshop_id = str(membership.workshop_id)
        user_id = str(membership.user_id)
        if workshop_id not in workshop_users_map:
            workshop_users_map[workshop_id] = []
        workshop_users_map[workshop_id].append(user_id)
    
    return {"workshop_users": workshop_users_map}

