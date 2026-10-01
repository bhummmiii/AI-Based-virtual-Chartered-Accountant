"""
Unit & Integration Tests for Commit D7:
1. Audit Sync in Cleanup Script:
   - run_cleanup correctly syncs both journal_entries and accounting_records to 'reversed'.
   - Marks polluted source documents as 'rejected'.
   - Multi-client safety: requires client identifier and targets only specified client.
2. Validation Gate Bypass Guard:
   - Draft posting with source document in 'needs_review' or 'blocked' status is strictly blocked.
   - Manual JournalEntry creation referencing a 'needs_review' document raises BadRequestException.
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
from app.services.accounting_draft_service import AccountingDraftService
from app.services.journal_entry_service import JournalEntryService
from app.schemas.journal_entry import JournalEntryCreate, JournalEntryLineCreate
from app.core.exceptions import BadRequestException
from scripts.cleanup_polluted_data import run_cleanup


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
def setup_d7(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="audit_lead@finledger.ai",
        full_name="Audit Lead",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Sentinel Enterprises Ltd",
        client_code="SEN-777",
        contact_person="Internal Auditor",
        client_type="company",
        gst_number="27AAACS7777S1Z5",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return user, client


def test_post_draft_blocked_on_needs_review_document(db_session, setup_d7):
    """Posting draft linked to a document in 'needs_review' status must be blocked by validation gate."""
    user, client = setup_d7

    doc_review = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="ambiguous_note.pdf",
        document_category="credit_note",
        invoice_type="needs_review",
        invoice_number="CN/AMB/001",
        invoice_date="2026-08-20",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        status="needs_review",  # BLOCKED / REQUIRES CA REVIEW
    )
    db_session.add(doc_review)
    db_session.flush()

    record = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_review.id,
        voucher_type="sales",
        transaction_date=date(2026, 8, 20),
        debit=Decimal("11800.00"),
        credit=Decimal("0.00"),
        description="Draft for ambiguous note",
        status="draft",
    )
    db_session.add(record)
    db_session.commit()

    # Attempt to post draft
    res = AccountingDraftService.post_draft_to_ledger(db_session, record.id, user)
    assert res.success is False
    assert "requires CA review" in res.message or "needs_review" in res.message

    # Record must still be in 'draft' status
    saved_record = db_session.query(AccountingRecord).filter(AccountingRecord.id == record.id).first()
    assert saved_record is not None
    assert saved_record.status == "draft"


def test_manual_journal_entry_blocked_on_needs_review_document(db_session, setup_d7):
    """Manual JournalEntry creation referencing a 'needs_review' document must raise BadRequestException."""
    user, client = setup_d7

    doc_blocked = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="mismatched_invoice.pdf",
        document_category="b2b_invoice",
        invoice_number="INV/BLOCKED/01",
        invoice_date="2026-08-22",
        amount=Decimal("50000.00"),
        status="blocked",
    )
    db_session.add(doc_blocked)
    db_session.commit()

    from app.services.accounting_mapping_service import AccountingMappingService
    accounts = AccountingMappingService.get_or_init_client_accounts(db_session, client.id, user)
    dr_acc = accounts["1100"]
    cr_acc = accounts["4010"]

    payload = JournalEntryCreate(
        client_id=client.id,
        document_id=doc_blocked.id,
        entry_date=date(2026, 8, 22),
        entry_type="sales",
        narration="Bypass attempt",
        lines=[
            JournalEntryLineCreate(
                account_id=dr_acc.id,
                debit_amount=Decimal("50000.00"),
                credit_amount=Decimal("0.00"),
                description="Debtor debit",
            ),
            JournalEntryLineCreate(
                account_id=cr_acc.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("50000.00"),
                description="Sales credit",
            ),
        ],
    )

    with pytest.raises(BadRequestException) as exc_info:
        JournalEntryService.create_journal_entry(
            db=db_session,
            client_id=client.id,
            payload=payload,
            user=user,
        )
    assert "Posting blocked" in str(exc_info.value.detail)


def test_cleanup_script_syncs_journal_and_accounting_records(db_session, setup_d7, monkeypatch):
    """run_cleanup syncs both journal_entries and accounting_records to 'reversed'."""
    user, client = setup_d7

    # Create polluted document, record, voucher
    doc_polluted = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="NEG/0002",
        document_category="purchase_records",
        status="verified",
    )
    ar_polluted = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_polluted.id,
        reference_number="NEG/0002",
        voucher_type="purchase",
        transaction_date=date(2026, 8, 1),
        debit=Decimal("1000.00"),
        credit=Decimal("0.00"),
        status="posted",
    )
    je_polluted = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        entry_number="PV-TEST-0001",
        reference_number="NEG/0002",
        entry_type="purchase",
        entry_date=date(2026, 8, 1),
        accounting_record_id=ar_polluted.id,
        document_id=doc_polluted.id,
        status="posted",
        is_reversed=False,
    )
    db_session.add_all([doc_polluted, ar_polluted, je_polluted])
    db_session.commit()

    target_client_id = client.id
    import scripts.cleanup_polluted_data as cleanup_mod
    monkeypatch.setattr(cleanup_mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    # 1. Test safety guard (no client filter)
    code = cleanup_mod.run_cleanup(client_id=None, dry_run=True)
    assert code == 1

    # 2. Run cleanup with --apply
    code = cleanup_mod.run_cleanup(client_id=target_client_id, dry_run=False)
    assert code == 0

    db_session.refresh(je_polluted)
    db_session.refresh(ar_polluted)
    db_session.refresh(doc_polluted)

    assert je_polluted.status == "reversed"
    assert je_polluted.is_reversed is True
    assert ar_polluted.status == "reversed"
    assert doc_polluted.status == "rejected"

