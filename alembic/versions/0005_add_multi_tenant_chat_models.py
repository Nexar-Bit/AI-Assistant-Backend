"""Add multi-tenant chat models with workshop isolation.

Revision ID: 0005_add_multi_tenant_chat_models
Revises: 0004_create_audit_logs
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_multi_tenant_chat"
down_revision: Union[str, None] = "0004_create_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create workshops table (root tenant entity)
    op.create_table(
        "workshops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.Column("updated_by", sa.String(length=50), nullable=True),
        sa.Column("deleted_by", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=False),  # UUID as string
        sa.Column("monthly_token_limit", sa.Integer(), server_default="100000"),
        sa.Column("tokens_used_this_month", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("allow_auto_invites", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=True),  # Hex color
    )
    op.create_index("idx_workshops_slug", "workshops", ["slug"], unique=True)
    op.create_index("idx_workshops_active", "workshops", ["is_active", "is_deleted"])

    # 2. Create workshop_members table (user-workshop relationships)
    op.create_table(
        "workshop_members",
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
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    # Unique constraint: user can only have one active membership per workshop
    op.create_index(
        "idx_workshop_members_unique",
        "workshop_members",
        ["workshop_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND is_active = true"),
    )
    op.create_index("idx_workshop_members_workshop", "workshop_members", ["workshop_id"])
    op.create_index("idx_workshop_members_user", "workshop_members", ["user_id"])

    # 3. Update vehicles table: Add workshop_id and automotive fields
    op.add_column("vehicles", sa.Column("workshop_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("vehicles", sa.Column("current_km", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("last_service_km", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("last_service_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vehicles", sa.Column("engine_type", sa.String(length=50), nullable=True))
    op.add_column("vehicles", sa.Column("fuel_type", sa.String(length=20), nullable=True))
    
    # Add foreign key for workshop_id
    op.create_foreign_key(
        "fk_vehicles_workshop",
        "vehicles",
        "workshops",
        ["workshop_id"],
        ["id"],
        ondelete="SET NULL",
    )
    
    # Remove old unique constraint on license_plate (now workshop-scoped)
    # In PostgreSQL, unique constraints are implemented as indexes, so drop the constraint
    op.drop_constraint("vehicles_license_plate_key", "vehicles", type_="unique")
    
    # Add new unique constraint: license_plate unique within workshop
    op.create_index(
        "idx_vehicles_workshop_license",
        "vehicles",
        ["workshop_id", "license_plate"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("idx_vehicles_workshop", "vehicles", ["workshop_id"])

    # 4. Create chat_threads table (replaces consultations for chat-based conversations)
    op.create_table(
        "chat_threads",
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
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("license_plate", sa.String(length=20), nullable=False),
        sa.Column("vehicle_km", sa.Integer(), nullable=True),
        sa.Column("error_codes", sa.String(length=500), nullable=True),  # Comma-separated DTC codes
        sa.Column("vehicle_context", sa.String(length=1000), nullable=True),
        sa.Column("total_prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    # CRITICAL: Index for workshop isolation queries
    op.create_index("idx_chat_threads_workshop", "chat_threads", ["workshop_id"])
    op.create_index("idx_chat_threads_user", "chat_threads", ["user_id"])
    op.create_index("idx_chat_threads_workshop_user", "chat_threads", ["workshop_id", "user_id"])
    op.create_index("idx_chat_threads_created", "chat_threads", ["created_at"])

    # 5. Create chat_messages table (individual messages in threads)
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=50), nullable=True),
        sa.Column("updated_by", sa.String(length=50), nullable=True),
        sa.Column("deleted_by", sa.String(length=50), nullable=True),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),  # user, assistant, system
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ai_model_used", sa.String(length=50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("is_edited", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_chat_messages_thread", "chat_messages", ["thread_id", "sequence_number"])
    op.create_index("idx_chat_messages_user", "chat_messages", ["user_id"])


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
    
    # Revert vehicles table changes
    op.drop_index("idx_vehicles_workshop", table_name="vehicles")
    op.drop_index("idx_vehicles_workshop_license", table_name="vehicles")
    op.drop_constraint("fk_vehicles_workshop", "vehicles", type_="foreignkey")
    op.drop_column("vehicles", "fuel_type")
    op.drop_column("vehicles", "engine_type")
    op.drop_column("vehicles", "last_service_date")
    op.drop_column("vehicles", "last_service_km")
    op.drop_column("vehicles", "current_km")
    op.drop_column("vehicles", "workshop_id")
    # Restore old unique constraint
    op.create_unique_constraint("vehicles_license_plate_key", "vehicles", ["license_plate"], type_="unique")
    
    op.drop_table("workshop_members")
    op.drop_table("workshops")

