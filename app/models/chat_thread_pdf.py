import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampedUUIDModel


class ChatThreadPDF(TimestampedUUIDModel):
    """PDF reports for chat threads."""

    __tablename__ = "chat_thread_pdfs"

    # Multi-tenant: Workshop association
    workshop_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("workshops.id", ondelete="CASCADE"), nullable=True
    )
    
    thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), ForeignKey("chat_threads.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)

