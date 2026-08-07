"""Add uploaded_documents table for Invoice module document categories

Revision ID: 0003_add_uploaded_documents
Revises: 0002_add_client_extended_fields
Create Date: 2026-08-05 00:00:00 UTC

Creates the uploaded_documents table supporting all 13 GST document categories.
No existing data is modified.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_add_uploaded_documents"
down_revision = "0002_add_client_extended_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Classification
        sa.Column("document_category", sa.String(50), nullable=False),
        sa.Column(
            "document_type", sa.String(20), nullable=False, server_default="upload"
        ),
        sa.Column("invoice_type", sa.String(30), nullable=True),
        # Core invoice fields
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("gstin", sa.String(20), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("customer", sa.String(255), nullable=True),
        sa.Column("invoice_date", sa.String(20), nullable=True),
        # Financial fields
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("taxable_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("cgst", sa.Numeric(15, 2), nullable=True),
        sa.Column("sgst", sa.Numeric(15, 2), nullable=True),
        sa.Column("igst", sa.Numeric(15, 2), nullable=True),
        sa.Column("cess", sa.Numeric(15, 2), nullable=True),
        sa.Column("hsn", sa.String(50), nullable=True),
        # GST return fields
        sa.Column("gst_return_type", sa.String(20), nullable=True),
        sa.Column("financial_year", sa.String(10), nullable=True),
        sa.Column("month", sa.String(20), nullable=True),
        sa.Column("filed_date", sa.String(20), nullable=True),
        sa.Column("arn", sa.String(50), nullable=True),
        # Notice fields
        sa.Column("notice_number", sa.String(100), nullable=True),
        sa.Column("notice_date", sa.String(20), nullable=True),
        sa.Column("response_due_date", sa.String(20), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),
        # File storage
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("file_size", sa.String(20), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        # OCR
        sa.Column("ocr_status", sa.String(20), nullable=True, server_default="pending"),
        sa.Column("ocr_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        # Status & meta
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("uploaded_by", sa.String(255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_uploaded_documents_id", "uploaded_documents", ["id"])
    op.create_index(
        "ix_uploaded_doc_client_cat",
        "uploaded_documents",
        ["client_id", "document_category"],
    )
    op.create_index("ix_uploaded_doc_gstin", "uploaded_documents", ["gstin"])
    op.create_index(
        "ix_uploaded_doc_invoice_number", "uploaded_documents", ["invoice_number"]
    )
    op.create_index("ix_uploaded_doc_status", "uploaded_documents", ["status"])


def downgrade() -> None:
    op.drop_table("uploaded_documents")
