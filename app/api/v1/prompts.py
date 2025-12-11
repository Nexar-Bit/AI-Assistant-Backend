"""AI Prompt management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user, require_superuser
from app.models.user import User
from app.models.prompt import GlobalPrompt
from app.workshops.models import Workshop
from app.workshops.tenant_context import get_tenant_context
import uuid

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ==================== Global Prompts (Platform Admin Only) ====================

class GlobalPromptCreate(BaseModel):
    prompt_text: str = Field(..., min_length=10, description="The prompt text")
    name: Optional[str] = Field(None, max_length=200, description="Optional name/description")
    is_active: bool = Field(True, description="Whether this prompt is active")


class GlobalPromptUpdate(BaseModel):
    prompt_text: Optional[str] = Field(None, min_length=10)
    name: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None


class GlobalPromptResponse(BaseModel):
    id: str
    prompt_text: str
    name: Optional[str]
    is_active: bool
    version: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.post("/global", response_model=GlobalPromptResponse, status_code=status.HTTP_201_CREATED)
def create_global_prompt(
    prompt_data: GlobalPromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Create a new global prompt (platform admin only)."""
    # Deactivate all existing prompts if this one is active
    if prompt_data.is_active:
        db.query(GlobalPrompt).filter(GlobalPrompt.is_active == True).update({"is_active": False})
    
    prompt = GlobalPrompt(
        id=uuid.uuid4(),
        prompt_text=prompt_data.prompt_text,
        name=prompt_data.name,
        is_active=prompt_data.is_active,
        version=1,
        created_by=str(current_user.id),
    )
    
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    
    return prompt


@router.get("/global", response_model=List[GlobalPromptResponse])
def list_global_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """List all global prompts (platform admin only)."""
    prompts = db.query(GlobalPrompt).filter(
        GlobalPrompt.is_deleted == False
    ).order_by(GlobalPrompt.created_at.desc()).all()
    return prompts


@router.get("/global/active", response_model=Optional[GlobalPromptResponse])
def get_active_global_prompt(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the currently active global prompt (any authenticated user can view)."""
    prompt = db.query(GlobalPrompt).filter(
        GlobalPrompt.is_active == True,
        GlobalPrompt.is_deleted == False
    ).order_by(GlobalPrompt.created_at.desc()).first()
    return prompt


@router.get("/global/{prompt_id}", response_model=GlobalPromptResponse)
def get_global_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get a specific global prompt by ID (platform admin only)."""
    try:
        prompt_uuid = uuid.UUID(prompt_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid prompt ID",
        )
    
    prompt = db.query(GlobalPrompt).filter(
        GlobalPrompt.id == prompt_uuid,
        GlobalPrompt.is_deleted == False
    ).first()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found",
        )
    
    return prompt


@router.put("/global/{prompt_id}", response_model=GlobalPromptResponse)
def update_global_prompt(
    prompt_id: str,
    prompt_data: GlobalPromptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Update a global prompt (platform admin only)."""
    try:
        prompt_uuid = uuid.UUID(prompt_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid prompt ID",
        )
    
    prompt = db.query(GlobalPrompt).filter(
        GlobalPrompt.id == prompt_uuid,
        GlobalPrompt.is_deleted == False
    ).first()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found",
        )
    
    # If activating this prompt, deactivate others
    if prompt_data.is_active is True:
        db.query(GlobalPrompt).filter(
            GlobalPrompt.id != prompt_uuid,
            GlobalPrompt.is_active == True
        ).update({"is_active": False})
    
    # Update fields
    if prompt_data.prompt_text is not None:
        prompt.prompt_text = prompt_data.prompt_text
        prompt.version += 1
    if prompt_data.name is not None:
        prompt.name = prompt_data.name
    if prompt_data.is_active is not None:
        prompt.is_active = prompt_data.is_active
    
    prompt.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(prompt)
    
    return prompt


@router.delete("/global/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Delete a global prompt (soft delete, platform admin only)."""
    try:
        prompt_uuid = uuid.UUID(prompt_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid prompt ID",
        )
    
    prompt = db.query(GlobalPrompt).filter(
        GlobalPrompt.id == prompt_uuid,
        GlobalPrompt.is_deleted == False
    ).first()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found",
        )
    
    # Soft delete
    prompt.is_deleted = True
    prompt.deleted_by = str(current_user.id)
    
    db.commit()


# ==================== Workshop Prompts (Workshop Admin Only) ====================

class WorkshopPromptUpdate(BaseModel):
    workshop_prompt: Optional[str] = Field(None, min_length=10, description="Workshop-specific prompt")


@router.get("/workshop/{workshop_id}", response_model=Optional[str])
def get_workshop_prompt(
    workshop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workshop-specific prompt (workshop admin/owner only, technicians cannot see)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    # Check user is admin or owner of workshop
    tenant_context = get_tenant_context(workshop_uuid, current_user, db)
    if not tenant_context.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workshop administrators can view prompts",
        )
    
    workshop = db.query(Workshop).filter(Workshop.id == workshop_uuid).first()
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    return workshop.workshop_prompt


@router.put("/workshop/{workshop_id}", response_model=dict)
def update_workshop_prompt(
    workshop_id: str,
    prompt_data: WorkshopPromptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update workshop-specific prompt (workshop admin/owner only)."""
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop ID",
        )
    
    # Check user is admin or owner of workshop
    tenant_context = get_tenant_context(workshop_uuid, current_user, db)
    if not tenant_context.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workshop administrators can update prompts",
        )
    
    workshop = db.query(Workshop).filter(Workshop.id == workshop_uuid).first()
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    if prompt_data.workshop_prompt is not None:
        workshop.workshop_prompt = prompt_data.workshop_prompt
        workshop.updated_by = str(current_user.id)
    
    db.commit()
    db.refresh(workshop)
    
    return {"workshop_prompt": workshop.workshop_prompt}

