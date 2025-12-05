"""Add token accounting system.

Revision ID: 0007_add_token_accounting
Revises: 0006_enhance_chat_realtime
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_add_token_accounting"
down_revision: Union[str, None] = "0006_enhance_chat_realtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enhance workshops table
    op.add_column(
        "workshops",
        sa.Column("token_reset_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "workshops",
        sa.Column("token_allocation_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "workshops",
        sa.Column("token_reset_day", sa.Integer(), nullable=False, server_default="1"),
    )
    
    # Create user_token_usage table
    op.create_table(
        "user_token_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.Column("updated_by", sa.String(length=50), nullable=True),
        sa.Column("deleted_by", sa.String(length=50), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workshop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workshops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("input_tokens_today", sa.Integer(), server_default="0"),
        sa.Column("output_tokens_today", sa.Integer(), server_default="0"),
        sa.Column("total_tokens_today", sa.Integer(), server_default="0"),
        sa.Column("input_tokens_month", sa.Integer(), server_default="0"),
        sa.Column("output_tokens_month", sa.Integer(), server_default="0"),
        sa.Column("total_tokens_month", sa.Integer(), server_default="0"),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_limit", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create unique constraint
    op.create_unique_constraint(
        "uq_user_workshop_date",
        "user_token_usage",
        ["user_id", "workshop_id", "date"],
    )
    
    # Create indexes
    op.create_index(
        "idx_user_token_usage_user_workshop",
        "user_token_usage",
        ["user_id", "workshop_id", "date"],
    )
    op.create_index(
        "idx_user_token_usage_date",
        "user_token_usage",
        ["date"],
    )


def downgrade() -> None:
    op.drop_table("user_token_usage")
    op.drop_column("workshops", "token_reset_day")
    op.drop_column("workshops", "token_allocation_date")
    op.drop_column("workshops", "token_reset_date")

