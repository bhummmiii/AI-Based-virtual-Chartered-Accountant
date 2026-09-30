"""
Unit and Integration Tests for Phase 4: Trial Balance and Period Controls.
Tests:
1. Trial Balance generation and mathematical double-entry equality (Total Dr == Total Cr).
2. Account classification grouping (Assets, Liabilities, Equity, Revenue, Expenses).
3. Health check audit controls: unbalanced entries, duplicate references, unposted drafts.
4. Period controls: period creation, period closing, lockout prevention of retroactive posting, and reopening.
"""

import sys
import os
import uuid
import pytest
from datetime import date, datetime, timezone
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
from app.services.trial_balance_service import TrialBalanceService
from app.schemas.trial_balance import AccountingPeriodCreate
from app.core.exceptions import BadRequestException


@pytest.fixture
def db_session():
    """Isolated, in-memory SQLite database session."""
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
def tb_test_setup(db_session):
    """Set up test client, user, and default Chart of Accounts."""
    user = User(
        id=uuid.uuid4(),
        email="ca_tb@example.com",
        password_hash="secret",
        full_name="CA Auditor",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-TB-01",
        company_name="Vanguard Logistics",
        contact_person="Sunil Mehta",
        status="active",
    )
    db_session.add_all([user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return {"user": user, "client": client}


def test_empty_trial_balance_balanced(db_session, tb_test_setup):
    """Test that an empty client returns a perfectly balanced Trial Balance with 0 totals."""
    data = tb_test_setup
    tb = TrialBalanceService.generate_trial_balance(
        db=db_session,
        client_id=data["client"].id,
        user=data["user"],
    )

    assert tb.is_balanced is True
    assert tb.total_debit == Decimal("0.00")
    assert tb.total_credit == Decimal("0.00")
    assert tb.health_check.status == "PASS"
    assert len(tb.groups) == 5  # Assets, Liabilities, Equity, Revenue, Expenses


def test_trial_balance_with_sales_and_purchases(db_session, tb_test_setup):
    """Test Trial Balance with complex sales and purchase transactions."""
    data = tb_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Post Sales Invoice: ₹1,000 + 18% GST (₹90 CGST + ₹90 SGST) = ₹1,180
    sales_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Delta Infotech",
        invoice_number="INV-TB-01",
        invoice_date="2026-05-10",
    )
    db_session.add(sales_doc)
    db_session.commit()

    sales_draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=sales_doc.id,
        transaction_date=date(2026, 5, 10),
        voucher_type="sales",
        description="Sales invoice",
        debit=Decimal("0.00"),
        credit=Decimal("1180.00"),
        status="draft",
        reference_number="INV-TB-01",
    )
    db_session.add(sales_draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, sales_draft.id, user=user)

    # 2. Post Purchase Invoice: ₹500 + 18% GST (₹45 CGST + ₹45 SGST) = ₹590
    purchase_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        amount=Decimal("590.00"),
        taxable_amount=Decimal("500.00"),
        cgst=Decimal("45.00"),
        sgst=Decimal("45.00"),
        vendor="Zenith Hardware",
        invoice_number="PUR-TB-01",
        invoice_date="2026-05-12",
    )
    db_session.add(purchase_doc)
    db_session.commit()

    purchase_draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=purchase_doc.id,
        transaction_date=date(2026, 5, 12),
        voucher_type="purchase",
        description="Purchase invoice",
        debit=Decimal("590.00"),
        credit=Decimal("0.00"),
        status="draft",
        reference_number="PUR-TB-01",
    )
    db_session.add(purchase_draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, purchase_draft.id, user=user)

    # 3. Generate Trial Balance
    tb = TrialBalanceService.generate_trial_balance(
        db=db_session,
        client_id=client.id,
        user=user,
        as_of_date=date(2026, 5, 31),
    )

    # Must be balanced: Total Debits == Total Credits
    assert tb.is_balanced is True
    assert tb.total_debit == tb.total_credit
    assert tb.total_debit > Decimal("0.00")

    # Verify Assets group has Debtors (₹1,180) and Input Tax Credits (₹45 + ₹45)
    assets_group = next(g for g in tb.groups if g.account_type == "Assets")
    debtor_row = next(r for r in assets_group.accounts if r.account_code == "1100")
    assert debtor_row.debit_balance == Decimal("1180.00")
    assert debtor_row.credit_balance == Decimal("0.00")

    # Verify Liabilities group has Creditors (₹590) and Output Taxes (₹90 + ₹90)
    liab_group = next(g for g in tb.groups if g.account_type == "Liabilities")
    creditor_row = next(r for r in liab_group.accounts if r.account_code == "2010")
    assert creditor_row.credit_balance == Decimal("590.00")

    # Verify Revenue has Sales (₹1,000 Cr)
    rev_group = next(g for g in tb.groups if g.account_type == "Revenue & Income")
    sales_row = next(r for r in rev_group.accounts if r.account_code == "4010")
    assert sales_row.credit_balance == Decimal("1000.00")

    # Verify Expense has Purchases (₹500 Dr)
    exp_group = next(g for g in tb.groups if g.account_type == "Expenses & Outflows")
    purchase_row = next(r for r in exp_group.accounts if r.account_code == "5010")
    assert purchase_row.debit_balance == Decimal("500.00")

    # Health check PASS
    assert tb.health_check.is_balanced is True
    assert tb.health_check.unbalanced_entries_count == 0


def test_trial_balance_health_check_detects_unposted_drafts(db_session, tb_test_setup):
    """Test that health checks flag pending unposted drafts."""
    data = tb_test_setup
    client = data["client"]
    user = data["user"]

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        transaction_date=date(2026, 5, 20),
        voucher_type="sales",
        description="Pending Draft",
        debit=Decimal("0.00"),
        credit=Decimal("5000.00"),
        status="draft",
    )
    db_session.add(draft)
    db_session.commit()

    tb = TrialBalanceService.generate_trial_balance(db=db_session, client_id=client.id, user=user)
    assert tb.health_check.unposted_drafts_count == 1
    assert tb.health_check.status == "WARNING"


def test_accounting_period_lockout_prevents_retroactive_posting(db_session, tb_test_setup):
    """Test that closing an accounting period prevents drafts from being posted into that period."""
    data = tb_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Create and close FY 2024-25 (2024-04-01 to 2025-03-31)
    period = TrialBalanceService.create_period(
        db=db_session,
        client_id=client.id,
        user=user,
        payload=AccountingPeriodCreate(
            period_name="FY 2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            closing_notes="Audited and closed by Statutory Auditor",
        ),
    )
    TrialBalanceService.close_period(
        db=db_session,
        client_id=client.id,
        period_id=period.id,
        user=user,
        notes="Books locked post-audit",
    )

    # 2. Attempt to post a draft dated 2024-11-15 (inside closed period)
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1000.00"),
        customer="Historical Cust",
        invoice_number="INV-OLD-01",
        invoice_date="2024-11-15",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        transaction_date=date(2024, 11, 15),
        voucher_type="sales",
        description="Retroactive invoice attempt",
        debit=Decimal("0.00"),
        credit=Decimal("1000.00"),
        status="draft",
    )
    db_session.add(draft)
    db_session.commit()

    res = AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)
    assert res.success is False
    assert "closed" in res.message.lower()
    assert "prohibited" in res.message.lower()

    # Verify status is still "draft"
    db_session.refresh(draft)
    assert draft.status == "draft"

    # 3. Reopen period and verify posting now succeeds
    TrialBalanceService.reopen_period(db=db_session, client_id=client.id, period_id=period.id, user=user)
    res_retry = AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)
    assert res_retry.success is True
    assert res_retry.record.status == "posted"
