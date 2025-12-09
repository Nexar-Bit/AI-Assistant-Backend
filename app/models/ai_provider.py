"""AI Provider models for workshop configuration."""

import uuid
from sqlalchemy import Boolean, ForeignKey, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import TimestampedUUIDModel


class AIProviderType(str, enum.Enum):
    """Supported AI provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    LOCAL = "local"
    CUSTOM = "custom"


class AIProvider(TimestampedUUIDModel):
    """Global AI Provider configuration (superuser only)."""

    __tablename__ = "ai_providers"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)  # openai, anthropic, etc.
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted in production
    api_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)  # For custom endpoints
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Default model
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Usage limits (optional)
    max_tokens_per_request: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(nullable=True)


class WorkshopAIProvider(TimestampedUUIDModel):
    """Workshop-specific AI Provider assignment."""

    __tablename__ = "workshop_ai_providers"

    workshop_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False
    )
    ai_provider_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False
    )
    
    # Priority order (lower number = higher priority)
    priority: Mapped[int] = mapped_column(default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Workshop-specific overrides
    custom_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Override global key
    custom_model: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Override default model
    custom_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)

