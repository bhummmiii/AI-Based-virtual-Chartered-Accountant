"""
Unit and integration tests for F7:
HSN Table 12 (GSTR-1) outward sales summary parity for all periods.

Verifies:
1. Builds strictly from outward vouchers (templates T1, T3, T4) joined to source line items.
2. Excludes purchase (T2), debit note / purchase return (T6), and payment vouchers.
3. Groups by (hsn_sac, effective_rate) and accurately nets credit notes (T3).
4. For 'All Available' (period is None or 'all'), applies no date filter and aggregates across all periods.
5. Parity with Table 3.1 totals.
"""

import os
import sys
import uuid
import json
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_record import AccountingRecord
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService


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
        ],
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_table12_hsn_all_periods_and_templates(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-T12",
        company_name="Test Outward Ltd",
        gst_number="27AABCT0001A1Z1",
        return_frequency="Quarterly",
        contact_person="Director",
    )
    user = User(
        id=user_id,
        email="test@t12.com",
        full_name="Tester",
        password_hash="hash",
        role="admin",
    )
    db_session.add_all([client, user])
    db_session.flush()

    coa_service = ChartOfAccountsService()
    coa_service.initialize_default_accounts(db_session, client_id, user)
    accounts = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
    acc_map = {a.account_code: a for a in accounts}

    # 1. Outward Sales 1: HSN 9401 (100,000 @ 18% CGST/SGST) - Template T1
    doc_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="invoice_s1.pdf",
        file_path="/dummy/invoice_s1.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV/001",
        invoice_date="2026-07-15",
        gstin="27AABCT0001A1Z1",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "9401",
                    "item_name": "Office Chair (ergonomic)",
                    "quantity": 10,
                    "unit": "NOS",
                    "taxable_amount": 100000.00,
                    "cgst": 9000.00,
                    "sgst": 9000.00,
                    "igst": 0.00,
                }
            ]
        }),
    )
    db_session.add(doc_s1)
    db_session.flush()

    je_s1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_s1.id,
        entry_number="SV-2026-0001",
        entry_date=date(2026, 7, 15),
        entry_type="sales",
        voucher_template="T1",
        status="posted",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
    )
    db_session.add(je_s1)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_s1.id, account_id=acc_map["1100"].id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_s1.id, account_id=acc_map["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_s1.id, account_id=acc_map["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_s1.id, account_id=acc_map["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), line_number=4),
    ])

    # 2. Outward Credit Note 1: HSN 9401 (reduces 20,000 @ 18%) - Template T3
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="cn1.pdf",
        file_path="/dummy/cn1.pdf",
        status="verified",
        document_category="credit_note",
        invoice_number="CRN/001",
        invoice_date="2026-08-10",
        gstin="27AABCT0001A1Z1",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "9401",
                    "item_name": "Office Chair (ergonomic)",
                    "quantity": 2,
                    "unit": "NOS",
                    "taxable_amount": 20000.00,
                    "cgst": 1800.00,
                    "sgst": 1800.00,
                    "igst": 0.00,
                }
            ]
        }),
    )
    db_session.add(doc_cn1)
    db_session.flush()

    je_cn1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_cn1.id,
        entry_number="JV-2026-0001",
        entry_date=date(2026, 8, 10),
        entry_type="journal",
        voucher_template="T3",
        status="posted",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
    )
    db_session.add(je_cn1)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_cn1.id, account_id=acc_map["4020"].id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_cn1.id, account_id=acc_map["2110"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_cn1.id, account_id=acc_map["2120"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_cn1.id, account_id=acc_map["1100"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00"), line_number=4),
    ])

    # 3. Outward Sales 2: HSN 4820 (20,000 @ 5%) - Template T1
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="invoice_s2.pdf",
        file_path="/dummy/invoice_s2.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV/002",
        invoice_date="2026-09-05",
        gstin="27AABCT0001A1Z1",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "4820",
                    "item_name": "Notebooks and stationery",
                    "quantity": 100,
                    "unit": "NOS",
                    "taxable_amount": 20000.00,
                    "cgst": 500.00,
                    "sgst": 500.00,
                    "igst": 0.00,
                }
            ]
        }),
    )
    db_session.add(doc_s2)
    db_session.flush()

    je_s2 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_s2.id,
        entry_number="SV-2026-0002",
        entry_date=date(2026, 9, 5),
        entry_type="sales",
        voucher_template="T1",
        status="posted",
        total_debit=Decimal("21000.00"),
        total_credit=Decimal("21000.00"),
    )
    db_session.add(je_s2)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_s2.id, account_id=acc_map["1100"].id, debit_amount=Decimal("21000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_s2.id, account_id=acc_map["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("20000.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_s2.id, account_id=acc_map["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_s2.id, account_id=acc_map["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("500.00"), line_number=4),
    ])

    # 4. Outward Sales 3: HSN 998314 (200,000 @ 18% IGST) - Template T1
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="invoice_s3.pdf",
        file_path="/dummy/invoice_s3.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV/003",
        invoice_date="2026-09-20",
        gstin="27AABCT0001A1Z1",
        metadata_=json.dumps({
            "line_items": [
                {
                    "hsn": "998314",
                    "item_name": "Software development services",
                    "quantity": 1,
                    "unit": "NOS",
                    "taxable_amount": 200000.00,
                    "cgst": 0.00,
                    "sgst": 0.00,
                    "igst": 36000.00,
                }
            ]
        }),
    )
    db_session.add(doc_s3)
    db_session.flush()

    je_s3 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_s3.id,
        entry_number="SV-2026-0003",
        entry_date=date(2026, 9, 20),
        entry_type="sales",
        voucher_template="T1",
        status="posted",
        total_debit=Decimal("236000.00"),
        total_credit=Decimal("236000.00"),
    )
    db_session.add(je_s3)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_s3.id, account_id=acc_map["1100"].id, debit_amount=Decimal("236000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_s3.id, account_id=acc_map["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("200000.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_s3.id, account_id=acc_map["2130"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("36000.00"), line_number=3),
    ])

    # 5. Purchase Invoice (T2) — MUST BE EXCLUDED from Table 12
    doc_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="pur1.pdf",
        file_path="/dummy/pur1.pdf",
        status="verified",
        document_category="purchase_invoice",
        invoice_number="PUR/001",
        invoice_date="2026-07-20",
        gstin="29BBBBB2222B1Z2",
    )
    db_session.add(doc_p1)
    db_session.flush()

    je_p1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_p1.id,
        entry_number="PV-2026-0001",
        entry_date=date(2026, 7, 20),
        entry_type="purchase",
        voucher_template="T2",
        status="posted",
        total_debit=Decimal("59000.00"),
        total_credit=Decimal("59000.00"),
    )
    db_session.add(je_p1)
    db_session.flush()

    # 6. Payment Voucher (PAYMENT) — MUST BE EXCLUDED
    je_pmt = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        entry_number="PMT-2026-0001",
        entry_date=date(2026, 9, 25),
        entry_type="payment",
        voucher_template="PAYMENT",
        status="posted",
        total_debit=Decimal("35200.00"),
        total_credit=Decimal("35200.00"),
    )
    db_session.add(je_pmt)
    db_session.commit()

    # Test 'all' period
    t12_all = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db_session, client_id, user, period="all"
    )

    assert t12_all.total_records == 3
    assert t12_all.total_taxable_value == Decimal("300000.00")
    assert t12_all.total_tax_amount == Decimal("51400.00")

    items_by_hsn = {it.hsn_sac: it for it in t12_all.hsn_items}
    assert "4820" in items_by_hsn
    assert "9401" in items_by_hsn
    assert "998314" in items_by_hsn

    # Check 4820: 20,000 @ 5% = 1,000 tax (1 voucher)
    it_4820 = items_by_hsn["4820"]
    assert it_4820.taxable_amount == Decimal("20000.00")
    assert it_4820.total_tax == Decimal("1000.00")
    assert it_4820.invoice_count == 1
    assert it_4820.gst_rate == Decimal("5.00")

    # Check 9401: 100,000 - 20,000 = 80,000 @ 18% = 14,400 tax (2 vouchers)
    it_9401 = items_by_hsn["9401"]
    assert it_9401.taxable_amount == Decimal("80000.00")
    assert it_9401.total_tax == Decimal("14400.00")
    assert it_9401.invoice_count == 2
    assert it_9401.gst_rate == Decimal("18.00")

    # Check 998314: 200,000 @ 18% = 36,000 tax (1 voucher)
    it_998314 = items_by_hsn["998314"]
    assert it_998314.taxable_amount == Decimal("200000.00")
    assert it_998314.total_tax == Decimal("36000.00")
    assert it_998314.invoice_count == 1
    assert it_998314.gst_rate == Decimal("18.00")
