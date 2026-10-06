"""
Unit and integration tests for E2:
HSN Table 12 (GSTR-1) outward sales vouchers only.

Rule:
- Build Table 12 strictly from posted outward sales vouchers (templates T1, T3, T4: B2B, B2C, Sales Return Credit Note) joined to their source-document line items.
- Exclude payment vouchers (e.g. GST Challan payment).
- Grouping: (hsn_sac, effective_rate) so different rates under the same HSN stay separate.
- Description: line-item description (first non-note line for that code; fallback to HSN master uploaded for the client; never party name).
- Rate: item rate as % (or tax/taxable * 100 rounded to 2 decimals).
- Amounts: taxable, CGST, SGST, IGST, total_tax = sum of items; credit notes reduce turnover/tax.
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


def test_e2_table_12_outward_sales_only_and_payment_excluded(db_session):
    """
    Test that Table 12 aggregates outward sales and credit notes while excluding payment vouchers.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"e2_test_{uuid.uuid4().hex[:6]}@example.com",
        full_name="CA Auditor",
        password_hash="mock_hash",
        role="admin",
        is_active=True,
    )
    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        client_code="E2-TEST-001",
        company_name="Beta Traders Pvt Ltd",
        contact_person="Director",
        gst_number="27AAACB1111A1Z5",
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

    # 1. S1: B2B Invoice (HSN 9401, Office Chair, 100k taxable, 9k CGST, 9k SGST)
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
        metadata_='{"line_items": [{"hsn": "9401", "item_name": "Office Chair (ergonomic)", "quantity": 50, "taxable_amount": 100000.0, "cgst": 9000.0, "sgst": 9000.0}]}',
    )
    # 2. S2: B2B Inter-state Invoice (HSN 998314, Software services, 200k taxable, 36k IGST)
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
        metadata_='{"line_items": [{"hsn": "998314", "item_name": "Software development services", "quantity": 1, "taxable_amount": 200000.0, "igst": 36000.0}]}',
    )
    # 3. S3: B2C Invoice (HSN 4820, Notebooks, 20k taxable, 500 CGST, 500 SGST)
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
        metadata_='{"line_items": [{"hsn": "4820", "item_name": "Notebooks and stationery", "quantity": 200, "taxable_amount": 20000.0, "cgst": 500.0, "sgst": 500.0}]}',
    )
    # 4. CN1: Credit Note (against S1, HSN 9401, 20k taxable, 1.8k CGST, 1.8k SGST)
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
        metadata_='{"line_items": [{"hsn": "9401", "item_name": "Sales return - Office Chair", "quantity": 10, "taxable_amount": 20000.0, "cgst": 1800.0, "sgst": 1800.0}]}',
    )
    # 5. Payment Voucher (Challan 84,700) - MUST BE EXCLUDED!
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

    db_session.add_all([doc_s1, doc_s2, doc_s3, doc_cn1, doc_pmt])
    db_session.commit()

    # Create Journal Entries
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

    je_pmt = JournalEntry(
        client_id=client.id, document_id=doc_pmt.id, entry_number="JE-PMT",
        entry_date=date(2026, 8, 20), entry_type="payment",
        total_debit=Decimal("84700.00"), total_credit=Decimal("84700.00"), status="posted",
    )
    je_pmt.lines = [
        JournalEntryLine(line_number=1, account_id=coa["2150"].id, debit_amount=Decimal("84700.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(line_number=2, account_id=coa["1020"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("84700.00")),
    ]

    db_session.add_all([je_s1, je_s2, je_s3, je_cn1, je_pmt])
    db_session.commit()

    resp = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-Q2",
    )

    # Acceptance expectations:
    # 1. Exactly 3 rows
    assert len(resp.hsn_items) == 3, f"Expected 3 rows, got {len(resp.hsn_items)}"

    by_code = {it.hsn_sac: it for it in resp.hsn_items}
    assert "4820" in by_code
    assert "9401" in by_code
    assert "998314" in by_code
    assert "OTH" not in by_code

    # 1) 4820 | Notebooks and stationery | 5.00% | 20,000 | 1,000 | 1 voucher
    it_4820 = by_code["4820"]
    assert it_4820.description == "Notebooks and stationery"
    assert it_4820.gst_rate == Decimal("5.00")
    assert it_4820.taxable_amount == Decimal("20000.00")
    assert it_4820.total_tax == Decimal("1000.00")
    assert it_4820.invoice_count == 1

    # 2) 9401 | Office Chair (ergonomic) | 18.00% | 80,000 | 14,400 | 2 vouchers
    it_9401 = by_code["9401"]
    assert it_9401.description == "Office Chair (ergonomic)"
    assert it_9401.gst_rate == Decimal("18.00")
    assert it_9401.taxable_amount == Decimal("80000.00")
    assert it_9401.total_tax == Decimal("14400.00")
    assert it_9401.invoice_count == 2

    # 3) 998314 | Software development services | 18.00% | 200,000 | 36,000 | 1 voucher
    it_998314 = by_code["998314"]
    assert it_998314.description == "Software development services"
    assert it_998314.gst_rate == Decimal("18.00")
    assert it_998314.taxable_amount == Decimal("200000.00")
    assert it_998314.total_tax == Decimal("36000.00")
    assert it_998314.invoice_count == 1

    # Totals: 300,000 taxable and 51,400 tax
    assert resp.total_taxable_value == Decimal("300000.00")
    assert resp.total_tax_amount == Decimal("51400.00")
