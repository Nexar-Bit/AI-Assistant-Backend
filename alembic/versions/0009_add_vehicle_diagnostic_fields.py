"""Add diagnostic tracking fields to vehicles table.

Revision ID: 0009_vehicle_diag_fields
Revises: 0008_workshop_id_multi_tenant
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_vehicle_diag_fields"
down_revision: Union[str, None] = "0008_workshop_id_multi_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add diagnostic tracking fields to vehicles table
    op.add_column(
        "vehicles",
        sa.Column(
            "total_diagnostic_sessions",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column(
            "last_diagnostic_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column(
            "common_error_codes",
            sa.String(500),
            nullable=True,
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column(
            "notes",
            sa.String(1000),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vehicles", "notes")
    op.drop_column("vehicles", "common_error_codes")
    op.drop_column("vehicles", "last_diagnostic_date")
    op.drop_column("vehicles", "total_diagnostic_sessions")

