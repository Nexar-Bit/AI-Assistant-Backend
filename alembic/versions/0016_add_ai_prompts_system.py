"""Add AI prompts system

Revision ID: 0016_ai_prompts
Revises: 0015_timestamped_fields
Create Date: 2025-12-09 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0016_ai_prompts'
down_revision: Union[str, None] = '0015_timestamped_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create global_prompts table
    op.create_table(
        'global_prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column('version', sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=50), nullable=True),
        sa.Column('updated_by', sa.String(length=50), nullable=True),
        sa.Column('deleted_by', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add workshop_prompt field to workshops table
    op.add_column('workshops', sa.Column('workshop_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove workshop_prompt field from workshops
    op.drop_column('workshops', 'workshop_prompt')
    
    # Drop global_prompts table
    op.drop_table('global_prompts')

