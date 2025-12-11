"""AI Prompt models for global and workshop-specific prompts."""

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedUUIDModel


class GlobalPrompt(TimestampedUUIDModel):
    """Global AI prompt configuration (platform admin only)."""

    __tablename__ = "global_prompts"

    # Prompt content
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Metadata
    name: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional name/description
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Version tracking
    version: Mapped[int] = mapped_column(default=1)  # Increment on updates


# Workshop prompts are stored in the Workshop model as a JSONB field
# This allows workshop admins to set their own prompts

