"""
Test F1: Note CDNR vs CDNUR Classification by Recipient GSTIN.
Verifies:
1. Registered credit note -> CDNR with recipient GSTIN from note or parent invoice.
2. Unregistered credit note -> CDNUR with Party GSTIN empty / "Unregistered".
3. Header counterparty columns on voucher are honored if present.
"""

import uuid
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.services.gst_reconciliation_service import GstReconciliationService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_note_cdnr_with_recipient_gstin(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-TEST-1",
        company_name="Test Client Corp",
        gst_number="27AABCA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@test.com", full_name="CA Test User", password_hash="hashed_pw", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Create Chart of accounts
    sales_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="4010", account_name="Sales", account_type="income", role="SALES")
    sales_ret_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="4020", account_name="Sales Return", account_type="income", role="SALES_RETURN")
    cgst_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2110", account_name="Output CGST", account_type="liability", role="OUTPUT_CGST")
    sgst_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2120", account_name="Output SGST", account_type="liability", role="OUTPUT_SGST")
    debtor_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1100", account_name="Debtors", account_type="asset", role="DEBTORS")
    db_session.add_all([sales_acc, sales_ret_acc, cgst_acc, sgst_acc, debtor_acc])
    db_session.commit()

    # 1. Registered Credit Note CN1
    # Document has client GSTIN as issuer, but metadata/voucher has recipient GSTIN
    cn_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="credit_note",
        invoice_number="CN-001",
        invoice_date="2026-08-10",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Mehta Enterprises",
        vendor="Test Client Corp",
        gstin="27AABCA1234A1Z5",  # Client's own GSTIN
        status="verified",
        metadata_='{"fields": {"customer_gstin": "27AAAPM5678B1Z2", "customer": "Mehta Enterprises"}}',
    )
    db_session.add(cn_doc)
    db_session.commit()

    je_cn = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=cn_doc.id,
        entry_number="JV-CN-001",
        entry_date=date(2026, 8, 10),
        entry_type="journal",
        status="posted",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
        counterparty_name="Mehta Enterprises",
        counterparty_gstin="27AAAPM5678B1Z2",
        voucher_template="T3",
    )
    db_session.add(je_cn)
    db_session.flush()

    line1 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=1, account_id=sales_ret_acc.id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00"))
    line2 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=2, account_id=cgst_acc.id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"))
    line3 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=3, account_id=sgst_acc.id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"))
    line4 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=4, account_id=debtor_acc.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00"))
    db_session.add_all([line1, line2, line3, line4])
    db_session.commit()

    # Reconcile GSTR-1
    gstr1 = GstReconciliationService.reconcile_gstr1(db_session, client_id, user, period="2026-Q2")
    cn_summary = gstr1.credit_notes_summary

    assert cn_summary.invoice_count == 1
    assert cn_summary.taxable_amount == Decimal("-20000.00")
    assert cn_summary.cgst == Decimal("-1800.00")
    assert cn_summary.sgst == Decimal("-1800.00")
    assert cn_summary.total_tax == Decimal("-3600.00")

    cn_item = next(inv for inv in gstr1.invoices if inv.invoice_number == "CN-001")
    assert cn_item.supply_type == "CDNR"
    assert cn_item.party_name == "Mehta Enterprises"
    assert cn_item.party_gstin == "27AAAPM5678B1Z2"


def test_unregistered_note_resolves_to_cdnur(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-TEST-2",
        company_name="Test Client Corp",
        gst_number="27AABCA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@test.com", full_name="CA Test User", password_hash="hashed_pw", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    sales_ret_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="4020", account_name="Sales Return", account_type="income", role="SALES_RETURN")
    cgst_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2110", account_name="Output CGST", account_type="liability", role="OUTPUT_CGST")
    sgst_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2120", account_name="Output SGST", account_type="liability", role="OUTPUT_SGST")
    debtor_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1100", account_name="Debtors", account_type="asset", role="DEBTORS")
    db_session.add_all([sales_ret_acc, cgst_acc, sgst_acc, debtor_acc])
    db_session.commit()

    # Credit Note to an unregistered customer (no valid 15-char GSTIN)
    cn_unreg = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="credit_note",
        invoice_number="CN-UNREG-001",
        invoice_date="2026-08-15",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Walk-in Retail Buyer (Unregistered)",
        vendor="Test Client Corp",
        gstin="27AABCA1234A1Z5",
        status="verified",
        metadata_='{"fields": {}}',
    )
    db_session.add(cn_unreg)
    db_session.commit()

    je_cn = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=cn_unreg.id,
        entry_number="JV-CN-UNREG",
        entry_date=date(2026, 8, 15),
        entry_type="journal",
        status="posted",
        total_debit=Decimal("1180.00"),
        total_credit=Decimal("1180.00"),
        voucher_template="T3",
    )
    db_session.add(je_cn)
    db_session.flush()

    line1 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=1, account_id=sales_ret_acc.id, debit_amount=Decimal("1000.00"), credit_amount=Decimal("0.00"))
    line2 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=2, account_id=cgst_acc.id, debit_amount=Decimal("90.00"), credit_amount=Decimal("0.00"))
    line3 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=3, account_id=sgst_acc.id, debit_amount=Decimal("90.00"), credit_amount=Decimal("0.00"))
    line4 = JournalEntryLine(journal_entry_id=je_cn.id, line_number=4, account_id=debtor_acc.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("1180.00"))
    db_session.add_all([line1, line2, line3, line4])
    db_session.commit()

    gstr1 = GstReconciliationService.reconcile_gstr1(db_session, client_id, user, period="2026-Q2")
    cn_item = next(inv for inv in gstr1.invoices if inv.invoice_number == "CN-UNREG-001")
    assert cn_item.supply_type == "CDNUR"
    assert cn_item.party_gstin == ""
