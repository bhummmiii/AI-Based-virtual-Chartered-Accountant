"""
Unit & Integration Tests for D1: Stable Account Roles and 4020 Code Collision Resolution.
Verifies that accounts are resolved by stable functional roles and that the 4020 collision
between legacy 'Sales Return Account' and modern 'Inter-State Sales' is cleanly resolved.
"""

import uuid
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.services.chart_of_accounts_service import (
    ChartOfAccountsService,
    determine_account_role,
    ICAI_DEFAULT_ACCOUNTS,
)
from app.services.gst_reconciliation_service import GstReconciliationService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_determine_account_role_tax_accounts():
    """Verify statutory tax roles derive correctly from code and name."""
    assert determine_account_role("2110", "Output CGST Account") == "OUTPUT_CGST"
    assert determine_account_role("2020", "CGST Payable Account") == "OUTPUT_CGST"
    assert determine_account_role("2120", "Output SGST Account") == "OUTPUT_SGST"
    assert determine_account_role("2130", "Output IGST Account") == "OUTPUT_IGST"
    assert determine_account_role("2140", "Output Cess Account") == "OUTPUT_CESS"

    assert determine_account_role("1210", "Input CGST Account (ITC)") == "INPUT_CGST"
    assert determine_account_role("1060", "CGST Input Tax Credit") == "INPUT_CGST"
    assert determine_account_role("1220", "Input SGST Account (ITC)") == "INPUT_SGST"
    assert determine_account_role("1230", "Input IGST Account (ITC)") == "INPUT_IGST"
    assert determine_account_role("1240", "Input Cess Account (ITC)") == "INPUT_CESS"


def test_determine_account_role_4020_collision_resolution():
    """
    CRITICAL INVARIANT: The 4020 code collision must resolve by account name and role.
    Legacy 4020 ('Sales Return Account') must resolve to SALES_RETURN.
    Modern 4020 ('Inter-State Sales') must resolve to SALES.
    4030 ('Sales Returns') must resolve to SALES_RETURN.
    4030 ('Other Operating Income') must resolve to OTHER_INCOME.
    """
    # Legacy chart
    assert determine_account_role("4020", "Sales Return Account") == "SALES_RETURN"
    assert determine_account_role("4010", "Sales Revenue Account") == "SALES"
    assert determine_account_role("4030", "Other Operating Income") == "OTHER_INCOME"

    # Modern chart (README chart)
    assert determine_account_role("4010", "Domestic Sales") == "SALES"
    assert determine_account_role("4020", "Inter-State Sales") == "SALES"
    assert determine_account_role("4030", "Sales Returns") == "SALES_RETURN"

    # Direct purchase vs purchase return
    assert determine_account_role("5010", "Purchase Expense Account") == "PURCHASE"
    assert determine_account_role("5020", "Purchase Return Account") == "PURCHASE_RETURN"

    # Trade Debtors & Creditors
    assert determine_account_role("1100", "Sundry Debtors (Trade Receivables)") == "DEBTORS"
    assert determine_account_role("1010", "Sundry Debtors") == "DEBTORS"
    assert determine_account_role("1010", "Cash in Hand") is None
    assert determine_account_role("2010", "Sundry Creditors (Trade Payables)") == "CREDITORS"
    assert determine_account_role("2200", "TDS Payable Account") is None


def test_reconciliation_resolves_4020_legacy_chart(db_session):
    """
    In a legacy chart where 4020 is 'Sales Return Account', a debit to 4020
    must reduce sales turnover, rather than being treated as revenue.
    """
    user = User(id=uuid.uuid4(), full_name="CA Test", email="ca_legacy@test.in", password_hash="pw", role="ca")
    db_session.add(user)
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        user_id=user.id,
        client_code="C-9991",
        company_name="Test Legacy Client",
        contact_person="Ankit Sharma",
        email="ankit@test.in",
        gst_number="27TEST1234A1Z5",
        status="active",
    )
    db_session.add(client)

    # Seed legacy COA
    acc_4010 = ChartOfAccounts(
        client_id=client_id,
        account_code="4010",
        account_name="Sales Revenue Account",
        account_type="revenue",
        role="SALES",
    )
    acc_4020_legacy = ChartOfAccounts(
        client_id=client_id,
        account_code="4020",
        account_name="Sales Return Account",
        account_type="revenue",
        role="SALES_RETURN",
    )
    acc_2110 = ChartOfAccounts(
        client_id=client_id,
        account_code="2110",
        account_name="Output CGST Account",
        account_type="liability",
        role="OUTPUT_CGST",
    )
    db_session.add_all([acc_4010, acc_4020_legacy, acc_2110])
    db_session.commit()

    # 1. Post a Sale: Cr 4010 ₹100,000
    je_sale = JournalEntry(
        client_id=client_id,
        entry_number="JE-SALE-1",
        entry_type="sales",
        entry_date=date(2026, 8, 1),
        status="posted",
        total_debit=Decimal("100000.00"),
        total_credit=Decimal("100000.00"),
    )
    db_session.add(je_sale)
    db_session.flush()

    line_sale = JournalEntryLine(
        journal_entry_id=je_sale.id,
        line_number=1,
        account_id=acc_4010.id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("100000.00"),
    )
    db_session.add(line_sale)

    # 2. Post a Credit Note: Dr 4020 ₹20,000 (Sales Return)
    je_cn = JournalEntry(
        client_id=client_id,
        entry_number="JE-CN-1",
        entry_type="journal",
        entry_date=date(2026, 8, 10),
        status="posted",
        total_debit=Decimal("20000.00"),
        total_credit=Decimal("20000.00"),
    )
    db_session.add(je_cn)
    db_session.flush()

    line_cn = JournalEntryLine(
        journal_entry_id=je_cn.id,
        line_number=1,
        account_id=acc_4020_legacy.id,
        debit_amount=Decimal("20000.00"),
        credit_amount=Decimal("0.00"),
    )
    db_session.add(line_cn)
    db_session.commit()

    # Calculate GSTR-1 reconciliation
    res = GstReconciliationService.reconcile_gstr1(db_session, client_id, user, period="2026-Q2")

    # Net turnover must be 100,000 - 20,000 = 80,000.00
    assert res.ledger_sales_turnover == Decimal("80000.00")
    assert res.total_outward_taxable == Decimal("80000.00")


def test_reconciliation_resolves_4020_modern_chart(db_session):
    """
    In a modern chart where 4020 is 'Inter-State Sales', a credit to 4020
    must increase sales turnover (not be treated as return).
    """
    user = User(id=uuid.uuid4(), full_name="CA Modern Test", email="ca_modern@test.in", password_hash="pw", role="ca")
    db_session.add(user)
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        user_id=user.id,
        client_code="C-9992",
        company_name="Test Modern Client",
        contact_person="Rohan Gupta",
        email="rohan@test.in",
        gst_number="27TEST1234A1Z5",
        status="active",
    )
    db_session.add(client)

    acc_4010 = ChartOfAccounts(
        client_id=client_id,
        account_code="4010",
        account_name="Domestic Sales",
        account_type="revenue",
        role="SALES",
    )
    acc_4020_modern = ChartOfAccounts(
        client_id=client_id,
        account_code="4020",
        account_name="Inter-State Sales",
        account_type="revenue",
        role="SALES",
    )
    acc_4030_return = ChartOfAccounts(
        client_id=client_id,
        account_code="4030",
        account_name="Sales Returns",
        account_type="revenue",
        role="SALES_RETURN",
    )
    db_session.add_all([acc_4010, acc_4020_modern, acc_4030_return])
    db_session.commit()

    # 1. Post Domestic Sale Cr 4010 ₹100,000
    je1 = JournalEntry(
        client_id=client_id,
        entry_number="JE-DOM-1",
        entry_type="sales",
        entry_date=date(2026, 8, 1),
        status="posted",
        total_debit=Decimal("100000.00"),
        total_credit=Decimal("100000.00"),
    )
    db_session.add(je1)
    db_session.flush()
    db_session.add(JournalEntryLine(
        journal_entry_id=je1.id,
        line_number=1,
        account_id=acc_4010.id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("100000.00"),
    ))

    # 2. Post Inter-State Sale Cr 4020 ₹200,000
    je2 = JournalEntry(
        client_id=client_id,
        entry_number="JE-INTER-1",
        entry_type="sales",
        entry_date=date(2026, 8, 5),
        status="posted",
        total_debit=Decimal("200000.00"),
        total_credit=Decimal("200000.00"),
    )
    db_session.add(je2)
    db_session.flush()
    db_session.add(JournalEntryLine(
        journal_entry_id=je2.id,
        line_number=1,
        account_id=acc_4020_modern.id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("200000.00"),
    ))

    # 3. Post Sales Return Dr 4030 ₹15,000
    je3 = JournalEntry(
        client_id=client_id,
        entry_number="JE-RET-1",
        entry_type="journal",
        entry_date=date(2026, 8, 12),
        status="posted",
        total_debit=Decimal("15000.00"),
        total_credit=Decimal("15000.00"),
    )
    db_session.add(je3)
    db_session.flush()
    db_session.add(JournalEntryLine(
        journal_entry_id=je3.id,
        line_number=1,
        account_id=acc_4030_return.id,
        debit_amount=Decimal("15000.00"),
        credit_amount=Decimal("0.00"),
    ))
    db_session.commit()

    res = GstReconciliationService.reconcile_gstr1(db_session, client_id, user, period="2026-Q2")

    # Net turnover must be 100,000 + 200,000 - 15,000 = 285,000.00
    assert res.ledger_sales_turnover == Decimal("285000.00")
    assert res.total_outward_taxable == Decimal("285000.00")
