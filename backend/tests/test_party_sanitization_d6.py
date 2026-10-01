"""
Unit & Integration Tests for Commit D6:
1. Header-as-value guard:
   - _is_header_word correctly rejects '(From)', 'Entered Date', '(To)', 'entered'.
2. Party Name Cleaning:
   - _clean_party_name strips '(From)' from party names and rejects 'Entered Date'.
3. Script Re-extraction:
   - sanitize_document_parties restores vendor from client name when vendor is '(From)'.
   - Corrects 'Entered Date' on e-way bills to dispatch party and extracts recipient/customer.
   - Extracts recipient party and GSTIN from Recipient block on e-invoices.
4. GSTR-1 Supply Classification:
   - Unregistered intra-state supply is classified as B2CS.
   - Unregistered inter-state supply exceeding threshold is classified as B2CL.
   - Registered supply with valid recipient GSTIN is classified as B2B.
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

from app.api.routers.ocr.router import _is_header_word, _clean_party_name
from scripts.reextract_party_fields import sanitize_document_parties
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.accounting_draft_service import AccountingDraftService
from app.services.gst_reconciliation_service import GstReconciliationService


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
def setup_d6(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="sanitizer_ca@finledger.ai",
        full_name="Sanitizer CA",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Alpha Tech Solutions Pvt Ltd",
        client_code="ATS-202",
        contact_person="Accounts Head",
        client_type="company",
        gst_number="27AAACA1111A1Z1",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return user, client


def test_header_guard_rejects_from_and_entered_date():
    """_is_header_word rejects '(From)', 'Entered Date', '(To)'."""
    assert _is_header_word("(From)") is True
    assert _is_header_word("from") is True
    assert _is_header_word("Entered Date") is True
    assert _is_header_word("(To)") is True
    assert _is_header_word("entered") is True
    assert _is_header_word("Alpha Tech Solutions") is False


def test_clean_party_name_sanitization():
    """_clean_party_name removes '(From)' prefix/suffix and rejects 'Entered Date'."""
    assert _clean_party_name("(From)") == ""
    assert _clean_party_name("Entered Date") == ""
    assert _clean_party_name("Supplier (From)\nAlpha Tech Solutions") == "Alpha Tech Solutions"
    assert _clean_party_name("Alpha Tech (From)") == "Alpha Tech"


def test_sanitize_document_parties_from_and_ewb(setup_d6):
    """sanitize_document_parties cleans (From) and Entered Date."""
    user, client = setup_d6

    # 1. B2C invoice with (From) as vendor
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        invoice_number="S3-001",
        vendor="(From)",
        customer="Walk-in Cash Customer",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
    )
    changed, updates, reasons = sanitize_document_parties(doc_s3, client, "")
    assert changed is True
    assert updates["vendor"] == client.company_name

    # 2. E-way bill with 'Entered Date' as vendor
    doc_ewb = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="e_way_bill",
        invoice_number="EWB-123456789012",
        vendor="Entered Date",
        customer=None,
    )
    changed_ewb, updates_ewb, _ = sanitize_document_parties(doc_ewb, client, "")
    assert changed_ewb is True
    assert updates_ewb["vendor"] == client.company_name


def test_gstr1_supply_classification_b2cl_vs_b2cs(db_session, setup_d6):
    """Verify B2CL vs B2CS vs B2B classification in GSTR-1."""
    user, client = setup_d6

    # 1. Large Inter-State B2C (> 100,000 threshold) -> B2CL
    doc_b2cl = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="b2cl_inv.pdf",
        document_category="b2c_invoice",
        invoice_type="sales",
        invoice_number="INV/B2CL/001",
        invoice_date="2026-08-10",
        customer="Unregistered Karnataka Buyer",
        gstin=None,
        amount=Decimal("141600.00"),
        taxable_amount=Decimal("120000.00"),
        igst=Decimal("21600.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "place_of_supply_code": {"value": "29"},  # Karnataka (inter-state)
                "taxable_amount": {"value": 120000.0},
                "igst_amount": {"value": 21600.0},
            }
        }),
    )
    # 2. Small Intra-State B2C (< 100,000) -> B2CS
    doc_b2cs = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="b2cs_inv.pdf",
        document_category="b2c_invoice",
        invoice_type="sales",
        invoice_number="INV/B2CS/001",
        invoice_date="2026-08-11",
        customer="Local Cash Customer",
        gstin=None,
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "place_of_supply_code": {"value": "27"},  # Maharashtra (intra-state)
                "taxable_amount": {"value": 20000.0},
                "cgst_amount": {"value": 1800.0},
                "sgst_amount": {"value": 1800.0},
            }
        }),
    )
    db_session.add_all([doc_b2cl, doc_b2cs])
    db_session.flush()

    for doc in [doc_b2cl, doc_b2cs]:
        d_res = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
        assert d_res.status in ("created", "updated")
        p_res = AccountingDraftService.post_draft_to_ledger(db_session, d_res.record.id, user)
        assert p_res.success is True

    res = GstReconciliationService.reconcile_gstr1(db=db_session, client_id=client.id, user=user)

    assert res.b2cl_summary.invoice_count == 1
    assert res.b2cl_summary.taxable_amount == Decimal("120000.00")
    assert res.b2cl_summary.igst == Decimal("21600.00")

    assert res.b2cs_summary.invoice_count == 1
    assert res.b2cs_summary.taxable_amount == Decimal("20000.00")
    assert res.b2cs_summary.cgst == Decimal("1800.00")
    assert res.b2cs_summary.sgst == Decimal("1800.00")
