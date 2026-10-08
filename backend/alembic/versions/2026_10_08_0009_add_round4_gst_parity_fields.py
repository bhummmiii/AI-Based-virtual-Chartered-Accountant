"""Add round 4 GST parity fields: counterparty on vouchers, IRN and rejection on documents, voiding & periods on GST records.

Revision ID: 0009_round4_gst_parity_fields
Revises: 0008_add_coa_role
Create Date: 2026-10-08 12:00:00 UTC
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0009_round4_gst_parity_fields"
down_revision = "0008_add_coa_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Additive columns on journal_entries
    op.add_column("journal_entries", sa.Column("counterparty_name", sa.String(255), nullable=True))
    op.add_column("journal_entries", sa.Column("counterparty_gstin", sa.String(20), nullable=True))
    op.add_column("journal_entries", sa.Column("voucher_template", sa.String(50), nullable=True))
    op.create_index("ix_journal_entries_counterparty_gstin", "journal_entries", ["counterparty_gstin"])
    op.create_index("ix_journal_entries_voucher_template", "journal_entries", ["voucher_template"])

    # 2. Additive columns on gst_records
    op.add_column("gst_records", sa.Column("period_start", sa.Date(), nullable=True))
    op.add_column("gst_records", sa.Column("period_end", sa.Date(), nullable=True))
    op.add_column("gst_records", sa.Column("period_label", sa.String(50), nullable=True))
    op.add_column("gst_records", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("gst_records", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))

    # 3. Additive columns on uploaded_documents
    op.add_column("uploaded_documents", sa.Column("irn", sa.String(100), nullable=True))
    op.add_column("uploaded_documents", sa.Column("rejection_reason", sa.String(100), nullable=True))
    op.add_column("uploaded_documents", sa.Column("linked_document_id", UUID(as_uuid=True), sa.ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_uploaded_documents_irn", "uploaded_documents", ["irn"])
    op.create_index("ix_uploaded_documents_linked_doc", "uploaded_documents", ["linked_document_id"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_documents_linked_doc", table_name="uploaded_documents")
    op.drop_index("ix_uploaded_documents_irn", table_name="uploaded_documents")
    op.drop_column("uploaded_documents", "linked_document_id")
    op.drop_column("uploaded_documents", "rejection_reason")
    op.drop_column("uploaded_documents", "irn")

    op.drop_column("gst_records", "voided_at")
    op.drop_column("gst_records", "void_reason")
    op.drop_column("gst_records", "period_label")
    op.drop_column("gst_records", "period_end")
    op.drop_column("gst_records", "period_start")

    op.drop_index("ix_journal_entries_voucher_template", table_name="journal_entries")
    op.drop_index("ix_journal_entries_counterparty_gstin", table_name="journal_entries")
    op.drop_column("journal_entries", "voucher_template")
    op.drop_column("journal_entries", "counterparty_gstin")
    op.drop_column("journal_entries", "counterparty_name")
