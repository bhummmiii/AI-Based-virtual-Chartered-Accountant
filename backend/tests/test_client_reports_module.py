"""
Unit and Integration Tests for Client Reports Module:
- Cash Flow Statement (ICAI AS-3 mathematical reconciliation)
- GST Summary Report (GSTR-1, GSTR-2B, GSTR-3B parity)
- Data Integrity and Anti-Fraud Audit (Double-entry balance, duplicates, math checks)
- Master Client Reports Summary endpoint
- Tenant isolation and access verification
"""

import os
import sys
import uuid
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
from app.services.report_service import ReportService
from app.core.exceptions import ForbiddenException


@pytest.fixture
def db_session():
    """In-memory SQLite test session."""
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
def setup_client_data(db_session):
    """Set up client with chart of accounts, documents, and posted journal entries."""
    user = User(
        id=uuid.uuid4(),
        email="test_ca_partner@example.com",
        password_hash="hashed_pw",
        full_name="Bhumi Jha, CA",
        role="ca",
    )
    unauth_user = User(
        id=uuid.uuid4(),
        email="unauth_ca@example.com",
        password_hash="hashed_pw",
        full_name="Unauth CA",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-1071",
        company_name="oggy pvt ltd",
        contact_person="Oggy",
        status="active",
    )
    db_session.add_all([user, unauth_user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    accounts = {
        a.account_code: a
        for a in db_session.query(ChartOfAccounts).filter_by(client_id=client.id).all()
    }

    # 1. Post a sales entry: Debtor Dr 118,000 / Sales Cr 100,000 / Output GST Cr 18,000
    sales_je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        entry_number="JE-SALE-001",
        entry_date=date(2026, 5, 10),
        entry_type="sales",
        status="posted",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
        is_balanced=True,
    )
    db_session.add(sales_je)
    db_session.flush()

    line1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=sales_je.id,
        line_number=1,
        account_id=accounts["1100"].id,  # Sundry Debtors
        debit_amount=Decimal("118000.00"),
        credit_amount=Decimal("0.00"),
    )
    line2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=sales_je.id,
        line_number=2,
        account_id=accounts["4010"].id,  # Sales Revenue
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("100000.00"),
    )
    line3 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=sales_je.id,
        line_number=3,
        account_id=accounts["2130"].id,  # Output IGST
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("18000.00"),
    )
    db_session.add_all([line1, line2, line3])

    # 2. Customer Receipt into Bank: Bank Dr 118,000 / Debtor Cr 118,000
    receipt_je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        entry_number="JE-REC-001",
        entry_date=date(2026, 5, 15),
        entry_type="receipt",
        status="posted",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
        is_balanced=True,
    )
    db_session.add(receipt_je)
    db_session.flush()

    r_line1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=receipt_je.id,
        line_number=1,
        account_id=accounts["1020"].id,  # Main Bank Current Account
        debit_amount=Decimal("118000.00"),
        credit_amount=Decimal("0.00"),
    )
    r_line2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=receipt_je.id,
        line_number=2,
        account_id=accounts["1100"].id,  # Sundry Debtors
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("118000.00"),
    )
    db_session.add_all([r_line1, r_line2])

    # 3. Rent Expense Paid from Bank: Rent Dr 20,000 / Bank Cr 20,000
    rent_je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        entry_number="JE-PAY-001",
        entry_date=date(2026, 5, 20),
        entry_type="payment",
        status="posted",
        total_debit=Decimal("20000.00"),
        total_credit=Decimal("20000.00"),
        is_balanced=True,
    )
    db_session.add(rent_je)
    db_session.flush()

    p_line1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=rent_je.id,
        line_number=1,
        account_id=accounts["5110"].id,  # Rent Expense
        debit_amount=Decimal("20000.00"),
        credit_amount=Decimal("0.00"),
    )
    p_line2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=rent_je.id,
        line_number=2,
        account_id=accounts["1020"].id,  # Main Bank Current Account
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("20000.00"),
    )
    db_session.add_all([p_line1, p_line2])

    # 4. Uploaded Invoices
    inv1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-2026-001",
        gstin="27AABCA1234A1Z5",
        customer="Client Corp",
        invoice_date="2026-05-10",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        cess=Decimal("0.00"),
        status="verified",
    )
    pur1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        invoice_number="PUR-2026-001",
        gstin="27XYZPA5678B1Z2",
        vendor="Supplier Ltd",
        invoice_date="2026-05-12",
        amount=Decimal("47200.00"),
        taxable_amount=Decimal("40000.00"),
        cgst=Decimal("3600.00"),
        sgst=Decimal("3600.00"),
        igst=Decimal("0.00"),
        cess=Decimal("0.00"),
        status="verified",
    )
    db_session.add_all([inv1, pur1])

    # 5. GST Record
    gst_rec = GSTRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        gst_period="2026-05",
        gst_type="GSTR-3B",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        total_tax=Decimal("18000.00"),
        filing_status="filed",
        due_date=date(2026, 6, 20),
    )
    db_session.add(gst_rec)
    db_session.commit()

    return {
        "user": user,
        "unauth_user": unauth_user,
        "client": client,
        "accounts": accounts,
    }


def test_cash_flow_statement_reconciliation(db_session, setup_client_data):
    """Test Cash Flow Statement computes operating receipts/payments and reconciles closing cash."""
    data = setup_client_data
    client = data["client"]
    user = data["user"]

    cf = ReportService.generate_cash_flow(
        db_session,
        client.id,
        user,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 5, 31),
    )

    # Receipt = 118,000, Rent Paid = 20,000 -> Net Cash Flow = 98,000
    assert cf.operating_activities.total == Decimal("98000.00")
    assert cf.net_cash_flow == Decimal("98000.00")
    assert cf.closing_cash_balance == Decimal("98000.00")
    assert cf.is_reconciled is True


def test_gst_summary_report(db_session, setup_client_data):
    """Test GST Summary Report integrates outward supplies, inward ITC, and net payable."""
    data = setup_client_data
    client = data["client"]
    user = data["user"]

    gst = ReportService.generate_gst_summary(
        db_session,
        client.id,
        user,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 5, 31),
    )

    assert gst.total_outward_taxable == Decimal("100000.00")
    assert gst.total_output_tax == Decimal("18000.00")
    assert gst.total_inward_taxable == Decimal("40000.00")
    assert gst.total_input_tax_credit == Decimal("7200.00")
    # Net payable = 18000 - 7200 = 10800
    assert gst.net_tax_payable == Decimal("10800.00")
    assert len(gst.filing_records) == 1
    assert gst.filing_records[0].filing_status == "filed"


def test_integrity_audit_clean_client(db_session, setup_client_data):
    """Test Data Integrity Audit on a clean client returns high score with all assertions passed."""
    data = setup_client_data
    client = data["client"]
    user = data["user"]

    audit = ReportService.generate_integrity_audit(
        db_session,
        client.id,
        user,
        as_of_date=date(2026, 5, 31),
    )

    # Double entry check passed
    assert audit.unbalanced_entries_count == 0
    assert audit.duplicate_invoices_count == 0
    assert audit.math_mismatches_count == 0
    assert audit.integrity_score >= 85
    assert audit.status in ("EXCELLENT", "GOOD")


def test_integrity_audit_detects_duplicate_invoice(db_session, setup_client_data):
    """Test Data Integrity Audit flags duplicate invoice uploads with specific anomaly alert."""
    data = setup_client_data
    client = data["client"]
    user = data["user"]

    # Inject a duplicate invoice with same invoice_number and gstin
    dup_inv = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-2026-001",  # Same number!
        gstin="27AABCA1234A1Z5",        # Same GSTIN!
        customer="Client Corp",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        status="pending",
    )
    db_session.add(dup_inv)
    db_session.commit()

    audit = ReportService.generate_integrity_audit(
        db_session,
        client.id,
        user,
        as_of_date=date(2026, 5, 31),
    )

    assert audit.duplicate_invoices_count == 1
    dup_anomalies = [a for a in audit.anomalies if a.rule_code == "DUPLICATE_INVOICE"]
    assert len(dup_anomalies) == 1
    assert "INV-2026-001" in dup_anomalies[0].title


def test_client_reports_summary(db_session, setup_client_data):
    """Test unified client reports summary endpoint combines all 4 modules seamlessly."""
    data = setup_client_data
    client = data["client"]
    user = data["user"]

    summary = ReportService.generate_client_reports_summary(
        db_session,
        client.id,
        user,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 5, 31),
    )

    assert summary.client_id == client.id
    assert summary.company_name == "oggy pvt ltd"
    # P&L revenue = 100,000, rent expense = 20,000 -> Net profit = 80,000
    assert summary.revenue == Decimal("100000.00")
    assert summary.net_profit == Decimal("80000.00")
    # Balance sheet
    assert summary.is_balance_sheet_balanced is True
    # GST
    assert summary.total_output_tax == Decimal("18000.00")
    assert summary.net_gst_payable == Decimal("10800.00")
    # Cash flow
    assert summary.closing_cash_balance == Decimal("98000.00")


def test_report_isolation_unauthorized_user(db_session, setup_client_data):
    """Test tenant security: unauthorized CA user cannot access client reports."""
    data = setup_client_data
    client = data["client"]
    unauth_user = data["unauth_user"]

    with pytest.raises(ForbiddenException):
        ReportService.generate_cash_flow(
            db_session,
            client.id,
            unauth_user,
        )

    with pytest.raises(ForbiddenException):
        ReportService.generate_integrity_audit(
            db_session,
            client.id,
            unauth_user,
        )
