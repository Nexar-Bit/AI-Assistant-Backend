"""Add registration approval fields

Revision ID: 0014_registration_approval
Revises: 0013_ai_providers
Create Date: 2025-12-09 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0014_registration_approval'
down_revision: Union[str, None] = '0013_ai_providers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add registration fields to users table
    op.add_column('users', sa.Column('registration_message', sa.String(500), nullable=True))
    op.add_column('users', sa.Column('registration_approved', sa.Boolean(), default=False, server_default='false'))
    
    # Set existing users as approved
    op.execute("UPDATE users SET registration_approved = TRUE WHERE is_active = TRUE")


def downgrade() -> None:
    op.drop_column('users', 'registration_approved')
    op.drop_column('users', 'registration_message')

