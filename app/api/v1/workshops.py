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
    return {"members": members}


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

