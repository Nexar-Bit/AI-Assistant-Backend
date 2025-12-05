"""Add workshop_id to consultations and audit logs for multi-tenancy.

Revision ID: 0008_add_workshop_id_to_consultations_and_audit
Revises: 0007_add_token_accounting
Create Date: 2025-01-XX XX:XX:XX
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_workshop_id_multi_tenant"
down_revision: Union[str, None] = "0007_add_token_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add workshop_id to consultations table
    op.add_column(
        "consultations",
        sa.Column(
            "workshop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_consultations_workshop_id",
        "consultations",
        "workshops",
        ["workshop_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_consultations_workshop_id",
        "consultations",
        ["workshop_id"],
    )
    
    # Add workshop_id to consultation_pdfs table
    op.add_column(
        "consultation_pdfs",
        sa.Column(
            "workshop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_consultation_pdfs_workshop_id",
        "consultation_pdfs",
        "workshops",
        ["workshop_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_consultation_pdfs_workshop_id",
        "consultation_pdfs",
        ["workshop_id"],
    )
    
    # Add workshop_id to audit_logs table
    op.add_column(
        "audit_logs",
        sa.Column(
            "workshop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_audit_logs_workshop_id",
        "audit_logs",
        "workshops",
        ["workshop_id"],
        ["id"],
        ondelete="SET NULL",  # Keep audit logs even if workshop is deleted
    )
    op.create_index(
        "ix_audit_logs_workshop_id",
        "audit_logs",
        ["workshop_id"],
    )


def downgrade() -> None:
    # Remove workshop_id from audit_logs
    op.drop_index("ix_audit_logs_workshop_id", table_name="audit_logs")
    op.drop_constraint("fk_audit_logs_workshop_id", "audit_logs", type_="foreignkey")
    op.drop_column("audit_logs", "workshop_id")
    
    # Remove workshop_id from consultation_pdfs
    op.drop_index("ix_consultation_pdfs_workshop_id", table_name="consultation_pdfs")
    op.drop_constraint("fk_consultation_pdfs_workshop_id", "consultation_pdfs", type_="foreignkey")
    op.drop_column("consultation_pdfs", "workshop_id")
    
    # Remove workshop_id from consultations
    op.drop_index("ix_consultations_workshop_id", table_name="consultations")
    op.drop_constraint("fk_consultations_workshop_id", "consultations", type_="foreignkey")
    op.drop_column("consultations", "workshop_id")

