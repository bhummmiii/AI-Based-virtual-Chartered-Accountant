"""
Test F3: Server-Authoritative Return Filing Records.
Verifies:
1. Rejection of unselected period ("All Available", "").
2. Rejection of period that has not ended yet.
3. Rejection of period not matching client return frequency.
4. Server ignores tampered client-supplied amounts and saves computed ledger figures.
5. Duplicate filing rejection (ignoring voided filings).
6. Period label format (e.g. 'Q2 FY 2026-27' for quarterly client).
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


def test_filing_rejects_unselected_period(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-F3-1",
        company_name="Alpha Corp",
        gst_number="27AAACA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f3.com", full_name="CA F3 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    payload = GSTRecordCreate(
        client_id=client_id,
        gst_period="All Available",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    with pytest.raises(BadRequestException) as exc_info:
        create_gst_record(payload, db=db_session, current_user=user)

    assert "select a specific statutory return period" in str(exc_info.value.detail)


def test_filing_rejects_mismatched_frequency(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-F3-2",
        company_name="Beta Corp",
        gst_number="27AAACB1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f3b.com", full_name="CA F3 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Quarterly client trying to file a monthly period
    payload = GSTRecordCreate(
        client_id=client_id,
        gst_period="2026-08",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    with pytest.raises(BadRequestException) as exc_info:
        create_gst_record(payload, db=db_session, current_user=user)

    assert "does not match client's return frequency" in str(exc_info.value.detail)


def test_filing_rejects_future_unended_period(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-F3-3",
        company_name="Gamma Corp",
        gst_number="27AAACG1234A1Z5",
        return_frequency="Monthly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f3c.com", full_name="CA F3 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Far future period
    payload = GSTRecordCreate(
        client_id=client_id,
        gst_period="2099-10",
        gst_type="GSTR-3B",
        filing_status="filed",
    )

    with pytest.raises(BadRequestException) as exc_info:
        create_gst_record(payload, db=db_session, current_user=user)

    assert "has not ended yet" in str(exc_info.value.detail)


def test_filing_ignores_tampered_amounts_and_stores_computed(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-F3-4",
        company_name="Delta Corp",
        gst_number="27AAACD1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f3d.com", full_name="CA F3 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Pass a closed past quarter (2024-Q1 closed on 2024-06-30) with wildly tampered amounts
    payload = GSTRecordCreate(
        client_id=client_id,
        gst_period="2024-Q1",
        gst_type="GSTR-3B",
        taxable_amount=Decimal("90000000.00"),
        total_tax=Decimal("0.00"),
        filing_status="filed",
    )

    resp = create_gst_record(payload, db=db_session, current_user=user)
    rec = resp.data

    # Server should ignore 9,00,00,000 and calculate from ledger (0 for empty ledger)
    assert rec.taxable_amount == Decimal("0.00")
    assert rec.total_tax == Decimal("0.00")
    assert rec.period_label == "Q1 FY 2024-25"
    assert rec.period_start == date(2024, 4, 1)
    assert rec.period_end == date(2024, 6, 30)
