"""Workshop models for multi-tenant architecture."""

import uuid
from datetime import date

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Date
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedUUIDModel


class Workshop(TimestampedUUIDModel):
    """Workshop/tenant entity for multi-tenant isolation."""

    __tablename__ = "workshops"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Owner/creator
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)  # UUID as string
    
    # Token management
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=100000)
    tokens_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    token_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # Next reset date
    token_allocation_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # When limit was set
    token_reset_day: Mapped[int] = mapped_column(Integer, default=1)  # Day of month to reset (1-28)
    
    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_auto_invites: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Branding
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # Hex color
    
    # Customization settings (JSONB for flexibility)
    vehicle_templates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Default vehicle templates
    quick_replies: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Workshop-specific quick replies
    diagnostic_code_library: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Custom diagnostic codes


class WorkshopMember(TimestampedUUIDModel):
    """User membership in a workshop with role-based access."""

    __tablename__ = "workshop_members"

    workshop_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    
    # Role within the workshop
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="member"
    )  # owner, admin, technician, viewer
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
