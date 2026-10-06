"""
Unit and integration tests for E1:
GSTR-3B cash calculation and negative ITC heads.

Rule:
Per head h:
  liability[h] = net outward tax[h] + max(-net_itc[h], 0) ("ITC reversal payable")
  credit[h] = max(net_itc[h], 0)

Set-off order (statutory, CGST Act Sections 49, 49A, 49B):
  IGST credit -> IGST liability, then CGST liability, then SGST liability
  CGST credit -> CGST liability, then IGST liability (never SGST)
  SGST credit -> SGST liability, then IGST liability (never CGST)
  Cash[h] = remaining liability floored at 0
  Unused credit[h] = carry-forward ITC per head

Invariant:
  cash_total + unused_credit_total == total_liability - total_net_itc
  (whenever no outward head is negative)
"""

import sys
import os
import uuid
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import Base, SessionLocal
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_period import AccountingPeriod
from app.models.gst_record import GSTRecord
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.schemas.gst_reconciliation import Gstr3bResponse


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
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
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_e1_statutory_setoff_acceptance_math():
    """
    Test statutory cash calculation math matching the exact acceptance data:
    Outward: IGST 36,000 | CGST 7,700 | SGST 7,700 | Total 51,400
    Net ITC: IGST -1,800 | CGST 9,000 | SGST 9,000 | Total 16,200
    Expected:
      Liability: IGST 37,800 (36,000 + 1,800), CGST 7,700, SGST 7,700
      Credit: CGST 9,000, SGST 9,000
      CGST credit pays CGST 7,700, surplus 1,300 -> IGST
      SGST credit pays SGST 7,700, surplus 1,300 -> IGST
      Cash: IGST 35,200, CGST 0, SGST 0, TOTAL 35,200
      Carry-forward: 0
      Invariant: 35,200 + 0 == 51,400 - 16,200
    """
    raw_l_igst = Decimal("36000.00")
    raw_l_cgst = Decimal("7700.00")
    raw_l_sgst = Decimal("7700.00")

    net_itc_igst = Decimal("-1800.00")
    net_itc_cgst = Decimal("9000.00")
    net_itc_sgst = Decimal("9000.00")

    itc_rev_igst = max(-net_itc_igst, Decimal("0.00"))
    itc_rev_cgst = max(-net_itc_cgst, Decimal("0.00"))
    itc_rev_sgst = max(-net_itc_sgst, Decimal("0.00"))

    assert itc_rev_igst == Decimal("1800.00")
    assert itc_rev_cgst == Decimal("0.00")
    assert itc_rev_sgst == Decimal("0.00")

    rem_l_igst = max(Decimal("0.00"), raw_l_igst) + itc_rev_igst
    rem_l_cgst = max(Decimal("0.00"), raw_l_cgst) + itc_rev_cgst
    rem_l_sgst = max(Decimal("0.00"), raw_l_sgst) + itc_rev_sgst

    assert rem_l_igst == Decimal("37800.00")
    assert rem_l_cgst == Decimal("7700.00")
    assert rem_l_sgst == Decimal("7700.00")

    rem_c_igst = max(Decimal("0.00"), net_itc_igst)
    rem_c_cgst = max(Decimal("0.00"), net_itc_cgst)
    rem_c_sgst = max(Decimal("0.00"), net_itc_sgst)

    assert rem_c_igst == Decimal("0.00")
    assert rem_c_cgst == Decimal("9000.00")
    assert rem_c_sgst == Decimal("9000.00")

    # Step 1: IGST credit (0)
    used_igst_igst = min(rem_c_igst, rem_l_igst)
    rem_l_igst -= used_igst_igst
    rem_c_igst -= used_igst_igst

    # Step 2: CGST credit
    used_cgst_cgst = min(rem_c_cgst, rem_l_cgst)
    rem_l_cgst -= used_cgst_cgst
    rem_c_cgst -= used_cgst_cgst

    used_cgst_igst = min(rem_c_cgst, rem_l_igst)
    rem_l_igst -= used_cgst_igst
    rem_c_cgst -= used_cgst_igst

    # Step 3: SGST credit
    used_sgst_sgst = min(rem_c_sgst, rem_l_sgst)
    rem_l_sgst -= used_sgst_sgst
    rem_c_sgst -= used_sgst_sgst

    used_sgst_igst = min(rem_c_sgst, rem_l_igst)
    rem_l_igst -= used_sgst_igst
    rem_c_sgst -= used_sgst_igst

    cash_igst = rem_l_igst
    cash_cgst = rem_l_cgst
    cash_sgst = rem_l_sgst
    total_cash = cash_igst + cash_cgst + cash_sgst

    assert cash_igst == Decimal("35200.00")
    assert cash_cgst == Decimal("0.00")
    assert cash_sgst == Decimal("0.00")
    assert total_cash == Decimal("35200.00")

    # Invariant
    total_liab = raw_l_igst + raw_l_cgst + raw_l_sgst
    total_itc = net_itc_igst + net_itc_cgst + net_itc_sgst
    total_unused = rem_c_igst + rem_c_cgst + rem_c_sgst

    assert total_cash + total_unused == total_liab - total_itc


def test_e1_generate_gstr3b_negative_itc_integration(db_session):
    """
    Integration test creating a client with outward liability and negative ITC in one head.
    Verifies that generate_gstr3b executes the E1 rule and produces:
      - Table 4 row (A) Available (purchases only)
      - Table 4 row (B) Reversed (positive amount)
      - Table 4 row (C) Net ITC
      - Table 6 cash payable of 35,200
      - Invariant: cash_total + unused_credit == liability - net_itc
    """
    user = User(
        id=uuid.uuid4(),
        email=f"e1_test_{uuid.uuid4().hex[:6]}@example.com",
        full_name="CA Auditor",
        password_hash="mock_hash",
        role="admin",
        is_active=True,
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="E1-TEST-001",
        company_name="Alpha Traders Pvt Ltd",
        contact_person="Director",
        gst_number="27AAACA9999A1Z5",
        state="Maharashtra",
        billing_cycle="quarterly",
        return_frequency="Quarterly",
        status="active",
    )
    db_session.add_all([user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)

    # Fetch accounts
    coa = {
        acc.account_code: acc
        for acc in db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()
    }

    # 1. Post Outward Sales Vouchers: S1 (intra 100k, 9k CGST, 9k SGST), S2 (inter 200k, 36k IGST), S3 (intra 20k, 500 CGST, 500 SGST)
    # Total outward before CN: 320k taxable | 36k IGST | 9.5k CGST | 9.5k SGST
    # Sales return CN1: -20k taxable | -1.8k CGST | -1.8k SGST
    # Net outward = 300k taxable | 36k IGST | 7.7k CGST | 7.7k SGST | Total 51.4k tax

    # Doc S2: Inter-state sales
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-002",
        invoice_date="2026-07-15",
        gstin="29BBBCB1111B1Z2",
        amount=Decimal("236000.00"),
        taxable_amount=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        status="verified",
    )
    # Doc S1: Intra-state sales
    doc_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="INV-001",
        invoice_date="2026-07-10",
        gstin="27CCCC1111C1Z3",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
    )
    # Doc S3: B2C sales
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        invoice_number="INV-003",
        invoice_date="2026-08-01",
        amount=Decimal("21000.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"),
        sgst=Decimal("500.00"),
        status="verified",
    )
    # Doc CN1: Credit note
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="credit_note",
        invoice_number="CN-001",
        invoice_date="2026-08-10",
        gstin="27CCCC1111C1Z3",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        status="verified",
    )

    # Inward Doc P1: Purchase
    doc_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        invoice_number="PUR-001",
        invoice_date="2026-07-20",
        gstin="27DDDCD1111D1Z4",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
    )
    # Inward Doc PDN1: Purchase return debit note (IGST -1,800)
    doc_pdn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="debit_note",
        invoice_number="PDN-001",
        invoice_date="2026-08-15",
        gstin="33EEEEE1111E1Z5",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("-10000.00"),
        igst=Decimal("-1800.00"),
        status="verified",
    )

    db_session.add_all([doc_s2, doc_s1, doc_s3, doc_cn1, doc_p1, doc_pdn1])
    db_session.commit()

    # Create Journal Entries
    # S2
    je_s2 = JournalEntry(
        client_id=client.id,
        document_id=doc_s2.id,
        entry_number="JE-S2",
        entry_date=date(2026, 7, 15),
        entry_type="sales",
        total_debit=Decimal("236000.00"),
        total_credit=Decimal("236000.00"),
        status="posted",
    )
    je_s2.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("236000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("200000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2130"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("36000.00"), tax_head="igst"),
    ]

    # S1
    je_s1 = JournalEntry(
        client_id=client.id,
        document_id=doc_s1.id,
        entry_number="JE-S1",
        entry_date=date(2026, 7, 10),
        entry_type="sales",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
        status="posted",
    )
    je_s1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), tax_head="cgst"),
        JournalEntryLine(line_number=4, account_id=coa["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), tax_head="sgst"),
    ]

    # S3
    je_s3 = JournalEntry(
        client_id=client.id,
        document_id=doc_s3.id,
        entry_number="JE-S3",
        entry_date=date(2026, 8, 1),
        entry_type="sales",
        total_debit=Decimal("21000.00"),
        total_credit=Decimal("21000.00"),
        status="posted",
    )
    je_s3.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("21000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("20000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00"), tax_head="cgst"),
        JournalEntryLine(line_number=4, account_id=coa["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00"), tax_head="sgst"),
    ]

    # CN1
    je_cn1 = JournalEntry(
        client_id=client.id,
        document_id=doc_cn1.id,
        entry_number="JE-CN1",
        entry_date=date(2026, 8, 10),
        entry_type="journal",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
        status="posted",
    )
    je_cn1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["4020"].id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["2110"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), tax_head="cgst"),
        JournalEntryLine(line_number=3, account_id=coa["2120"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), tax_head="sgst"),
        JournalEntryLine(line_number=4, account_id=coa["1100"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00")),
    ]

    # P1
    je_p1 = JournalEntry(
        client_id=client.id,
        document_id=doc_p1.id,
        entry_number="JE-P1",
        entry_date=date(2026, 7, 20),
        entry_type="purchase",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
        status="posted",
    )
    je_p1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["5010"].id, debit_amount=Decimal("100000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["1210"].id, debit_amount=Decimal("9000.00"), credit_amount=Decimal("0.00"), tax_head="cgst"),
        JournalEntryLine(line_number=3, account_id=coa["1220"].id, debit_amount=Decimal("9000.00"), credit_amount=Decimal("0.00"), tax_head="sgst"),
        JournalEntryLine(line_number=4, account_id=coa["2010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("118000.00")),
    ]

    # PDN1
    je_pdn1 = JournalEntry(
        client_id=client.id,
        document_id=doc_pdn1.id,
        entry_number="JE-PDN1",
        entry_date=date(2026, 8, 15),
        entry_type="journal",
        total_debit=Decimal("11800.00"),
        total_credit=Decimal("11800.00"),
        status="posted",
    )
    je_pdn1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["2010"].id, debit_amount=Decimal("11800.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["5020"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("10000.00")),
        JournalEntryLine(line_number=3, account_id=coa["1230"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("1800.00"), tax_head="igst"),
    ]

    db_session.add_all([je_s2, je_s1, je_s3, je_cn1, je_p1, je_pdn1])
    db_session.commit()

    resp = GstReconciliationService.generate_gstr3b(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-Q2",
    )

    # 1. Table 3.1
    assert resp.table_3_1_outward.taxable_value == Decimal("300000.00")
    assert resp.table_3_1_outward.igst == Decimal("36000.00")
    assert resp.table_3_1_outward.cgst == Decimal("7700.00")
    assert resp.table_3_1_outward.sgst == Decimal("7700.00")

    # 2. Table 4 Net ITC
    assert resp.table_4_net_itc.taxable_value == Decimal("90000.00")
    assert resp.table_4_net_itc.igst == Decimal("-1800.00")
    assert resp.table_4_net_itc.cgst == Decimal("9000.00")
    assert resp.table_4_net_itc.sgst == Decimal("9000.00")

    # 3. Table 4 Decomposed: (A) purchases only, (B) reversals (positive)
    assert resp.table_4_itc_available.taxable_value == Decimal("100000.00")
    assert resp.table_4_itc_available.cgst == Decimal("9000.00")
    assert resp.table_4_itc_available.sgst == Decimal("9000.00")
    assert resp.table_4_itc_available.igst == Decimal("0.00")

    assert resp.table_4_itc_reversed.taxable_value == Decimal("10000.00")
    assert resp.table_4_itc_reversed.igst == Decimal("1800.00")

    # 4. Table 6 Cash Payable
    assert resp.tax_payable_in_cash == Decimal("35200.00")
    assert resp.cash_payable_igst == Decimal("35200.00")
    assert resp.cash_payable_cgst == Decimal("0.00")
    assert resp.cash_payable_sgst == Decimal("0.00")
    assert resp.excess_credit_carried_forward == Decimal("0.00")

    # 5. E1 Flags and Invariants
    assert resp.itc_reversal_payable_igst == Decimal("1800.00")
    assert resp.itc_reversal_payable_total == Decimal("1800.00")
    assert resp.has_negative_itc_head is True
    assert resp.needs_ca_review is True
    assert any("Negative ITC head" in note for note in resp.review_notes)

    # Invariant: cash_total + unused_credit == liability - net_itc
    tot_liab = resp.table_3_1_outward.igst + resp.table_3_1_outward.cgst + resp.table_3_1_outward.sgst
    tot_net_itc = resp.table_4_net_itc.igst + resp.table_4_net_itc.cgst + resp.table_4_net_itc.sgst
    assert resp.tax_payable_in_cash + resp.excess_credit_carried_forward == tot_liab - tot_net_itc
