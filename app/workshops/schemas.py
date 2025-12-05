"""Pydantic schemas for workshop management."""

from datetime import date
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class WorkshopBase(BaseModel):
    """Base workshop schema."""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    monthly_token_limit: int = Field(default=100000, ge=0)
    is_active: bool = True
    allow_auto_invites: bool = False
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    vehicle_templates: Optional[Dict[str, Any]] = None
    quick_replies: Optional[Dict[str, Any]] = None
    diagnostic_code_library: Optional[Dict[str, Any]] = None


class WorkshopCreate(WorkshopBase):
    """Schema for creating a workshop."""
    pass


class WorkshopUpdate(BaseModel):
    """Schema for updating a workshop."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    monthly_token_limit: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    allow_auto_invites: Optional[bool] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    vehicle_templates: Optional[Dict[str, Any]] = None
    quick_replies: Optional[Dict[str, Any]] = None
    diagnostic_code_library: Optional[Dict[str, Any]] = None


class WorkshopCustomizationUpdate(BaseModel):
    """Schema for updating workshop customization only."""
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    vehicle_templates: Optional[Dict[str, Any]] = None
    quick_replies: Optional[Dict[str, Any]] = None
    diagnostic_code_library: Optional[Dict[str, Any]] = None


class VehicleTemplate(BaseModel):
    """Vehicle template schema."""
    name: str = Field(..., min_length=1, max_length=100)
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine_type: Optional[str] = None
    fuel_type: Optional[str] = None
    default_fields: Optional[Dict[str, Any]] = None


class QuickReply(BaseModel):
    """Quick reply schema."""
    label: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = None  # e.g., "diagnostics", "repair", "general"


class DiagnosticCodeEntry(BaseModel):
    """Diagnostic code library entry schema."""
    code: str = Field(..., pattern=r"^[PBCU]\d{4}$")
    description: str = Field(..., min_length=1, max_length=500)
    severity: str = Field(default="warning", pattern="^(critical|warning|info)$")
    common_causes: Optional[List[str]] = None
    notes: Optional[str] = None


class WorkshopResponse(WorkshopBase):
    """Schema for workshop response."""
    id: UUID
    owner_id: str
    tokens_used_this_month: int
    token_reset_date: Optional[date] = None
    token_allocation_date: Optional[date] = None
    token_reset_day: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WorkshopMemberBase(BaseModel):
    """Base workshop member schema."""
    role: str = Field(default="member", pattern="^(owner|admin|technician|viewer|member)$")
    is_active: bool = True


class WorkshopMemberCreate(WorkshopMemberBase):
    """Schema for creating a workshop member."""
    user_id: UUID
    workshop_id: UUID


class WorkshopMemberUpdate(BaseModel):
    """Schema for updating a workshop member."""
    role: Optional[str] = Field(None, pattern="^(owner|admin|technician|viewer|member)$")
    is_active: Optional[bool] = None


class WorkshopMemberResponse(WorkshopMemberBase):
    """Schema for workshop member response."""
    id: UUID
    workshop_id: UUID
    user_id: UUID
    invited_by: Optional[UUID] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

