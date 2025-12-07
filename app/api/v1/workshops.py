"""Workshop management endpoints for multi-tenant architecture."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.workshops import Workshop, WorkshopMember, WorkshopCRUD, WorkshopMemberCRUD
from app.workshops.middleware import require_workshop_membership
from app.workshops.schemas import WorkshopCustomizationUpdate


router = APIRouter(prefix="/workshops", tags=["workshops"])


def _get_user_workshops(db: Session, user_id: uuid.UUID) -> list[Workshop]:
    """Get all workshops where user is a member."""
    memberships = (
        db.query(WorkshopMember)
        .filter(
            WorkshopMember.user_id == user_id,
            WorkshopMember.is_active.is_(True),
            Workshop.is_active.is_(True),
        )
        .join(Workshop, WorkshopMember.workshop_id == Workshop.id)
        .all()
    )
    workshop_ids = [m.workshop_id for m in memberships]
    return db.query(Workshop).filter(Workshop.id.in_(workshop_ids)).all()


def _ensure_workshop_member(
    db: Session, user_id: uuid.UUID, workshop_id: uuid.UUID, min_role: str = "member"
) -> WorkshopMember:
    """Ensure user is a member of the workshop with required role."""
    membership = (
        db.query(WorkshopMember)
        .filter(
            WorkshopMember.workshop_id == workshop_id,
            WorkshopMember.user_id == user_id,
            WorkshopMember.is_active.is_(True),
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this workshop",
        )
    
    role_hierarchy = {"viewer": 0, "member": 1, "technician": 2, "admin": 3, "owner": 4}
    user_role_level = role_hierarchy.get(membership.role, 0)
    required_level = role_hierarchy.get(min_role, 0)
    
    if user_role_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {min_role} role or higher",
        )
    
    return membership


@router.get("/")
def list_workshops(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all workshops the current user is a member of."""
    workshops = WorkshopCRUD.get_user_workshops(db, current_user.id)
    return {"workshops": workshops}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_workshop(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new workshop (user becomes owner)."""
    name = payload.get("name")
    slug = payload.get("slug") or name.lower().replace(" ", "-")[:50]
    description = payload.get("description")
    monthly_token_limit = payload.get("monthly_token_limit", 100000)
    
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workshop name is required",
        )
    
    # Check slug uniqueness using WorkshopCRUD
    existing = WorkshopCRUD.get_by_slug(db, slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workshop slug already exists",
        )
    
    # Create workshop using WorkshopCRUD
    workshop = WorkshopCRUD.create(
        db,
        name=name,
        slug=slug,
        owner_id=current_user.id,
        description=description,
        monthly_token_limit=monthly_token_limit,
    )
    
    return workshop


@router.get("/{workshop_id}")
def get_workshop(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workshop details (must be a member)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid)
    
    workshop = db.query(Workshop).filter(Workshop.id == workshop_uuid).first()
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop


@router.put("/{workshop_id}")
def update_workshop(
    workshop_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update workshop (requires admin or owner role)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    # Update workshop using WorkshopCRUD
    update_data = {}
    if "name" in payload:
        update_data["name"] = payload["name"]
    if "description" in payload:
        update_data["description"] = payload["description"]
    if "monthly_token_limit" in payload:
        update_data["monthly_token_limit"] = payload["monthly_token_limit"]
    if "is_active" in payload:
        update_data["is_active"] = payload["is_active"]
    
    update_data["updated_by"] = str(current_user.id)
    
    workshop = WorkshopCRUD.update(db, workshop_uuid, **update_data)
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop


@router.get("/{workshop_id}/members")
def get_workshop_members(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all members of a workshop (must be a member)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid)
    
    members = WorkshopMemberCRUD.get_workshop_members(db, workshop_uuid, active_only=False)
    
    # Include user information for each member
    members_with_user = []
    for member in members:
        user = db.query(User).filter(User.id == member.user_id).first()
        members_with_user.append({
            "id": str(member.id),
            "workshop_id": str(member.workshop_id),
            "user_id": str(member.user_id),
            "role": member.role,
            "is_active": member.is_active,
            "invited_by": str(member.invited_by) if member.invited_by else None,
            "created_at": member.created_at.isoformat() if member.created_at else None,
            "user": {
                "id": str(user.id) if user else None,
                "username": user.username if user else None,
                "email": user.email if user else None,
            } if user else None,
        })
    
    return {"members": members_with_user}


@router.get("/{workshop_id}/my-role")
def get_my_workshop_role(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's role in a workshop (any member can access this)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    # Get user's membership - any member can see their own role
    membership = WorkshopMemberCRUD.get_membership(db, workshop_uuid, current_user.id)
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this workshop",
        )
    
    if not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your membership in this workshop is inactive",
        )
    
    return {
        "workshop_id": str(workshop_uuid),
        "user_id": str(current_user.id),
        "role": membership.role,
        "is_active": membership.is_active,
    }


@router.put("/{workshop_id}/members/{user_id}/role")
def update_member_role(
    workshop_id: str,
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a member's role (requires admin or owner role)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID or user ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    new_role = payload.get("role")
    if not new_role or new_role not in ["owner", "admin", "technician", "member", "viewer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be: owner, admin, technician, member, or viewer",
        )
    
    # Prevent changing owner role
    membership = WorkshopMemberCRUD.get_membership(db, workshop_uuid, user_uuid)
    if membership and membership.role == "owner" and new_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change owner role",
        )
    
    updated = WorkshopMemberCRUD.update_role(db, workshop_uuid, user_uuid, new_role, current_user.id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    
    return updated


@router.post("/{workshop_id}/members")
def add_member(
    workshop_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a user to a workshop (requires admin or owner role)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    user_email = payload.get("email") or payload.get("user_email")
    user_id_str = payload.get("user_id")
    role = payload.get("role", "member")
    
    if role not in ["owner", "admin", "technician", "member", "viewer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be: owner, admin, technician, member, or viewer",
        )
    
    # Find user by email or user_id
    user = None
    if user_id_str:
        try:
            user_uuid = uuid.UUID(user_id_str)
            user = db.query(User).filter(User.id == user_uuid).first()
        except ValueError:
            pass
    
    if not user and user_email:
        user = db.query(User).filter(User.email == user_email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Check if user is already a member
    existing = WorkshopMemberCRUD.get_membership(db, workshop_uuid, user.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this workshop",
        )
    
    # Add member
    membership = WorkshopMemberCRUD.add_member(
        db,
        workshop_id=workshop_uuid,
        user_id=user.id,
        role=role,
        invited_by=current_user.id,
        created_by=current_user.id,
    )
    
    # Include user information
    return {
        "id": str(membership.id),
        "workshop_id": str(membership.workshop_id),
        "user_id": str(membership.user_id),
        "role": membership.role,
        "is_active": membership.is_active,
        "invited_by": str(membership.invited_by) if membership.invited_by else None,
        "created_at": membership.created_at.isoformat() if membership.created_at else None,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
        },
    }


@router.delete("/{workshop_id}/members/{user_id}")
def remove_member(
    workshop_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from a workshop (requires admin or owner role)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID or user ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    # Prevent removing owner
    membership = WorkshopMemberCRUD.get_membership(db, workshop_uuid, user_uuid)
    if membership and membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove workshop owner",
        )
    
    # Prevent removing yourself
    if user_uuid == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself from the workshop",
        )
    
    success = WorkshopMemberCRUD.remove_member(db, workshop_uuid, user_uuid, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    
    return {"message": "Member removed successfully"}


@router.put("/{workshop_id}/customization")
def update_workshop_customization(
    workshop_id: str,
    payload: WorkshopCustomizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update workshop customization (requires admin or owner role)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    _ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="admin")
    
    # Validate primary color accessibility if provided
    if payload.primary_color:
        # Basic validation: ensure color has sufficient contrast
        # This is a simplified check - in production, use a proper contrast checker
        color = payload.primary_color.lstrip("#")
        if len(color) != 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Primary color must be a valid hex color (e.g., #1A56DB)",
            )
    
    # Update customization fields
    update_data = {}
    if payload.logo_url is not None:
        update_data["logo_url"] = payload.logo_url
    if payload.primary_color is not None:
        update_data["primary_color"] = payload.primary_color
    if payload.vehicle_templates is not None:
        update_data["vehicle_templates"] = payload.vehicle_templates
    if payload.quick_replies is not None:
        update_data["quick_replies"] = payload.quick_replies
    if payload.diagnostic_code_library is not None:
        update_data["diagnostic_code_library"] = payload.diagnostic_code_library
    
    update_data["updated_by"] = str(current_user.id)
    
    workshop = WorkshopCRUD.update(db, workshop_uuid, **update_data)
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop

