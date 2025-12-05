import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampedUUIDModel


class Consultation(TimestampedUUIDModel):
    __tablename__ = "consultations"

    # Multi-tenant: Workshop association
    workshop_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=True
    )
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response: Mapped[str] = mapped_column(Text, nullable=False)
    ai_model_used: Mapped[str] = mapped_column(String(50), default="gpt-3.5-turbo")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[float | None]
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    # optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


