"""Add AI providers tables

Revision ID: 0013_ai_providers
Revises: 0012_chat_thread_pdfs
Create Date: 2025-12-09 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0013_ai_providers'
down_revision: Union[str, None] = '0012_chat_thread_pdfs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create AI providers table
    op.create_table(
        'ai_providers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('api_endpoint', sa.String(500), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_tokens_per_request', sa.Integer(), nullable=True),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create workshop AI providers junction table
    op.create_table(
        'workshop_ai_providers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workshop_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workshops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ai_provider_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('custom_api_key', sa.Text(), nullable=True),
        sa.Column('custom_model', sa.String(100), nullable=True),
        sa.Column('custom_endpoint', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes
    op.create_index('ix_ai_providers_provider_type', 'ai_providers', ['provider_type'])
    op.create_index('ix_ai_providers_is_active', 'ai_providers', ['is_active'])
    op.create_index('ix_workshop_ai_providers_workshop', 'workshop_ai_providers', ['workshop_id'])
    op.create_index('ix_workshop_ai_providers_provider', 'workshop_ai_providers', ['ai_provider_id'])

    # Add unique constraint for workshop-provider combination
    op.create_unique_constraint(
        'uq_workshop_ai_provider', 
        'workshop_ai_providers', 
        ['workshop_id', 'ai_provider_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_workshop_ai_provider', 'workshop_ai_providers')
    op.drop_index('ix_workshop_ai_providers_provider')
    op.drop_index('ix_workshop_ai_providers_workshop')
    op.drop_index('ix_ai_providers_is_active')
    op.drop_index('ix_ai_providers_provider_type')
    op.drop_table('workshop_ai_providers')
    op.drop_table('ai_providers')

