"""
Focused test suite for Verified Document -> Accounting Draft Bridge.

Tests:
1. Transaction mapping for sales, purchases, credit notes, debit notes, tax payments.
2. Exclusion of informational documents (notices, returns, lists, e-way bills).
3. Data validation (unverified rejection, amount validation, party validation, flexible date parsing).
4. Duplicate prevention and idempotency (in-place draft updates on document re-verification).
5. Explicit posting to ledger and protection of posted records.
6. Preservation of standard accounting records behavior.
"""

import sys
import os
import uuid
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.services.accounting_draft_service import (
    AccountingDraftService,
    parse_flexible_date,
    FINANCIAL_CATEGORIES,
    INFORMATIONAL_CATEGORIES,
)
from app.schemas.accounting import AccountingRecordResponse


# ── 1. Date Parsing Tests ──────────────────────────────────────────────

def test_parse_flexible_date():
    fallback = datetime(2026, 4, 15, 10, 30, tzinfo=timezone.utc)
    
    assert parse_flexible_date("2026-03-31", fallback) == date(2026, 3, 31)
    assert parse_flexible_date("15/04/2026", fallback) == date(2026, 4, 15)
    assert parse_flexible_date("01-05-2026", fallback) == date(2026, 5, 1)
    assert parse_flexible_date("2026/06/20", fallback) == date(2026, 6, 20)
    assert parse_flexible_date("15-Mar-2026", fallback) == date(2026, 3, 15)
    assert parse_flexible_date(None, fallback) == date(2026, 4, 15)
    assert parse_flexible_date("", fallback) == date(2026, 4, 15)


# ── 2. Validation & Informational Document Exclusion Tests ────────────

def test_informational_documents_are_excluded():
    for cat in INFORMATIONAL_CATEGORIES:
        doc = UploadedDocument(
            id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            document_category=cat,
            status="verified",
            amount=Decimal("15000.00"),
            vendor="Tax Authority",
            invoice_date="2026-03-10",
        )
        val = AccountingDraftService.validate_document(doc)
        assert not val.eligible
        assert val.status == "informational_skipped"
        assert "informational" in val.reason.lower()


def test_unverified_document_is_rejected():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="purchase_records",
        status="pending",  # Not verified!
        amount=Decimal("5000.00"),
        vendor="Hardware Supplies Ltd",
        invoice_date="2026-03-10",
    )
    val = AccountingDraftService.validate_document(doc)
    assert not val.eligible
    assert val.status == "unverified"
    assert "must be verified" in val.reason


def test_missing_or_zero_amount_rejected():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="sales_records",
        status="verified",
        amount=Decimal("0.00"),
        customer="Apex Enterprises",
        invoice_date="2026-03-10",
    )
    val = AccountingDraftService.validate_document(doc)
    assert not val.eligible
    assert val.status == "validation_error"
    assert "greater than 0" in val.reason


def test_missing_party_rejected_for_commercial_invoices():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="sales_records",
        status="verified",
        amount=Decimal("12000.00"),
        customer=None,
        vendor=None,
        invoice_date="2026-03-10",
    )
    val = AccountingDraftService.validate_document(doc)
    assert not val.eligible
    assert val.status == "validation_error"
    assert "Party name" in val.reason


# ── 3. Transaction Mapping Tests ───────────────────────────────────────

def test_sales_record_mapping():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="sales_records",
        status="verified",
        invoice_number="INV-2026-001",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Apex Retailers Ltd",
        invoice_date="2026-03-15",
    )
    fields = AccountingDraftService.map_document_to_record_fields(doc)
    assert fields["voucher_type"] == "sales"
    assert fields["category"] == "sales"
    assert fields["credit"] == Decimal("23600.00")
    assert fields["debit"] == Decimal("0.00")
    assert fields["reference_number"] == "INV-2026-001"
    assert fields["status"] == "draft"
    assert "Apex Retailers Ltd" in fields["description"]
    assert "Taxable: ₹20000.00" in fields["description"]


def test_purchase_record_mapping():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="purchase_records",
        status="verified",
        invoice_number="BILL-9988",
        amount=Decimal("5900.00"),
        vendor="FastLogistics Pvt Ltd",
        invoice_date="2026-03-20",
    )
    fields = AccountingDraftService.map_document_to_record_fields(doc)
    assert fields["voucher_type"] == "purchase"
    assert fields["category"] == "purchase"
    assert fields["debit"] == Decimal("5900.00")
    assert fields["credit"] == Decimal("0.00")
    assert fields["reference_number"] == "BILL-9988"
    assert fields["status"] == "draft"
    assert "FastLogistics Pvt Ltd" in fields["description"]


def test_credit_note_mapping():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="credit_note",
        status="verified",
        invoice_number="CN-104",
        amount=Decimal("1180.00"),
        customer="Apex Retailers Ltd",
        invoice_date="2026-03-22",
    )
    fields = AccountingDraftService.map_document_to_record_fields(doc)
    assert fields["voucher_type"] == "journal"
    assert fields["category"] == "credit_note"
    assert fields["debit"] == Decimal("1180.00")
    assert fields["credit"] == Decimal("0.00")


def test_debit_note_mapping():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="debit_note",
        status="verified",
        invoice_number="DN-55",
        amount=Decimal("2000.00"),
        vendor="Global Raw Materials",
        invoice_date="2026-03-23",
    )
    fields = AccountingDraftService.map_document_to_record_fields(doc)
    assert fields["voucher_type"] == "journal"
    assert fields["category"] == "debit_note"
    assert fields["credit"] == Decimal("2000.00")
    assert fields["debit"] == Decimal("0.00")


def test_gst_challan_mapping():
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        document_category="gst_challan",
        status="verified",
        arn="CPIN2603991827",
        amount=Decimal("45000.00"),
        invoice_date="2026-03-25",
    )
    fields = AccountingDraftService.map_document_to_record_fields(doc)
    assert fields["voucher_type"] == "payment"
    assert fields["category"] == "tax"
    assert fields["debit"] == Decimal("45000.00")
    assert fields["credit"] == Decimal("0.00")
    assert fields["reference_number"] == "CPIN2603991827"


# ── 4. Duplicate Prevention & Idempotency Tests ───────────────────────

def test_duplicate_prevention_on_posted_record():
    doc_id = uuid.uuid4()
    mock_doc = UploadedDocument(
        id=doc_id,
        client_id=uuid.uuid4(),
        document_category="sales_records",
        status="verified",
        amount=Decimal("10000.00"),
        customer="Test Customer",
        invoice_date="2026-03-10",
    )
    # Existing record is already posted
    existing_record = AccountingRecord(
        id=uuid.uuid4(),
        client_id=mock_doc.client_id,
        document_id=doc_id,
        status="posted",
        voucher_type="sales",
        debit=Decimal("0"),
        credit=Decimal("10000.00"),
        transaction_date=date(2026, 3, 10),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_doc, existing_record]

    resp = AccountingDraftService.generate_or_update_draft(mock_db, doc_id)
    assert resp.status == "error"
    assert resp.validation.status == "already_posted"
    assert "already been posted" in resp.message
    # No new record added
    mock_db.add.assert_not_called()


def test_idempotent_draft_update():
    doc_id = uuid.uuid4()
    client_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    mock_doc = UploadedDocument(
        id=doc_id,
        client_id=client_id,
        document_category="purchase_records",
        status="verified",
        invoice_number="INV-UPDATED",
        amount=Decimal("7500.00"),  # Edited amount
        vendor="Updated Vendor",
        invoice_date="2026-03-12",
    )
    # Existing unposted draft
    existing_draft = AccountingRecord(
        id=draft_id,
        client_id=client_id,
        document_id=doc_id,
        status="draft",
        voucher_type="purchase",
        debit=Decimal("5000.00"),  # Old amount
        credit=Decimal("0.00"),
        transaction_date=date(2026, 3, 10),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_doc, existing_draft]

    resp = AccountingDraftService.generate_or_update_draft(mock_db, doc_id)
    assert resp.status == "updated"
    assert existing_draft.debit == Decimal("7500.00")
    assert existing_draft.reference_number == "INV-UPDATED"
    mock_db.commit.assert_called_once()
    mock_db.add.assert_not_called()


# ── 5. Explicit Ledger Posting Tests ──────────────────────────────────

def test_explicit_post_draft_to_ledger():
    draft_id = uuid.uuid4()
    mock_record = AccountingRecord(
        id=draft_id,
        client_id=uuid.uuid4(),
        status="draft",
        voucher_type="sales",
        debit=Decimal("0"),
        credit=Decimal("15000.00"),
        transaction_date=date(2026, 3, 15),
        description="Draft entry",
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_record

    resp = AccountingDraftService.post_draft_to_ledger(mock_db, draft_id)
    assert resp.success
    assert mock_record.status == "posted"
    assert "Posted:" in mock_record.description
    mock_db.commit.assert_called_once()


def test_cannot_delete_posted_record():
    draft_id = uuid.uuid4()
    mock_record = AccountingRecord(
        id=draft_id,
        client_id=uuid.uuid4(),
        status="posted",
        voucher_type="sales",
        debit=Decimal("0"),
        credit=Decimal("1000.00"),
        transaction_date=date(2026, 3, 15),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_record

    success, msg = AccountingDraftService.delete_draft(mock_db, draft_id)
    assert not success
    assert "Cannot delete a posted" in msg
    mock_db.delete.assert_not_called()


# ── 6. Preservation of Existing AccountingRecord Behavior ─────────────

def test_accounting_record_backward_compatibility():
    record_id = uuid.uuid4()
    client_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Legacy record without document_id or explicit status
    legacy_record = AccountingRecord(
        id=record_id,
        client_id=client_id,
        transaction_date=date(2026, 2, 1),
        voucher_type="journal",
        description="Legacy adjustment entry",
        debit=Decimal("1000.00"),
        credit=Decimal("1000.00"),
        category="misc",
        created_at=now,
    )

    # Validate against Pydantic schema
    resp = AccountingRecordResponse.model_validate(legacy_record)
    assert resp.id == record_id
    assert resp.client_id == client_id
    assert resp.document_id is None
    assert resp.status == "draft"
    assert resp.debit == Decimal("1000.00")
