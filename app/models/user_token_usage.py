"""User token usage tracking model."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampedUUIDModel


class UserTokenUsage(TimestampedUUIDModel):
    """Daily and monthly token usage tracking per user per workshop."""

    __tablename__ = "user_token_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workshop_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Daily tracking
    input_tokens_today: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens_today: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_today: Mapped[int] = mapped_column(Integer, default=0)
    
    # Monthly tracking (aggregated)
    input_tokens_month: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens_month: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_month: Mapped[int] = mapped_column(Integer, default=0)
    
    # Limits (cached for performance)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Metadata
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        UniqueConstraint("user_id", "workshop_id", "date", name="uq_user_workshop_date"),
    )

