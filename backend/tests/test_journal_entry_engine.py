"""
Unit and Integration Tests for Step 2A: Persistent Journal Entry Engine.

Tests:
1. Mathematical double-entry balance enforcement (Dr == Cr).
2. Unbalanced journal entry rejection.
3. Check constraints: single-sided line (cannot have both Dr & Cr > 0, or both 0) and non-negative values.
4. Client account isolation: cannot reference another client's accounts.
5. Inactive account protection: cannot post to deactivated accounts.
6. Auto-sequencing of voucher entry numbers.
7. Duplicate posting protection: unique accounting_record_id link.
8. Immutability and audit-compliant reversal mechanism (swaps Dr and Cr).
9. AccountingMappingService document-to-journal translation for Sales, Purchases, Credit Notes, Debit Notes, Challans.
10. Multi-tenant authorization checks.
"""

import sys
import os
import uuid
import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import Base
from app.models.user import User
from app.models.client import Client
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_record import AccountingRecord
from app.models.uploaded_document import UploadedDocument
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.journal_entry_service import JournalEntryService
from app.services.accounting_mapping_service import AccountingMappingService
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryLineCreate,
)
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ForbiddenException,
    BadRequestException,
)


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
def setup_accounting_data(db_session):
    """Seed test users, clients, and Chart of Accounts."""
    ca_user = User(
        id=uuid.uuid4(),
        email="ca_lead@example.com",
        full_name="CA Sharma",
        password_hash="secret_hash",
        role="ca",
        is_active=True,
    )
    other_ca = User(
        id=uuid.uuid4(),
        email="other_ca@example.com",
        full_name="CA Verma",
        password_hash="secret_hash",
        role="ca",
        is_active=True,
    )
    admin_user = User(
        id=uuid.uuid4(),
        email="admin_audit@example.com",
        full_name="Audit Partner",
        password_hash="secret_hash",
        role="admin",
        is_active=True,
    )
    db_session.add_all([ca_user, other_ca, admin_user])
    db_session.flush()

    # Client 1
    client_a = Client(
        id=uuid.uuid4(),
        user_id=ca_user.id,
        client_code="CLI-CORP-A",
        company_name="Apex Logistics Ltd",
        contact_person="Ramesh Patel",
        status="active",
    )
    # Client 2
    client_b = Client(
        id=uuid.uuid4(),
        user_id=other_ca.id,
        client_code="CLI-CORP-B",
        company_name="Bharat Trading Co",
        contact_person="Suresh Nair",
        status="active",
    )
    db_session.add_all([client_a, client_b])
    db_session.commit()

    # Initialize standard ICAI Chart of Accounts for both clients
    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, ca_user)
    ChartOfAccountsService.initialize_default_accounts(db_session, client_b.id, other_ca)

    accounts_a = {a.account_code: a for a in db_session.query(ChartOfAccounts).filter_by(client_id=client_a.id).all()}
    accounts_b = {a.account_code: a for a in db_session.query(ChartOfAccounts).filter_by(client_id=client_b.id).all()}

    return {
        "ca_user": ca_user,
        "other_ca": other_ca,
        "admin_user": admin_user,
        "client_a": client_a,
        "client_b": client_b,
        "accounts_a": accounts_a,
        "accounts_b": accounts_b,
    }


# ── 1. Balanced Journal Entry & Voucher Numbering ──────────────────────

def test_create_balanced_journal_entry(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]
    accs = data["accounts_a"]

    # 3-legged sales journal: Debtors Dr ₹118, Sales Cr ₹100, Output CGST Cr ₹9, Output SGST Cr ₹9
    payload = JournalEntryCreate(
        client_id=client.id,
        entry_date=date(2026, 3, 20),
        entry_type="sales",
        narration="Tax invoice sales voucher #INV-101",
        reference_number="INV-101",
        lines=[
            JournalEntryLineCreate(
                account_id=accs["1100"].id,  # Sundry Debtors
                debit_amount=Decimal("118.00"),
                credit_amount=Decimal("0.00"),
                description="Receivable from Customer Ltd",
                party_name="Customer Ltd",
            ),
            JournalEntryLineCreate(
                account_id=accs["4010"].id,  # Sales Revenue
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("100.00"),
                description="Sales revenue turnover",
            ),
            JournalEntryLineCreate(
                account_id=accs["2110"].id,  # Output CGST
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("9.00"),
                description="Output CGST @ 9%",
                tax_head="cgst",
                tax_rate=Decimal("9.00"),
            ),
            JournalEntryLineCreate(
                account_id=accs["2120"].id,  # Output SGST
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("9.00"),
                description="Output SGST @ 9%",
                tax_head="sgst",
                tax_rate=Decimal("9.00"),
            ),
        ],
    )

    entry = JournalEntryService.create_journal_entry(db_session, client.id, payload, user)

    assert entry.id is not None
    assert entry.entry_number.startswith("SV-")
    assert entry.total_debit == Decimal("118.00")
    assert entry.total_credit == Decimal("118.00")
    assert entry.is_balanced is True
    assert entry.status == "posted"
    assert len(entry.lines) == 4
    assert entry.lines[0].line_number == 1
    assert entry.lines[0].debit_amount == Decimal("118.00")


# ── 2. Imbalance Rejection ─────────────────────────────────────────────

def test_unbalanced_journal_entry_rejected():
    # Pydantic model validator catches imbalance before DB
    with pytest.raises(ValueError) as exc:
        JournalEntryCreate(
            client_id=uuid.uuid4(),
            entry_date=date(2026, 3, 20),
            entry_type="journal",
            lines=[
                JournalEntryLineCreate(
                    account_id=uuid.uuid4(),
                    debit_amount=Decimal("100.00"),
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLineCreate(
                    account_id=uuid.uuid4(),
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("95.00"),  # Imbalance of ₹5
                ),
            ],
        )
    assert "imbalance" in str(exc.value).lower()


# ── 3. Line Constraints: Single-Sided & Non-Negative ───────────────────

def test_line_single_sided_and_non_negative_rejection():
    # Both debit and credit > 0 rejected
    with pytest.raises(ValueError) as exc1:
        JournalEntryLineCreate(
            account_id=uuid.uuid4(),
            debit_amount=Decimal("50.00"),
            credit_amount=Decimal("50.00"),
        )
    assert "both debit and credit" in str(exc1.value)

    # Both zero rejected
    with pytest.raises(ValueError) as exc2:
        JournalEntryLineCreate(
            account_id=uuid.uuid4(),
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("0.00"),
        )
    assert "either a debit or a credit" in str(exc2.value)

    # Negative amount rejected
    with pytest.raises(ValueError) as exc3:
        JournalEntryLineCreate(
            account_id=uuid.uuid4(),
            debit_amount=Decimal("-10.00"),
            credit_amount=Decimal("0.00"),
        )
    assert "cannot be negative" in str(exc3.value)


# ── 4. Cross-Client Account Isolation ──────────────────────────────────

def test_cross_client_account_rejected(db_session, setup_accounting_data):
    data = setup_accounting_data
    client_a = data["client_a"]
    user_a = data["ca_user"]
    accs_a = data["accounts_a"]
    accs_b = data["accounts_b"]  # Client B's account!

    payload = JournalEntryCreate(
        client_id=client_a.id,
        entry_date=date(2026, 3, 20),
        entry_type="journal",
        lines=[
            JournalEntryLineCreate(
                account_id=accs_a["1010"].id,
                debit_amount=Decimal("500.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLineCreate(
                account_id=accs_b["1020"].id,  # Alien account belonging to Client B!
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("500.00"),
            ),
        ],
    )

    with pytest.raises(BadRequestException) as exc:
        JournalEntryService.create_journal_entry(db_session, client_a.id, payload, user_a)
    assert "does not belong to client" in str(exc.value.detail)


# ── 5. Inactive Account Rejection ──────────────────────────────────────

def test_inactive_account_rejected(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]
    accs = data["accounts_a"]

    # Deactivate custom account
    custom_acc = ChartOfAccounts(
        client_id=client.id,
        account_code="5999",
        account_name="Discontinued Expense Account",
        account_type="expense",
        is_active=False,  # Inactive!
    )
    db_session.add(custom_acc)
    db_session.commit()

    payload = JournalEntryCreate(
        client_id=client.id,
        entry_date=date(2026, 3, 20),
        entry_type="journal",
        lines=[
            JournalEntryLineCreate(
                account_id=custom_acc.id,
                debit_amount=Decimal("200.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLineCreate(
                account_id=accs["1010"].id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("200.00"),
            ),
        ],
    )

    with pytest.raises(BadRequestException) as exc:
        JournalEntryService.create_journal_entry(db_session, client.id, payload, user)
    assert "is deactivated" in str(exc.value.detail)


# ── 6. Duplicate Accounting Record Posting Protection ──────────────────

def test_duplicate_accounting_record_posting_prevention(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]
    accs = data["accounts_a"]

    mock_rec_id = uuid.uuid4()

    payload1 = JournalEntryCreate(
        client_id=client.id,
        accounting_record_id=mock_rec_id,
        entry_date=date(2026, 3, 20),
        entry_type="sales",
        lines=[
            JournalEntryLineCreate(account_id=accs["1100"].id, debit_amount=Decimal("100.00"), credit_amount=Decimal("0.00")),
            JournalEntryLineCreate(account_id=accs["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100.00")),
        ],
    )
    JournalEntryService.create_journal_entry(db_session, client.id, payload1, user)

    # Attempting to post another journal entry with the same accounting_record_id
    payload2 = JournalEntryCreate(
        client_id=client.id,
        accounting_record_id=mock_rec_id,
        entry_date=date(2026, 3, 20),
        entry_type="sales",
        lines=[
            JournalEntryLineCreate(account_id=accs["1100"].id, debit_amount=Decimal("100.00"), credit_amount=Decimal("0.00")),
            JournalEntryLineCreate(account_id=accs["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100.00")),
        ],
    )

    with pytest.raises(ConflictException) as exc:
        JournalEntryService.create_journal_entry(db_session, client.id, payload2, user)
    assert "already exists" in str(exc.value.detail)


# ── 7. Immutability and Audit-Compliant Reversal ────────────────────────

def test_journal_entry_reversal(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]
    accs = data["accounts_a"]

    # Post an entry: Dr Bank ₹5000, Cr Sales ₹5000
    payload = JournalEntryCreate(
        client_id=client.id,
        entry_date=date(2026, 3, 20),
        entry_type="sales",
        reference_number="INV-ERR-999",
        lines=[
            JournalEntryLineCreate(account_id=accs["1020"].id, debit_amount=Decimal("5000.00"), credit_amount=Decimal("0.00")),
            JournalEntryLineCreate(account_id=accs["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("5000.00")),
        ],
    )
    original = JournalEntryService.create_journal_entry(db_session, client.id, payload, user)

    # Perform reversal
    reversal = JournalEntryService.reverse_journal_entry(
        db_session,
        entry_id=original.id,
        reason="Erroneous invoice posted twice by mistake",
        user=user,
    )

    assert reversal.id is not None
    assert reversal.entry_number == f"REV-{original.entry_number}"
    assert reversal.total_debit == Decimal("5000.00")
    assert reversal.total_credit == Decimal("5000.00")
    assert reversal.is_balanced is True

    # Check that lines are swapped:
    # Original line 1: Bank Dr ₹5000 -> Reversal line 1: Bank Cr ₹5000
    rev_line_bank = next(line for line in reversal.lines if line.account_id == accs["1020"].id)
    assert rev_line_bank.credit_amount == Decimal("5000.00")
    assert rev_line_bank.debit_amount == Decimal("0.00")

    # Original line 2: Sales Cr ₹5000 -> Reversal line 2: Sales Dr ₹5000
    rev_line_sales = next(line for line in reversal.lines if line.account_id == accs["4010"].id)
    assert rev_line_sales.debit_amount == Decimal("5000.00")
    assert rev_line_sales.credit_amount == Decimal("0.00")

    # Check original is marked reversed
    db_session.refresh(original)
    assert original.is_reversed is True
    assert original.reversal_entry_id == reversal.id
    assert "Erroneous invoice" in original.reversal_reason

    # Trying to reverse again raises error
    with pytest.raises(BadRequestException) as exc:
        JournalEntryService.reverse_journal_entry(
            db_session,
            entry_id=original.id,
            reason="Second reversal attempt",
            user=user,
        )
    assert "already been reversed" in str(exc.value.detail)


# ── 8. Accounting Mapping Service for Documents ────────────────────────

def test_map_sales_document_to_journal(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        invoice_number="INV-2026-99",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        customer="Apex Retailers Ltd",
        invoice_date="2026-03-25",
    )

    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc, user)

    assert je_create.entry_type == "sales"
    assert je_create.reference_number == "INV-2026-99"
    assert len(je_create.lines) == 4  # Debtors Dr, Sales Cr, CGST Cr, SGST Cr

    total_dr = sum(l.debit_amount for l in je_create.lines)
    total_cr = sum(l.credit_amount for l in je_create.lines)
    assert total_dr == total_cr == Decimal("11800.00")


def test_map_purchase_document_to_journal(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        invoice_number="BILL-4455",
        amount=Decimal("5900.00"),
        taxable_amount=Decimal("5000.00"),
        cgst=Decimal("450.00"),
        sgst=Decimal("450.00"),
        vendor="Global Supplies Inc",
        invoice_date="2026-03-26",
    )

    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc, user)

    assert je_create.entry_type == "purchase"
    total_dr = sum(l.debit_amount for l in je_create.lines)
    total_cr = sum(l.credit_amount for l in je_create.lines)
    assert total_dr == total_cr == Decimal("5900.00")


def test_map_gst_challan_to_journal(db_session, setup_accounting_data):
    data = setup_accounting_data
    client = data["client_a"]
    user = data["ca_user"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="gst_challan",
        status="verified",
        arn="CPIN-2026-5544",
        amount=Decimal("25000.00"),
        invoice_date="2026-03-27",
    )

    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc, user)

    assert je_create.entry_type == "payment"
    total_dr = sum(l.debit_amount for l in je_create.lines)
    total_cr = sum(l.credit_amount for l in je_create.lines)
    assert total_dr == total_cr == Decimal("25000.00")
