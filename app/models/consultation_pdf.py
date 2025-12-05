import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampedUUIDModel


class ConsultationPDF(TimestampedUUIDModel):
    __tablename__ = "consultation_pdfs"

    # Multi-tenant: Workshop association
    workshop_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=True
    )
    
    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), unique=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)


