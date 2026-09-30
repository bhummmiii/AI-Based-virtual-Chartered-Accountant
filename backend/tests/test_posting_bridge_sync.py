"""
Unit and Integration Tests for Step 2B: Dual-Layer Bridge Integration & Posting Synchronization.

Tests:
1. Atomic posting: post_draft_to_ledger creates both AccountingRecord (status=posted) and JournalEntry + lines.
2. Source document traceability: JournalEntry links back to uploaded_document and accounting_record.
3. Idempotency & duplicate protection: calling post on an already posted record returns existing data without duplicates.
4. Authorization enforcement: unauthorized CA user cannot post drafts for another CA's client.
5. Legacy voucher preservation: historical records without journal entries query cleanly.
6. Bulk post synchronization: multiple drafts post atomically with persistent journal entries.
7. Manual voucher posting: manual accounting records without document_id post to balanced journal entries.
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
from app.services.accounting_draft_service import AccountingDraftService
from app.core.exceptions import ForbiddenException


@pytest.fixture
def db_session():
    """Isolated, in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Exclude AccountingRecord index collision in SQLite if present, or create required tables
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
def setup_sync_data(db_session):
    """Seed test users, clients, Chart of Accounts, and verified documents."""
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

    # Client A (owned by ca_user)
    client_a = Client(
        id=uuid.uuid4(),
        user_id=ca_user.id,
        client_code="CLI-A",
        company_name="Apex Logistics Ltd",
        contact_person="Ramesh Patel",
        status="active",
    )
    # Client B (owned by other_ca)
    client_b = Client(
        id=uuid.uuid4(),
        user_id=other_ca.id,
        client_code="CLI-B",
        company_name="Bharat Trading Co",
        contact_person="Suresh Nair",
        status="active",
    )
    db_session.add_all([client_a, client_b])
    db_session.commit()

    # Initialize standard ICAI Chart of Accounts
    ChartOfAccountsService.initialize_default_accounts(db_session, client_a.id, ca_user)
    ChartOfAccountsService.initialize_default_accounts(db_session, client_b.id, other_ca)

    return {
        "ca_user": ca_user,
        "other_ca": other_ca,
        "admin_user": admin_user,
        "client_a": client_a,
        "client_b": client_b,
    }


# ── 1. Atomic Posting of Verified Document Draft ─────────────────────────

def test_atomic_posting_verified_document_creates_journal(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]
    user = data["ca_user"]

    # 1. Create a verified sales document
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        invoice_number="INV-SYNC-001",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Metro Corp Ltd",
        invoice_date="2026-03-25",
    )
    db_session.add(doc)
    db_session.commit()

    # 2. Generate accounting draft
    draft_res = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
    assert draft_res.status == "created"
    draft_record = draft_res.record
    assert draft_record.status == "draft"

    # 3. Explicitly post to ledger
    post_res = AccountingDraftService.post_draft_to_ledger(db_session, draft_record.id, user=user)

    assert post_res.success is True
    assert post_res.record.status == "posted"
    assert "Posted:" in post_res.record.description
    assert post_res.journal_entry is not None

    je = post_res.journal_entry
    assert je.total_debit == Decimal("23600.00")
    assert je.total_credit == Decimal("23600.00")
    assert je.is_balanced is True
    assert je.entry_type == "sales"
    assert je.reference_number == "INV-SYNC-001"

    # Verify database persistence
    db_je = db_session.query(JournalEntry).filter_by(accounting_record_id=draft_record.id).first()
    assert db_je is not None
    assert db_je.document_id == doc.id
    assert len(db_je.lines) == 4  # Debtors Dr, Sales Cr, CGST Cr, SGST Cr


# ── 2. Idempotency & Duplicate Prevention ────────────────────────────────

def test_post_draft_idempotency_prevents_duplicate_journal(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]
    user = data["ca_user"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        invoice_number="BILL-SYNC-99",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        vendor="Apex Hardware",
        invoice_date="2026-03-26",
    )
    db_session.add(doc)
    db_session.commit()

    draft_res = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
    draft_id = draft_res.record.id

    # First post
    res1 = AccountingDraftService.post_draft_to_ledger(db_session, draft_id, user=user)
    assert res1.success is True
    je_id1 = res1.journal_entry.id

    # Second post (repeated request)
    res2 = AccountingDraftService.post_draft_to_ledger(db_session, draft_id, user=user)
    assert res2.success is True
    assert "already posted" in res2.message.lower()
    assert res2.journal_entry.id == je_id1

    # Exactly 1 journal entry exists
    count = db_session.query(JournalEntry).filter_by(accounting_record_id=draft_id).count()
    assert count == 1


# ── 3. Authorization Enforcement ─────────────────────────────────────────

def test_unauthorized_user_cannot_post_draft(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]
    other_ca = data["other_ca"]  # User 2 does NOT own Client A

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("5000.00"),
        customer="Client A Customer",
        invoice_date="2026-03-25",
    )
    db_session.add(doc)
    db_session.commit()

    draft_res = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
    draft_id = draft_res.record.id

    # User 2 attempts to post Client A's draft
    with pytest.raises(ForbiddenException) as exc:
        AccountingDraftService.post_draft_to_ledger(db_session, draft_id, user=other_ca)
    assert "not authorized" in str(exc.value.detail).lower()


# ── 4. Legacy Record Preservation ─────────────────────────────────────────

def test_legacy_record_without_journal_preserved(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]

    # Historical record created before Step 2B (status=posted, no journal_entry)
    legacy = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        transaction_date=date(2026, 1, 15),
        voucher_type="sales",
        description="Historical sales posting | Posted: 2026-01-15 12:00:00 UTC",
        debit=Decimal("0.00"),
        credit=Decimal("50000.00"),
        status="posted",
    )
    db_session.add(legacy)
    db_session.commit()

    # Querying legacy record succeeds
    fetched = AccountingDraftService.get_draft_by_id(db_session, legacy.id)
    assert fetched is not None
    assert fetched.status == "posted"

    # No fabricated journal entry exists
    db_je = db_session.query(JournalEntry).filter_by(accounting_record_id=legacy.id).first()
    assert db_je is None


# ── 5. Bulk Posting Synchronization ───────────────────────────────────────

def test_bulk_posting_synchronization(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]
    user = data["ca_user"]

    doc1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        invoice_number="BULK-01",
        amount=Decimal("1000.00"),
        customer="Cust 1",
    )
    doc2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        invoice_number="BULK-02",
        amount=Decimal("2000.00"),
        vendor="Vend 2",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    draft1 = AccountingDraftService.generate_or_update_draft(db_session, doc1.id).record
    draft2 = AccountingDraftService.generate_or_update_draft(db_session, doc2.id).record

    bulk_res = AccountingDraftService.bulk_post_drafts(
        db_session,
        [draft1.id, draft2.id],
        user=user,
    )

    assert bulk_res.total_requested == 2
    assert bulk_res.posted_count == 2
    assert bulk_res.failed_count == 0

    # Verify both have journal entries
    je1 = db_session.query(JournalEntry).filter_by(accounting_record_id=draft1.id).first()
    je2 = db_session.query(JournalEntry).filter_by(accounting_record_id=draft2.id).first()
    assert je1 is not None
    assert je2 is not None


# ── 6. Atomic Rollback on Failure ──────────────────────────────────────────

def test_atomic_rollback_on_mapping_failure(db_session, setup_sync_data):
    data = setup_sync_data
    client = data["client_a"]
    user = data["ca_user"]

    # Create a draft record whose linked document is unverified (causes mapping exception)
    unverified_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="pending",  # Unverified!
        amount=Decimal("1000.00"),
        customer="Unverified Cust",
    )
    db_session.add(unverified_doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=unverified_doc.id,
        transaction_date=date(2026, 3, 20),
        voucher_type="sales",
        description="Pending review voucher",
        debit=Decimal("0.00"),
        credit=Decimal("1000.00"),
        status="draft",
    )
    db_session.add(draft)
    db_session.commit()

    # Attempt to post — should fail and roll back
    res = AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)
    assert res.success is False
    assert "failed to post" in res.message.lower()

    # Verify that draft status was rolled back and is STILL "draft"
    db_session.refresh(draft)
    assert draft.status == "draft"

    # Verify no orphan journal entry was created
    je = db_session.query(JournalEntry).filter_by(accounting_record_id=draft.id).first()
    assert je is None

