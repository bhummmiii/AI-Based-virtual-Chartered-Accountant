"""
Unit and Integration Tests for Phase 5: Receipts, Payments, Contra, and Outstanding Balances.
Tests:
1. Customer receipt recording, double-entry creation (Dr Bank, Cr Debtors), and AR outstanding reduction.
2. Supplier payment recording, double-entry creation (Dr Creditors, Cr Bank), and AP outstanding reduction.
3. Contra cash/bank liquidity transfers.
4. Aging calculation (0-30, 31-60, 61-90, 90+ days) for receivables and payables.
5. Closed period protection preventing receipts/payments in locked fiscal periods.
"""

import sys
import os
import uuid
import pytest
from datetime import date, datetime, timedelta
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
from app.services.voucher_service import VoucherService
from app.services.trial_balance_service import TrialBalanceService
from app.schemas.voucher_management import (
    CustomerReceiptCreate,
    SupplierPaymentCreate,
    ContraVoucherCreate,
)
from app.schemas.trial_balance import AccountingPeriodCreate
from app.core.exceptions import BadRequestException


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
def voucher_test_setup(db_session):
    """Set up test client, user, and default Chart of Accounts."""
    user = User(
        id=uuid.uuid4(),
        email="ca_vm@example.com",
        password_hash="secret",
        full_name="CA Manager",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-VM-01",
        company_name="Horizon Retail Ltd",
        contact_person="Anita Rao",
        status="active",
    )
    db_session.add_all([user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return {"user": user, "client": client}


def test_customer_receipt_reduces_receivables(db_session, voucher_test_setup):
    """Test customer receipt records Dr Bank / Cr Debtors and reduces net outstanding balance."""
    data = voucher_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Post Sales Invoice of ₹5,000
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("5000.00"),
        customer="Alpha Global Corp",
        invoice_number="INV-AG-01",
        invoice_date="2026-06-01",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        transaction_date=date(2026, 6, 1),
        voucher_type="sales",
        description="Sales invoice",
        debit=Decimal("0.00"),
        credit=Decimal("5000.00"),
        status="draft",
        reference_number="INV-AG-01",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    # Verify initial outstanding is ₹5,000
    report_before = VoucherService.get_outstanding_receivables(
        db=db_session, client_id=client.id, user=user, as_of_date=date(2026, 6, 30)
    )
    assert report_before.total_outstanding == Decimal("5000.00")

    # 2. Record Customer Receipt of ₹3,000 into Bank (1020)
    receipt_payload = CustomerReceiptCreate(
        client_id=client.id,
        receipt_date=date(2026, 6, 15),
        amount=Decimal("3000.00"),
        customer_name="Alpha Global Corp",
        bank_or_cash_account_code="1020",
        reference_number="NEFT-REC-001",
        allocated_document_id=doc.id,
        narration="NEFT Part Payment from Alpha Global",
    )
    receipt_je = VoucherService.record_customer_receipt(db_session, receipt_payload, user)

    assert receipt_je.is_balanced is True
    assert receipt_je.entry_type == "receipt"
    assert len(receipt_je.lines) == 2

    bank_line = next(l for l in receipt_je.lines if l.debit_amount > Decimal("0.00"))
    assert bank_line.debit_amount == Decimal("3000.00")

    debtor_line = next(l for l in receipt_je.lines if l.credit_amount > Decimal("0.00"))
    assert debtor_line.credit_amount == Decimal("3000.00")
    assert debtor_line.party_name == "Alpha Global Corp"

    # 3. Check updated outstanding report
    report_after = VoucherService.get_outstanding_receivables(
        db=db_session, client_id=client.id, user=user, as_of_date=date(2026, 6, 30)
    )
    assert report_after.total_invoiced == Decimal("5000.00")
    assert report_after.total_settled == Decimal("3000.00")
    assert report_after.total_outstanding == Decimal("2000.00")

    party_item = next(p for p in report_after.parties if p.party_name == "Alpha Global Corp")
    assert party_item.net_outstanding == Decimal("2000.00")


def test_supplier_payment_reduces_payables(db_session, voucher_test_setup):
    """Test supplier payment records Dr Creditors / Cr Bank and clears net payables."""
    data = voucher_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Post Purchase Bill of ₹4,000
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        amount=Decimal("4000.00"),
        vendor="Beta Steel Works",
        invoice_number="BILL-BSW-01",
        invoice_date="2026-06-05",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        transaction_date=date(2026, 6, 5),
        voucher_type="purchase",
        description="Purchase bill",
        debit=Decimal("4000.00"),
        credit=Decimal("0.00"),
        status="draft",
        reference_number="BILL-BSW-01",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    # 2. Record full payment of ₹4,000 from Bank (1020)
    payment_payload = SupplierPaymentCreate(
        client_id=client.id,
        payment_date=date(2026, 6, 20),
        amount=Decimal("4000.00"),
        vendor_name="Beta Steel Works",
        bank_or_cash_account_code="1020",
        reference_number="RTGS-PAY-001",
        allocated_document_id=doc.id,
        narration="Full settlement of bill BILL-BSW-01",
    )
    payment_je = VoucherService.record_supplier_payment(db_session, payment_payload, user)

    assert payment_je.is_balanced is True
    assert payment_je.entry_type == "payment"

    # 3. Check updated payables report: net outstanding must be 0
    payables_report = VoucherService.get_outstanding_payables(
        db=db_session, client_id=client.id, user=user, as_of_date=date(2026, 6, 30)
    )
    assert payables_report.total_invoiced == Decimal("4000.00")
    assert payables_report.total_settled == Decimal("4000.00")
    assert payables_report.total_outstanding == Decimal("0.00")


def test_contra_cash_and_bank_transfer(db_session, voucher_test_setup):
    """Test contra voucher transfers liquidity between Bank (1020) and Cash (1010)."""
    data = voucher_test_setup
    client = data["client"]
    user = data["user"]

    contra_payload = ContraVoucherCreate(
        client_id=client.id,
        voucher_date=date(2026, 6, 10),
        amount=Decimal("1500.00"),
        from_account_code="1020",  # Bank
        to_account_code="1010",    # Cash
        reference_number="CHQ-CASH-WITHDRAW",
        narration="Cash withdrawal for office petty expenses",
    )
    je = VoucherService.record_contra_voucher(db_session, contra_payload, user)

    assert je.is_balanced is True
    assert je.entry_type == "contra"
    assert len(je.lines) == 2

    # Dr Cash (1010), Cr Bank (1020)
    dr_line = next(l for l in je.lines if l.debit_amount > Decimal("0.00"))
    assert dr_line.debit_amount == Decimal("1500.00")
    assert dr_line.account.account_code == "1010"

    cr_line = next(l for l in je.lines if l.credit_amount > Decimal("0.00"))
    assert cr_line.credit_amount == Decimal("1500.00")
    assert cr_line.account.account_code == "1020"

    # Reject identical from/to accounts
    invalid_contra = ContraVoucherCreate(
        client_id=client.id,
        voucher_date=date(2026, 6, 10),
        amount=Decimal("100.00"),
        from_account_code="1010",
        to_account_code="1010",
    )
    with pytest.raises(BadRequestException):
        VoucherService.record_contra_voucher(db_session, invalid_contra, user)


def test_ar_aging_buckets(db_session, voucher_test_setup):
    """Test aging bucket allocation (0-30, 31-60, 61-90, 90+ days)."""
    data = voucher_test_setup
    client = data["client"]
    user = data["user"]
    today = date(2026, 6, 30)

    # Invoice 1: 15 days ago -> 0-30 days bucket
    doc1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1000.00"),
        customer="Client A",
        invoice_number="INV-30",
        invoice_date="2026-06-15",
    )
    # Invoice 2: 45 days ago -> 31-60 days bucket
    doc2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("2000.00"),
        customer="Client A",
        invoice_number="INV-60",
        invoice_date="2026-05-16",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    draft1 = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc1.id,
        transaction_date=date(2026, 6, 15), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1000.00"), status="draft",
        reference_number="INV-30",
    )
    draft2 = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc2.id,
        transaction_date=date(2026, 5, 16), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("2000.00"), status="draft",
        reference_number="INV-60",
    )
    db_session.add_all([draft1, draft2])
    db_session.commit()

    AccountingDraftService.post_draft_to_ledger(db_session, draft1.id, user=user)
    AccountingDraftService.post_draft_to_ledger(db_session, draft2.id, user=user)

    report = VoucherService.get_outstanding_receivables(db_session, client.id, user, as_of_date=today)
    assert report.total_outstanding == Decimal("3000.00")
    assert report.aging_0_30_total == Decimal("1000.00")
    assert report.aging_31_60_total == Decimal("2000.00")


def test_receipt_blocked_by_closed_period(db_session, voucher_test_setup):
    """Test that recording receipt in a closed period is strictly rejected."""
    data = voucher_test_setup
    client = data["client"]
    user = data["user"]

    period = TrialBalanceService.create_period(
        db=db_session,
        client_id=client.id,
        user=user,
        payload=AccountingPeriodCreate(
            period_name="Locked Month May 2026",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
        ),
    )
    TrialBalanceService.close_period(db=db_session, client_id=client.id, period_id=period.id, user=user)

    payload = CustomerReceiptCreate(
        client_id=client.id,
        receipt_date=date(2026, 5, 20),
        amount=Decimal("500.00"),
        customer_name="Any Customer",
    )
    with pytest.raises(BadRequestException):
        VoucherService.record_customer_receipt(db_session, payload, user)
