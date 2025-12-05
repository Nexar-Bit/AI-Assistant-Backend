"""Enhance chat models for real-time support.

Revision ID: 0006_enhance_chat_realtime
Revises: 0005_multi_tenant_chat
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_enhance_chat_realtime"
down_revision: Union[str, None] = "0005_multi_tenant_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enhance chat_threads table
    op.add_column(
        "chat_threads",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column(
        "chat_threads",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chat_threads",
        sa.Column("session_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
    )
    
    # Add check constraint for status
    op.create_check_constraint(
        "ck_chat_threads_status",
        "chat_threads",
        "status IN ('active', 'completed', 'archived')",
    )
    
    # Enhance chat_messages table
    op.add_column(
        "chat_messages",
        sa.Column("sender_type", sa.String(length=20), nullable=False, server_default="technician"),
    )
    op.add_column(
        "chat_messages",
        sa.Column("is_markdown", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "chat_messages",
        sa.Column("attachments", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "chat_messages",
        sa.Column("message_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
    )
    
    # Add check constraint for sender_type
    op.create_check_constraint(
        "ck_chat_messages_sender_type",
        "chat_messages",
        "sender_type IN ('technician', 'ai', 'system')",
    )
    
    # Add index for status queries
    op.create_index(
        "idx_chat_threads_status_workshop",
        "chat_threads",
        ["workshop_id", "status", "last_message_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_threads_status_workshop", table_name="chat_threads")
    op.drop_constraint("ck_chat_messages_sender_type", "chat_messages", type_="check")
    op.drop_constraint("ck_chat_threads_status", "chat_threads", type_="check")
    op.drop_column("chat_messages", "message_metadata")
    op.drop_column("chat_messages", "attachments")
    op.drop_column("chat_messages", "is_markdown")
    op.drop_column("chat_messages", "sender_type")
    op.drop_column("chat_threads", "session_metadata")
    op.drop_column("chat_threads", "last_message_at")
    op.drop_column("chat_threads", "status")

