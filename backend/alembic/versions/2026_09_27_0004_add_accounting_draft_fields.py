"""Add document_id, status, and reference_number to accounting_records

Revision ID: 0004_add_accounting_draft_fields
Revises: 0003_add_uploaded_documents
Create Date: 2026-09-27 00:00:00 UTC

Adds document_id (FK to uploaded_documents), status, and reference_number
to the accounting_records table to support the Verified Document -> Accounting Draft bridge.
Preserves all existing data with safe defaults (status defaults to 'draft').
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004_add_accounting_draft_fields"
down_revision = "0003_add_uploaded_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add document_id column with foreign key to uploaded_documents
    op.add_column(
        "accounting_records",
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("uploaded_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    
    # 2. Add status column ('draft' | 'posted') with default 'draft'
    op.add_column(
        "accounting_records",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
    )
    
    # 3. Add reference_number column (e.g. invoice/bill number)
    op.add_column(
        "accounting_records",
        sa.Column(
            "reference_number",
            sa.String(100),
            nullable=True,
        ),
    )

    # 4. Create indexes for performance and querying
    op.create_index(
        "ix_accounting_records_document_id",
        "accounting_records",
        ["document_id"],
    )
    op.create_index(
        "ix_accounting_records_status",
        "accounting_records",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_accounting_records_status", table_name="accounting_records")
    op.drop_index("ix_accounting_records_document_id", table_name="accounting_records")
    op.drop_column("accounting_records", "reference_number")
    op.drop_column("accounting_records", "status")
    op.drop_column("accounting_records", "document_id")
