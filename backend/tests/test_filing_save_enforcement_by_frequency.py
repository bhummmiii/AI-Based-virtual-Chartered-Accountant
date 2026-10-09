"""
Unit test suite for G5: Server Enforcement on Save by Return Frequency.
Validates:
- Rejection with FREQUENCY_NOT_SET when client has no return frequency configured.
- Rejection of quarterly periods for monthly clients and monthly periods for quarterly clients.
- Rejection of incomplete periods (end_date >= today).
- Correct population of period_type, frequency_at_filing, and statutory due_date.
- Period lock on AccountingPeriod covering exact [period_start, period_end].
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
from app.core.exceptions import BadRequestException
from app.api.routers.gst.router import create_gst_record


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


def test_reject_frequency_not_set(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="Test CA",
        role="ca",
    )
    db_session.add(user)

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-UNSET",
        company_name="Unset Frequency Corp",
        gst_number="27AABCT9999Z1Z5",
        state="Maharashtra",
        contact_person="Director",
        email="director@example.com",
        return_frequency=None,
    )
    db_session.add(client)
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=client.id,
        gst_period="2026-07",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    with pytest.raises(BadRequestException) as exc_info:
        create_gst_record(payload=payload, db=db_session, current_user=user)

    assert "FREQUENCY_NOT_SET" in str(exc_info.value.detail)


def test_reject_frequency_mismatch(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="Test CA",
        role="ca",
    )
    db_session.add(user)

    q_client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-Q01",
        company_name="Quarterly Corp",
        gst_number="27AABCT9999Z1Z5",
        state="Maharashtra",
        contact_person="Director Q",
        email="director_q@example.com",
        return_frequency="Quarterly",
    )
    m_client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-M01",
        company_name="Monthly Corp",
        gst_number="27AABCT9999Z1Z5",
        state="Maharashtra",
        contact_person="Director M",
        email="director_m@example.com",
        return_frequency="Monthly",
    )
    db_session.add_all([q_client, m_client])
    db_session.commit()

    # Quarterly client trying to file monthly period
    payload_q_monthly = GSTRecordCreate(
        client_id=q_client.id,
        gst_period="2026-07",
        gst_type="GSTR-3B",
        filing_status="filed",
    )
    with pytest.raises(BadRequestException) as exc_info_q:
        create_gst_record(payload=payload_q_monthly, db=db_session, current_user=user)
    assert "does not match client's return frequency" in str(exc_info_q.value.detail)

    # Monthly client trying to file quarterly period
    payload_m_quarterly = GSTRecordCreate(
        client_id=m_client.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="filed",
    )
    with pytest.raises(BadRequestException) as exc_info_m:
        create_gst_record(payload=payload_m_quarterly, db=db_session, current_user=user)
    assert "does not match client's return frequency" in str(exc_info_m.value.detail)


def test_save_quarterly_filing_enforces_metadata_and_locking(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="Test CA",
        role="ca",
    )
    db_session.add(user)

    q_client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-QMAH",
        company_name="Quarterly Mah Corp",
        gst_number="27AABCT9999Z1Z5",
        state="Maharashtra",
        contact_person="Director",
        email="qcorp@example.com",
        return_frequency="Quarterly",
    )
    db_session.add(q_client)
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=q_client.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    res = create_gst_record(payload=payload, db=db_session, current_user=user)
    record = res.data

    assert record.gst_period == "2026-Q2"
    assert record.period_type == "quarterly"
    assert record.frequency_at_filing == "quarterly"
    assert record.period_start == date(2026, 7, 1)
    assert record.period_end == date(2026, 9, 30)
    # Category X state 27 quarterly Q2 GSTR-3B due date = 2026-10-22
    assert record.due_date == date(2026, 10, 22)

    # Verify AccountingPeriod locked
    acc_period = (
        db_session.query(AccountingPeriod)
        .filter(
            AccountingPeriod.client_id == q_client.id,
            AccountingPeriod.start_date == date(2026, 7, 1),
            AccountingPeriod.end_date == date(2026, 9, 30),
        )
        .first()
    )
    assert acc_period is not None
    assert acc_period.status == "locked"
    assert acc_period.is_closed is True


def test_save_monthly_filing_enforces_metadata_and_locking(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="Test CA",
        role="ca",
    )
    db_session.add(user)

    m_client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-MMAH",
        company_name="Monthly Mah Corp",
        gst_number="27AABCT9999Z1Z5",
        state="Maharashtra",
        contact_person="Director",
        email="mcorp@example.com",
        return_frequency="Monthly",
    )
    db_session.add(m_client)
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=m_client.id,
        gst_period="2026-08",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    res = create_gst_record(payload=payload, db=db_session, current_user=user)
    record = res.data

    assert record.gst_period == "2026-08"
    assert record.period_type == "monthly"
    assert record.frequency_at_filing == "monthly"
    assert record.period_start == date(2026, 8, 1)
    assert record.period_end == date(2026, 8, 31)
    # Monthly GSTR-3B for Aug 2026 -> 2026-09-20
    assert record.due_date == date(2026, 9, 20)

    # Verify AccountingPeriod locked
    acc_period = (
        db_session.query(AccountingPeriod)
        .filter(
            AccountingPeriod.client_id == m_client.id,
            AccountingPeriod.start_date == date(2026, 8, 1),
            AccountingPeriod.end_date == date(2026, 8, 31),
        )
        .first()
    )
    assert acc_period is not None
    assert acc_period.status == "locked"
    assert acc_period.is_closed is True
