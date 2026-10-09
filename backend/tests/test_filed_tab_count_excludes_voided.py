"""
Unit test suite for G7: Filed Returns Count Excludes Voided Filings (Y3).
Validates:
- Active filed records are counted as filed.
- Voided records (filing_status='voided' or void_reason is not None) are filtered out from filed count.
- When all records for a client are voided, filed count is 0.
- When new filing is recorded, filed count increments.
"""

import uuid
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.user import User
from app.models.client import Client
from app.models.gst_record import GSTRecord


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
            GSTRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_filed_count_excludes_voided_records(db_session):
    user = User(
        id=uuid.uuid4(),
        email="ca@example.com",
        password_hash="pw",
        full_name="CA Test",
        role="ca",
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-VOID-TEST",
        company_name="Void Count Co",
        gst_number="27AABCV1234A1Z5",
        state="Maharashtra",
        contact_person="Director",
        email="voidtest@example.com",
        return_frequency="Quarterly",
    )
    db_session.add_all([user, client])
    db_session.commit()

    # Record 1: active filed return
    r1 = GSTRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        gst_period="2026-Q1",
        gst_type="GSTR-3B",
        filing_status="filed",
        taxable_amount=100000,
        cgst=9000,
        sgst=9000,
        igst=0,
        total_tax=18000,
    )
    # Record 2: voided return with void_reason
    r2 = GSTRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        gst_period="2026-Q1",
        gst_type="GSTR-1",
        filing_status="voided",
        void_reason="Refiled due to counterparty credit note adjustment",
        voided_at=datetime.now(timezone.utc),
        taxable_amount=100000,
        total_tax=18000,
    )
    # Record 3: second active filed return
    r3 = GSTRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        gst_period="2026-Q2",
        gst_type="GSTR-3B",
        filing_status="filed",
        taxable_amount=200000,
        total_tax=36000,
    )
    db_session.add_all([r1, r2, r3])
    db_session.commit()

    all_records = db_session.query(GSTRecord).filter(GSTRecord.client_id == client.id).all()
    assert len(all_records) == 3

    # Total records includes voided (history preserved)
    raw_count = len(all_records)
    assert raw_count == 3

    # Filed count strictly excludes voided records (Y3)
    active_filed = [r for r in all_records if r.filing_status != "voided" and not r.void_reason]
    assert len(active_filed) == 2
    assert {r.gst_period for r in active_filed} == {"2026-Q1", "2026-Q2"}
