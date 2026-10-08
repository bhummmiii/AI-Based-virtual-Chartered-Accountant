"""
Unit and integration tests for F8:
Payment voucher isolation from GST registers and return tables.

Verifies:
1. Payment vouchers (entry_type='payment' or template='PAYMENT') are balance sheet transfers (clearing taxes against bank).
2. Payment vouchers are excluded from GSTR-1 outward registers (total_outward_taxable, B2B, B2C, CN, Table 12).
3. Payment vouchers are excluded from GSTR-2B inward registers (total_inward_taxable, eligible_itc).
4. Payment vouchers are excluded from GSTR-3B Table 3.1 and Table 4 ITC.
5. In GSTR-3B, cash payable and closing ITC balance carried forward are computed correctly.
"""

import uuid
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


def test_payment_voucher_strict_isolation(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-PMT",
        company_name="Payment Isolation Ltd",
        gst_number="27AABCP1111A1Z1",
        return_frequency="Quarterly",
        contact_person="Director",
    )
    user = User(
        id=user_id,
        email="test@pmt.com",
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

    # 1. Outward Sales Voucher (SV-1, 100k taxable, 18k tax)
    doc_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="s1.pdf",
        file_path="/dummy/s1.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV/001",
        invoice_date="2026-07-10",
        gstin="27AABCP1111A1Z1",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
    )
    db_session.add(doc_s1)
    db_session.flush()

    je_s1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_s1.id,
        entry_number="SV-2026-0001",
        entry_date=date(2026, 7, 10),
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

    # 2. Inward Purchase Voucher (PV-1, 50k taxable, 9k tax)
    doc_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="p1.pdf",
        file_path="/dummy/p1.pdf",
        status="verified",
        document_category="purchase_invoice",
        invoice_number="PUR/001",
        invoice_date="2026-07-20",
        gstin="27AABCS9999A1Z9",
        taxable_amount=Decimal("50000.00"),
        cgst=Decimal("4500.00"),
        sgst=Decimal("4500.00"),
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
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_p1.id, account_id=acc_map["5010"].id, debit_amount=Decimal("50000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_p1.id, account_id=acc_map["1210"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_p1.id, account_id=acc_map["1220"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_p1.id, account_id=acc_map["2010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("59000.00"), line_number=4),
    ])

    # 3. Payment Voucher (PMT-1, Tax Challan Payment ₹9,000)
    # Dr GST Clearing / Cr Bank — Balance Sheet Transfer ONLY
    doc_pmt = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        file_name="challan.pdf",
        file_path="/dummy/challan.pdf",
        status="verified",
        document_category="gst_challan",
        invoice_number="CHL-2026-001",
        invoice_date="2026-09-20",
        amount=Decimal("9000.00"),
        taxable_amount=Decimal("9000.00"),
    )
    db_session.add(doc_pmt)
    db_session.flush()

    je_pmt = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=doc_pmt.id,
        entry_number="PMT-2026-0001",
        entry_date=date(2026, 9, 20),
        entry_type="payment",
        voucher_template="PAYMENT",
        status="posted",
        total_debit=Decimal("9000.00"),
        total_credit=Decimal("9000.00"),
    )
    db_session.add(je_pmt)
    db_session.flush()
    db_session.add_all([
        JournalEntryLine(journal_entry_id=je_pmt.id, account_id=acc_map["2110"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_pmt.id, account_id=acc_map["2120"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_pmt.id, account_id=acc_map["1010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), line_number=3),
    ])
    db_session.commit()

    # Verify GSTR-1 excludes PMT-1
    g1 = GstReconciliationService.reconcile_gstr1(db_session, client_id, user, period="2026-Q2")
    assert g1.total_outward_taxable == Decimal("100000.00")
    assert g1.total_outward_tax == Decimal("18000.00")
    assert len(g1.invoices) == 1
    assert g1.invoices[0].invoice_number == "INV/001"

    # Verify Table 12 HSN excludes PMT-1
    t12 = GstReconciliationService.get_gstr1_table_12_hsn_summary(db_session, client_id, user, period="2026-Q2")
    assert t12.total_taxable_value == Decimal("100000.00")
    assert t12.total_tax_amount == Decimal("18000.00")

    # Verify GSTR-2B excludes PMT-1
    g2 = GstReconciliationService.reconcile_gstr2b(db_session, client_id, user, period="2026-Q2")
    assert g2.total_inward_taxable == Decimal("50000.00")
    assert g2.total_eligible_itc == Decimal("9000.00")
    assert len(g2.invoices) == 1
    assert g2.invoices[0].invoice_number == "PUR/001"

    # Verify GSTR-3B Table 3.1 & Table 4 exclude PMT-1
    g3 = GstReconciliationService.generate_gstr3b(db_session, client_id, user, period="2026-Q2")
    assert g3.table_3_1_outward.taxable_value == Decimal("100000.00")
    assert g3.table_4_itc_available.taxable_value == Decimal("50000.00")
    assert g3.table_4_net_itc.cgst == Decimal("4500.00")
    assert g3.table_4_net_itc.sgst == Decimal("4500.00")
    # Cash payable: 18,000 output - 9,000 ITC = 9,000 in cash (4,500 CGST + 4,500 SGST)
    assert g3.tax_payable_in_cash == Decimal("9000.00")
    assert g3.cash_payable_cgst == Decimal("4500.00")
    assert g3.cash_payable_sgst == Decimal("4500.00")
    assert g3.excess_credit_carried_forward == Decimal("0.00")
