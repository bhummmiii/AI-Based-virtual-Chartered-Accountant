"""
Unit test suite for G2: get_filing_preview mathematical parity with GST tab.
Validates:
- Preview figures equal the GST tab (generate_gstr3b / reconcile_gstr1) for the same period and client.
- Due date calculation for Quarterly GSTR-3B (22nd for Cat X) and GSTR-1 (13th).
- Blocker validation:
  - PERIOD_NOT_ENDED when period_end >= today
  - FREQUENCY_MISMATCH when quarterly client requests monthly or vice-versa
  - ALREADY_FILED when active filing record exists
  - FREQUENCY_NOT_SET when client has null frequency
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

from app.services.gst_filing_service import get_filing_preview, get_filing_profile
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
            AccountingPeriod.__table__,
            GSTRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_filing_preview_mathematical_parity_gstr3b(db_session):
    u = User(id=uuid.uuid4(), email="user_prev@test.com", password_hash="dummy", full_name="Preview User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="Q-PREV",
        company_name="Preview Client",
        contact_person="Preview Contact",
        email="prev@client.com",
        return_frequency="Quarterly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    today = date(2026, 10, 9)
    period = "2026-Q2"

    preview = get_filing_preview(db_session, c, period=period, form="GSTR-3B", user=u, today=today)
    g3b = GstReconciliationService.generate_gstr3b(db_session, c.id, u, period=period)

    # Parity check
    assert preview.taxable_value == g3b.table_3_1_outward.taxable_value
    assert preview.total_cash_payable == g3b.tax_payable_in_cash
    assert preview.cash_payable_igst == g3b.cash_payable_igst
    assert preview.cash_payable_cgst == g3b.cash_payable_cgst
    assert preview.cash_payable_sgst == g3b.cash_payable_sgst
    assert preview.itc_reversal_payable_igst == g3b.itc_reversal_payable_igst
    assert preview.excess_credit_carried_forward == g3b.excess_credit_carried_forward
    # Due date for Quarterly Q2 FY 2026-27 in state 27 (Category X) is 22-Oct-2026
    assert preview.due_date == "2026-10-22"
    assert preview.period_type == "quarterly"
    assert preview.period_start == date(2026, 7, 1)
    assert preview.period_end == date(2026, 9, 30)


def test_filing_preview_mathematical_parity_gstr1(db_session):
    u = User(id=uuid.uuid4(), email="user_g1@test.com", password_hash="dummy", full_name="G1 User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="Q-G1",
        company_name="G1 Client",
        contact_person="G1 Contact",
        email="g1@client.com",
        return_frequency="Quarterly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    today = date(2026, 10, 9)
    period = "2026-Q2"

    preview = get_filing_preview(db_session, c, period=period, form="GSTR-1", user=u, today=today)
    g1 = GstReconciliationService.reconcile_gstr1(db_session, c.id, u, period=period)

    assert preview.taxable_value == g1.total_outward_taxable
    assert preview.total_liability == g1.total_outward_tax
    # Due date for Quarterly GSTR-1 Q2 is 13-Oct-2026
    assert preview.due_date == "2026-10-13"


def test_filing_preview_blockers(db_session):
    u = User(id=uuid.uuid4(), email="user_blk@test.com", password_hash="dummy", full_name="Blocker User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="Q-BLK",
        company_name="Blocker Client",
        contact_person="Blocker Contact",
        email="blk@client.com",
        return_frequency="Quarterly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    today = date(2026, 10, 9)

    # 1. Period not ended (Q3 FY 2026-27 ends 2026-12-31 >= today)
    prev_unended = get_filing_preview(db_session, c, period="2026-Q3", form="GSTR-3B", user=u, today=today)
    blocker_codes = [b.code for b in prev_unended.blockers]
    assert "PERIOD_NOT_ENDED" in blocker_codes

    # 2. Frequency mismatch (Quarterly client requesting monthly period 2026-09)
    prev_mismatch = get_filing_preview(db_session, c, period="2026-09", form="GSTR-3B", user=u, today=today)
    blocker_codes = [b.code for b in prev_mismatch.blockers]
    assert "FREQUENCY_MISMATCH" in blocker_codes

    # 3. Already filed
    rec = GSTRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="filed",
    )
    db_session.add(rec)
    db_session.commit()

    prev_filed = get_filing_preview(db_session, c, period="2026-Q2", form="GSTR-3B", user=u, today=today)
    blocker_codes = [b.code for b in prev_filed.blockers]
    assert "ALREADY_FILED" in blocker_codes


def test_filing_preview_frequency_not_set(db_session):
    u = User(id=uuid.uuid4(), email="user_noset@test.com", password_hash="dummy", full_name="NoSet User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="N-NOSET",
        company_name="No Set Client",
        contact_person="NoSet Contact",
        email="noset@client.com",
        return_frequency=None,
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    today = date(2026, 10, 9)
    prev = get_filing_preview(db_session, c, period="2026-Q2", form="GSTR-3B", user=u, today=today)
    blocker_codes = [b.code for b in prev.blockers]
    assert "FREQUENCY_NOT_SET" in blocker_codes
