"""Add missing TimestampedUUIDModel fields to AI providers tables

Revision ID: 0015_add_missing_timestamped_fields
Revises: 0014_add_registration_fields
Create Date: 2025-12-09 21:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0015_timestamped_fields'
down_revision: Union[str, None] = '0014_registration_approval'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing TimestampedUUIDModel fields to ai_providers table
    op.add_column('ai_providers', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column('ai_providers', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ai_providers', sa.Column('created_by', sa.String(length=50), nullable=True))
    op.add_column('ai_providers', sa.Column('updated_by', sa.String(length=50), nullable=True))
    op.add_column('ai_providers', sa.Column('deleted_by', sa.String(length=50), nullable=True))
    
    # Update created_at and updated_at to have server defaults
    op.alter_column('ai_providers', 'created_at',
                    server_default=sa.func.now(),
                    existing_type=sa.DateTime(timezone=True),
                    existing_nullable=False)
    op.alter_column('ai_providers', 'updated_at',
                    server_default=sa.func.now(),
                    existing_type=sa.DateTime(timezone=True),
                    existing_nullable=False)
    
    # Add missing TimestampedUUIDModel fields to workshop_ai_providers table
    op.add_column('workshop_ai_providers', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column('workshop_ai_providers', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workshop_ai_providers', sa.Column('created_by', sa.String(length=50), nullable=True))
    op.add_column('workshop_ai_providers', sa.Column('updated_by', sa.String(length=50), nullable=True))
    op.add_column('workshop_ai_providers', sa.Column('deleted_by', sa.String(length=50), nullable=True))
    
    # Update created_at and updated_at to have server defaults
    op.alter_column('workshop_ai_providers', 'created_at',
                    server_default=sa.func.now(),
                    existing_type=sa.DateTime(timezone=True),
                    existing_nullable=False)
    op.alter_column('workshop_ai_providers', 'updated_at',
                    server_default=sa.func.now(),
                    existing_type=sa.DateTime(timezone=True),
                    existing_nullable=False)


def downgrade() -> None:
    # Remove fields from workshop_ai_providers
    op.alter_column('workshop_ai_providers', 'updated_at', server_default=None)
    op.alter_column('workshop_ai_providers', 'created_at', server_default=None)
    op.drop_column('workshop_ai_providers', 'deleted_by')
    op.drop_column('workshop_ai_providers', 'updated_by')
    op.drop_column('workshop_ai_providers', 'created_by')
    op.drop_column('workshop_ai_providers', 'deleted_at')
    op.drop_column('workshop_ai_providers', 'is_deleted')
    
    # Remove fields from ai_providers
    op.alter_column('ai_providers', 'updated_at', server_default=None)
    op.alter_column('ai_providers', 'created_at', server_default=None)
    op.drop_column('ai_providers', 'deleted_by')
    op.drop_column('ai_providers', 'updated_by')
    op.drop_column('ai_providers', 'created_by')
    op.drop_column('ai_providers', 'deleted_at')
    op.drop_column('ai_providers', 'is_deleted')

