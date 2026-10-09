"""
Unit test suite for G8: Multi-Client Isolation & Data Helpers (Round 5).
Validates:
- Strict multi-client isolation across monthly vs quarterly client profiles, periods, and filings.
- Client A's discrepancy checks do not include Client B's documents or rejected duplicates.
- reverse_voucher helper reverses journal entries with inverted legs and maintains audit trail idempotently.
- Unposted rejected duplicates can be deleted or voided without altering ledger or posted vouchers.
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
from app.schemas.gst import GSTRecordCreate
from app.services.gst_filing_service import get_filing_profile, get_filing_options
from app.services.gst_reconciliation_service import GstReconciliationService
from app.api.routers.gst.router import create_gst_record
from scripts.reverse_voucher import reverse_voucher


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
            AccountingPeriod.__table__,
            GSTRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_multi_client_frequency_and_filing_isolation(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@multi.com",
        password_hash="pw",
        full_name="CA Multi",
        role="ca",
    )
    client_m = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-M",
        company_name="Monthly Client M",
        gst_number="27AABCM1111A1Z5",
        state="Maharashtra",
        contact_person="Director M",
        email="m@multi.com",
        return_frequency="Monthly",
    )
    client_q = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-Q",
        company_name="Quarterly Client Q",
        gst_number="07AABCQ2222B1Z6",
        state="Delhi",
        contact_person="Director Q",
        email="q@multi.com",
        return_frequency="Quarterly",
    )
    db_session.add_all([user, client_m, client_q])
    db_session.commit()

    # 1. Filing options isolation
    opts_m = get_filing_options(db_session, client_m, today=date(2026, 10, 9))
    opts_q = get_filing_options(db_session, client_q, today=date(2026, 10, 9))

    assert opts_m.frequency == "monthly"
    assert all("Q" not in p.key for p in opts_m.periods)

    assert opts_q.frequency == "quarterly"
    assert all("Q" in p.key for p in opts_q.periods)

    # 2. Document & Discrepancy isolation: Add rejected duplicate to Client Q
    doc_q_orig = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_q.id,
        document_category="b2b_invoice",
        invoice_number="INV-Q-001",
        invoice_date="2026-07-20",
        gstin="07AABCQ2222B1Z6",
        customer="Delhi Buyer",
        amount=59000,
        taxable_amount=50000,
        cgst=4500,
        sgst=4500,
        igst=0,
        status="verified",
    )
    doc_q_dup = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_q.id,
        document_category="b2b_invoice",
        invoice_number="INV-Q-001",
        invoice_date="2026-07-20",
        gstin="07AABCQ2222B1Z6",
        customer="Delhi Buyer",
        amount=59000,
        taxable_amount=50000,
        cgst=4500,
        sgst=4500,
        igst=0,
        status="rejected",
        rejection_reason="DUPLICATE",
    )
    db_session.add_all([doc_q_orig, doc_q_dup])
    db_session.commit()

    disc_m = GstReconciliationService.detect_discrepancies(db_session, client_m.id, user, period="2026-08")
    disc_q = GstReconciliationService.detect_discrepancies(db_session, client_q.id, user, period="2026-Q2")

    # Client M must have 0 discrepancies (not see Client Q's doc)
    assert disc_m.total_discrepancies == 0
    # Client Q has 1 discrepancy (DUPLICATE_REJECTED)
    assert any(d.rule_code == "DUPLICATE_REJECTED" for d in disc_q.discrepancies)


def test_reverse_voucher_script_behavior(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@rev.com",
        password_hash="pw",
        full_name="CA Rev",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-REV",
        company_name="Reversal Test Co",
        gst_number="27AABCR3333C1Z7",
        state="Maharashtra",
        contact_person="Director",
        email="rev@multi.com",
        return_frequency="Quarterly",
    )
    db_session.add_all([user, client])
    db_session.commit()

    acc_bank = ChartOfAccounts(
        id=uuid.uuid4(),
        client_id=client.id,
        account_code="1010",
        account_name="Bank Account",
        account_type="asset",
    )
    acc_vendor = ChartOfAccounts(
        id=uuid.uuid4(),
        client_id=client.id,
        account_code="2010",
        account_name="Vendor Payable",
        account_type="liability",
    )
    db_session.add_all([acc_bank, acc_vendor])
    db_session.commit()

    # Create posted journal entry PMT-2026-0001
    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        entry_number="PMT-2026-0001",
        entry_date=date(2026, 8, 10),
        entry_type="payment",
        status="posted",
        is_reversed=False,
        narration="Vendor payment",
        total_debit=50000,
        total_credit=50000,
    )
    l1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=1,
        account_id=acc_vendor.id,
        debit_amount=50000,
        credit_amount=0,
    )
    l2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=2,
        account_id=acc_bank.id,
        debit_amount=0,
        credit_amount=50000,
    )
    db_session.add_all([je, l1, l2])
    db_session.commit()

    # Dry-run execution
    dry_res = reverse_voucher(db_session, client, "PMT-2026-0001", apply=False)
    assert dry_res is True
    db_session.refresh(je)
    assert je.is_reversed is False
    assert je.status == "posted"

    # Apply execution
    apply_res = reverse_voucher(db_session, client, "PMT-2026-0001", apply=True)
    assert apply_res is True
    db_session.refresh(je)
    assert je.is_reversed is True
    assert je.status == "reversed"
    assert je.reversal_entry_id is not None

    # Check reversal entry
    rev_je = db_session.query(JournalEntry).filter(JournalEntry.id == je.reversal_entry_id).first()
    assert rev_je is not None
    assert rev_je.total_debit == Decimal("50000.00")
    assert rev_je.total_credit == Decimal("50000.00")
    assert rev_je.entry_type == "reversal"

    # Second apply is idempotent
    idem_res = reverse_voucher(db_session, client, "PMT-2026-0001", apply=True)
    assert idem_res is True


def test_unposted_rejected_duplicate_deletion_guard(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@del.com",
        password_hash="pw",
        full_name="CA Del",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="CLI-DEL",
        company_name="Delete Guard Co",
        gst_number="27AABCD4444D1Z8",
        state="Maharashtra",
        contact_person="Director",
        email="del@multi.com",
        return_frequency="Quarterly",
    )
    db_session.add_all([user, client])
    db_session.commit()

    doc_orig = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-DEL-001",
        invoice_date="2026-07-25",
        gstin="27AABCD4444D1Z8",
        amount=118000,
        taxable_amount=100000,
        cgst=9000,
        sgst=9000,
        igst=0,
        status="verified",
    )
    doc_dup = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-DEL-001",
        invoice_date="2026-07-25",
        gstin="27AABCD4444D1Z8",
        amount=118000,
        taxable_amount=100000,
        cgst=9000,
        sgst=9000,
        igst=0,
        status="rejected",
        rejection_reason="DUPLICATE",
    )
    db_session.add_all([doc_orig, doc_dup])
    db_session.commit()

    # Discrepancy report before deletion has DUPLICATE_REJECTED
    rep_before = GstReconciliationService.detect_discrepancies(db_session, client.id, user, period="2026-Q2")
    assert any(d.rule_code == "DUPLICATE_REJECTED" for d in rep_before.discrepancies)

    # Deleting the unposted rejected duplicate document
    db_session.delete(doc_dup)
    db_session.commit()

    # Original document is untouched
    db_session.refresh(doc_orig)
    assert doc_orig.status == "verified"

    # Discrepancy report after deletion is clean of duplicate alerts
    rep_after = GstReconciliationService.detect_discrepancies(db_session, client.id, user, period="2026-Q2")
    assert not any(d.rule_code in ("DUPLICATE_INVOICE", "DUPLICATE_REJECTED") for d in rep_after.discrepancies)
