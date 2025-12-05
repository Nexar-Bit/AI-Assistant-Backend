"""Chat models for multi-message conversations."""

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedUUIDModel


class ChatThread(TimestampedUUIDModel):
    """Chat conversation thread - replaces single Q/A consultations."""

    __tablename__ = "chat_threads"

    workshop_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True
    )
    
    # Thread metadata
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Auto-generated from first message
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Vehicle context (stored at thread creation)
    vehicle_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_codes: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Comma-separated DTC codes
    vehicle_context: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # Additional context
    
    # Token tracking (aggregated from all messages)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, completed, archived
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # For storing session-specific data
    
    # Optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ChatMessage(TimestampedUUIDModel):
    """Individual message in a chat thread."""

    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    
    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False, default="technician")  # technician, ai, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_markdown: Mapped[bool] = mapped_column(Boolean, default=True)  # Whether content is markdown
    attachments: Mapped[dict] = mapped_column(JSONB, default=dict)  # For storing file paths, error codes, etc.
    
    # AI response metadata (only for assistant messages)
    ai_model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    
    # Message ordering
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)  # Order within thread
    
    # Status
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # For storing message-specific data

