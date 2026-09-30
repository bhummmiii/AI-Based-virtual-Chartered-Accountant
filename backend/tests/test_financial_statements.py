"""
Unit and Integration Tests for Phase 6: Profit & Loss Statement, Balance Sheet, and Drill-Down.
Tests:
1. Profit & Loss computation (Revenue, COGS, Gross Profit, Operating Expenses, Net Profit).
2. Balance Sheet double-entry mathematical equality (Total Assets == Total Liabilities + Equity).
3. Audit drill-down from statement lines to journal entries, vouchers, and source documents.
4. Client tenant authorization and isolation.
"""

import sys
import os
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
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.accounting_draft_service import AccountingDraftService
from app.services.financial_statements_service import FinancialStatementsService
from app.core.exceptions import ForbiddenException


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
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
        ],
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def report_test_setup(db_session):
    """Set up client, users, and Chart of Accounts."""
    user = User(
        id=uuid.uuid4(),
        email="ca_reports@example.com",
        password_hash="secret",
        full_name="CA Partner",
        role="ca",
    )
    unauth_user = User(
        id=uuid.uuid4(),
        email="other_ca_reports@example.com",
        password_hash="secret",
        full_name="Other CA",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-REP-01",
        company_name="Apex Global Exports",
        contact_person="Vikram Malhotra",
        status="active",
    )
    db_session.add_all([user, unauth_user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    accounts = {
        a.account_code: a
        for a in db_session.query(ChartOfAccounts).filter_by(client_id=client.id).all()
    }
    return {
        "user": user,
        "unauth_user": unauth_user,
        "client": client,
        "accounts": accounts,
    }


def test_profit_and_loss_calculation(db_session, report_test_setup):
    """Test Profit & Loss statement calculates Gross Profit and Net Profit accurately."""
    data = report_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Post Sales Invoice: ₹10,000 turnover + 18% GST (₹900 CGST + ₹900 SGST) = ₹11,800
    doc_sales = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        customer="Global Buyer Ltd",
        invoice_number="INV-REP-01",
        invoice_date="2026-07-10",
    )
    db_session.add(doc_sales)
    db_session.commit()

    draft_sales = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_sales.id,
        transaction_date=date(2026, 7, 10), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("11800.00"), status="draft",
        reference_number="INV-REP-01",
    )
    db_session.add(draft_sales)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_sales.id, user=user)

    # 2. Post Purchase Bill: ₹6,000 cost of sales + 18% GST (₹540 CGST + ₹540 SGST) = ₹7,080
    doc_pur = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        amount=Decimal("7080.00"),
        taxable_amount=Decimal("6000.00"),
        cgst=Decimal("540.00"),
        sgst=Decimal("540.00"),
        vendor="Raw Materials Supplier",
        invoice_number="PUR-REP-01",
        invoice_date="2026-07-15",
    )
    db_session.add(doc_pur)
    db_session.commit()

    draft_pur = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_pur.id,
        transaction_date=date(2026, 7, 15), voucher_type="purchase",
        debit=Decimal("7080.00"), credit=Decimal("0.00"), status="draft",
        reference_number="PUR-REP-01",
    )
    db_session.add(draft_pur)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_pur.id, user=user)

    # 3. Generate Profit & Loss
    pnl = FinancialStatementsService.generate_profit_and_loss(
        db=db_session,
        client_id=client.id,
        user=user,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
    )

    # Revenue = ₹10,000
    assert pnl.revenue_section.total == Decimal("10000.00")
    # Cost of Sales = ₹6,000
    assert pnl.cost_of_sales_section.total == Decimal("6000.00")
    # Gross Profit = ₹10,000 - ₹6,000 = ₹4,000
    assert pnl.gross_profit == Decimal("4000.00")
    assert pnl.gross_profit_margin_pct == Decimal("40.00")
    # Net Profit = ₹4,000 (0 opex in this period)
    assert pnl.net_profit_before_tax == Decimal("4000.00")
    assert pnl.net_profit_margin_pct == Decimal("40.00")


def test_balance_sheet_balanced_equation(db_session, report_test_setup):
    """Test that Balance Sheet mathematically balances (Assets == Liabilities + Equity)."""
    data = report_test_setup
    client = data["client"]
    user = data["user"]

    # Post an invoice to generate assets and liabilities
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Apex Buyer",
        invoice_number="INV-BS-01",
        invoice_date="2026-07-20",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc.id,
        transaction_date=date(2026, 7, 20), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1180.00"), status="draft",
        reference_number="INV-BS-01",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    bs = FinancialStatementsService.generate_balance_sheet(
        db=db_session,
        client_id=client.id,
        user=user,
        as_of_date=date(2026, 7, 31),
    )

    # Total Assets = Debtors (₹1,180)
    assert bs.total_assets == Decimal("1180.00")

    # Liabilities = Output Taxes (₹90 + ₹90 = ₹180)
    assert bs.total_liabilities == Decimal("180.00")

    # Equity = Net Profit from Revenue (₹1,000)
    assert bs.current_period_net_profit == Decimal("1000.00")
    assert bs.total_equity == Decimal("1000.00")

    # Double-entry balance check: 1180 == 180 + 1000
    assert bs.is_balanced is True
    assert bs.difference == Decimal("0.00")
    assert bs.total_assets == bs.total_equity_and_liabilities


def test_drilldown_links_to_vouchers_and_docs(db_session, report_test_setup):
    """Test audit drill-down from statement lines to vouchers and source documents."""
    data = report_test_setup
    client = data["client"]
    user = data["user"]
    accounts = data["accounts"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Drilldown Customer Ltd",
        invoice_number="INV-DRILL-01",
        invoice_date="2026-07-25",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc.id,
        transaction_date=date(2026, 7, 25), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1180.00"), status="draft",
        reference_number="INV-DRILL-01",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    sales_acc = accounts["4010"]
    drill = FinancialStatementsService.get_report_drilldown(
        db=db_session,
        client_id=client.id,
        account_id=sales_acc.id,
        user=user,
    )

    assert drill.account_code == "4010"
    assert drill.transaction_count == 1

    tx = drill.transactions[0]
    assert tx.reference_number == "INV-DRILL-01"
    assert tx.document_id == doc.id
    assert tx.voucher_id == draft.id
    assert tx.credit == Decimal("1000.00")


def test_client_tenant_isolation_on_reports(db_session, report_test_setup):
    """Test unauthorized user cannot view financial statements."""
    data = report_test_setup
    client = data["client"]
    unauth_user = data["unauth_user"]
    accounts = data["accounts"]

    with pytest.raises(ForbiddenException):
        FinancialStatementsService.generate_profit_and_loss(
            db=db_session, client_id=client.id, user=unauth_user,
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31)
        )

    with pytest.raises(ForbiddenException):
        FinancialStatementsService.generate_balance_sheet(
            db=db_session, client_id=client.id, user=unauth_user,
            as_of_date=date(2026, 7, 31)
        )
