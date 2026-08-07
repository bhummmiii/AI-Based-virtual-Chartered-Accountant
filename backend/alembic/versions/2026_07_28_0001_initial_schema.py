"""Initial schema — 10 tables with UUID primary keys

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-28 00:00:00 UTC

Tables created:
  users, clients, accounting_records, gst_records, tax_records,
  audit_reports, invoices, documents, government_rules, notifications
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── 1. users ──────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="ca"),
        sa.Column("profile_image", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── 2. clients ─────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("client_code", sa.String(50), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column(
            "client_type", sa.String(50), nullable=False, server_default="company"
        ),
        sa.Column("contact_person", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("gst_number", sa.String(20), nullable=True),
        sa.Column("pan_number", sa.String(15), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True, server_default="India"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
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
    op.create_index("ix_clients_id", "clients", ["id"])
    op.create_index("ix_clients_client_code", "clients", ["client_code"], unique=True)
    op.create_index("ix_clients_company_name", "clients", ["company_name"])
    op.create_index("ix_clients_gst_number", "clients", ["gst_number"])
    op.create_index("ix_clients_pan_number", "clients", ["pan_number"])
    op.create_index("ix_clients_status_risk", "clients", ["status", "risk_level"])
    op.create_index("ix_clients_gst_pan", "clients", ["gst_number", "pan_number"])

    # ── 3. accounting_records ──────────────────────────────────
    op.create_table(
        "accounting_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("voucher_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("debit", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_accounting_records_id", "accounting_records", ["id"])
    op.create_index(
        "ix_accounting_client_date",
        "accounting_records",
        ["client_id", "transaction_date"],
    )
    op.create_index(
        "ix_accounting_voucher_type", "accounting_records", ["voucher_type"]
    )

    # ── 4. gst_records ─────────────────────────────────────────
    op.create_table(
        "gst_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gst_period", sa.String(20), nullable=False),
        sa.Column("gst_type", sa.String(30), nullable=False, server_default="GSTR-3B"),
        sa.Column(
            "taxable_amount", sa.Numeric(15, 2), nullable=False, server_default="0"
        ),
        sa.Column("cgst", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("sgst", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("igst", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total_tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column(
            "filing_status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_gst_records_id", "gst_records", ["id"])
    op.create_index("ix_gst_client_period", "gst_records", ["client_id", "gst_period"])
    op.create_index("ix_gst_filing_status", "gst_records", ["filing_status"])

    # ── 5. tax_records ─────────────────────────────────────────
    op.create_table(
        "tax_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("financial_year", sa.String(10), nullable=False),
        sa.Column("tax_type", sa.String(50), nullable=False),
        sa.Column(
            "taxable_income", sa.Numeric(15, 2), nullable=False, server_default="0"
        ),
        sa.Column("tds", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("advance_tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total_tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tax_records_id", "tax_records", ["id"])
    op.create_index("ix_tax_client_fy", "tax_records", ["client_id", "financial_year"])
    op.create_index("ix_tax_status", "tax_records", ["status"])

    # ── 6. audit_reports ───────────────────────────────────────
    op.create_table(
        "audit_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audit_type", sa.String(50), nullable=False),
        sa.Column(
            "audit_status", sa.String(30), nullable=False, server_default="pending"
        ),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_reports_id", "audit_reports", ["id"])
    op.create_index(
        "ix_audit_client_status", "audit_reports", ["client_id", "audit_status"]
    )
    op.create_index("ix_audit_type", "audit_reports", ["audit_type"])

    # ── 7. invoices ────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_invoices_id", "invoices", ["id"])
    op.create_index("ix_invoice_client_date", "invoices", ["client_id", "invoice_date"])
    op.create_index("ix_invoice_number", "invoices", ["invoice_number"])

    # ── 8. documents ───────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_id", "documents", ["id"])
    op.create_index("ix_document_client_type", "documents", ["client_id", "file_type"])

    # ── 9. government_rules ────────────────────────────────────
    op.create_table(
        "government_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_government_rules_id", "government_rules", ["id"])
    op.create_index("ix_gov_rules_category", "government_rules", ["category"])
    op.create_index(
        "ix_gov_rules_category_date", "government_rules", ["category", "published_date"]
    )

    # ── 10. notifications ──────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index(
        "ix_notification_user_read", "notifications", ["user_id", "is_read"]
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("government_rules")
    op.drop_table("documents")
    op.drop_table("invoices")
    op.drop_table("audit_reports")
    op.drop_table("tax_records")
    op.drop_table("gst_records")
    op.drop_table("accounting_records")
    op.drop_table("clients")
    op.drop_table("users")
