"""
Comprehensive Unit Tests for Audit Posting Hardening & Statutory GST Controls:
1. Strict Line Ordering: Debits first (1, 2, ...), then Credits.
2. Tax Account Splitting: Sales, Purchases, Credit Notes, Debit Notes.
3. Direction Decision from Issuer vs Client GSTIN.
4. Posting Validation:
   - Block on component math mismatch (printed total != sum of components).
   - Block on state code / tax parity mismatch (intra-state with IGST, inter-state with CGST/SGST).
5. Removal of plug logic in GST reconciliation.
6. GST Module reads only posted ledger entries (unposted documents excluded from returns).
7. Document deletion protection for posted entries.
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
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.journal_entry_service import JournalEntryService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.core.exceptions import BadRequestException
from app.schemas.journal_entry import JournalEntryCreate, JournalEntryLineCreate


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
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def audit_fixture(db_session):
    """Seed CA user, Maharashtra-registered Client, and COA."""
    user = User(
        id=uuid.uuid4(),
        email="lead_ca@precisionaudit.in",
        full_name="CA Rajesh Varma",
        password_hash="mockhash",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Maharashtra Client (State Code 27)
    client = Client(
        id=uuid.uuid4(),
        company_name="Apex Precision Mfg Pvt Ltd",
        client_code="APEX-MUM",
        contact_person="Rajesh Varma",
        gst_number="27AABCA1234F1Z8",  # Maharashtra (27)
        email="contact@apexprecision.in",
        status="active",
        user_id=user.id,
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db=db_session, client_id=client.id, user=user)
    coa_map = {acc.account_code: acc for acc in db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()}

    return {
        "user": user,
        "client": client,
        "coa": coa_map,
    }


# ── 1. Test Strict Line Ordering: Debits First ────────────────────────────────

def test_journal_entry_line_ordering_debits_first(db_session, audit_fixture):
    """Ensure JournalEntryService orders all debit lines before credit lines sequentially."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]
    coa = data["coa"]

    # Submit lines in reverse order (Credits first, then Debits)
    payload = JournalEntryCreate(
        client_id=client.id,
        entry_date=date(2026, 8, 15),
        entry_type="journal",
        narration="Reversed input line test",
        lines=[
            JournalEntryLineCreate(
                account_id=coa["4010"].id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("5000.00"),
                description="Credit line 1",
            ),
            JournalEntryLineCreate(
                account_id=coa["2110"].id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("450.00"),
                description="Credit line 2",
            ),
            JournalEntryLineCreate(
                account_id=coa["1100"].id,
                debit_amount=Decimal("5450.00"),
                credit_amount=Decimal("0.00"),
                description="Debit line 1",
            ),
        ],
    )

    je = JournalEntryService.create_journal_entry(db=db_session, client_id=client.id, payload=payload, user=user)
    assert len(je.lines) == 3
    # First line MUST be the debit line with line_number == 1
    assert je.lines[0].line_number == 1
    assert je.lines[0].debit_amount == Decimal("5450.00")
    assert je.lines[0].credit_amount == Decimal("0.00")

    # Lines 2 and 3 must be credits
    assert je.lines[1].line_number == 2
    assert je.lines[1].credit_amount > Decimal("0.00")
    assert je.lines[2].line_number == 3
    assert je.lines[2].credit_amount > Decimal("0.00")


def test_reversal_entry_ordering_debits_first(db_session, audit_fixture):
    """Ensure reverse_journal_entry also places swapped debits first."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]
    coa = data["coa"]

    payload = JournalEntryCreate(
        client_id=client.id,
        entry_date=date(2026, 8, 15),
        entry_type="sales",
        narration="Original sales entry",
        lines=[
            JournalEntryLineCreate(
                account_id=coa["1100"].id,
                debit_amount=Decimal("1180.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLineCreate(
                account_id=coa["4010"].id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("1000.00"),
            ),
            JournalEntryLineCreate(
                account_id=coa["2110"].id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("180.00"),
            ),
        ],
    )
    orig = JournalEntryService.create_journal_entry(db=db_session, client_id=client.id, payload=payload, user=user)
    rev = JournalEntryService.reverse_journal_entry(db=db_session, entry_id=orig.id, user=user, reason="Correction")

    assert len(rev.lines) == 3
    # Swapped original credits (Sales 1000 and CGST 180) now become Debits, and must be first!
    assert rev.lines[0].debit_amount > Decimal("0.00")
    assert rev.lines[0].line_number == 1
    assert rev.lines[1].debit_amount > Decimal("0.00")
    assert rev.lines[1].line_number == 2
    # Debtor 1180 is now credit, and must be last!
    assert rev.lines[2].credit_amount == Decimal("1180.00")
    assert rev.lines[2].line_number == 3


# ── 2. Test Tax Split for Credit and Debit Notes ──────────────────────────────

def test_credit_note_tax_account_splitting(db_session, audit_fixture):
    """Outward credit note must debit Sales Return and Output GST accounts, and credit Debtor."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]

    doc_cn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="credit_note",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Mahindra Retailers Ltd",
        gstin="27XYZAB9999R1Z1",  # Same state intra-state
        invoice_number="CN-2026-001",
    )
    db_session.add(doc_cn)
    db_session.commit()

    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc_cn, user)
    assert len(je_create.lines) == 4  # Sales Return, Output CGST, Output SGST, Debtor

    # Debits first:
    # 1. Sales Return (4020)
    assert je_create.lines[0].account_id == data["coa"]["4020"].id
    assert je_create.lines[0].debit_amount == Decimal("1000.00")
    # 2. Output CGST (2110)
    assert je_create.lines[1].account_id == data["coa"]["2110"].id
    assert je_create.lines[1].debit_amount == Decimal("90.00")
    # 3. Output SGST (2120)
    assert je_create.lines[2].account_id == data["coa"]["2120"].id
    assert je_create.lines[2].debit_amount == Decimal("90.00")
    # Credit last:
    # 4. Debtor (1100)
    assert je_create.lines[3].account_id == data["coa"]["1100"].id
    assert je_create.lines[3].credit_amount == Decimal("1180.00")


def test_debit_note_tax_account_splitting(db_session, audit_fixture):
    """Inward debit note must debit Creditor, credit Purchase Return and Input GST accounts."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]

    doc_dn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="debit_note",
        status="verified",
        amount=Decimal("2360.00"),
        taxable_amount=Decimal("2000.00"),
        cgst=Decimal("180.00"),
        sgst=Decimal("180.00"),
        vendor="Precision Raw Steels Ltd",
        gstin="27DEFGH5555M1Z2",  # Intra-state vendor
        invoice_number="DN-2026-001",
    )
    db_session.add(doc_dn)
    db_session.commit()

    je_create = AccountingMappingService.map_document_to_journal_entry(db_session, doc_dn, user)
    assert len(je_create.lines) == 4

    # Debit first:
    # 1. Creditor (2010)
    assert je_create.lines[0].account_id == data["coa"]["2010"].id
    assert je_create.lines[0].debit_amount == Decimal("2360.00")
    # Credits:
    # 2. Purchase Return (5020)
    assert je_create.lines[1].account_id == data["coa"]["5020"].id
    assert je_create.lines[1].credit_amount == Decimal("2000.00")
    # 3. Input CGST Reversal (1210)
    assert je_create.lines[2].account_id == data["coa"]["1210"].id
    assert je_create.lines[2].credit_amount == Decimal("180.00")
    # 4. Input SGST Reversal (1220)
    assert je_create.lines[3].account_id == data["coa"]["1220"].id
    assert je_create.lines[3].credit_amount == Decimal("180.00")


# ── 3. Test Direction Decision from Issuer vs Client GSTIN ────────────────────

def test_direction_decided_from_issuer_and_client_gstin(db_session, audit_fixture):
    """When issuer GSTIN == client GSTIN, it is outward; when issuer != client, it is inward."""
    data = audit_fixture
    client = data["client"]  # GSTIN: 27AABCA1234F1Z8

    # A. B2B document where client is supplier (Outward sales)
    doc_out = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        gstin="27AABCA1234F1Z8",  # matches client GSTIN
        metadata_='{"fields": {"supplier_gstin": {"value": "27AABCA1234F1Z8"}, "customer_gstin": {"value": "27XYZAB9999R1Z1"}}}',
    )
    assert GstReconciliationService.determine_document_direction(doc_out, client.gst_number) == "OUTWARD"

    # B. B2B document where vendor is external supplier (Inward purchase)
    doc_in = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        gstin="27XYZAB9999R1Z1",  # External supplier
        metadata_='{"fields": {"supplier_gstin": {"value": "27XYZAB9999R1Z1"}, "customer_gstin": {"value": "27AABCA1234F1Z8"}}}',
    )
    assert GstReconciliationService.determine_document_direction(doc_in, client.gst_number) == "INWARD"


# ── 4. Test Posting Block on Math Variance & State Code Tax Mismatch ──────────

def test_block_posting_on_component_sum_mismatch(db_session, audit_fixture):
    """Sum of components differing from printed total must block posting."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]

    # Printed total 1500 != 1000 + 100 + 100 = 1200
    doc_bad_math = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1500.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("100.00"),
        sgst=Decimal("100.00"),
        invoice_number="INV-BAD-MATH",
    )
    db_session.add(doc_bad_math)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(db_session, doc_bad_math, user)
    assert "differs from printed total" in str(exc.value).lower()


def test_block_posting_on_state_code_intra_with_igst(db_session, audit_fixture):
    """Intra-state supply (same state codes 27 == 27) cannot charge IGST."""
    data = audit_fixture
    client = data["client"]  # State 27
    user = data["user"]

    # Customer is also in Maharashtra (27), but invoice has IGST!
    doc_intra_igst = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        igst=Decimal("180.00"),  # ILLEGAL for intra-state
        cgst=Decimal("0.00"),
        sgst=Decimal("0.00"),
        gstin="27MNO9999P1Z3",  # State 27
        invoice_number="INV-ILLEGAL-IGST",
    )
    db_session.add(doc_intra_igst)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(db_session, doc_intra_igst, user)
    assert "intra-state supply" in str(exc.value).lower()
    assert "cannot have igst" in str(exc.value).lower()


def test_block_posting_on_state_code_inter_with_cgst_sgst(db_session, audit_fixture):
    """Inter-state supply (client 27 vs recipient 29 Karnataka) cannot charge CGST/SGST."""
    data = audit_fixture
    client = data["client"]  # State 27
    user = data["user"]

    # Customer in Karnataka (State 29), but invoice has CGST/SGST!
    doc_inter_cgst = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),   # ILLEGAL for inter-state
        sgst=Decimal("90.00"),   # ILLEGAL for inter-state
        igst=Decimal("0.00"),
        gstin="29BLR1234K1Z0",  # State 29
        invoice_number="INV-ILLEGAL-CGST",
    )
    db_session.add(doc_inter_cgst)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(db_session, doc_inter_cgst, user)
    assert "inter-state" in str(exc.value).lower()
    assert "cannot have cgst" in str(exc.value).lower()


# ── 5. Test GST Module Reads ONLY Posted Ledger Entries & No Plug Logic ────────

def test_gst_module_reads_only_posted_ledger_entries(db_session, audit_fixture):
    """Unposted documents must NOT appear in GSTR-1 or GSTR-2B return calculations."""
    data = audit_fixture
    client = data["client"]
    user = data["user"]

    # 1. Posted invoice
    doc_posted = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        gstin="27LOCAL1234F1Z1",
        invoice_number="INV-POSTED-01",
        invoice_date="2026-08-10",
    )
    db_session.add(doc_posted)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_posted.id,
        transaction_date=date(2026, 8, 10), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1180.00"), status="draft",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    # 2. Unposted invoice (verified but NOT posted to ledger)
    doc_unposted = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("5900.00"),
        taxable_amount=Decimal("5000.00"),
        cgst=Decimal("450.00"),
        sgst=Decimal("450.00"),
        gstin="27LOCAL5678F1Z2",
        invoice_number="INV-UNPOSTED-02",
        invoice_date="2026-08-12",
    )
    db_session.add(doc_unposted)
    db_session.commit()

    # Reconcile GSTR-1
    gstr1 = GstReconciliationService.reconcile_gstr1(db=db_session, client_id=client.id, user=user, period="2026-08")

    # Only the posted invoice (₹1,000.00 taxable) must be counted!
    assert gstr1.total_outward_taxable == Decimal("1000.00")
    assert gstr1.total_outward_cgst == Decimal("90.00")
    assert gstr1.total_outward_sgst == Decimal("90.00")
    assert len(gstr1.invoices) == 1
    assert gstr1.invoices[0].invoice_number == "INV-POSTED-01"


# ── 6. Test Document Deletion Protection for Posted Entries ───────────────────

def test_prevent_deleting_document_with_posted_entry(db_session, audit_fixture):
    """Attempting to delete a document linked to a posted JournalEntry must be blocked."""
    from app.api.invoice_router import delete_document

    data = audit_fixture
    client = data["client"]
    user = data["user"]

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        invoice_number="INV-PROTECTED",
        invoice_date="2026-08-10",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc.id,
        transaction_date=date(2026, 8, 10), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1180.00"), status="draft",
    )
    db_session.add(draft)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft.id, user=user)

    # Deleting the document MUST raise BadRequestException
    with pytest.raises(BadRequestException) as exc:
        delete_document(doc_id=doc.id, db=db_session, current_user=user)
    assert "cannot delete document with a posted ledger entry" in str(exc.value).lower()
