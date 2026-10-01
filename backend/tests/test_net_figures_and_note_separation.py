"""
Unit & Integration Tests for Statutory GST Parity (D3):
1. Net Outward Figures:
   Outward Taxable = Sales + Other Operating Income - Sales Return (₹10,000 for S3 + CN1 + DN1).
2. Head-wise Output Taxes:
   CGST: -1,300.00, SGST: -1,300.00, IGST: +1,800.00, Total Tax: -800.00.
3. Strict Register Isolation:
   Sales-side credit notes (CN1) and sales-side debit notes (DN1) are completely
   excluded from the GSTR-2B Purchase Register.
"""

import uuid
import json
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
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.accounting_draft_service import AccountingDraftService
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
def setup_data(db_session):
    """Seed user, client, COA and standard documents."""
    user = User(
        id=uuid.uuid4(),
        email="ca.tester@example.com",
        full_name="CA Tester",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    client = Client(
        id=uuid.uuid4(),
        user_id=user.id,
        company_name="Ankit public Ltd",
        client_code="ANK-001",
        contact_person="Director Ankit",
        client_type="company",
        gst_number="27AABCF8939R1ZW",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)

    period = AccountingPeriod(
        id=uuid.uuid4(),
        client_id=client.id,
        period_name="Q2 FY 2026-27",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 9, 30),
        status="open",
    )
    db_session.add(period)
    db_session.flush()

    return user, client, period


def test_d3_net_figures_and_strict_register_isolation(db_session, setup_data):
    user, client, period = setup_data

    # 1. Original Sales E-Invoice S2 (for DN1 reference lookup)
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="invoice_abc_002.pdf",
        document_category="e_invoice",
        invoice_type="sales",
        invoice_number="ABC/26-27/002",
        invoice_date="2026-07-10",
        customer="Global Exports Ltd",
        gstin="29ABCDE1234F1Z5",
        amount=Decimal("118000.00"),
        taxable_amount=Decimal("100000.00"),
        igst=Decimal("18000.00"),
        status="processed",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "29ABCDE1234F1Z5"},
                "taxable_amount": {"value": 100000.0},
                "igst_amount": {"value": 18000.0},
                "place_of_supply_code": {"value": "29"},
            }
        }),
    )
    db_session.add(doc_s2)
    db_session.flush()

    # 2. S3: Walk-in cash sales, B2CS
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="cash_memo_s3.pdf",
        document_category="b2c_invoice",
        invoice_type="sales",
        invoice_number="CASH/26-27/001",
        invoice_date="2026-08-15",
        customer="Cash Customer (Unregistered)",
        amount=Decimal("22600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1300.00"),
        sgst=Decimal("1300.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "taxable_amount": {"value": 20000.0},
                "cgst_amount": {"value": 1300.0},
                "sgst_amount": {"value": 1300.0},
                "place_of_supply_code": {"value": "27"},
            }
        }),
    )
    db_session.add(doc_s3)
    db_session.flush()

    # Post S3
    d_res_s3 = AccountingDraftService.generate_or_update_draft(db_session, doc_s3.id)
    assert d_res_s3.status in ("created", "updated")
    res_s3 = AccountingDraftService.post_draft_to_ledger(db_session, d_res_s3.record.id, user)
    assert res_s3.success is True

    # 3. CN1: Sales Credit Note (reducing sales/output tax)
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="credit_note_cn1.pdf",
        document_category="credit_note",
        invoice_type="sales",
        invoice_number="ABC/CN/26-27/001",
        invoice_date="2026-08-20",
        customer="Apex Enterprises",
        gstin="27XYZPA1234A1Z9",
        amount=Decimal("25200.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("2600.00"),
        sgst=Decimal("2600.00"),
        applies_to="SALES",
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "27XYZPA1234A1Z9"},
                "taxable_amount": {"value": 20000.0},
                "cgst_amount": {"value": 2600.0},
                "sgst_amount": {"value": 2600.0},
                "place_of_supply_code": {"value": "27"},
            }
        }),
    )
    db_session.add(doc_cn1)
    db_session.flush()

    d_res_cn1 = AccountingDraftService.generate_or_update_draft(db_session, doc_cn1.id)
    assert d_res_cn1.status in ("created", "updated")
    res_cn1 = AccountingDraftService.post_draft_to_ledger(db_session, d_res_cn1.record.id, user)
    assert res_cn1.success is True

    # 4. DN1: Sales Debit Note against original sales invoice ABC/26-27/002
    doc_dn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        file_name="debit_note_dn1.pdf",
        document_category="debit_note",
        invoice_type="sales",
        invoice_number="ABC/DN/26-27/001",
        invoice_date="2026-08-25",
        customer="Global Exports Ltd",
        gstin="29ABCDE1234F1Z5",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"),
        status="verified",
        metadata_=json.dumps({
            "fields": {
                "original_invoice_number": {"value": "ABC/26-27/002"},
                "supplier_gstin": {"value": client.gst_number},
                "customer_gstin": {"value": "29ABCDE1234F1Z5"},
                "taxable_amount": {"value": 10000.0},
                "igst_amount": {"value": 1800.0},
                "place_of_supply_code": {"value": "29"},
            }
        }),
    )
    db_session.add(doc_dn1)
    db_session.flush()

    je_create_dn1 = AccountingMappingService.map_document_to_journal_entry(db_session, doc_dn1, user)
    # DN1 must be mapped as Template T4 (sales debit note: Dr Debtors, Cr Other Operating Income, Cr Output IGST)
    account_ids = [line.account_id for line in je_create_dn1.lines if line.credit_amount > 0]
    credit_accounts = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.id.in_(account_ids)).all()
    credit_account_codes = [a.account_code for a in credit_accounts]
    credit_roles = [a.role for a in credit_accounts]
    assert "4030" in credit_account_codes or "4000" in credit_account_codes or "OTHER_INCOME" in credit_roles
    assert "2130" in credit_account_codes or "2013" in credit_account_codes or "OUTPUT_IGST" in credit_roles

    d_res_dn1 = AccountingDraftService.generate_or_update_draft(db_session, doc_dn1.id)
    assert d_res_dn1.status in ("created", "updated")
    res_dn1 = AccountingDraftService.post_draft_to_ledger(db_session, d_res_dn1.record.id, user)
    assert res_dn1.success is True

    # ── GSTR-1 Reconciliation Verification ──
    gstr1_res = GstReconciliationService.reconcile_gstr1(
        db=db_session,
        client_id=client.id,
        user=user,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 9, 30),
    )

    # Check Net Outward Taxable:
    # S3 (20,000) - CN1 (20,000) + DN1 (10,000) = 10,000.00
    assert gstr1_res.total_outward_taxable == Decimal("10000.00")

    # Check Head-wise Taxes:
    # S3 (CGST 1,300, SGST 1,300)
    # CN1 (CGST -2,600, SGST -2,600)
    # DN1 (IGST +1,800)
    # Net CGST: -1,300.00, Net SGST: -1,300.00, Net IGST: +1,800.00, Total Tax: -800.00
    assert gstr1_res.total_outward_cgst == Decimal("-1300.00")
    assert gstr1_res.total_outward_sgst == Decimal("-1300.00")
    assert gstr1_res.total_outward_igst == Decimal("1800.00")
    assert gstr1_res.total_outward_tax == Decimal("-800.00")

    # ── GSTR-2B Reconciliation Verification (Strict Isolation) ──
    gstr2b_res = GstReconciliationService.reconcile_gstr2b(
        db=db_session,
        client_id=client.id,
        user=user,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 9, 30),
    )

    # Purchase register must be strictly empty (no sales documents or sales notes leak in)
    assert len(gstr2b_res.invoices) == 0
    assert gstr2b_res.total_inward_taxable == Decimal("0.00")
    assert gstr2b_res.total_eligible_itc == Decimal("0.00")
