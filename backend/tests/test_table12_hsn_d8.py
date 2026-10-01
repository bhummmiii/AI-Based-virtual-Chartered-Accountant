"""
Unit Tests for Commit D8:
GSTR-1 Table 12 HSN/SAC Summary dynamic aggregation:
1. Returns zero/empty records when client has no outward supplies (zero mock fallback).
2. Aggregates multi-line outward invoices accurately by HSN/SAC code.
3. Credit notes reduce taxable amount, quantity, and tax liabilities in Table 12.
4. Falls back to document-level HSN when granular line items are absent.
"""

import json
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

from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService


@pytest.fixture
def db_session():
    """In-memory SQLite database session."""
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


@pytest.fixture
def setup_d8(db_session):
    """Seed user, client, COA."""
    user = User(
        id=uuid.uuid4(),
        email="hsn_auditor@finledger.ai",
        full_name="HSN Auditor",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Apex Global Technologies",
        client_code="APX-888",
        contact_person="Tax Lead",
        client_type="company",
        gst_number="27AAACA1234A1Z5",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)
    return user, client


def test_table12_hsn_empty_when_no_records(db_session, setup_d8):
    """Empty list returned when client has no outward supplies (zero static mock fallback)."""
    user, client = setup_d8

    resp = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-Q2",
    )

    assert resp.client_id == client.id
    assert resp.period == "2026-Q2"
    assert resp.total_records == 0
    assert resp.total_taxable_value == Decimal("0.00")
    assert resp.total_tax_amount == Decimal("0.00")
    assert len(resp.hsn_items) == 0


def test_table12_hsn_aggregation_with_line_items(db_session, setup_d8):
    """Aggregates outward line items by HSN/SAC accurately from posted ledger vouchers."""
    user, client = setup_d8

    # Create outward sales document with line items metadata
    meta = {
        "line_items": [
            {
                "hsn": "8471",
                "description": "Laptops Core i7",
                "quantity": 2,
                "unit": "NOS",
                "taxable_amount": 100000.0,
                "cgst": 9000.0,
                "sgst": 9000.0,
                "igst": 0.0,
            },
            {
                "hsn": "9983",
                "description": "IT Support Annual",
                "quantity": 1,
                "unit": "OTH",
                "taxable_amount": 50000.0,
                "cgst": 4500.0,
                "sgst": 4500.0,
                "igst": 0.0,
            },
        ]
    }

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="sales_inv_101.pdf",
        document_category="sales_invoice",
        invoice_type="sales",
        invoice_number="INV/2026/101",
        invoice_date="2026-08-15",
        customer="Omega Retail Ltd",
        gstin="27AAACR9999R1ZZ",
        amount=Decimal("177000.00"),
        taxable_amount=Decimal("150000.00"),
        cgst=Decimal("13500.00"),
        sgst=Decimal("13500.00"),
        status="verified",
        metadata_=json.dumps(meta),
    )
    db_session.add(doc)
    db_session.flush()

    # Create posted JournalEntry with lines
    debtors = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "1100").first()
    sales = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4010").first()
    cgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2110").first()
    sgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2120").first()

    je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc.id,
        entry_number="JE-SALES-101",
        entry_date=date(2026, 8, 15),
        narration="Sale to Omega Retail",
        entry_type="sales",
        status="posted",
        total_debit=Decimal("177000.00"),
        total_credit=Decimal("177000.00"),
    )
    db_session.add(je)
    db_session.flush()

    db_session.add_all([
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=1, account_id=debtors.id, debit_amount=Decimal("177000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=2, account_id=sales.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("150000.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=3, account_id=cgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("13500.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je.id, line_number=4, account_id=sgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("13500.00")),
    ])
    db_session.commit()

    resp = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-Q2",
    )

    assert resp.total_records == 2
    assert resp.total_taxable_value == Decimal("150000.00")
    assert resp.total_tax_amount == Decimal("27000.00")

    items_by_hsn = {it.hsn_sac: it for it in resp.hsn_items}
    assert "8471" in items_by_hsn
    assert "9983" in items_by_hsn

    it_8471 = items_by_hsn["8471"]
    assert it_8471.taxable_amount == Decimal("100000.00")
    assert it_8471.cgst == Decimal("9000.00")
    assert it_8471.sgst == Decimal("9000.00")
    assert it_8471.total_tax == Decimal("18000.00")
    assert it_8471.total_quantity == Decimal("2.00")
    assert it_8471.gst_rate == Decimal("18.00")

    it_9983 = items_by_hsn["9983"]
    assert it_9983.taxable_amount == Decimal("50000.00")
    assert it_9983.total_tax == Decimal("9000.00")
    assert it_9983.total_quantity == Decimal("1.00")
    assert it_9983.gst_rate == Decimal("18.00")


def test_table12_hsn_credit_note_reduction(db_session, setup_d8):
    """Sales credit note reduces taxable amount and tax in Table 12."""
    user, client = setup_d8

    # Sales Invoice: 10 units @ 10,000 = 100,000 + 18,000 tax
    meta_inv = {
        "line_items": [
            {
                "hsn": "8471",
                "description": "Monitors",
                "quantity": 10,
                "unit": "NOS",
                "taxable_amount": 100000.0,
                "cgst": 9000.0,
                "sgst": 9000.0,
            }
        ]
    }
    doc_inv = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="inv_monitors.pdf",
        document_category="sales_invoice",
        invoice_type="sales",
        invoice_number="INV-MON-01",
        invoice_date="2026-08-01",
        customer="Beta Corp",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        status="verified",
        metadata_=json.dumps(meta_inv),
    )
    db_session.add(doc_inv)
    db_session.flush()

    debtors = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "1100").first()
    sales = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4010").first()
    sales_return = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "4020").first()
    cgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2110").first()
    sgst = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id, ChartOfAccounts.account_code == "2120").first()

    je_inv = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_inv.id,
        entry_number="JE-MON-01",
        entry_date=date(2026, 8, 1),
        narration="Sale of Monitors",
        entry_type="sales",
        status="posted",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
    )
    db_session.add(je_inv)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_inv.id, line_number=1, account_id=debtors.id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_inv.id, line_number=2, account_id=sales.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_inv.id, line_number=3, account_id=cgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_inv.id, line_number=4, account_id=sgst.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00")),
    ])

    # Sales Credit Note: 2 units returned @ 10,000 = 20,000 + 3,600 tax
    meta_cn = {
        "line_items": [
            {
                "hsn": "8471",
                "description": "Monitors Return",
                "quantity": 2,
                "unit": "NOS",
                "taxable_amount": 20000.0,
                "cgst": 1800.0,
                "sgst": 1800.0,
            }
        ]
    }
    doc_cn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="cn_monitors.pdf",
        document_category="credit_note",
        invoice_type="credit_note",
        invoice_number="CN-MON-01",
        invoice_date="2026-08-20",
        customer="Beta Corp",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        status="verified",
        metadata_=json.dumps(meta_cn),
    )
    db_session.add(doc_cn)
    db_session.flush()

    je_cn = JournalEntry(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_cn.id,
        entry_number="JE-CN-01",
        entry_date=date(2026, 8, 20),
        narration="Return of 2 Monitors",
        entry_type="credit_note",
        status="posted",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
    )
    db_session.add(je_cn)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_cn.id, line_number=1, account_id=sales_return.id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_cn.id, line_number=2, account_id=cgst.id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_cn.id, line_number=3, account_id=sgst.id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00")),
        JournalEntryLine(id=uuid.uuid4(), journal_entry_id=je_cn.id, line_number=4, account_id=debtors.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00")),
    ])
    db_session.commit()

    resp = GstReconciliationService.get_gstr1_table_12_hsn_summary(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-Q2",
    )

    assert resp.total_records == 1
    # 100,000 - 20,000 = 80,000
    assert resp.total_taxable_value == Decimal("80000.00")
    # 18,000 - 3,600 = 14,400
    assert resp.total_tax_amount == Decimal("14400.00")

    item = resp.hsn_items[0]
    assert item.hsn_sac == "8471"
    assert item.taxable_amount == Decimal("80000.00")
    assert item.cgst == Decimal("7200.00")
    assert item.sgst == Decimal("7200.00")
    assert item.total_tax == Decimal("14400.00")
    # 10 - 2 = 8
    assert item.total_quantity == Decimal("8.00")
