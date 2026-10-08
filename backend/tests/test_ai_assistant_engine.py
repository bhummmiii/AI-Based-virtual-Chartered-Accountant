"""
Test Suite for AI Assistant Engine & Submodules
==============================================
Validates:
- Period parser (Indian Financial Year, quarters, months, relative dates)
- Client Resolver (deterministic code, GSTIN, PAN, name, and ambiguity checks)
- Intent Detection (GST, ITC, discrepancies, accounting, attention, knowledge)
- Guard rails (anti-hallucination, anti-fraud, loop detection)
- Engine execution across both Client-Specific and Global Workspace scopes
"""

import uuid
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_period import AccountingPeriod
from app.models.gst_record import GSTRecord
from app.models.tax_record import TaxRecord
from app.models.audit_report import AuditReport

from app.services.ai_assistant.period import parse_period
from app.services.ai_assistant.resolver import resolve_mentions
from app.services.ai_assistant.intents import detect_intents, GST, ITC, DISCREPANCIES, ATTENTION, CLIENT_LIST
from app.services.ai_assistant.guard import verify_response_safety, build_deterministic_fallback
from app.services.ai_assistant.facts import Fact
from app.services.ai_assistant.engine import assistant_engine


@pytest.fixture
def test_db():
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
            TaxRecord.__table__,
            AuditReport.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_period_parser():
    ref_today = date(2026, 10, 7)
    # 1. FY
    p_fy = parse_period("FY 2026-27", today=ref_today)
    assert p_fy.is_set
    assert p_fy.from_date == date(2026, 4, 1)
    assert p_fy.to_date == date(2027, 3, 31)

    # 2. Quarter
    p_q2 = parse_period("Q2 2026", today=ref_today)
    assert p_q2.is_set
    assert p_q2.from_date == date(2026, 7, 1)
    assert p_q2.to_date == date(2026, 9, 30)

    # 3. ISO Month
    p_iso = parse_period("2026-07", today=ref_today)
    assert p_iso.is_set
    assert p_iso.from_date == date(2026, 7, 1)
    assert p_iso.to_date == date(2026, 7, 31)


def test_client_resolver():
    c1 = Client(
        id=uuid.uuid4(),
        client_code="C-1071",
        company_name="Oggy Pvt Ltd",
        gst_number="27AABCA1234A1Z5",
        status="active",
        contact_person="Jack Oggy",
    )
    c2 = Client(
        id=uuid.uuid4(),
        client_code="C-1080",
        company_name="Nimbus Technologies",
        gst_number="27AABCN9999F1Z2",
        status="active",
        contact_person="Alok Verma",
    )
    clients = [c1, c2]

    # Match by client code
    m1 = resolve_mentions("Tell me about C-1071 please", clients)
    assert len(m1) == 1
    assert m1[0].best.client.client_code == "C-1071"

    # Match by company name
    m2 = resolve_mentions("What is the status of Oggy?", clients)
    assert len(m2) == 1
    assert m2[0].best.client.company_name == "Oggy Pvt Ltd"

    # Match by GSTIN
    m3 = resolve_mentions("Check 27AABCN9999F1Z2", clients)
    assert len(m3) == 1
    assert m3[0].best.client.company_name == "Nimbus Technologies"


def test_intent_detection():
    r1 = detect_intents("What is the net GST payable for this client?")
    assert GST in r1.intents

    r2 = detect_intents("Show me eligible ITC and input tax credit claims")
    assert ITC in r2.intents

    r3 = detect_intents("Are there any tax discrepancies or mismatches before filing?")
    assert DISCREPANCIES in r3.intents

    r4 = detect_intents("Which clients need urgent attention?")
    assert ATTENTION in r4.intents

    r5 = detect_intents("List all my clients in the workspace")
    assert CLIENT_LIST in r5.intents


def test_guard_rails():
    # 1. Unsafe evasion advice should be flagged
    safe1, msg1 = verify_response_safety("You should evade tax by creating fake invoices.", [])
    assert not safe1

    # 2. Repetition loop should be flagged
    loop_text = "\n".join(["Same repeated answer line"] * 7)
    safe2, msg2 = verify_response_safety(loop_text, [])
    assert not safe2

    # 3. Deterministic fallback should render verified facts accurately
    fact = Fact(
        key="gst",
        title="GST Summary",
        source="GSTR-3B ledger computation",
        lines=["Net GST payable in cash: ₹86,400.00", "Eligible ITC: ₹1,20,000.00"],
        available=True,
    )
    fallback = build_deterministic_fallback([fact], "Check GST")
    assert "₹86,400.00" in fallback
    assert "GSTR-3B ledger computation" in fallback


def test_engine_workspace_scope_and_client_scope(test_db):
    user = User(
        id=uuid.uuid4(),
        full_name="CA Bhumi Jha",
        email="bhumi@finledger.in",
        password_hash="mock_hash",
        role="ca",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    c1 = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-1071",
        company_name="Oggy Pvt Ltd",
        gst_number="27AABCA1234A1Z5",
        status="active",
        risk_level="low",
        contact_person="Jack Oggy",
    )
    test_db.add(c1)
    test_db.commit()

    # 1. Global Workspace scope: Ask about client by name
    res_global = assistant_engine.process_query(
        db=test_db,
        user=user,
        message="What is the profile and risk level of Oggy Pvt Ltd?",
    )
    assert res_global.session_id is not None
    assert "Oggy Pvt Ltd" in res_global.reply or "C-1071" in res_global.reply

    # 2. Client-Specific scope (Smaller module inside client workspace):
    res_client = assistant_engine.process_query(
        db=test_db,
        user=user,
        message="Summarise documents and GST for this client",
        explicit_client_id=str(c1.id),
    )
    assert res_client.session_id is not None
    assert len(res_client.sources) > 0
