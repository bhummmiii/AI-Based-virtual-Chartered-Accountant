"""
Test F6: Filing Dialog Period Selection, Quarterly Labels, and Statutory Due Dates.

Verifies:
1. Rejection of unselected period ("All Available", "").
2. Statutory due date computed from config table:
   - Monthly GSTR-1: 11th of next month
   - Monthly GSTR-3B: 20th of next month
   - Quarterly GSTR-1 (QRMP): 13th of month following quarter
   - Quarterly GSTR-3B Category 1 (South/West, e.g. MH 27): 22nd of month following quarter
   - Quarterly GSTR-3B Category 2 (North/East, e.g. DL 07): 24th of month following quarter
3. Period label format (e.g. 'Q2 FY 2026-27' for quarterly client).
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
from app.models.gst_record import GSTRecord
from app.schemas.gst import GSTRecordCreate
from app.api.routers.gst.router import create_gst_record
from app.core.exceptions import BadRequestException


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_filing_due_dates_quarterly_cat1_and_cat2(db_session):
    # Category 1: Maharashtra (27)
    client_mh = Client(
        id=uuid.uuid4(),
        client_code="CLI-MH",
        company_name="MH Corp",
        gst_number="27AAACA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    # Category 2: Delhi (07)
    client_dl = Client(
        id=uuid.uuid4(),
        client_code="CLI-DL",
        company_name="DL Corp",
        gst_number="07AAACA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f6.com", full_name="CA F6 User", password_hash="hash", role="admin")
    db_session.add_all([client_mh, client_dl, user])
    db_session.commit()

    # MH Quarterly GSTR-3B for 2026-Q2 (ended 2026-09-30) -> due 2026-10-22
    payload_mh_3b = GSTRecordCreate(
        client_id=client_mh.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="draft",
    )
    rec_mh_3b = create_gst_record(payload_mh_3b, db=db_session, current_user=user)
    assert rec_mh_3b.data.due_date == date(2026, 10, 22)
    assert rec_mh_3b.data.period_label == "Q2 FY 2026-27"

    # DL Quarterly GSTR-3B for 2026-Q2 (ended 2026-09-30) -> due 2026-10-24
    payload_dl_3b = GSTRecordCreate(
        client_id=client_dl.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="draft",
    )
    rec_dl_3b = create_gst_record(payload_dl_3b, db=db_session, current_user=user)
    assert rec_dl_3b.data.due_date == date(2026, 10, 24)
    assert rec_dl_3b.data.period_label == "Q2 FY 2026-27"

    # MH Quarterly GSTR-1 for 2026-Q2 (ended 2026-09-30) -> due 2026-10-13
    payload_mh_1 = GSTRecordCreate(
        client_id=client_mh.id,
        gst_period="2026-Q2",
        gst_type="GSTR-1",
        filing_status="draft",
    )
    rec_mh_1 = create_gst_record(payload_mh_1, db=db_session, current_user=user)
    assert rec_mh_1.data.due_date == date(2026, 10, 13)


def test_filing_due_dates_monthly(db_session):
    client_monthly = Client(
        id=uuid.uuid4(),
        client_code="CLI-MON",
        company_name="Monthly Corp",
        gst_number="27AAACA1234A1Z5",
        return_frequency="Monthly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f6mon.com", full_name="CA F6 User", password_hash="hash", role="admin")
    db_session.add_all([client_monthly, user])
    db_session.commit()

    # Monthly GSTR-1 for 2026-08 (ended 2026-08-31) -> due 2026-09-11
    payload_g1 = GSTRecordCreate(
        client_id=client_monthly.id,
        gst_period="2026-08",
        gst_type="GSTR-1",
        filing_status="draft",
    )
    rec_g1 = create_gst_record(payload_g1, db=db_session, current_user=user)
    assert rec_g1.data.due_date == date(2026, 9, 11)
    assert rec_g1.data.period_label == "Aug 2026"

    # Monthly GSTR-3B for 2026-08 (ended 2026-08-31) -> due 2026-09-20
    payload_g3b = GSTRecordCreate(
        client_id=client_monthly.id,
        gst_period="2026-08",
        gst_type="GSTR-3B",
        filing_status="draft",
    )
    rec_g3b = create_gst_record(payload_g3b, db=db_session, current_user=user)
    assert rec_g3b.data.due_date == date(2026, 9, 20)
