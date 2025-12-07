"""Add chat_thread_pdfs table for PDF reports.

Revision ID: 0012_chat_thread_pdfs
Revises: 0011_email_verification
Create Date: 2025-01-XX XX:XX:XX
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_chat_thread_pdfs"
down_revision: Union[str, None] = "0011_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_thread_pdfs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.Column("updated_by", sa.String(length=50), nullable=True),
        sa.Column("deleted_by", sa.String(length=50), nullable=True),
        sa.Column(
            "workshop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workshops.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("download_count", sa.Integer(), server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("chat_thread_pdfs")

