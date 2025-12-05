import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampedUUIDModel


class Vehicle(TimestampedUUIDModel):
    """Vehicle model with automotive-specific fields."""

    __tablename__ = "vehicles"

    # Basic identification
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_type: Mapped[str | None] = mapped_column(String(50))
    make: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(50))
    year: Mapped[int | None] = mapped_column(Integer)
    vin: Mapped[str | None] = mapped_column(String(50))
    
    # Automotive-specific fields
    current_km: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Current odometer reading
    last_service_km: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Last service mileage
    last_service_date: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engine_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "2.0L Turbo", "Electric"
    fuel_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Gasoline, Diesel, Electric, Hybrid
    
    # Diagnostic history tracking
    total_diagnostic_sessions: Mapped[int] = mapped_column(Integer, default=0)  # Number of chat sessions
    last_diagnostic_date: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Last diagnostic session
    common_error_codes: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Most frequent error codes
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # Workshop notes about vehicle
    
    # Workshop association (multi-tenant)
    workshop_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id"), nullable=True
    )
    
    # Note: created_by is inherited from TimestampedUUIDModel as VARCHAR for audit trail
    # created_by_user_id is the actual ForeignKey to users.id
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


