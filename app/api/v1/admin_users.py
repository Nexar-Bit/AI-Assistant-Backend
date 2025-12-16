"""User management endpoints for platform administrators."""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_serializer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user, require_superuser
from app.core.security import get_password_hash
from app.models.user import User
from app.workshops.models import WorkshopMember, Workshop
from app.workshops import WorkshopMemberCRUD
from sqlalchemy import and_

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=12)
    # Global role: owner (super admin), admin, technician, viewer, member
    role: str = Field(default="technician", pattern="^(owner|admin|technician|viewer|member)$")
    is_active: bool = Field(default=True)
    # Optional: assign to workshop (platform owners can assign to any workshop)
    workshop_id: Optional[uuid.UUID] = None
    workshop_role: Optional[str] = Field(None, pattern="^(owner|admin|technician|member|viewer)$")


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern="^(owner|admin|technician|viewer|member)$")
    is_active: Optional[bool] = None
    daily_token_limit: Optional[int] = Field(None, ge=0)


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=12)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool
    email_verified: bool
    registration_approved: bool
    daily_token_limit: int
    created_at: datetime
    updated_at: datetime

    @field_serializer('id')
    def serialize_id(self, value: uuid.UUID) -> str:
        return str(value)

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat() if value else None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List all users (platform admin only)."""
    query = db.query(User).filter(User.is_deleted == False)
    
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    users = query.order_by(User.created_at.desc()).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get a specific user by ID (platform admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID",
        )
    
    user = db.query(User).filter(
        User.id == user_uuid,
        User.is_deleted == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Create a new user (platform admin only)."""
    # Check if user already exists
    existing = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    
    if existing:
        if existing.username == user_data.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        if existing.email == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )
    
    # Hash password
    try:
        password_hash = get_password_hash(user_data.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Create user
    user = User(
        id=uuid.uuid4(),
        username=user_data.username,
        email=user_data.email,
        password_hash=password_hash,
        role=user_data.role,
        is_active=user_data.is_active,
        email_verified=True,  # Platform admin-created users are auto-verified
        registration_approved=True,  # Admin-created users are auto-approved
        created_by=str(current_user.id),
    )
    
    db.add(user)
    db.flush()
    
    # If workshop_id is provided, assign user to workshop (platform owners can assign to any workshop)
    if user_data.workshop_id and user_data.workshop_role:
        # Verify workshop exists
        workshop = db.query(Workshop).filter(
            Workshop.id == user_data.workshop_id,
            Workshop.is_deleted == False
        ).first()
        
        if not workshop:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workshop not found",
            )
        
        # Check if user is already a member
        existing_membership = WorkshopMemberCRUD.get_membership(db, user_data.workshop_id, user.id)
        if existing_membership:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this workshop",
            )
        
        # Add user to workshop
        WorkshopMemberCRUD.add_member(
            db,
            workshop_id=user_data.workshop_id,
            user_id=user.id,
            role=user_data.workshop_role,
            invited_by=current_user.id,
            created_by=current_user.id,
        )
    
    db.commit()
    db.refresh(user)
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Update a user (platform admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID",
        )
    
    user = db.query(User).filter(
        User.id == user_uuid,
        User.is_deleted == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Prevent changing own role or deactivating self
    if user.id == current_user.id:
        if user_data.role is not None and user_data.role != user.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own role",
            )
        if user_data.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate yourself",
            )
    
    # Check for conflicts if updating username or email
    if user_data.username and user_data.username != user.username:
        existing = db.query(User).filter(User.username == user_data.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
    
    if user_data.email and user_data.email != user.email:
        existing = db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )
    
    # Update fields
    if user_data.username is not None:
        user.username = user_data.username
    if user_data.email is not None:
        user.email = user_data.email
    
    # Update role in users table AND synchronize with workshop_members table
    if user_data.role is not None:
        old_role = user.role
        user.role = user_data.role
        
        # Also update workshop_members.role for all active workshops where this user is a member
        # This keeps both tables synchronized when changing roles from admin panel
        memberships = db.query(WorkshopMember).filter(
            and_(
                WorkshopMember.user_id == user_uuid,
                WorkshopMember.is_deleted == False,
                WorkshopMember.is_active == True
            )
        ).all()
        
        for membership in memberships:
            # Sync workshop role to match the new global role
            # Exception: If new global role is "owner", preserve existing workshop role
            # (platform owners can have different roles in different workshops)
            if user_data.role == "owner":
                # Platform owners can have any workshop role, don't change it
                pass
            else:
                # For all other roles, sync workshop_members.role to match users.role
                membership.role = user_data.role
                membership.updated_by = str(current_user.id)
                db.add(membership)
    
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    if user_data.daily_token_limit is not None:
        user.daily_token_limit = user_data.daily_token_limit
    
    user.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(user)
    
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
def reset_user_password(
    user_id: str,
    password_data: UserPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Reset a user's password (platform admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID",
        )
    
    user = db.query(User).filter(
        User.id == user_uuid,
        User.is_deleted == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Hash new password
    try:
        password_hash = get_password_hash(password_data.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    user.password_hash = password_hash
    user.updated_by = str(current_user.id)
    
    db.commit()
    
    return {"message": "Password reset successfully", "user_id": str(user.id)}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Delete a user (soft delete, platform admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID",
        )
    
    # Prevent deleting self
    if user_uuid == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    
    user = db.query(User).filter(
        User.id == user_uuid,
        User.is_deleted == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Soft delete
    user.is_deleted = True
    user.deleted_by = str(current_user.id)
    
    # Also deactivate
    user.is_active = False
    
    db.commit()


@router.post("/{user_id}/toggle-active", response_model=UserResponse)
def toggle_user_active(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Toggle user active status (platform admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID",
        )
    
    user = db.query(User).filter(
        User.id == user_uuid,
        User.is_deleted == False
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Toggle active status
    user.is_active = not user.is_active
    user.updated_by = str(current_user.id)
    db.commit()
    db.refresh(user)
    return user

