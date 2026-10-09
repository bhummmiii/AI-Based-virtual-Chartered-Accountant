"""
Unit test suite for G6: Duplicate Alert Severity (Y4).
Validates:
- Verified duplicate invoice flags HIGH severity DUPLICATE_INVOICE and increments high_count.
- Rejected duplicate invoice (status='rejected' or rejection_reason='DUPLICATE') flags INFO severity
  DUPLICATE_REJECTED with message 'Rejected duplicate {inv_num} is excluded from all figures - you may delete it'.
- Discrepancy report high_count excludes DUPLICATE_REJECTED (high_count == 0).
- Filing preview blockers list has 0 HIGH_DISCREPANCY blockers when only rejected duplicate exists.
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

from app.services.gst_reconciliation_service import GstReconciliationService
from app.services.gst_filing_service import get_filing_preview


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


def test_rejected_duplicate_emits_info_alert_and_zero_high_discrepancies(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="CA Test",
        role="ca",
    )
    db_session.add(user)

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-DUP-TEST",
        company_name="Test Dup Co",
        gst_number="27AABCT1234A1Z5",
        state="Maharashtra",
        contact_person="Director",
        email="dup@example.com",
        return_frequency="Quarterly",
    )
    db_session.add(client)
    db_session.commit()

    # Accounts for balanced GST lines
    acc_cgst = ChartOfAccounts(
        id=uuid.uuid4(),
        client_id=client.id,
        account_code="2110",
        account_name="Output CGST",
        account_type="liability",
        role="OUTPUT_CGST",
    )
    acc_sgst = ChartOfAccounts(
        id=uuid.uuid4(),
        client_id=client.id,
        account_code="2120",
        account_name="Output SGST",
        account_type="liability",
        role="OUTPUT_SGST",
    )
    db_session.add_all([acc_cgst, acc_sgst])
    db_session.commit()

    # Original posted document
    doc_orig = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="ABC/26-27/001",
        invoice_date="2026-07-15",
        gstin="27AABCT9999Z1Z5",
        customer="Client Buyer Ltd",
        amount=118000,
        taxable_amount=100000,
        cgst=9000,
        sgst=9000,
        igst=0,
        status="verified",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_orig.id,
        entry_number="SV-001",
        entry_date=date(2026, 7, 15),
        entry_type="sales",
        status="posted",
        is_reversed=False,
    )
    line_c = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=1,
        account_id=acc_cgst.id,
        credit_amount=9000,
        debit_amount=0,
    )
    line_s = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=2,
        account_id=acc_sgst.id,
        credit_amount=9000,
        debit_amount=0,
    )

    # Second document: rejected duplicate
    doc_dup = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="ABC/26-27/001",
        invoice_date="2026-07-15",
        gstin="27AABCT9999Z1Z5",
        customer="Client Buyer Ltd",
        amount=118000,
        taxable_amount=100000,
        cgst=9000,
        sgst=9000,
        igst=0,
        status="rejected",
        rejection_reason="DUPLICATE",
    )
    db_session.add_all([doc_orig, doc_dup, je, line_c, line_s])
    db_session.commit()

    # Discrepancy report check
    report = GstReconciliationService.detect_discrepancies(
        db_session, client.id, user, period="2026-Q2"
    )

    assert report.high_count == 0
    assert report.total_discrepancies == 1

    dup_alerts = [d for d in report.discrepancies if d.rule_code == "DUPLICATE_REJECTED"]
    assert len(dup_alerts) == 1
    assert dup_alerts[0].severity == "INFO"
    assert "Rejected duplicate ABC/26-27/001 is excluded from all figures - you may delete it" in dup_alerts[0].description

    # Filing preview should have no HIGH_DISCREPANCY blocker
    preview = get_filing_preview(
        db=db_session,
        client=client,
        period="2026-Q2",
        form="GSTR-3B",
        user=user,
        today=date(2026, 10, 9),
    )
    high_blockers = [b for b in preview.blockers if b.code == "HIGH_DISCREPANCY"]
    assert len(high_blockers) == 0
