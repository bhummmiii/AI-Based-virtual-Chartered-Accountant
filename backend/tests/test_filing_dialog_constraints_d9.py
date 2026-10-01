"""
Unit & Statutory Tests for Commit D9:
Statutory Return Filing Dialog Locking & Pre-fill:
1. Rejects filing when outward tax liability or taxable turnover is negative.
2. Rejects filing when client has unresolved high-risk statutory discrepancies.
3. Successfully records filing and auto-locks accounting period when client has zero discrepancies.
4. Rejects duplicate filing records for the same client, period, and return form.
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
from app.schemas.gst import GSTRecordCreate
from app.api.routers.gst.router import create_gst_record
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
def setup_d9(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="filing_officer@finledger.ai",
        full_name="Filing Compliance Officer",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Vanguard Logistics Ltd",
        client_code="VNG-999",
        contact_person="Compliance Head",
        client_type="company",
        gst_number="27AAACV9999V1Z1",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return user, client


def test_create_gst_record_blocks_negative_liability(db_session, setup_d9):
    """Statutory gate blocks return filing when tax liability is negative."""
    user, client = setup_d9

    payload = GSTRecordCreate(
        client_id=client.id,
        gst_period="2026-09",
        gst_type="GSTR-3B",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("-900.00"),
        sgst=Decimal("-900.00"),
        igst=Decimal("0.00"),
        total_tax=Decimal("-1800.00"),
        filing_status="filed",
        due_date=date(2026, 10, 20),
    )

    with pytest.raises(BadRequestException) as exc:
        create_gst_record(payload=payload, db=db_session, current_user=user)

    assert "negative" in str(exc.value.detail).lower()


def test_create_gst_record_blocks_when_high_risk_discrepancy_exists(db_session, setup_d9):
    """Statutory gate blocks return filing when unposted invoices or high-risk discrepancies exist."""
    user, client = setup_d9

    # Add an unposted invoice causing UNPOSTED_INVOICE discrepancy
    unposted_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="unposted_bill.pdf",
        document_category="sales_invoice",
        invoice_type="sales",
        invoice_number="INV/UNP/01",
        invoice_date="2026-09-10",
        customer="Beta Corp",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
    )
    db_session.add(unposted_doc)
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=client.id,
        gst_period="2026-09",
        gst_type="GSTR-1",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        total_tax=Decimal("18000.00"),
        filing_status="filed",
        due_date=date(2026, 10, 11),
    )

    with pytest.raises(BadRequestException) as exc:
        create_gst_record(payload=payload, db=db_session, current_user=user)

    assert "unresolved high-risk discrepancy" in str(exc.value.detail).lower()


def test_create_gst_record_succeeds_when_clean(db_session, setup_d9):
    """Statutory filing succeeds and auto-locks accounting period when zero discrepancies exist."""
    user, client = setup_d9

    # Fully posted sales document and journal entry
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="posted_sales.pdf",
        document_category="sales_invoice",
        invoice_type="sales",
        invoice_number="INV/PST/01",
        invoice_date="2026-09-05",
        customer="Beta Corp",
        gstin="27AAACR9999R1ZZ",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
    )
    db_session.add(doc)
    db_session.flush()

    debtors = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "1100").first()
    sales = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4010").first()
    cgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2110").first()
    sgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2120").first()

    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        entry_number="JE-PST-01",
        entry_date=date(2026, 9, 5),
        narration="Sale to Beta Corp",
        entry_type="sales",
        status="posted",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
    )
    db_session.add(je)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=1, account_id=debtors.id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=2, account_id=sales.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=3, account_id=cgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=4, account_id=sgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
    ])
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=client.id,
        gst_period="2026-09",
        gst_type="GSTR-1",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        total_tax=Decimal("18000.00"),
        filing_status="filed",
        due_date=date(2026, 10, 11),
    )

    resp = create_gst_record(payload=payload, db=db_session, current_user=user)
    assert resp.success is True
    assert resp.data.gst_period == "2026-09"
    assert resp.data.filing_status == "filed"

    # Verify accounting period is locked
    locked_period = db_session.query(AccountingPeriod).filter(
        AccountingPeriod.client_id == client.id,
        AccountingPeriod.start_date == date(2026, 9, 1),
    ).first()
    assert locked_period is not None
    assert locked_period.status == "locked"


def test_create_gst_record_duplicate_rejected(db_session, setup_d9):
    """Duplicate filing record for same client, period, and return type is rejected."""
    user, client = setup_d9

    payload = GSTRecordCreate(
        client_id=client.id,
        gst_period="2026-09",
        gst_type="GSTR-3B",
        taxable_amount=Decimal("50000.00"),
        cgst=Decimal("4500.00"),
        sgst=Decimal("4500.00"),
        igst=Decimal("0.00"),
        total_tax=Decimal("9000.00"),
        filing_status="pending",
        due_date=date(2026, 10, 20),
    )

    create_gst_record(payload=payload, db=db_session, current_user=user)

    # Attempting second filing
    with pytest.raises(BadRequestException) as exc:
        create_gst_record(payload=payload, db=db_session, current_user=user)

    assert "already exists" in str(exc.value.detail).lower()
