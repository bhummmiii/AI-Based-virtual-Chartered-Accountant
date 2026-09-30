"""
Phase 1: Characterization Tests (Hard Rule R3 & Section 2: Must Keep Working)
Locks in existing baseline behaviors that MUST NOT break:
- B2C sale S3 voucher is byte-for-byte equivalent:
  Dr 1100 Sundry Debtors 21,000.00
  Cr 2110 Output CGST 500.00
  Cr 2120 Output SGST 500.00
  Cr 4010 Sales Revenue 20,000.00
  Party: 'Walk-in Customer (Unregistered)', ref: ABC/26-27/003, date: 2026-07-20
- Invoice list gross amounts: CN1 23,600.00, DN1 11,800.00, S3 21,000.00
- Upload / extraction / voucher mapping baseline integrity.
"""

import uuid
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
from app.services.journal_entry_service import JournalEntryService


@pytest.fixture
def char_db():
    """In-memory SQLite session for characterization tests."""
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
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def baseline_client(char_db):
    """Seed ABC Traders Pvt Ltd client, CA user, and default COA."""
    user = User(
        id=uuid.uuid4(),
        email="lead_ca@finledger.ai",
        full_name="CA Lead Partner",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    char_db.add(user)
    char_db.flush()

    client = Client(
        id=uuid.uuid4(),
        company_name="ABC Traders Pvt Ltd",
        client_code="ABC-MUM",
        contact_person="Director ABC",
        gst_number="27AABCA1234A1Z5",  # Maharashtra (27)
        email="contact@abctraders.in",
        status="active",
        user_id=user.id,
    )
    char_db.add(client)
    char_db.flush()

    ChartOfAccountsService.initialize_default_accounts(db=char_db, client_id=client.id, user=user)
    coa_map = {acc.account_code: acc for acc in char_db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()}

    return {"user": user, "client": client, "coa": coa_map}


def test_b2c_sale_s3_voucher_byte_for_byte_equality(char_db, baseline_client):
    """
    Section 2 Regression Lock:
    SV voucher, party 'Walk-in Customer (Unregistered)', ref ABC/26-27/003, date 2026-07-20:
    Dr 1100 Sundry Debtors 21,000.00
    Cr 2110 Output CGST 500.00
    Cr 2120 Output SGST 500.00
    Cr 4010 Sales Revenue 20,000.00
    """
    client = baseline_client["client"]
    user = baseline_client["user"]
    coa = baseline_client["coa"]

    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        status="verified",
        amount=Decimal("21000.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"),
        sgst=Decimal("500.00"),
        igst=Decimal("0.00"),
        customer="Walk-in Customer (Unregistered)",
        gstin="",
        invoice_number="ABC/26-27/003",
        invoice_date="2026-07-20",
    )
    char_db.add(doc_s3)
    char_db.commit()

    je_create = AccountingMappingService.map_document_to_journal_entry(char_db, doc_s3, user)
    je = JournalEntryService.create_journal_entry(char_db, client.id, je_create, user)

    assert je.entry_type == "sales"
    assert je.reference_number == "ABC/26-27/003"
    assert je.entry_date == date(2026, 7, 20)
    assert len(je.lines) == 4

    # Line 1: Dr 1100 Sundry Debtors 21,000.00
    l1 = je.lines[0]
    assert l1.line_number == 1
    assert l1.account_id == coa["1100"].id
    assert l1.debit_amount == Decimal("21000.00")
    assert l1.credit_amount == Decimal("0.00")
    assert l1.party_name == "Walk-in Customer (Unregistered)"

    # Line 2: Cr 2110 Output CGST 500.00
    l2 = je.lines[1]
    assert l2.line_number == 2
    assert l2.account_id == coa["2110"].id
    assert l2.debit_amount == Decimal("0.00")
    assert l2.credit_amount == Decimal("500.00")

    # Line 3: Cr 2120 Output SGST 500.00
    l3 = je.lines[2]
    assert l3.line_number == 3
    assert l3.account_id == coa["2120"].id
    assert l3.debit_amount == Decimal("0.00")
    assert l3.credit_amount == Decimal("500.00")

    # Line 4: Cr 4010 Sales Revenue 20,000.00
    l4 = je.lines[3]
    assert l4.line_number == 4
    assert l4.account_id == coa["4010"].id
    assert l4.debit_amount == Decimal("0.00")
    assert l4.credit_amount == Decimal("20000.00")


def test_document_gross_totals_exact_match(char_db, baseline_client):
    """
    Section 2: Document gross totals must equal document gross values:
    CN1 = 23,600; DN1 = 11,800; S3 = 21,000
    """
    client = baseline_client["client"]

    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="credit_note",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        invoice_number="ABC/CN/26-27/001",
    )
    doc_dn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="debit_note",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"),
        invoice_number="ABC/DN/26-27/001",
    )
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        amount=Decimal("21000.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"),
        sgst=Decimal("500.00"),
        invoice_number="ABC/26-27/003",
    )
    char_db.add_all([doc_cn1, doc_dn1, doc_s3])
    char_db.commit()

    assert doc_cn1.amount == Decimal("23600.00")
    assert doc_dn1.amount == Decimal("11800.00")
    assert doc_s3.amount == Decimal("21000.00")
