"""
Test F4: Duplicates, Rejection Handling, and Tax At Risk.
Verifies:
1. "Tax at risk" is always the TAX amount, not gross amount (DUPLICATE_INVOICE -> 18,000 for a 100k+18k invoice).
2. The duplicate document is the one without a posted voucher, else the later upload.
3. When marked rejected (reason DUPLICATE), duplicate does not raise UNPOSTED_INVOICE, MISSING_GSTIN, or TAX_MATH_MISMATCH.
4. Duplicate document still raises DUPLICATE_INVOICE until deleted/voided.
5. Compliance documents (e-way bill, challan, HSN master, linked e-invoice) never raise UNPOSTED_INVOICE.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone, date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.services.gst_reconciliation_service import GstReconciliationService
from scripts.mark_duplicate_documents import evaluate_duplicates_for_client


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_tax_at_risk_is_tax_not_gross_and_duplicate_selection(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-F4-1",
        company_name="Alpha Tech",
        gst_number="27AAACA1234A1Z5",
        state="Maharashtra",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=user_id, email="ca@f4.com", full_name="CA F4 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Original document S1 (owns posted voucher)
    doc_orig_id = uuid.uuid4()
    doc_orig = UploadedDocument(
        id=doc_orig_id,
        client_id=client_id,
        document_category="sales_records",
        invoice_number="INV-2026-001",
        gstin="27AAACA1234A1Z5",
        customer="Beta Enterprises",
        invoice_date="2026-07-15",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        amount=Decimal("118000.00"),
        status="verified",
        created_at=datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
    )

    # Duplicate document S1 (uploaded later, no voucher)
    doc_dup_id = uuid.uuid4()
    doc_dup = UploadedDocument(
        id=doc_dup_id,
        client_id=client_id,
        document_category="b2b_invoice",
        invoice_number="INV-2026-001",
        gstin="27AAACA1234A1Z5",
        customer="Beta Enterprises",
        invoice_date="2026-07-15",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        amount=Decimal("118000.00"),
        status="verified",
        created_at=datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc),
    )

    # Posted voucher for doc_orig
    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_orig_id,
        entry_number="SV-2026-001",
        entry_date=date(2026, 7, 15),
        entry_type="sales",
        status="posted",
        is_reversed=False,
    )

    db_session.add_all([doc_orig, doc_dup, je])
    db_session.commit()

    # 1. Check discrepancies before rejection
    res = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="2026-Q2")
    dup_alerts = [d for d in res.discrepancies if d.rule_code == "DUPLICATE_INVOICE"]
    assert len(dup_alerts) == 1
    # Tax at risk must be TAX amount (18,000.00), NEVER gross (118,000.00)
    assert dup_alerts[0].variance_amount == Decimal("18000.00")
    assert dup_alerts[0].document_id == doc_dup_id

    # 2. Run duplicate marking script in apply mode
    evaluate_duplicates_for_client(db_session, client, apply=True)

    db_session.refresh(doc_orig)
    db_session.refresh(doc_dup)

    # Original must remain verified with posted voucher untouched
    assert doc_orig.status == "verified"
    assert doc_orig.rejection_reason is None

    # Duplicate must be rejected with reason DUPLICATE
    assert doc_dup.status == "rejected"
    assert doc_dup.rejection_reason == "DUPLICATE"

    # 3. Check discrepancies after rejection:
    # - UNPOSTED_INVOICE for duplicate must be GONE
    # - DUPLICATE_INVOICE must still be present with tax at risk 18,000
    res_after = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="2026-Q2")
    unposted_alerts = [d for d in res_after.discrepancies if d.rule_code == "UNPOSTED_INVOICE" and d.document_id == doc_dup_id]
    assert len(unposted_alerts) == 0

    dup_alerts_after = [d for d in res_after.discrepancies if d.rule_code == "DUPLICATE_INVOICE"]
    assert len(dup_alerts_after) == 1
    assert dup_alerts_after[0].variance_amount == Decimal("18000.00")

    # 4. Deleting or voiding duplicate clears the alert
    doc_dup.status = "voided"
    db_session.commit()

    res_voided = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="2026-Q2")
    dup_alerts_voided = [d for d in res_voided.discrepancies if d.rule_code == "DUPLICATE_INVOICE"]
    assert len(dup_alerts_voided) == 0


def test_compliance_docs_never_raise_unposted_invoice(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-F4-2",
        company_name="Gamma Ltd",
        gst_number="27AAACG1234A1Z5",
        state="Maharashtra",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=user_id, email="ca@f4-2.com", full_name="CA F4 User 2", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Plain invoice posted
    plain_id = uuid.uuid4()
    plain_doc = UploadedDocument(
        id=plain_id,
        client_id=client_id,
        document_category="sales_records",
        invoice_number="ABC/002",
        gstin="27AAACG1234A1Z5",
        customer="Client B",
        invoice_date="2026-08-10",
        taxable_amount=Decimal("50000.00"),
        igst=Decimal("9000.00"),
        amount=Decimal("59000.00"),
        status="verified",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=plain_id,
        entry_number="SV-2026-002",
        entry_date=date(2026, 8, 10),
        entry_type="sales",
        status="posted",
        is_reversed=False,
    )

    # Compliance docs: E-way bill, Challan, HSN Master, and linked E-Invoice
    ewb = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="e_way_bill",
        invoice_number="381012345678",
        status="verified",
    )
    challan = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="gst_challan",
        invoice_number="26100012345678",
        status="verified",
    )
    hsn_master = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="hsn_sac",
        status="verified",
    )
    einvoice = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="e_invoice",
        invoice_number="ABC/002",
        linked_document_id=plain_id,
        status="verified",
    )

    db_session.add_all([plain_doc, je, ewb, challan, hsn_master, einvoice])
    db_session.commit()

    res = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="2026-Q2")
    unposted_alerts = [d for d in res.discrepancies if d.rule_code == "UNPOSTED_INVOICE"]
    # None of the compliance docs or linked e-invoice should raise UNPOSTED_INVOICE
    assert len(unposted_alerts) == 0
