"""
Unit & Integration Tests for Commit D5:
1. GSTR-1 Schema Contract:
   - Gstr1ReconciliationResponse contains debit_notes_summary alongside credit_notes_summary, b2b_summary, etc.
   - reconcile_gstr1 correctly populates debit_notes_summary for outward debit notes.
2. Discrepancy Tax-at-Risk Rule (R5):
   - detect_discrepancies returns variance_amount strictly equal to doc_tax (tax at risk), never gross amount.
3. AccountingRecord / JournalEntry Post Mapping:
   - Documents with a posted AccountingRecord or JournalEntry do not trigger UNPOSTED_INVOICE discrepancy.
4. Needs Review / Blocked Documents Discrepancy:
   - Documents in 'needs_review' or 'blocked' status are flagged with rule NEEDS_REVIEW and variance_amount == doc_tax.
"""

import uuid
import json
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.user import User
from app.models.client import Client
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_period import AccountingPeriod
from app.models.gst_record import GSTRecord

from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.accounting_draft_service import AccountingDraftService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.schemas.gst_reconciliation import Gstr1ReconciliationResponse


@pytest.fixture
def db_session():
    """In-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Client.__table__,
            ChartOfAccounts.__table__,
            UploadedDocument.__table__,
            AccountingRecord.__table__,
            JournalEntry.__table__,
            JournalEntryLine.__table__,
            AccountingPeriod.__table__,
            GSTRecord.__table__,
        ],
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def setup_d5(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="ca_auditor@finledger.ai",
        full_name="CA Auditor",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Apex Logistics Ltd",
        client_code="APX-101",
        contact_person="Finance Controller",
        client_type="company",
        gst_number="27AAACA9999A1Z1",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return user, client


def test_gstr1_response_has_debit_notes_summary(db_session, setup_d5):
    """Ensure Gstr1ReconciliationResponse schema and service populate debit_notes_summary."""
    user, client = setup_d5

    # 1. B2B Sales Invoice
    doc_inv = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="inv_001.pdf",
        document_category="b2b_invoice",
        invoice_type="sales",
        invoice_number="INV/2026/001",
        invoice_date="2026-08-01",
        customer="Client Buyer Pvt Ltd",
        gstin="27AABCB2222B1Z2",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "27AABCB2222B1Z2"},
                "taxable_amount": {"value": 10000.0},
                "cgst_amount": {"value": 900.0},
                "sgst_amount": {"value": 900.0},
                "place_of_supply_code": {"value": "27"},
            }
        }),
    )
    # 2. Credit Note
    doc_cn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="cn_001.pdf",
        document_category="credit_note",
        invoice_type="sales",
        invoice_number="CN/2026/001",
        invoice_date="2026-08-05",
        customer="Client Buyer Pvt Ltd",
        gstin="27AABCB2222B1Z2",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        applies_to="SALES",
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "27AABCB2222B1Z2"},
                "taxable_amount": {"value": 1000.0},
                "cgst_amount": {"value": 90.0},
                "sgst_amount": {"value": 90.0},
                "place_of_supply_code": {"value": "27"},
            }
        }),
    )
    # 3. Debit Note
    doc_dn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="dn_001.pdf",
        document_category="debit_note",
        invoice_type="sales",
        invoice_number="DN/2026/001",
        invoice_date="2026-08-10",
        customer="Client Buyer Pvt Ltd",
        gstin="27AABCB2222B1Z2",
        amount=Decimal("2360.00"),
        taxable_amount=Decimal("2000.00"),
        cgst=Decimal("180.00"),
        sgst=Decimal("180.00"),
        applies_to="SALES",
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "27AABCB2222B1Z2"},
                "taxable_amount": {"value": 2000.0},
                "cgst_amount": {"value": 180.0},
                "sgst_amount": {"value": 180.0},
                "place_of_supply_code": {"value": "27"},
            }
        }),
    )
    db_session.add_all([doc_inv, doc_cn, doc_dn])
    db_session.flush()

    # Post drafts to ledger so they are eligible for GSTR-1
    for doc in [doc_inv, doc_cn, doc_dn]:
        d_res = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
        assert d_res.status in ("created", "updated")
        p_res = AccountingDraftService.post_draft_to_ledger(db_session, d_res.record.id, user)
        assert p_res.success is True

    response: Gstr1ReconciliationResponse = GstReconciliationService.reconcile_gstr1(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    assert hasattr(response, "debit_notes_summary")
    assert response.debit_notes_summary is not None
    assert response.debit_notes_summary.invoice_count == 1
    assert response.debit_notes_summary.taxable_amount == Decimal("2000.00")
    assert response.debit_notes_summary.total_tax == Decimal("360.00")

    assert response.credit_notes_summary is not None
    assert response.credit_notes_summary.invoice_count == 1
    # Credit notes are stored with negative sign in GSTR-1 section calculation
    assert response.credit_notes_summary.taxable_amount == Decimal("-1000.00")
    assert response.credit_notes_summary.total_tax == Decimal("-180.00")

    assert response.b2b_summary.invoice_count == 1
    assert response.b2b_summary.taxable_amount == Decimal("10000.00")


def test_detect_discrepancies_variance_is_tax_at_risk_not_gross(db_session, setup_d5):
    """Rule R5: Discrepancy variance_amount must strictly be tax at risk (doc_tax), never gross."""
    user, client = setup_d5

    # Document missing GSTIN on B2B
    doc_no_gstin = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="b2b_no_gstin.pdf",
        document_category="b2b_invoice",
        invoice_type="sales",
        invoice_number="INV/2026/999",
        invoice_date="2026-08-15",
        customer="Corporate Enterprises Ltd",
        gstin=None,  # Missing GSTIN!
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        status="verified",
    )
    db_session.add(doc_no_gstin)
    db_session.flush()

    report = GstReconciliationService.detect_discrepancies(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    # Missing GSTIN discrepancy
    missing_gstin_disc = next((d for d in report.discrepancies if d.rule_code == "MISSING_GSTIN"), None)
    assert missing_gstin_disc is not None
    # Tax at risk must be 18000.00, NOT 118000.00
    assert missing_gstin_disc.variance_amount == Decimal("18000.00")
    assert missing_gstin_disc.variance_amount != Decimal("118000.00")


def test_detect_discrepancies_posted_accounting_record_prevents_unposted_invoice(db_session, setup_d5):
    """Document with a posted AccountingRecord must not trigger UNPOSTED_INVOICE."""
    user, client = setup_d5

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="posted_rec_doc.pdf",
        document_category="b2b_invoice",
        invoice_type="sales",
        invoice_number="INV/POSTED/001",
        invoice_date="2026-08-18",
        customer="Valid Corp Ltd",
        gstin="27AAACB1111B1Z3",
        amount=Decimal("59000.00"),
        taxable_amount=Decimal("50000.00"),
        cgst=Decimal("4500.00"),
        sgst=Decimal("4500.00"),
        status="verified",
    )
    db_session.add(doc)
    db_session.flush()

    # Create posted AccountingRecord referencing this document
    rec = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        voucher_type="sales",
        transaction_date=date(2026, 8, 18),
        debit=Decimal("59000.00"),
        credit=Decimal("0.00"),
        description="Posted sales record",
        status="posted",
    )
    db_session.add(rec)
    db_session.flush()

    report = GstReconciliationService.detect_discrepancies(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    unposted_disc = [d for d in report.discrepancies if d.rule_code == "UNPOSTED_INVOICE" and d.document_id == doc.id]
    assert len(unposted_disc) == 0, "Document with posted AccountingRecord should not be flagged UNPOSTED_INVOICE"


def test_detect_discrepancies_flags_needs_review_document(db_session, setup_d5):
    """Documents with status='needs_review' or 'blocked' are surfaced as NEEDS_REVIEW discrepancies."""
    user, client = setup_d5

    doc_review = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="ambiguous_note.pdf",
        document_category="credit_note",
        invoice_type="needs_review",
        invoice_number="CN/REVIEW/01",
        invoice_date="2026-08-20",
        customer="Unknown Entity",
        gstin="27AAACX9999X1Z9",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        status="needs_review",
    )
    db_session.add(doc_review)
    db_session.flush()

    report = GstReconciliationService.detect_discrepancies(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    review_disc = next((d for d in report.discrepancies if d.rule_code == "NEEDS_REVIEW" and d.document_id == doc_review.id), None)
    assert review_disc is not None
    assert review_disc.severity == "HIGH"
    assert review_disc.variance_amount == Decimal("3600.00")
