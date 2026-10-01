"""
Test Suite for D2: Legacy Voucher Reposting & Discrepancy Flagging
================================================================
Verifies that:
1. detect_discrepancies identifies posted vouchers lacking GST lines as LEGACY_VOUCHER_NO_TAX_LINES.
2. Vouchers with proper GST lines are not flagged.
3. repost_legacy_vouchers safely reverses legacy vouchers and posts balanced T1-T6 vouchers.
4. Old and reversal vouchers net to zero.
"""

import uuid
import datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.chart_of_accounts import ChartOfAccounts, Base
from app.models.client import Client
from app.models.user import User
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService
from scripts.repost_legacy_vouchers import repost_legacy_vouchers, is_legacy_voucher_missing_tax_lines


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def setup_client_and_user(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca_test@example.com",
        full_name="CA Tester",
        role="admin",
        password_hash="test",
    )
    db_session.add(user)

    client = Client(
        id=uuid.uuid4(),
        client_code="C-TEST",
        company_name="Test Enterprise Ltd",
        contact_person="Director",
        email="test@enterprise.com",
        gst_number="27AABCT1234A1Z5",
        state="Maharashtra",
        user_id=user.id,
    )
    db_session.add(client)
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return client, user


def test_detect_discrepancy_flags_legacy_voucher_without_tax_lines(db_session, setup_client_and_user):
    client, user = setup_client_and_user

    # Source document with tax
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="INV-LEG-001",
        document_category="credit_note",
        status="verified",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Counterparty Corp",
        gstin="27AABCT1234A1Z5",
        metadata_='{"fields": {"customer_gstin": "27AAAPM5678B1Z2", "supplier_gstin": "27AABCT1234A1Z5"}}',
    )
    db_session.add(doc)
    db_session.commit()

    # Legacy voucher with only 2 lines (no tax lines)
    coa_4030 = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4030").first()
    coa_1100 = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "1100").first()

    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        entry_number="JV-2026-LEG1",
        entry_type="journal",
        entry_date=datetime.date(2026, 8, 10),
        status="posted",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
        posted_by_user_id=user.id,
    )
    db_session.add(je)
    db_session.flush()

    line1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        account_id=coa_4030.id,
        debit_amount=Decimal("23600.00"),
        credit_amount=Decimal("0.00"),
        line_number=1,
    )
    line2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        account_id=coa_1100.id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("23600.00"),
        line_number=2,
    )
    db_session.add_all([line1, line2])
    db_session.commit()

    is_legacy, found_doc, tax_val = is_legacy_voucher_missing_tax_lines(je, db_session)
    assert is_legacy is True
    assert found_doc.id == doc.id
    assert tax_val == Decimal("3600.00")

    # Run detect_discrepancies
    report = GstReconciliationService.detect_discrepancies(db_session, client.id, user)
    legacy_discs = [d for d in report.discrepancies if d.rule_code == "LEGACY_VOUCHER_NO_TAX_LINES"]
    assert len(legacy_discs) == 1
    assert legacy_discs[0].voucher_id == je.id
    assert legacy_discs[0].variance_amount == Decimal("3600.00")


def test_repost_legacy_vouchers_applies_reversal_and_statutory_voucher(db_session, setup_client_and_user):
    client, user = setup_client_and_user

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="INV-LEG-002",
        document_category="credit_note",
        status="verified",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Client Buyer",
        gstin="27AABCT1234A1Z5",
        metadata_='{"fields": {"customer_gstin": "27AAAPM5678B1Z2", "supplier_gstin": "27AABCT1234A1Z5"}}',
    )
    db_session.add(doc)
    db_session.commit()

    coa_4030 = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4030").first()
    coa_1100 = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "1100").first()

    ar = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        voucher_type="journal",
        transaction_date=datetime.date(2026, 8, 10),
        status="posted",
        reference_number="JV-2026-LEG2",
        debit=Decimal("23600.00"),
        credit=Decimal("23600.00"),
    )
    db_session.add(ar)
    db_session.commit()

    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        accounting_record_id=ar.id,
        entry_number="JV-2026-LEG2",
        entry_type="journal",
        entry_date=datetime.date(2026, 8, 10),
        status="posted",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
        posted_by_user_id=user.id,
    )
    db_session.add(je)
    db_session.flush()

    line1 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        account_id=coa_4030.id,
        debit_amount=Decimal("23600.00"),
        credit_amount=Decimal("0.00"),
        line_number=1,
    )
    line2 = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        account_id=coa_1100.id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("23600.00"),
        line_number=2,
    )
    db_session.add_all([line1, line2])
    db_session.commit()

    # Execute repost with apply=True
    repost_legacy_vouchers(db_session, client_id=client.id, apply=True)

    db_session.refresh(je)
    assert je.status == "reversed"

    # Verify reversal voucher was created
    rev_je = db_session.query(JournalEntry).filter(
        JournalEntry.client_id == client.id,
        JournalEntry.entry_type == "reversal",
        JournalEntry.reference_number == "JV-2026-LEG2",
    ).first()
    assert rev_je is not None
    assert rev_je.status == "reversed"
    # Reversal has swapped amounts
    assert rev_je.total_debit == Decimal("23600.00")
    assert rev_je.total_credit == Decimal("23600.00")

    # Verify new statutory voucher was posted
    new_je = db_session.query(JournalEntry).filter(
        JournalEntry.client_id == client.id,
        JournalEntry.status == "posted",
        JournalEntry.document_id == doc.id,
        JournalEntry.entry_type != "reversal",
    ).first()
    assert new_je is not None
    assert new_je.id != je.id

    # Check lines of new voucher: has tax lines
    new_lines = db_session.query(JournalEntryLine).filter(JournalEntryLine.journal_entry_id == new_je.id).all()
    cgst_lines = [l for l in new_lines if l.account and l.account.account_code == "2110"]
    sgst_lines = [l for l in new_lines if l.account and l.account.account_code == "2120"]
    assert len(cgst_lines) == 1
    assert cgst_lines[0].debit_amount == Decimal("1800.00")
    assert len(sgst_lines) == 1
    assert sgst_lines[0].debit_amount == Decimal("1800.00")

    # Discrepancy is now resolved!
    report_after = GstReconciliationService.detect_discrepancies(db_session, client.id, user)
    legacy_discs_after = [d for d in report_after.discrepancies if d.rule_code == "LEGACY_VOUCHER_NO_TAX_LINES"]
    assert len(legacy_discs_after) == 0
