"""
Unit test suite for G2: get_filing_options for Monthly and Quarterly clients.
Validates:
- Monthly clients: returns eligible calendar months, no quarters, default latest unfiled completed month.
- Quarterly clients: returns eligible Indian FY quarters (YYYY-Qn), no months, default latest unfiled completed quarter.
- Period completion constraint: only periods where period_end < today are eligible.
- Nil return identification: periods with 0 posted transactions marked is_nil=True.
- Filing status mapping: unfiled ('open'), filed ('filed', disabled), voided ('voided-refileable', selectable).
- Unrecognized or null frequency: returns empty periods and setup notice.
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

from app.services.gst_filing_service import get_filing_options, get_filing_profile


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


def test_filing_options_monthly_client(db_session):
    u = User(id=uuid.uuid4(), email="user_m@test.com", password_hash="dummy", full_name="Monthly User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="M-001",
        company_name="Monthly Client",
        contact_person="Contact Person",
        email="client_m@test.com",
        return_frequency="Monthly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    # Add posted vouchers in July and August 2026
    r1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        transaction_date=date(2026, 7, 10),
        voucher_type="sales",
        debit=100000,
        credit=0,
        status="posted",
    )
    r2 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        transaction_date=date(2026, 8, 15),
        voucher_type="purchase",
        debit=0,
        credit=50000,
        status="posted",
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    # Today is Oct 9, 2026
    today = date(2026, 10, 9)
    opts = get_filing_options(db_session, c, today=today)

    assert opts.frequency == "monthly"
    assert opts.default_period == "2026-09"
    keys = [p.key for p in opts.periods]
    assert keys == ["2026-07", "2026-08", "2026-09"]
    assert all("-Q" not in k for k in keys)

    # Form options
    form_codes = [f.code for f in opts.return_forms]
    assert "GSTR-3B" in form_codes
    assert "GSTR-1" in form_codes
    assert any("Monthly" in f.label for f in opts.return_forms)

    # September has 0 vouchers -> is_nil = True
    p_sep = next(p for p in opts.periods if p.key == "2026-09")
    assert p_sep.is_nil is True
    # July and August have vouchers -> is_nil = False
    p_jul = next(p for p in opts.periods if p.key == "2026-07")
    assert p_jul.is_nil is False


def test_filing_options_quarterly_client(db_session):
    u = User(id=uuid.uuid4(), email="user_q@test.com", password_hash="dummy", full_name="Quarterly User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="Q-001",
        company_name="Quarterly Client",
        contact_person="Quarterly Contact",
        email="client_q@test.com",
        return_frequency="Quarterly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    # Add posted voucher in July 2026 (Q2 FY 2026-27)
    r1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        transaction_date=date(2026, 7, 10),
        voucher_type="sales",
        debit=200000,
        credit=0,
        status="posted",
    )
    db_session.add(r1)
    db_session.commit()

    today = date(2026, 10, 9)
    opts = get_filing_options(db_session, c, today=today)

    assert opts.frequency == "quarterly"
    assert opts.default_period == "2026-Q2"
    keys = [p.key for p in opts.periods]
    # Q1 (Apr-Jun 2026) and Q2 (Jul-Sep 2026) are completed
    assert keys == ["2026-Q1", "2026-Q2"]
    # Q3 is NOT offered because it ends 2026-12-31 >= today
    assert "2026-Q3" not in keys
    assert all("-Q" in k for k in keys)

    # Q1 has no vouchers -> nil
    p_q1 = next(p for p in opts.periods if p.key == "2026-Q1")
    assert p_q1.is_nil is True
    assert p_q1.label == "Q1 FY 2026-27 (Apr-Jun)"

    # Q2 has vouchers -> not nil
    p_q2 = next(p for p in opts.periods if p.key == "2026-Q2")
    assert p_q2.is_nil is False
    assert p_q2.label == "Q2 FY 2026-27 (Jul-Sep)"


def test_filing_options_filing_statuses(db_session):
    u = User(id=uuid.uuid4(), email="user_st@test.com", password_hash="dummy", full_name="Status User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="Q-002",
        company_name="Status Client",
        contact_person="Status Contact",
        email="client_st@test.com",
        return_frequency="Quarterly",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    # Record Q1 as filed
    rec_q1 = GSTRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        gst_period="2026-Q1",
        gst_type="GSTR-3B",
        filing_status="filed",
    )
    # Record Q2 as voided
    rec_q2 = GSTRecord(
        id=uuid.uuid4(),
        client_id=c.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="voided",
        void_reason="Correction required",
    )
    db_session.add_all([rec_q1, rec_q2])
    db_session.commit()

    today = date(2026, 10, 9)
    opts = get_filing_options(db_session, c, today=today)

    p_q1 = next(p for p in opts.periods if p.key == "2026-Q1")
    assert p_q1.status == "filed"
    assert p_q1.is_selectable is False

    p_q2 = next(p for p in opts.periods if p.key == "2026-Q2")
    assert p_q2.status == "voided-refileable"
    assert p_q2.is_selectable is True
    # Default selects Q2 because Q1 is filed
    assert opts.default_period == "2026-Q2"


def test_filing_options_null_frequency(db_session):
    u = User(id=uuid.uuid4(), email="user_null@test.com", password_hash="dummy", full_name="Null User")
    c = Client(
        id=uuid.uuid4(),
        user_id=u.id,
        client_code="N-001",
        company_name="Null Freq Client",
        contact_person="Null Contact",
        email="client_null@test.com",
        return_frequency=None,
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
    )
    db_session.add_all([u, c])
    db_session.commit()

    opts = get_filing_options(db_session, c, today=date(2026, 10, 9))
    assert opts.frequency is None
    assert opts.periods == []
    assert opts.default_period is None
    assert "Set the return frequency in the client profile" in opts.reason
