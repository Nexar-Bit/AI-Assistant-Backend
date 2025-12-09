"""AI Provider management endpoints (Superuser only)."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_superuser
from app.core.database import get_db
from app.models.user import User
from app.models.ai_provider import AIProvider, AIProviderType, WorkshopAIProvider
from app.workshops.models import Workshop


router = APIRouter(prefix="/ai-providers", tags=["ai-providers"])


# Pydantic Schemas
class AIProviderCreate(BaseModel):
    """Schema for creating an AI provider."""
    name: str = Field(..., min_length=1, max_length=100)
    provider_type: AIProviderType
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    model_name: Optional[str] = None
    description: Optional[str] = None
    max_tokens_per_request: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    is_active: bool = True


class AIProviderUpdate(BaseModel):
    """Schema for updating an AI provider."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider_type: Optional[AIProviderType] = None
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    model_name: Optional[str] = None
    description: Optional[str] = None
    max_tokens_per_request: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    is_active: Optional[bool] = None


class AIProviderResponse(BaseModel):
    """Schema for AI provider response (hides API key)."""
    id: uuid.UUID
    name: str
    provider_type: str
    api_endpoint: Optional[str]
    model_name: Optional[str]
    description: Optional[str]
    max_tokens_per_request: Optional[int]
    rate_limit_per_minute: Optional[int]
    is_active: bool
    has_api_key: bool  # Don't expose the actual key
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WorkshopAIProviderAssign(BaseModel):
    """Schema for assigning AI provider to workshop."""
    provider_id: uuid.UUID
    priority: int = 0
    is_enabled: bool = True
    custom_api_key: Optional[str] = None
    custom_model: Optional[str] = None
    custom_endpoint: Optional[str] = None


class WorkshopAIProviderResponse(BaseModel):
    """Schema for workshop AI provider response."""
    id: uuid.UUID
    workshop_id: uuid.UUID
    ai_provider_id: uuid.UUID
    priority: int
    is_enabled: bool
    has_custom_api_key: bool
    custom_model: Optional[str]
    custom_endpoint: Optional[str]
    provider: AIProviderResponse

    class Config:
        from_attributes = True


# Superuser endpoints for managing global AI providers
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=AIProviderResponse)
def create_ai_provider(
    payload: AIProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Create a new AI provider (superuser only)."""
    provider = AIProvider(
        id=uuid.uuid4(),
        name=payload.name,
        provider_type=payload.provider_type.value,
        api_key=payload.api_key,
        api_endpoint=payload.api_endpoint,
        model_name=payload.model_name,
        description=payload.description,
        max_tokens_per_request=payload.max_tokens_per_request,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        is_active=payload.is_active,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)

    # Convert to response format
    response = AIProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        api_endpoint=provider.api_endpoint,
        model_name=provider.model_name,
        description=provider.description,
        max_tokens_per_request=provider.max_tokens_per_request,
        rate_limit_per_minute=provider.rate_limit_per_minute,
        is_active=provider.is_active,
        has_api_key=bool(provider.api_key),
        created_at=provider.created_at.isoformat(),
        updated_at=provider.updated_at.isoformat(),
    )
    return response


@router.get("/", response_model=List[AIProviderResponse])
def list_ai_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
    include_inactive: bool = False,
):
    """List all AI providers (superuser only)."""
    query = db.query(AIProvider)
    if not include_inactive:
        query = query.filter(AIProvider.is_active == True)
    
    providers = query.all()
    
    return [
        AIProviderResponse(
            id=p.id,
            name=p.name,
            provider_type=p.provider_type,
            api_endpoint=p.api_endpoint,
            model_name=p.model_name,
            description=p.description,
            max_tokens_per_request=p.max_tokens_per_request,
            rate_limit_per_minute=p.rate_limit_per_minute,
            is_active=p.is_active,
            has_api_key=bool(p.api_key),
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in providers
    ]


@router.get("/{provider_id}", response_model=AIProviderResponse)
def get_ai_provider(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get AI provider by ID (superuser only)."""
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI provider not found",
        )
    
    return AIProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        api_endpoint=provider.api_endpoint,
        model_name=provider.model_name,
        description=provider.description,
        max_tokens_per_request=provider.max_tokens_per_request,
        rate_limit_per_minute=provider.rate_limit_per_minute,
        is_active=provider.is_active,
        has_api_key=bool(provider.api_key),
        created_at=provider.created_at.isoformat(),
        updated_at=provider.updated_at.isoformat(),
    )


@router.patch("/{provider_id}", response_model=AIProviderResponse)
def update_ai_provider(
    provider_id: uuid.UUID,
    payload: AIProviderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Update AI provider (superuser only)."""
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI provider not found",
        )
    
    # Update fields
    update_data = payload.model_dump(exclude_unset=True)
    if "provider_type" in update_data:
        update_data["provider_type"] = update_data["provider_type"].value
    
    for field, value in update_data.items():
        setattr(provider, field, value)
    
    db.commit()
    db.refresh(provider)
    
    return AIProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        api_endpoint=provider.api_endpoint,
        model_name=provider.model_name,
        description=provider.description,
        max_tokens_per_request=provider.max_tokens_per_request,
        rate_limit_per_minute=provider.rate_limit_per_minute,
        is_active=provider.is_active,
        has_api_key=bool(provider.api_key),
        created_at=provider.created_at.isoformat(),
        updated_at=provider.updated_at.isoformat(),
    )


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_provider(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Delete AI provider (superuser only)."""
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI provider not found",
        )
    
    db.delete(provider)
    db.commit()
    return None


# Workshop AI provider assignment endpoints
@router.post("/workshops/{workshop_id}/providers", status_code=status.HTTP_201_CREATED)
def assign_provider_to_workshop(
    workshop_id: uuid.UUID,
    payload: WorkshopAIProviderAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign AI provider to workshop (workshop admin or superuser)."""
    # Check if user is admin of workshop or superuser
    if current_user.role != "admin":
        # Check workshop membership
        from app.workshops.models import WorkshopMember
        membership = db.query(WorkshopMember).filter(
            WorkshopMember.workshop_id == workshop_id,
            WorkshopMember.user_id == current_user.id,
            WorkshopMember.is_active == True,
        ).first()
        
        if not membership or membership.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only workshop admins can assign AI providers",
            )
    
    # Check if provider exists
    provider = db.query(AIProvider).filter(AIProvider.id == payload.provider_id).first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI provider not found",
        )
    
    # Check if already assigned
    existing = db.query(WorkshopAIProvider).filter(
        WorkshopAIProvider.workshop_id == workshop_id,
        WorkshopAIProvider.ai_provider_id == payload.provider_id,
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider already assigned to workshop",
        )
    
    # Create assignment
    assignment = WorkshopAIProvider(
        id=uuid.uuid4(),
        workshop_id=workshop_id,
        ai_provider_id=payload.provider_id,
        priority=payload.priority,
        is_enabled=payload.is_enabled,
        custom_api_key=payload.custom_api_key,
        custom_model=payload.custom_model,
        custom_endpoint=payload.custom_endpoint,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return {"message": "Provider assigned successfully", "id": assignment.id}


@router.get("/workshops/{workshop_id}/providers", response_model=List[WorkshopAIProviderResponse])
def list_workshop_providers(
    workshop_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List AI providers for a workshop."""
    # Check workshop membership
    from app.workshops import WorkshopMember
    membership = db.query(WorkshopMember).filter(
        WorkshopMember.workshop_id == workshop_id,
        WorkshopMember.user_id == current_user.id,
        WorkshopMember.is_active == True,
    ).first()
    
    if not membership and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workshop",
        )
    
    # Get assignments
    assignments = db.query(WorkshopAIProvider).filter(
        WorkshopAIProvider.workshop_id == workshop_id
    ).order_by(WorkshopAIProvider.priority).all()
    
    # Get providers
    provider_ids = [a.ai_provider_id for a in assignments]
    providers = db.query(AIProvider).filter(AIProvider.id.in_(provider_ids)).all()
    provider_map = {p.id: p for p in providers}
    
    return [
        WorkshopAIProviderResponse(
            id=a.id,
            workshop_id=a.workshop_id,
            ai_provider_id=a.ai_provider_id,
            priority=a.priority,
            is_enabled=a.is_enabled,
            has_custom_api_key=bool(a.custom_api_key),
            custom_model=a.custom_model,
            custom_endpoint=a.custom_endpoint,
            provider=AIProviderResponse(
                id=provider_map[a.ai_provider_id].id,
                name=provider_map[a.ai_provider_id].name,
                provider_type=provider_map[a.ai_provider_id].provider_type,
                api_endpoint=provider_map[a.ai_provider_id].api_endpoint,
                model_name=provider_map[a.ai_provider_id].model_name,
                description=provider_map[a.ai_provider_id].description,
                max_tokens_per_request=provider_map[a.ai_provider_id].max_tokens_per_request,
                rate_limit_per_minute=provider_map[a.ai_provider_id].rate_limit_per_minute,
                is_active=provider_map[a.ai_provider_id].is_active,
                has_api_key=bool(provider_map[a.ai_provider_id].api_key),
                created_at=provider_map[a.ai_provider_id].created_at.isoformat(),
                updated_at=provider_map[a.ai_provider_id].updated_at.isoformat(),
            ),
        )
        for a in assignments
    ]


@router.delete("/workshops/{workshop_id}/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider_from_workshop(
    workshop_id: uuid.UUID,
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove AI provider from workshop (workshop admin or superuser)."""
    # Check permissions
    if current_user.role != "admin":
        from app.workshops.models import WorkshopMember
        membership = db.query(WorkshopMember).filter(
            WorkshopMember.workshop_id == workshop_id,
            WorkshopMember.user_id == current_user.id,
            WorkshopMember.is_active == True,
        ).first()
        
        if not membership or membership.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only workshop admins can remove AI providers",
            )
    
    # Find and delete assignment
    assignment = db.query(WorkshopAIProvider).filter(
        WorkshopAIProvider.workshop_id == workshop_id,
        WorkshopAIProvider.ai_provider_id == provider_id,
    ).first()
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider assignment not found",
        )
    
    db.delete(assignment)
    db.commit()
    return None

