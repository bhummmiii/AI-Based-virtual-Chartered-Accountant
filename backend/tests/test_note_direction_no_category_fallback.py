"""
Unit Tests for Commit D4:
1. Note Direction Resolution Without Category Fallback:
   - Uploading/mapping DN1 under category 'debit_note' references sales invoice ABC/26-27/002
     and resolves strictly to Template T4 (sales debit note), NOT T5 (purchase return).
2. Ambiguous Note Direction:
   - Note without original invoice reference, without applies_to override, and without
     clear party/GSTIN anchor raises 'needs_review'.
3. Strict Client GSTIN Anchor:
   - If neither supplier nor recipient GSTIN matches client's GSTIN, raises 'CLIENT_MISMATCH'.
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
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.core.exceptions import BadRequestException


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
def setup_d4(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="lead_ca@finledger.ai",
        full_name="Lead CA",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="ABC Traders Pvt Ltd",
        client_code="ABC-001",
        contact_person="Director ABC",
        client_type="company",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)

    return user, client


def test_dn1_under_debit_note_category_resolves_to_t4(db_session, setup_d4):
    """DN1 uploaded with document_category='debit_note' references sales invoice ABC/26-27/002 -> Template T4."""
    user, client = setup_d4

    # 1. Original sales invoice S2 (ABC/26-27/002)
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="invoice_abc_002.pdf",
        document_category="e_invoice",
        invoice_type="sales",
        invoice_number="ABC/26-27/002",
        invoice_date="2026-07-10",
        customer="Global Exports Ltd",
        gstin="29ABCDE1234F1Z5",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        igst=Decimal("18000.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "29ABCDE1234F1Z5"},
                "taxable_amount": {"value": 100000.0},
                "igst_amount": {"value": 18000.0},
            }
        }),
    )
    db_session.add(doc_s2)
    db_session.flush()

    # 2. Debit Note DN1 uploaded with category 'debit_note' (NOT sales_records!)
    doc_dn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="debit_note_dn1.pdf",
        document_category="debit_note",
        invoice_number="ABC/DN/26-27/001",
        invoice_date="2026-08-25",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "original_invoice_number": {"value": "ABC/26-27/002"},
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "29ABCDE1234F1Z5"},
                "taxable_amount": {"value": 10000.0},
                "igst_amount": {"value": 1800.0},
                "place_of_supply_code": {"value": "29"},
            }
        }),
    )
    db_session.add(doc_dn1)
    db_session.flush()

    # Map to journal entry
    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc_dn1, user)

    # Must be Template T4 (Sales Debit Note):
    # Dr Debtors (1130)  11,800
    #   Cr Other Income (4030)  10,000
    #   Cr Output IGST (2130)    1,800
    account_ids = [line.account_id for line in je_create.lines if line.credit_amount > 0]
    credit_accounts = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.id.in_(account_ids)).all()
    credit_account_codes = [a.account_code for a in credit_accounts]
    credit_roles = [a.role for a in credit_accounts]

    assert "4030" in credit_account_codes or "4000" in credit_account_codes or "OTHER_INCOME" in credit_roles
    assert "2130" in credit_account_codes or "2013" in credit_account_codes or "OUTPUT_IGST" in credit_roles

    # Verify reconciliation direction is OUTWARD, not INWARD
    direction = GstReconciliationService.determine_document_direction(doc_dn1, client.gst_number, db=db_session)
    assert direction == "OUTWARD"


def test_ambiguous_note_without_reference_raises_needs_review(db_session, setup_d4):
    """Note with ambiguous parties and no original invoice or applies_to override raises needs_review."""
    user, client = setup_d4

    # Note with ambiguous parties (both present, neither matches client) and no reference
    doc_ambiguous = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="orphan_note.pdf",
        document_category="credit_note",
        invoice_number="ORPHAN/CN/01",
        invoice_date="2026-08-10",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        customer="Party A Ltd",
        vendor="Party B Ltd",
        status="verified",
    )
    db_session.add(doc_ambiguous)
    db_session.flush()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(db_session, doc_ambiguous, user)
    assert "needs_review" in str(exc.value).lower()

    direction = GstReconciliationService.determine_document_direction(doc_ambiguous, client.gst_number, db=db_session)
    assert direction == "NEEDS_REVIEW"


def test_client_mismatch_blocks_document(db_session, setup_d4):
    """Document where neither supplier nor recipient matches client GSTIN raises CLIENT_MISMATCH."""
    user, client = setup_d4

    doc_mismatch = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="foreign_invoice.pdf",
        document_category="b2b_invoice",
        invoice_number="INV/FOREIGN/001",
        invoice_date="2026-08-10",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": "27OTHER1111A1Z1"},
                "customer_gstin": {"value": "27OTHER2222B1Z2"},
            }
        }),
    )
    db_session.add(doc_mismatch)
    db_session.flush()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(db_session, doc_mismatch, user)
    assert "CLIENT_MISMATCH" in str(exc.value)
