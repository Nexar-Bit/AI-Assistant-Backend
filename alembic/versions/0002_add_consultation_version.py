"""Add version column to consultations for optimistic concurrency.

Revision ID: 0002_add_consultation_version
Revises: 0001_initial_schema
Create Date: 2025-12-04 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_consultation_version"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultations",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("consultations", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("consultations", "version")


