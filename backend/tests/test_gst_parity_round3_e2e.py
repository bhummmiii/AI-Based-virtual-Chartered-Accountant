"""
End-to-End Data Parity Verification Test (E4) for GST Round 3 Parity.

Verifies the full client ledger simultaneously against the same DB session:
1. Table 3.1 computation (300,000 / 18,000 / 36,000 / 51,400 total tax: 7,700 CGST + 7,700 SGST + 36,000 IGST)
2. Table 4 computation (0 / 8,100 / 8,100 / 16,200)
3. Table 6 statutory set-off (35,200 net cash, all on IGST, CGST/SGST zero cash)
4. Table 12 HSN outward summary (3 rows: 4820, 9401, 998314; matching turnover, tax, and rates; no OTH row; no payment voucher included)
5. GSTR-1 outward total equals Table 3.1 outward total exactly (300,000 / 51,400)
6. ITC ledger balances post-settlement: 0 IGST, 0 CGST, 0 SGST carried forward.
"""

import sys
import os
import uuid
import json
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import Base
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


def test_e4_full_gst_data_parity_round3(db_session):
    """
    Comprehensive parity test verifying all 6 assertions simultaneously.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"e4_ca_{uuid.uuid4().hex[:6]}@example.com",
        full_name="CA Senior Auditor",
        password_hash="hashed_secret",
        role="admin",
        is_active=True,
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="C-1071",
        company_name="ABC Traders Pvt Ltd",
        contact_person="Accounts Head",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
        billing_cycle="quarterly",
        return_frequency="Quarterly",
        status="active",
    )
    db_session.add_all([user, client])
    db_session.commit()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    coa = {
        acc.account_code: acc
        for acc in db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()
    }

    # Uploaded Documents
    # S1: B2B Invoice ABC/26-27/001
    doc_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="ABC/26-27/001",
        invoice_date="2026-07-05",
        gstin="27AAAPM5678B1Z2",
        customer="Mehta Enterprises",
        hsn="9401",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "9401",
                    "item_name": "Office Chair (ergonomic)",
                    "quantity": 50,
                    "unit": "NOS",
                    "taxable_amount": 100000.0,
                    "cgst": 9000.0,
                    "sgst": 9000.0,
                }
            ]
        }),
    )

    # S2: B2B Inter-state Invoice ABC/26-27/002
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        invoice_number="ABC/26-27/002",
        invoice_date="2026-07-15",
        gstin="29BBBBB2222B1Z3",
        customer="Bangalore Tech",
        hsn="998314",
        amount=Decimal("236000.00"),
        taxable_amount=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        status="verified",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "998314",
                    "item_name": "Software development services",
                    "quantity": 1,
                    "unit": "OTH",
                    "taxable_amount": 200000.0,
                    "igst": 36000.0,
                }
            ]
        }),
    )

    # S3: B2C Invoice ABC/26-27/003
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        invoice_number="ABC/26-27/003",
        invoice_date="2026-07-20",
        customer="Walk-in Customer (Unregistered)",
        hsn="4820",
        amount=Decimal("21000.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"),
        sgst=Decimal("500.00"),
        status="verified",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "4820",
                    "item_name": "Notebooks and stationery",
                    "quantity": 200,
                    "unit": "NOS",
                    "taxable_amount": 20000.0,
                    "cgst": 500.0,
                    "sgst": 500.0,
                }
            ]
        }),
    )

    # CN1: Credit Note ABC/CN/26-27/001
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="credit_note",
        invoice_number="ABC/CN/26-27/001",
        invoice_date="2026-08-10",
        gstin="27AAAPM5678B1Z2",
        customer="Mehta Enterprises",
        hsn="9401",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        status="verified",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "9401",
                    "item_name": "Sales return - Office Chair (10 nos)",
                    "quantity": 10,
                    "unit": "NOS",
                    "taxable_amount": 20000.0,
                    "cgst": 1800.0,
                    "sgst": 1800.0,
                }
            ]
        }),
    )

    # P1: Purchase Invoice PUR/26-27/001 (Inward, eligible ITC 8,100 CGST + 8,100 SGST)
    doc_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_invoice",
        invoice_number="PUR/26-27/001",
        invoice_date="2026-07-10",
        gstin="27AAACS9999S1Z4",
        customer="Raw Material Suppliers",
        amount=Decimal("106200.00"),
        taxable_amount=Decimal("90000.00"),
        cgst=Decimal("8100.00"),
        sgst=Decimal("8100.00"),
        status="verified",
    )

    # Payment Voucher: Challan 84,700 (MUST BE EXCLUDED FROM TABLE 12)
    doc_pmt = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="tax_challan",
        invoice_number="26100012345678",
        invoice_date="2026-08-20",
        amount=Decimal("84700.00"),
        taxable_amount=Decimal("84700.00"),
        status="verified",
    )

    db_session.add_all([doc_s1, doc_s2, doc_s3, doc_cn1, doc_p1, doc_pmt])
    db_session.commit()

    # Journal Entries
    # S1 JE
    je_s1 = JournalEntry(
        client_id=client.id, document_id=doc_s1.id, entry_number="JE-S1",
        entry_date=date(2026, 7, 5), entry_type="sales",
        total_debit=Decimal("118000.00"), total_credit=Decimal("118000.00"), status="posted",
    )
    je_s1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
        JournalEntryLine(line_number=4, account_id=coa["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
    ]

    # S2 JE
    je_s2 = JournalEntry(
        client_id=client.id, document_id=doc_s2.id, entry_number="JE-S2",
        entry_date=date(2026, 7, 15), entry_type="sales",
        total_debit=Decimal("236000.00"), total_credit=Decimal("236000.00"), status="posted",
    )
    je_s2.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("236000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("200000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2130"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("36000.00")),
    ]

    # S3 JE
    je_s3 = JournalEntry(
        client_id=client.id, document_id=doc_s3.id, entry_number="JE-S3",
        entry_date=date(2026, 7, 20), entry_type="sales",
        total_debit=Decimal("21000.00"), total_credit=Decimal("21000.00"), status="posted",
    )
    je_s3.lines = [
        JournalEntryLine(line_number=1, account_id=coa["1100"].id, debit_amount=Decimal("21000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("20000.00")),
        JournalEntryLine(line_number=3, account_id=coa["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00")),
        JournalEntryLine(line_number=4, account_id=coa["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00")),
    ]

    # CN1 JE
    je_cn1 = JournalEntry(
        client_id=client.id, document_id=doc_cn1.id, entry_number="JE-CN1",
        entry_date=date(2026, 8, 10), entry_type="journal",
        total_debit=Decimal("23600.00"), total_credit=Decimal("23600.00"), status="posted",
    )
    je_cn1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["4020"].id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["2110"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=3, account_id=coa["2120"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=4, account_id=coa["1100"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00")),
    ]

    # P1 JE
    je_p1 = JournalEntry(
        client_id=client.id, document_id=doc_p1.id, entry_number="JE-P1",
        entry_date=date(2026, 7, 10), entry_type="purchase",
        total_debit=Decimal("106200.00"), total_credit=Decimal("106200.00"), status="posted",
    )
    je_p1.lines = [
        JournalEntryLine(line_number=1, account_id=coa["5010"].id, debit_amount=Decimal("90000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["1210"].id, debit_amount=Decimal("8100.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=3, account_id=coa["1220"].id, debit_amount=Decimal("8100.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=4, account_id=coa["2010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("106200.00")),
    ]

    # PMT JE
    je_pmt = JournalEntry(
        client_id=client.id, document_id=doc_pmt.id, entry_number="JE-PMT",
        entry_date=date(2026, 8, 20), entry_type="payment",
        total_debit=Decimal("84700.00"), total_credit=Decimal("84700.00"), status="posted",
    )
    je_pmt.lines = [
        JournalEntryLine(line_number=1, account_id=coa["2150"].id, debit_amount=Decimal("84700.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["1020"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("84700.00")),
    ]

    db_session.add_all([je_s1, je_s2, je_s3, je_cn1, je_p1, je_pmt])
    db_session.commit()

    # ── 1. Table 3.1 Computation ──────────────────────────────────────
    gstr3b = GstReconciliationService.generate_gstr3b(
        db=db_session, client_id=client.id, user=user, period="2026-Q2"
    )
    t31 = gstr3b.table_3_1_outward
    assert t31.taxable_value == Decimal("300000.00"), f"Expected 300,000 taxable, got {t31.taxable_value}"
    assert t31.cgst == Decimal("7700.00"), f"Expected 7,700 CGST, got {t31.cgst}"
    assert t31.sgst == Decimal("7700.00"), f"Expected 7,700 SGST, got {t31.sgst}"
    t31_total_tax = t31.cgst + t31.sgst + t31.igst
    assert t31_total_tax == Decimal("51400.00"), f"Expected 51,400 total tax, got {t31_total_tax}"

    # ── 2. Table 4 ITC Computation ────────────────────────────────────
    t4 = gstr3b.table_4_net_itc
    assert t4.igst == Decimal("0.00"), f"Expected 0 IGST ITC, got {t4.igst}"
    assert t4.cgst == Decimal("8100.00"), f"Expected 8,100 CGST ITC, got {t4.cgst}"
    assert t4.sgst == Decimal("8100.00"), f"Expected 8,100 SGST ITC, got {t4.sgst}"
    net_itc = t4.cgst + t4.sgst + t4.igst
    assert net_itc == Decimal("16200.00"), f"Expected 16,200 net ITC, got {net_itc}"

    # ── 3. Table 6 Statutory Set-Off ──────────────────────────────────
    # Under Sec 49, 49A, 49B:
    # IGST liability 36,000 - (400 CGST surplus + 400 SGST surplus) = 35,200 cash on IGST
    # CGST liability 7,700 offset fully by CGST ITC -> 0 cash on CGST
    # SGST liability 7,700 offset fully by SGST ITC -> 0 cash on SGST
    assert gstr3b.cash_payable_igst == Decimal("35200.00"), f"Expected 35,200 IGST cash, got {gstr3b.cash_payable_igst}"
    assert gstr3b.cash_payable_cgst == Decimal("0.00"), f"Expected 0 CGST cash, got {gstr3b.cash_payable_cgst}"
    assert gstr3b.cash_payable_sgst == Decimal("0.00"), f"Expected 0 SGST cash, got {gstr3b.cash_payable_sgst}"
    assert gstr3b.tax_payable_in_cash == Decimal("35200.00"), f"Expected 35,200 net cash, got {gstr3b.tax_payable_in_cash}"

    # ── 4. Table 12 HSN Outward Summary ──────────────────────────────
    t12 = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db_session, client_id=client.id, user=user, period="2026-Q2"
    )
    assert len(t12.hsn_items) == 3, f"Expected exactly 3 rows in Table 12, got {len(t12.hsn_items)}"
    by_hsn = {it.hsn_sac: it for it in t12.hsn_items}
    assert "4820" in by_hsn
    assert "9401" in by_hsn
    assert "998314" in by_hsn
    assert "OTH" not in by_hsn

    it_4820 = by_hsn["4820"]
    assert it_4820.description == "Notebooks and stationery"
    assert it_4820.gst_rate == Decimal("5.00")
    assert it_4820.taxable_amount == Decimal("20000.00")
    assert it_4820.total_tax == Decimal("1000.00")
    assert it_4820.invoice_count == 1

    it_9401 = by_hsn["9401"]
    assert it_9401.description == "Office Chair (ergonomic)"
    assert it_9401.gst_rate == Decimal("18.00")
    assert it_9401.taxable_amount == Decimal("80000.00")
    assert it_9401.total_tax == Decimal("14400.00")
    assert it_9401.invoice_count == 2

    it_998314 = by_hsn["998314"]
    assert it_998314.description == "Software development services"
    assert it_998314.gst_rate == Decimal("18.00")
    assert it_998314.taxable_amount == Decimal("200000.00")
    assert it_998314.total_tax == Decimal("36000.00")
    assert it_998314.invoice_count == 1

    # ── 5. GSTR-1 Outward Total equals Table 3.1 Outward Total ────────
    gstr1 = GstReconciliationService.reconcile_gstr1(
        db=db_session, client_id=client.id, user=user, period="2026-Q2"
    )
    assert gstr1.total_outward_taxable == t31.taxable_value == Decimal("300000.00")
    gstr1_total_tax = gstr1.total_outward_cgst + gstr1.total_outward_sgst + gstr1.total_outward_igst
    assert gstr1_total_tax == t31_total_tax == Decimal("51400.00")

    # ── 6. ITC Ledger Balances Post-Settlement ────────────────────────
    assert gstr3b.itc_carried_forward_igst == Decimal("0.00")
    assert gstr3b.itc_carried_forward_cgst == Decimal("0.00")
    assert gstr3b.itc_carried_forward_sgst == Decimal("0.00")
    assert gstr3b.excess_credit_carried_forward == Decimal("0.00")
