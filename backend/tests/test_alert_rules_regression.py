"""
Unit and regression tests for F9:
Discrepancy rule set hardening & future dated payment alerts.

Verifies:
1. Payment vouchers (template='PAYMENT' or entry_type='payment') are excluded from LEGACY_VOUCHER_NO_TAX_LINES.
2. Future-dated payment vouchers (entry_date > date.today()) raise FUTURE_DATED_PAYMENT (MEDIUM, non-blocking).
3. Non-future dated payment vouchers trigger 0 discrepancies.
4. Non-blocking nature: high_count is 0 for future-dated payments.
"""

import uuid
from decimal import Decimal
from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_record import AccountingRecord
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService


@pytest.fixture
def db_session():
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
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_payment_voucher_discrepancy_hardening(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-F9",
        company_name="Alert Rule Hardening Ltd",
        gst_number="27AABCA9999A1Z9",
        return_frequency="Quarterly",
        contact_person="Director",
    )
    user = User(
        id=user_id,
        email="test@f9.com",
        full_name="Tester",
        password_hash="hash",
        role="admin",
    )
    db_session.add_all([client, user])
    db_session.flush()

    coa_service = ChartOfAccountsService()
    coa_service.initialize_default_accounts(db_session, client_id, user)
    accounts = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
    acc_map = {a.account_code: a for a in accounts}

    # 1. Past Payment Voucher (Yesterday)
    doc_past = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="past_challan.pdf",
        file_path="/dummy/past_challan.pdf",
        status="verified",
        document_category="gst_challan",
        invoice_number="CHL-PAST",
        invoice_date=str(date.today() - timedelta(days=5)),
        amount=Decimal("10000.00"),
        taxable_amount=Decimal("10000.00"),
    )
    db_session.add(doc_past)
    db_session.flush()

    je_past = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_past.id,
        entry_number="PMT-PAST-001",
        entry_date=date.today() - timedelta(days=5),
        entry_type="payment",
        voucher_template="PAYMENT",
        status="posted",
        total_debit=Decimal("10000.00"),
        total_credit=Decimal("10000.00"),
    )
    db_session.add(je_past)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_past.id, account_id=acc_map["2010"].id, debit_amount=Decimal("10000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_past.id, account_id=acc_map["1010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("10000.00"), line_number=2),
    ])

    # 2. Future-Dated Payment Voucher (10 days in future)
    future_date = date.today() + timedelta(days=10)
    doc_future = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="future_challan.pdf",
        file_path="/dummy/future_challan.pdf",
        status="verified",
        document_category="gst_challan",
        invoice_number="CHL-FUTURE",
        invoice_date=str(future_date),
        amount=Decimal("25000.00"),
        taxable_amount=Decimal("25000.00"),
    )
    db_session.add(doc_future)
    db_session.flush()

    je_future = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_future.id,
        entry_number="PMT-FUTURE-001",
        entry_date=future_date,
        entry_type="payment",
        voucher_template="PAYMENT",
        status="posted",
        total_debit=Decimal("25000.00"),
        total_credit=Decimal("25000.00"),
    )
    db_session.add(je_future)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_future.id, account_id=acc_map["2010"].id, debit_amount=Decimal("25000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_future.id, account_id=acc_map["1010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("25000.00"), line_number=2),
    ])
    db_session.commit()

    # Detect discrepancies for all periods
    disc_report = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="all")

    # Verify no LEGACY_VOUCHER_NO_TAX_LINES raised
    legacy_alerts = [d for d in disc_report.discrepancies if d.rule_code == "LEGACY_VOUCHER_NO_TAX_LINES"]
    assert len(legacy_alerts) == 0

    # Verify FUTURE_DATED_PAYMENT raised for PMT-FUTURE-001
    future_alerts = [d for d in disc_report.discrepancies if d.rule_code == "FUTURE_DATED_PAYMENT"]
    assert len(future_alerts) == 1
    assert future_alerts[0].severity == "MEDIUM"
    assert future_alerts[0].voucher_id == je_future.id

    # Verify high_count is 0 (non-blocking)
    assert disc_report.high_count == 0
    assert disc_report.medium_count == 1
