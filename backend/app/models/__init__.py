"""
Models package — register ALL models so Alembic autogenerate
and Base.metadata.create_all() discover every table.

Tables (10):
  users               — CA login & profile
  clients             — Client business profiles
  accounting_records  — Double-entry ledger transactions
  gst_records         — GST filing records
  tax_records         — Income tax / TDS records
  audit_reports       — Audit findings & recommendations
  invoices            — Client invoices with OCR support
  documents           — Uploaded files
  government_rules    — Scraped government notifications
  notifications       — In-app user notifications
"""

from app.models.user import User
from app.models.client import Client
from app.models.accounting_record import AccountingRecord
from app.models.gst_record import GSTRecord
from app.models.tax_record import TaxRecord
from app.models.audit_report import AuditReport
from app.models.invoice import Invoice
from app.models.document import Document
from app.models.government_rule import GovernmentRule
from app.models.notification import Notification
from app.models.uploaded_document import UploadedDocument
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_period import AccountingPeriod

__all__ = [
    "User", "Client", "AccountingRecord", "GSTRecord", "TaxRecord",
    "AuditReport", "Invoice", "Document", "GovernmentRule", "Notification",
    "UploadedDocument", "ChartOfAccounts", "JournalEntry", "JournalEntryLine",
    "AccountingPeriod",
]

