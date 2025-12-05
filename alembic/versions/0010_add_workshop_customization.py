"""Add workshop customization fields.

Revision ID: 0010_workshop_customization
Revises: 0009_vehicle_diag_fields
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_workshop_customization"
down_revision: Union[str, None] = "0009_vehicle_diag_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add customization JSONB fields to workshops table
    op.add_column(
        "workshops",
        sa.Column(
            "vehicle_templates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "workshops",
        sa.Column(
            "quick_replies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "workshops",
        sa.Column(
            "diagnostic_code_library",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workshops", "diagnostic_code_library")
    op.drop_column("workshops", "quick_replies")
    op.drop_column("workshops", "vehicle_templates")

