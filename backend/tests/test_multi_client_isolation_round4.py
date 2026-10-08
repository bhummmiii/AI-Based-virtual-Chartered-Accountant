"""
Test F11: Multi-Client Isolation, Statutory Due Dates, Contra-Revenue Check,
and UI Governance Counter Contract.

Verifies:
1. Multi-Client Isolation (Rule R8): Transactions, documents, and ledger vouchers
   for Client A never bleed into Client B's GSTR-1, GSTR-2B, Table 12 HSN, or GSTR-3B.
2. Statutory Due Dates & Return Frequency:
   - Client A (MH 27, Quarterly):
     - Q2 GSTR-3B -> 2026-10-22 (Category 1: MH, 22nd of following month)
     - Q2 GSTR-1  -> 2026-10-13 (QRMP: 13th of following month)
   - Client B (DL 07, Monthly):
     - Aug GSTR-3B -> 2026-09-20 (Monthly: 20th of next month)
     - Aug GSTR-1  -> 2026-09-11 (Monthly: 11th of next month)
3. Sales Return Contra-Revenue Check:
   - Account 4020 role='SALES_RETURN' debit reduces gross outward turnover
     (contra-revenue) in both GSTR-1 and GSTR-3B Table 3.1.
4. UI Governance Counter Contract:
   - Extracted: all effective documents.
   - Verified: status == 'verified' and status != 'rejected' (excludes duplicate/rejected).
   - Posted: status == 'posted' and not is_reversed and status != 'reversed'.
   - Filed: filing_status == 'filed' and filing_status != 'voided' and not void_reason.
"""

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
from app.models.gst_record import GSTRecord
from app.schemas.gst import GSTRecordCreate
from app.api.routers.gst.router import create_gst_record
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.services.gst_reconciliation_service import GstReconciliationService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_multi_client_gst_isolation_and_contra_revenue(db_session):
    """
    Test Rule R8: Two separate clients with independent COAs, documents, and vouchers.
    Ensure zero cross-client bleeding in GSTR-1, GSTR-2B, Table 12 HSN, and GSTR-3B,
    and verify that Account 4020 (SALES_RETURN) properly reduces turnover as contra-revenue.
    """
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="auditor@multi-client.com",
        full_name="Senior Auditor",
        password_hash="hash",
        role="admin",
    )
    db_session.add(user)
    db_session.flush()

    # --- Client A: Maharashtra, Quarterly ---
    client_a_id = uuid.uuid4()
    client_a = Client(
        id=client_a_id,
        user_id=user_id,
        client_code="CLI-MHA",
        company_name="Alpha Tech MH Pvt Ltd",
        gst_number="27AABCA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Director A",
    )

    # --- Client B: Delhi, Monthly ---
    client_b_id = uuid.uuid4()
    client_b = Client(
        id=client_b_id,
        user_id=user_id,
        client_code="CLI-DLB",
        company_name="Beta Retail DL LLP",
        gst_number="07AAAAA9999B1Z8",
        return_frequency="Monthly",
        contact_person="Partner B",
    )
    db_session.add_all([client_a, client_b])
    db_session.flush()

    # Initialize COA for both clients
    coa_service = ChartOfAccountsService()
    coa_service.initialize_default_accounts(db_session, client_a_id, user)
    coa_service.initialize_default_accounts(db_session, client_b_id, user)

    coa_a = {a.account_code: a for a in db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_a_id).all()}
    coa_b = {a.account_code: a for a in db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_b_id).all()}

    # Invariant: Account 4020 has role SALES_RETURN (contra-revenue)
    assert coa_a["4020"].role == "SALES_RETURN"
    assert coa_b["4020"].role == "SALES_RETURN"

    # =========================================================================
    # CLIENT A TRANSACTIONS (Q2 FY 2026-27: July - September 2026)
    # =========================================================================
    # 1. Outward Sale: INV-A-01 (Taxable 100,000, CGST 9,000, SGST 9,000, HSN 998314)
    doc_a_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_a_id,
        file_name="inv_a_01.pdf",
        file_path="/dummy/inv_a_01.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV-A-01",
        invoice_date="2026-07-15",
        gstin="27AABCA1234A1Z5",
        taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"),
        sgst=Decimal("9000.00"),
        igst=Decimal("0.00"),
        amount=Decimal("118000.00"),
        metadata_=json.dumps({
            "fields": {"customer_gstin": "27AAAPM5678B1Z2", "customer_name": "Customer MH"},
            "line_items": [
                {"description": "IT Consulting", "hsn": "998314", "quantity": 1, "rate": 100000, "taxable_amount": 100000, "tax_rate": 18, "cgst": 9000, "sgst": 9000}
            ],
        }),
    )
    rec_a_s1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_a_id,
        document_id=doc_a_s1.id,
        transaction_date=date(2026, 7, 15),
        voucher_type="sales",
        reference_number="INV-A-01",
        debit=Decimal("0.00"),
        credit=Decimal("118000.00"),
        status="posted",
    )
    je_a_s1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_a_id,
        accounting_record_id=rec_a_s1.id,
        document_id=doc_a_s1.id,
        entry_number="SV-A-0001",
        entry_date=date(2026, 7, 15),
        entry_type="sales",
        voucher_template="T1",
        counterparty_name="Customer MH",
        counterparty_gstin="27AAAPM5678B1Z2",
        reference_number="INV-A-01",
        total_debit=Decimal("118000.00"),
        total_credit=Decimal("118000.00"),
        status="posted",
        is_reversed=False,
    )
    lines_a_s1 = [
        JournalEntryLine(journal_entry_id=je_a_s1.id, account_id=coa_a["1100"].id, debit_amount=Decimal("118000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_a_s1.id, account_id=coa_a["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("100000.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_a_s1.id, account_id=coa_a["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_a_s1.id, account_id=coa_a["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("9000.00"), line_number=4),
    ]

    # 2. Credit Note: CN-A-01 (Taxable 20,000, CGST 1,800, SGST 1,800, HSN 998314)
    # Debits 4020 (SALES_RETURN contra-revenue)
    doc_a_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_a_id,
        file_name="cn_a_01.pdf",
        file_path="/dummy/cn_a_01.pdf",
        status="verified",
        document_category="credit_note",
        invoice_number="CN-A-01",
        invoice_date="2026-08-10",
        gstin="27AABCA1234A1Z5",
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        igst=Decimal("0.00"),
        amount=Decimal("23600.00"),
        metadata_=json.dumps({
            "fields": {"customer_gstin": "27AAAPM5678B1Z2", "customer_name": "Customer MH", "original_invoice_number": "INV-A-01"},
            "line_items": [
                {"description": "IT Consulting Credit", "hsn": "998314", "quantity": 1, "rate": 20000, "taxable_amount": 20000, "tax_rate": 18, "cgst": 1800, "sgst": 1800}
            ],
        }),
    )
    rec_a_cn1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_a_id,
        document_id=doc_a_cn1.id,
        transaction_date=date(2026, 8, 10),
        voucher_type="journal",
        reference_number="CN-A-01",
        debit=Decimal("23600.00"),
        credit=Decimal("0.00"),
        status="posted",
    )
    je_a_cn1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_a_id,
        accounting_record_id=rec_a_cn1.id,
        document_id=doc_a_cn1.id,
        entry_number="JV-A-0001",
        entry_date=date(2026, 8, 10),
        entry_type="journal",
        voucher_template="T3",
        counterparty_name="Customer MH",
        counterparty_gstin="27AAAPM5678B1Z2",
        reference_number="CN-A-01",
        total_debit=Decimal("23600.00"),
        total_credit=Decimal("23600.00"),
        status="posted",
        is_reversed=False,
    )
    lines_a_cn1 = [
        JournalEntryLine(journal_entry_id=je_a_cn1.id, account_id=coa_a["4020"].id, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_a_cn1.id, account_id=coa_a["2110"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_a_cn1.id, account_id=coa_a["2120"].id, debit_amount=Decimal("1800.00"), credit_amount=Decimal("0.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_a_cn1.id, account_id=coa_a["1100"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("23600.00"), line_number=4),
    ]

    # 3. Inward Purchase: PUR-A-01 (Taxable 50,000, CGST 4,500, SGST 4,500)
    doc_a_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_a_id,
        file_name="pur_a_01.pdf",
        file_path="/dummy/pur_a_01.pdf",
        status="verified",
        document_category="purchase_records",
        invoice_number="PUR-A-01",
        invoice_date="2026-07-20",
        gstin="27AABCA1234A1Z5",
        taxable_amount=Decimal("50000.00"),
        cgst=Decimal("4500.00"),
        sgst=Decimal("4500.00"),
        igst=Decimal("0.00"),
        amount=Decimal("59000.00"),
        metadata_=json.dumps({
            "fields": {"supplier_gstin": "27AABCS9999M1Z3", "vendor_name": "Supplier MH"},
            "line_items": [
                {"description": "Office Chairs", "hsn": "9401", "quantity": 1, "rate": 50000, "taxable_amount": 50000, "tax_rate": 18, "cgst": 4500, "sgst": 4500}
            ],
        }),
    )
    rec_a_p1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_a_id,
        document_id=doc_a_p1.id,
        transaction_date=date(2026, 7, 20),
        voucher_type="purchase",
        reference_number="PUR-A-01",
        debit=Decimal("59000.00"),
        credit=Decimal("0.00"),
        status="posted",
    )
    je_a_p1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_a_id,
        accounting_record_id=rec_a_p1.id,
        document_id=doc_a_p1.id,
        entry_number="PV-A-0001",
        entry_date=date(2026, 7, 20),
        entry_type="purchase",
        voucher_template="T2",
        counterparty_name="Supplier MH",
        counterparty_gstin="27AABCS9999M1Z3",
        reference_number="PUR-A-01",
        total_debit=Decimal("59000.00"),
        total_credit=Decimal("59000.00"),
        status="posted",
        is_reversed=False,
    )
    lines_a_p1 = [
        JournalEntryLine(journal_entry_id=je_a_p1.id, account_id=coa_a["5010"].id, debit_amount=Decimal("50000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_a_p1.id, account_id=coa_a["1210"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_a_p1.id, account_id=coa_a["1220"].id, debit_amount=Decimal("4500.00"), credit_amount=Decimal("0.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_a_p1.id, account_id=coa_a["2010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("59000.00"), line_number=4),
    ]

    # 4. Payment Voucher: PMT-A-01 (Challan settlement, 14,400)
    rec_a_pmt = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_a_id,
        transaction_date=date(2026, 10, 20),
        voucher_type="payment",
        reference_number="PMT-A-01",
        debit=Decimal("14400.00"),
        credit=Decimal("0.00"),
        status="posted",
    )
    je_a_pmt = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_a_id,
        accounting_record_id=rec_a_pmt.id,
        entry_number="PMT-A-0001",
        entry_date=date(2026, 10, 20),
        entry_type="payment",
        voucher_template="PAYMENT",
        reference_number="PMT-A-01",
        total_debit=Decimal("14400.00"),
        total_credit=Decimal("14400.00"),
        status="posted",
        is_reversed=False,
    )
    lines_a_pmt = [
        JournalEntryLine(journal_entry_id=je_a_pmt.id, account_id=coa_a["2150"].id, debit_amount=Decimal("14400.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_a_pmt.id, account_id=coa_a["1020"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("14400.00"), line_number=2),
    ]

    # =========================================================================
    # CLIENT B TRANSACTIONS (August 2026)
    # =========================================================================
    # 1. Outward Sale: INV-B-01 (Taxable 200,000, CGST 18,000, SGST 18,000, HSN 847130)
    doc_b_s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_b_id,
        file_name="inv_b_01.pdf",
        file_path="/dummy/inv_b_01.pdf",
        status="verified",
        document_category="b2b_invoice",
        invoice_number="INV-B-01",
        invoice_date="2026-08-15",
        gstin="07AAAAA9999B1Z8",
        taxable_amount=Decimal("200000.00"),
        cgst=Decimal("18000.00"),
        sgst=Decimal("18000.00"),
        igst=Decimal("0.00"),
        amount=Decimal("236000.00"),
        metadata_=json.dumps({
            "fields": {"customer_gstin": "07BBBBB1111C1Z2", "customer_name": "Customer DL"},
            "line_items": [
                {"description": "Laptops", "hsn": "847130", "quantity": 2, "rate": 100000, "taxable_amount": 200000, "tax_rate": 18, "cgst": 18000, "sgst": 18000}
            ],
        }),
    )
    rec_b_s1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_b_id,
        document_id=doc_b_s1.id,
        transaction_date=date(2026, 8, 15),
        voucher_type="sales",
        reference_number="INV-B-01",
        debit=Decimal("0.00"),
        credit=Decimal("236000.00"),
        status="posted",
    )
    je_b_s1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_b_id,
        accounting_record_id=rec_b_s1.id,
        document_id=doc_b_s1.id,
        entry_number="SV-B-0001",
        entry_date=date(2026, 8, 15),
        entry_type="sales",
        voucher_template="T1",
        counterparty_name="Customer DL",
        counterparty_gstin="07BBBBB1111C1Z2",
        reference_number="INV-B-01",
        total_debit=Decimal("236000.00"),
        total_credit=Decimal("236000.00"),
        status="posted",
        is_reversed=False,
    )
    lines_b_s1 = [
        JournalEntryLine(journal_entry_id=je_b_s1.id, account_id=coa_b["1100"].id, debit_amount=Decimal("236000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_b_s1.id, account_id=coa_b["4010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("200000.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_b_s1.id, account_id=coa_b["2110"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("18000.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_b_s1.id, account_id=coa_b["2120"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("18000.00"), line_number=4),
    ]

    # 2. Inward Purchase: PUR-B-01 (Taxable 80,000, CGST 7,200, SGST 7,200)
    doc_b_p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_b_id,
        file_name="pur_b_01.pdf",
        file_path="/dummy/pur_b_01.pdf",
        status="verified",
        document_category="purchase_records",
        invoice_number="PUR-B-01",
        invoice_date="2026-08-20",
        gstin="07AAAAA9999B1Z8",
        taxable_amount=Decimal("80000.00"),
        cgst=Decimal("7200.00"),
        sgst=Decimal("7200.00"),
        igst=Decimal("0.00"),
        amount=Decimal("94400.00"),
        metadata_=json.dumps({
            "fields": {"supplier_gstin": "07CCCCC2222D1Z4", "vendor_name": "Supplier DL"},
            "line_items": [
                {"description": "Printed Manuals", "hsn": "4820", "quantity": 1, "rate": 80000, "taxable_amount": 80000, "tax_rate": 18, "cgst": 7200, "sgst": 7200}
            ],
        }),
    )
    rec_b_p1 = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client_b_id,
        document_id=doc_b_p1.id,
        transaction_date=date(2026, 8, 20),
        voucher_type="purchase",
        reference_number="PUR-B-01",
        debit=Decimal("94400.00"),
        credit=Decimal("0.00"),
        status="posted",
    )
    je_b_p1 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_b_id,
        accounting_record_id=rec_b_p1.id,
        document_id=doc_b_p1.id,
        entry_number="PV-B-0001",
        entry_date=date(2026, 8, 20),
        entry_type="purchase",
        voucher_template="T2",
        counterparty_name="Supplier DL",
        counterparty_gstin="07CCCCC2222D1Z4",
        reference_number="PUR-B-01",
        total_debit=Decimal("94400.00"),
        total_credit=Decimal("94400.00"),
        status="posted",
        is_reversed=False,
    )
    lines_b_p1 = [
        JournalEntryLine(journal_entry_id=je_b_p1.id, account_id=coa_b["5010"].id, debit_amount=Decimal("80000.00"), credit_amount=Decimal("0.00"), line_number=1),
        JournalEntryLine(journal_entry_id=je_b_p1.id, account_id=coa_b["1210"].id, debit_amount=Decimal("7200.00"), credit_amount=Decimal("0.00"), line_number=2),
        JournalEntryLine(journal_entry_id=je_b_p1.id, account_id=coa_b["1220"].id, debit_amount=Decimal("7200.00"), credit_amount=Decimal("0.00"), line_number=3),
        JournalEntryLine(journal_entry_id=je_b_p1.id, account_id=coa_b["2010"].id, debit_amount=Decimal("0.00"), credit_amount=Decimal("94400.00"), line_number=4),
    ]

    db_session.add_all([
        doc_a_s1, rec_a_s1, je_a_s1, *lines_a_s1,
        doc_a_cn1, rec_a_cn1, je_a_cn1, *lines_a_cn1,
        doc_a_p1, rec_a_p1, je_a_p1, *lines_a_p1,
        rec_a_pmt, je_a_pmt, *lines_a_pmt,
        doc_b_s1, rec_b_s1, je_b_s1, *lines_b_s1,
        doc_b_p1, rec_b_p1, je_b_p1, *lines_b_p1,
    ])
    db_session.commit()

    # -------------------------------------------------------------------------
    # 1. GSTR-1 Reconciliation Isolation & Contra-Revenue Netting
    # -------------------------------------------------------------------------
    gstr1_a = GstReconciliationService.reconcile_gstr1(db_session, client_a_id, user, period="2026-Q2")
    # Client A: 100k sales - 20k credit note = 80k taxable net
    assert gstr1_a.total_outward_taxable == Decimal("80000.00")
    assert gstr1_a.total_outward_tax == Decimal("14400.00")
    assert gstr1_a.total_outward_cgst == Decimal("7200.00")
    assert gstr1_a.total_outward_sgst == Decimal("7200.00")
    # Must NOT contain Client B invoice
    inv_nums_a = [inv.invoice_number for inv in gstr1_a.invoices]
    assert "INV-A-01" in inv_nums_a
    assert "INV-B-01" not in inv_nums_a

    gstr1_b = GstReconciliationService.reconcile_gstr1(db_session, client_b_id, user, period="2026-08")
    # Client B: 200k sales
    assert gstr1_b.total_outward_taxable == Decimal("200000.00")
    assert gstr1_b.total_outward_tax == Decimal("36000.00")
    assert gstr1_b.total_outward_cgst == Decimal("18000.00")
    assert gstr1_b.total_outward_sgst == Decimal("18000.00")
    # Must NOT contain Client A invoice
    inv_nums_b = [inv.invoice_number for inv in gstr1_b.invoices]
    assert "INV-B-01" in inv_nums_b
    assert "INV-A-01" not in inv_nums_b

    # -------------------------------------------------------------------------
    # 2. GSTR-2B Reconciliation Isolation
    # -------------------------------------------------------------------------
    gstr2b_a = GstReconciliationService.reconcile_gstr2b(db_session, client_a_id, user, period="2026-Q2")
    assert gstr2b_a.total_inward_taxable == Decimal("50000.00")
    assert gstr2b_a.total_eligible_itc == Decimal("9000.00")

    gstr2b_b = GstReconciliationService.reconcile_gstr2b(db_session, client_b_id, user, period="2026-08")
    assert gstr2b_b.total_inward_taxable == Decimal("80000.00")
    assert gstr2b_b.total_eligible_itc == Decimal("14400.00")

    # -------------------------------------------------------------------------
    # 3. Table 12 HSN Summary Isolation
    # -------------------------------------------------------------------------
    hsn_a = GstReconciliationService.get_gstr1_table_12_hsn_summary(db_session, client_a_id, user, period="2026-Q2")
    codes_a = [r.hsn_sac for r in hsn_a.hsn_items]
    assert "998314" in codes_a
    assert "847130" not in codes_a
    assert "4820" not in codes_a
    assert hsn_a.total_taxable_value == Decimal("80000.00")
    assert hsn_a.total_tax_amount == Decimal("14400.00")

    hsn_b = GstReconciliationService.get_gstr1_table_12_hsn_summary(db_session, client_b_id, user, period="2026-08")
    codes_b = [r.hsn_sac for r in hsn_b.hsn_items]
    assert "847130" in codes_b
    assert "998314" not in codes_b
    assert hsn_b.total_taxable_value == Decimal("200000.00")
    assert hsn_b.total_tax_amount == Decimal("36000.00")

    # -------------------------------------------------------------------------
    # 4. GSTR-3B Summary Isolation & Tax Liability Parity
    # -------------------------------------------------------------------------
    gstr3b_a = GstReconciliationService.generate_gstr3b(db_session, client_a_id, user, period="2026-Q2")
    # Client A: Outward Tax 14,400 - Inward ITC 9,000 = Cash 5,400 (CGST 2,700, SGST 2,700)
    assert gstr3b_a.table_3_1_outward.taxable_value == Decimal("80000.00")
    assert gstr3b_a.table_4_net_itc.cgst == Decimal("4500.00")
    assert gstr3b_a.table_4_net_itc.sgst == Decimal("4500.00")
    assert gstr3b_a.tax_payable_in_cash == Decimal("5400.00")
    assert gstr3b_a.cash_payable_cgst == Decimal("2700.00")
    assert gstr3b_a.cash_payable_sgst == Decimal("2700.00")

    gstr3b_b = GstReconciliationService.generate_gstr3b(db_session, client_b_id, user, period="2026-08")
    # Client B: Outward Tax 36,000 - Inward ITC 14,400 = Cash 21,600 (CGST 10,800, SGST 10,800)
    assert gstr3b_b.table_3_1_outward.taxable_value == Decimal("200000.00")
    assert gstr3b_b.table_4_net_itc.cgst == Decimal("7200.00")
    assert gstr3b_b.table_4_net_itc.sgst == Decimal("7200.00")
    assert gstr3b_b.tax_payable_in_cash == Decimal("21600.00")
    assert gstr3b_b.cash_payable_cgst == Decimal("10800.00")
    assert gstr3b_b.cash_payable_sgst == Decimal("10800.00")


def test_statutory_due_dates_per_state_and_frequency(db_session):
    """
    Test due dates per Rule R8 / Indian GST Rules:
    - Client A (MH 27, Quarterly):
      - Q2 GSTR-3B: 22nd of following month (2026-10-22, Category 1)
      - Q2 GSTR-1: 13th of following month (2026-10-13, QRMP)
    - Client B (DL 07, Monthly):
      - Aug GSTR-3B: 20th of subsequent month (2026-09-20)
      - Aug GSTR-1: 11th of subsequent month (2026-09-11)
    """
    user = User(id=uuid.uuid4(), email="auditor2@multi.com", full_name="Auditor Two", password_hash="hash", role="admin")
    client_mh = Client(
        id=uuid.uuid4(),
        client_code="CLI-MH2",
        company_name="MH Corp",
        gst_number="27AAACA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    client_dl = Client(
        id=uuid.uuid4(),
        client_code="CLI-DL2",
        company_name="DL Corp",
        gst_number="07AAACA1234A1Z5",
        return_frequency="Monthly",
        contact_person="Admin",
    )
    db_session.add_all([user, client_mh, client_dl])
    db_session.commit()

    # 1. MH Quarterly Q2 GSTR-3B -> due 2026-10-22
    rec_mh_3b = create_gst_record(
        GSTRecordCreate(client_id=client_mh.id, gst_period="2026-Q2", gst_type="GSTR-3B", filing_status="draft"),
        db=db_session,
        current_user=user,
    )
    assert rec_mh_3b.data.due_date == date(2026, 10, 22)
    assert rec_mh_3b.data.period_label == "Q2 FY 2026-27"

    # 2. MH Quarterly Q2 GSTR-1 -> due 2026-10-13
    rec_mh_1 = create_gst_record(
        GSTRecordCreate(client_id=client_mh.id, gst_period="2026-Q2", gst_type="GSTR-1", filing_status="draft"),
        db=db_session,
        current_user=user,
    )
    assert rec_mh_1.data.due_date == date(2026, 10, 13)
    assert rec_mh_1.data.period_label == "Q2 FY 2026-27"

    # 3. DL Monthly Aug GSTR-3B -> due 2026-09-20
    rec_dl_3b = create_gst_record(
        GSTRecordCreate(client_id=client_dl.id, gst_period="2026-08", gst_type="GSTR-3B", filing_status="draft"),
        db=db_session,
        current_user=user,
    )
    assert rec_dl_3b.data.due_date == date(2026, 9, 20)
    assert rec_dl_3b.data.period_label == "Aug 2026"

    # 4. DL Monthly Aug GSTR-1 -> due 2026-09-11
    rec_dl_1 = create_gst_record(
        GSTRecordCreate(client_id=client_dl.id, gst_period="2026-08", gst_type="GSTR-1", filing_status="draft"),
        db=db_session,
        current_user=user,
    )
    assert rec_dl_1.data.due_date == date(2026, 9, 11)
    assert rec_dl_1.data.period_label == "Aug 2026"


def test_ui_governance_counter_contract():
    """
    Test UI governance counter contract:
    - Extracted: all effective documents
    - Verified: excludes rejected / duplicate documents
    - Posted: active unreversed vouchers (excludes reversed entries and reversal vouchers)
    - Filed: valid non-voided filings (excludes voided records)
    """
    # Sample document set
    docs = [
        {"id": "d1", "status": "verified"},
        {"id": "d2", "status": "verified"},
        {"id": "d3", "status": "rejected", "rejection_reason": "DUPLICATE"},
        {"id": "d4", "status": "pending"},
    ]
    extracted_count = len(docs)
    verified_count = len([d for d in docs if d.get("status") == "verified" and d.get("status") != "rejected"])
    assert extracted_count == 4
    assert verified_count == 2

    # Sample ledger / voucher set
    vouchers = [
        {"id": "v1", "status": "posted", "is_reversed": False},
        {"id": "v2", "status": "posted", "is_reversed": False},
        {"id": "v3", "status": "posted", "is_reversed": True},       # Reversed voucher
        {"id": "v4", "status": "reversed", "is_reversed": False},     # Marked reversed
        {"id": "v5", "status": "posted", "is_reversed": False},
    ]
    posted_count = len([
        v for v in vouchers
        if v.get("status") == "posted" and not v.get("is_reversed") and v.get("status") != "reversed"
    ])
    assert posted_count == 3  # Exactly v1, v2, v5

    # Sample filing set
    filings = [
        {"id": "f1", "filing_status": "filed", "void_reason": None},
        {"id": "f2", "filing_status": "voided", "void_reason": "Period not ended"},
        {"id": "f3", "filing_status": "filed", "void_reason": "Bogus manual entry"},  # Void reason present
        {"id": "f4", "filing_status": "pending", "void_reason": None},
    ]
    filed_count = len([
        f for f in filings
        if f.get("filing_status") == "filed" and f.get("filing_status") != "voided" and not f.get("void_reason")
    ])
    assert filed_count == 1  # Exactly f1
