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
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.accounting_draft_service import AccountingDraftService
from app.services.general_ledger_service import GeneralLedgerService
from app.services.journal_entry_service import JournalEntryService
from app.core.exceptions import ForbiddenException, NotFoundException


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
        ],
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def gl_test_setup(db_session):
    """Set up test clients, users, accounts, and sample verified documents."""
    user = User(
        id=uuid.uuid4(),
        email="ca_gl@example.com",
        password_hash="pw",
        full_name="CA GL Reviewer",
        role="client",
    )
    unauth_user = User(
        id=uuid.uuid4(),
        email="unauth_gl@example.com",
        password_hash="pw",
        full_name="Unauthorized User",
        role="client",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-GL-A",
        company_name="Apex Trading Enterprises",
        contact_person="Ramesh Patel",
        status="active",
    )
    other_client = Client(
        id=uuid.uuid4(),
        user_id=unauth_user.id,
        client_code="CLI-GL-B",
        company_name="Other Enterprise",
        contact_person="Suresh Verma",
        status="active",
    )
    db_session.add_all([user, unauth_user, client, other_client])
    db_session.commit()

    # Initialize Chart of Accounts for client
    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    accounts = {
        a.account_code: a
        for a in db_session.query(ChartOfAccounts).filter_by(client_id=client.id).all()
    }

    return {
        "user": user,
        "unauth_user": unauth_user,
        "client": client,
        "other_client": other_client,
        "accounts": accounts,
    }


def test_empty_ledger_summary(db_session, gl_test_setup):
    """Test that GL summary for a client with no transactions returns 26 accounts with zero balances."""
    data = gl_test_setup
    summary = GeneralLedgerService.get_general_ledger_summary(
        db=db_session,
        client_id=data["client"].id,
        user=data["user"],
    )

    assert summary.client_id == data["client"].id
    assert len(summary.accounts) == 26
    assert summary.total_debit == Decimal("0.00")
    assert summary.total_credit == Decimal("0.00")
    assert summary.net_difference == Decimal("0.00")

    # Check cash account 1010
    cash_acc = next(a for a in summary.accounts if a.account_code == "1010")
    assert cash_acc.closing_balance == Decimal("0.00")
    assert cash_acc.transaction_count == 0


def test_account_ledger_with_posted_transactions(db_session, gl_test_setup):
    """Test detailed running ledger for Debtors (1100) and Sales (4010) with verified invoice posting."""
    data = gl_test_setup
    client = data["client"]
    user = data["user"]
    accounts = data["accounts"]

    # 1. Create and post a sales invoice (₹1,000 + 9% CGST + 9% SGST = ₹1,180)
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Apex Customer Ltd",
        invoice_number="INV-2026-001",
        invoice_date="2026-04-10",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        transaction_date=date(2026, 4, 10),
        voucher_type="sales",
        description="Sales Invoice INV-2026-001",
        debit=Decimal("0.00"),
        credit=Decimal("1180.00"),
        status="draft",
        reference_number="INV-2026-001",
    )
    db_session.add(draft)
    db_session.commit()

    post_res = AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)
    assert post_res.success is True

    # 2. Inspect Debtors (1100) Ledger
    debtor_acc = accounts["1100"]
    debtor_ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=debtor_acc.id,
        user=user,
    )

    assert debtor_ledger.account_code == "1100"
    assert debtor_ledger.total_debit == Decimal("1180.00")
    assert debtor_ledger.total_credit == Decimal("0.00")
    assert debtor_ledger.closing_balance == Decimal("1180.00")
    assert debtor_ledger.closing_balance_side == "Dr"
    assert debtor_ledger.transaction_count == 1

    tx = debtor_ledger.transactions[0]
    assert tx.debit == Decimal("1180.00")
    assert tx.credit == Decimal("0.00")
    assert tx.running_balance == Decimal("1180.00")
    assert tx.balance_side == "Dr"
    assert tx.reference_number == "INV-2026-001"
    assert tx.party_name == "Apex Customer Ltd"

    # 3. Inspect Sales Revenue (4010) Ledger
    sales_acc = accounts["4010"]
    sales_ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=sales_acc.id,
        user=user,
    )

    assert sales_ledger.account_code == "4010"
    assert sales_ledger.total_debit == Decimal("0.00")
    assert sales_ledger.total_credit == Decimal("1000.00")
    assert sales_ledger.closing_balance == Decimal("1000.00")
    assert sales_ledger.closing_balance_side == "Cr"

    # 4. Inspect Output CGST (2110)
    cgst_acc = accounts["2110"]
    cgst_ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=cgst_acc.id,
        user=user,
    )
    assert cgst_ledger.total_credit == Decimal("90.00")
    assert cgst_ledger.closing_balance_side == "Cr"


def test_unposted_drafts_excluded_from_ledger(db_session, gl_test_setup):
    """Test that unposted drafts do NOT leak into the General Ledger."""
    data = gl_test_setup
    client = data["client"]
    user = data["user"]
    accounts = data["accounts"]

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        transaction_date=date(2026, 4, 15),
        voucher_type="sales",
        description="Draft voucher not posted",
        debit=Decimal("0.00"),
        credit=Decimal("5000.00"),
        status="draft",  # Unposted!
    )
    db_session.add(draft)
    db_session.commit()

    debtor_acc = accounts["1100"]
    ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=debtor_acc.id,
        user=user,
    )
    assert ledger.transaction_count == 0
    assert ledger.closing_balance == Decimal("0.00")


def test_date_filters_and_opening_balance(db_session, gl_test_setup):
    """Test date filtering and accurate calculation of opening balance roll-forward."""
    data = gl_test_setup
    client = data["client"]
    user = data["user"]
    accounts = data["accounts"]

    # Entry 1 in January (₹2,000 sales)
    doc_jan = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("2000.00"),
        customer="Jan Customer",
        invoice_number="INV-JAN",
        invoice_date="2026-01-15",
    )
    db_session.add(doc_jan)
    db_session.commit()

    draft_jan = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_jan.id,
        transaction_date=date(2026, 1, 15),
        voucher_type="sales",
        description="January Sale",
        debit=Decimal("0.00"),
        credit=Decimal("2000.00"),
        status="draft",
    )
    db_session.add(draft_jan)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_jan.id, user=user)

    # Entry 2 in February (₹3,000 sales)
    doc_feb = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("3000.00"),
        customer="Feb Customer",
        invoice_number="INV-FEB",
        invoice_date="2026-02-15",
    )
    db_session.add(doc_feb)
    db_session.commit()

    draft_feb = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_feb.id,
        transaction_date=date(2026, 2, 15),
        voucher_type="sales",
        description="February Sale",
        debit=Decimal("0.00"),
        credit=Decimal("3000.00"),
        status="draft",
    )
    db_session.add(draft_feb)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_feb.id, user=user)

    # Query February only (from 2026-02-01 to 2026-02-28)
    debtor_acc = accounts["1100"]
    feb_ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=debtor_acc.id,
        user=user,
        from_date=date(2026, 2, 1),
        to_date=date(2026, 2, 28),
    )

    # Opening balance must equal January's ₹2,000 Dr
    assert feb_ledger.opening_balance == Decimal("2000.00")
    assert feb_ledger.opening_balance_side == "Dr"
    # Period debit is February's ₹3,000 Dr
    assert feb_ledger.total_debit == Decimal("3000.00")
    # Closing balance must be ₹5,000 Dr
    assert feb_ledger.closing_balance == Decimal("5000.00")
    assert feb_ledger.closing_balance_side == "Dr"
    # Only 1 transaction in February period
    assert feb_ledger.transaction_count == 1
    assert feb_ledger.transactions[0].reference_number == "INV-FEB"


def test_reversal_entry_cancels_in_ledger(db_session, gl_test_setup):
    """Test that reversing a journal entry accurately zeroes out the balance."""
    data = gl_test_setup
    client = data["client"]
    user = data["user"]
    accounts = data["accounts"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1000.00"),
        customer="Erroneous Customer",
        invoice_number="INV-ERR",
        invoice_date="2026-03-01",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        transaction_date=date(2026, 3, 1),
        voucher_type="sales",
        description="Erroneous Invoice",
        debit=Decimal("0.00"),
        credit=Decimal("1000.00"),
        status="draft",
    )
    db_session.add(draft)
    db_session.commit()

    post_res = AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)
    assert post_res.journal_entry is not None

    # Reverse the journal entry
    JournalEntryService.reverse_journal_entry(
        db=db_session,
        entry_id=post_res.journal_entry.id,
        reason="Invoice issued in error to wrong customer",
        user=user,
    )

    # Inspect Debtors Ledger
    debtor_acc = accounts["1100"]
    ledger = GeneralLedgerService.get_account_ledger(
        db=db_session,
        client_id=client.id,
        account_id=debtor_acc.id,
        user=user,
    )

    # 2 transactions: original (₹1,000 Dr) + reversal (₹1,000 Cr)
    assert ledger.transaction_count == 2
    assert ledger.total_debit == Decimal("1000.00")
    assert ledger.total_credit == Decimal("1000.00")
    assert ledger.closing_balance == Decimal("0.00")


def test_client_isolation_on_ledger(db_session, gl_test_setup):
    """Test that unauthorized user cannot access another client's ledger."""
    data = gl_test_setup
    client = data["client"]
    unauth_user = data["unauth_user"]
    accounts = data["accounts"]

    with pytest.raises(ForbiddenException):
        GeneralLedgerService.get_general_ledger_summary(
            db=db_session,
            client_id=client.id,
            user=unauth_user,
        )

    debtor_acc = accounts["1100"]
    with pytest.raises(ForbiddenException):
        GeneralLedgerService.get_account_ledger(
            db=db_session,
            client_id=client.id,
            account_id=debtor_acc.id,
            user=unauth_user,
        )
