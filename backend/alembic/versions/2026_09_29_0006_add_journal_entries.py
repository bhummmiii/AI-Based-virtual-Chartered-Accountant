"""Create journal_entries and journal_entry_lines tables

Revision ID: 0006_add_journal_entries
Revises: 0005_add_chart_of_accounts
Create Date: 2026-09-29 00:00:00 UTC

Adds persistent, double-entry journal tables:
- journal_entries: Transaction header with UUID PK, client isolation, balance check constraint, audit fields
- journal_entry_lines: Multi-leg line items linked to chart_of_accounts.id with single-sided Dr/Cr check constraints
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0006_add_journal_entries"
down_revision = "0005_add_chart_of_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create journal_entries table ───────────────────────
    op.create_table(
        "journal_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "accounting_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounting_records.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("uploaded_documents.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("entry_number", sa.String(50), nullable=False, index=True),
        sa.Column("entry_date", sa.Date(), nullable=False, index=True),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True, index=True),
        sa.Column("total_debit", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
        sa.Column("total_credit", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
        sa.Column("is_balanced", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "posted_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_reversed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "reversal_entry_id",
            UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("client_id", "entry_number", name="uq_journal_entry_client_number"),
        sa.UniqueConstraint("accounting_record_id", name="uq_journal_entry_accounting_record"),
        sa.CheckConstraint("total_debit >= 0 AND total_credit >= 0", name="chk_journal_entry_non_negative"),
        sa.CheckConstraint("total_debit = total_credit", name="chk_journal_entry_balanced"),
    )

    op.create_index("ix_journal_client_date", "journal_entries", ["client_id", "entry_date"])
    op.create_index("ix_journal_client_type", "journal_entries", ["client_id", "entry_type"])
    op.create_index("ix_journal_status", "journal_entries", ["status"])

    # ── 2. Create journal_entry_lines table ───────────────────
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "journal_entry_id",
            UUID(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("debit_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
        sa.Column("credit_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("party_name", sa.String(255), nullable=True),
        sa.Column("party_gstin", sa.String(20), nullable=True),
        sa.Column("tax_head", sa.String(20), nullable=True),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_line_entry_seq"),
        sa.CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="chk_journal_line_non_negative"),
        sa.CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="chk_journal_line_single_sided",
        ),
    )

    op.create_index("ix_journal_lines_account_id", "journal_entry_lines", ["account_id"])
    op.create_index("ix_journal_lines_tax_head", "journal_entry_lines", ["tax_head"])


def downgrade() -> None:
    op.drop_index("ix_journal_lines_tax_head", table_name="journal_entry_lines")
    op.drop_index("ix_journal_lines_account_id", table_name="journal_entry_lines")
    op.drop_table("journal_entry_lines")

    op.drop_index("ix_journal_status", table_name="journal_entries")
    op.drop_index("ix_journal_client_type", table_name="journal_entries")
    op.drop_index("ix_journal_client_date", table_name="journal_entries")
    op.drop_table("journal_entries")
