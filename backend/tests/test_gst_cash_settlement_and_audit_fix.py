"""
Targeted Unit & Integration Tests for GST Cash Settlement & Audit Reconciliation Fix:
1. S3 + CN1 + DN1 statutory arithmetic and GSTR-3B Table 6 cash settlement.
2. Negative CGST/SGST output liability properly tracked as adjustment carried forward.
3. No cross-head subsidization: IGST cash payable is preserved when CGST/SGST are negative.
4. Purely negative output tax does not generate positive cash liability.
5. Unposted verified e-invoices correctly flagged under UNPOSTED_INVOICE.
6. Zero audit exceptions when all documents are cleanly posted.
7. Period isolation and quarterly parsing ('2026-Q2', '2026-Q1').
8. Strict exclusion of reversed vouchers from GSTR-3B and GL aggregations.
"""

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
from app.services.accounting_draft_service import AccountingDraftService
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


@pytest.fixture
def gst_fixture(db_session):
    """Seed client C-1070 test environment."""
    user = User(
        id=uuid.uuid4(),
        email="ca.gst.fix@example.com",
        full_name="CA Specialist",
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
        client_code="C-1070",
        contact_person="Director Ankit",
        client_type="company",
        gst_number="27AABCF8939R1ZW",
        state="Maharashtra",
        status="active",
    )
    db_session.add(client)
    db_session.flush()

    ChartOfAccountsService.initialize_default_accounts(db_session, client.id, user)

    return user, client


def test_quarterly_period_parsing():
    """Verify _parse_period_dates handles quarterly strings and monthly strings."""
    # 2026-Q2 -> Jul 1 to Sep 30, 2026
    s, e = GstReconciliationService._parse_period_dates("2026-Q2", None, None)
    assert s == date(2026, 7, 1)
    assert e == date(2026, 9, 30)

    # 2026-Q1 -> Apr 1 to Jun 30, 2026
    s1, e1 = GstReconciliationService._parse_period_dates("2026-Q1", None, None)
    assert s1 == date(2026, 4, 1)
    assert e1 == date(2026, 6, 30)

    # Monthly 2026-07 -> Jul 1 to Jul 31, 2026
    sm, em = GstReconciliationService._parse_period_dates("2026-07", None, None)
    assert sm == date(2026, 7, 1)
    assert em == date(2026, 7, 31)

    # All Available -> None, None
    sa, ea = GstReconciliationService._parse_period_dates("all", None, None)
    assert sa is None
    assert ea is None


def test_s3_cn1_dn1_net_tax_and_statutory_cash_settlement(db_session, gst_fixture):
    """
    Test statutory scenario S3 + CN1 + DN1:
    - S3: B2C Walk-in sales (Taxable ₹20,000, CGST ₹500, SGST ₹500)
    - CN1: Credit Note (Taxable -₹20,000, CGST -₹1,800, SGST -₹1,800)
    - DN1: Debit Note (Taxable ₹10,000, IGST ₹1,800)
    Results:
    - Net Taxable: ₹10,000.00
    - Net CGST: -₹1,300.00, Net SGST: -₹1,300.00, Net IGST: +₹1,800.00
    - Total Net Outward Tax: -₹800.00
    - Statutory Cash Due: ₹1,800.00 (IGST cannot be reduced by CGST/SGST)
    - Negative Liability Carried Forward: ₹2,600.00 (CGST ₹1,300 + SGST ₹1,300)
    """
    user, client = gst_fixture

    # 1. Document S3
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="ABC/26-27/003",
        document_category="b2c_invoice",
        invoice_date="2026-07-20",
        amount=Decimal("21000.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"),
        sgst=Decimal("500.00"),
        customer="Walk-in Customer (Unregistered)",
        status="verified",
    )
    db_session.add(doc_s3)
    db_session.flush()

    d_s3 = AccountingDraftService.generate_or_update_draft(db_session, doc_s3.id)
    AccountingDraftService.post_draft_to_ledger(db_session, d_s3.record.id, user)

    # 2. Document CN1
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="ABC/CN/26-27/001",
        document_category="credit_note",
        invoice_date="2026-08-10",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        applies_to="SALES",
        customer="Mehta Enterprises",
        gstin="27AAAPM5678B1Z2",
        status="verified",
    )
    db_session.add(doc_cn1)
    db_session.flush()

    d_cn1 = AccountingDraftService.generate_or_update_draft(db_session, doc_cn1.id)
    AccountingDraftService.post_draft_to_ledger(db_session, d_cn1.record.id, user)

    # 3. Document DN1
    doc_dn1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="ABC/DN/26-27/001",
        document_category="debit_note",
        invoice_date="2026-08-15",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"),
        customer="Kannan Software LLP",
        gstin="29AABCK4321C1Z8",
        status="verified",
    )
    db_session.add(doc_dn1)
    db_session.flush()

    d_dn1 = AccountingDraftService.generate_or_update_draft(db_session, doc_dn1.id)
    AccountingDraftService.post_draft_to_ledger(db_session, d_dn1.record.id, user)

    # ── Reconcile GSTR-1 ──
    g1 = GstReconciliationService.reconcile_gstr1(db_session, client.id, user, period="2026-Q2")
    assert g1.total_outward_taxable == Decimal("10000.00")
    assert g1.total_outward_cgst == Decimal("-1300.00")
    assert g1.total_outward_sgst == Decimal("-1300.00")
    assert g1.total_outward_igst == Decimal("1800.00")
    assert g1.total_outward_tax == Decimal("-800.00")

    # ── Generate GSTR-3B ──
    g3 = GstReconciliationService.generate_gstr3b(db_session, client.id, user, period="2026-Q2")

    # Table 3.1
    assert g3.table_3_1_outward.taxable_value == Decimal("10000.00")
    assert g3.table_3_1_outward.igst == Decimal("1800.00")
    assert g3.table_3_1_outward.cgst == Decimal("-1300.00")
    assert g3.table_3_1_outward.sgst == Decimal("-1300.00")

    # Statutory Set-off & Table 6 Cash Due
    assert g3.tax_payable_in_cash == Decimal("1800.00")
    assert g3.cash_payable_igst == Decimal("1800.00")
    assert g3.cash_payable_cgst == Decimal("0.00")
    assert g3.cash_payable_sgst == Decimal("0.00")

    # Negative Output Adjustment Carried Forward
    assert g3.negative_liability_carried_forward == Decimal("2600.00")
    assert g3.negative_liability_cgst == Decimal("1300.00")
    assert g3.negative_liability_sgst == Decimal("1300.00")
    assert g3.negative_liability_igst == Decimal("0.00")

    # Review & Explanatory Summary
    assert g3.needs_ca_review is True
    assert g3.settlement_summary is not None
    assert "IGST" in g3.settlement_summary
    assert "carried forward" in g3.settlement_summary


def test_negative_aggregate_tax_with_zero_igst(db_session, gst_fixture):
    """When net tax is negative without any positive IGST, cash due is strictly ₹0.00."""
    user, client = gst_fixture

    # Only a sales credit note
    doc_cn = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="CN-ONLY-01",
        document_category="credit_note",
        invoice_date="2026-08-10",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        applies_to="SALES",
        customer="Client Buyer",
        status="verified",
    )
    db_session.add(doc_cn)
    db_session.flush()

    d_cn = AccountingDraftService.generate_or_update_draft(db_session, doc_cn.id)
    AccountingDraftService.post_draft_to_ledger(db_session, d_cn.record.id, user)

    g3 = GstReconciliationService.generate_gstr3b(db_session, client.id, user, period="2026-Q2")

    assert g3.table_3_1_outward.cgst == Decimal("-900.00")
    assert g3.table_3_1_outward.sgst == Decimal("-900.00")
    assert g3.tax_payable_in_cash == Decimal("0.00")
    assert g3.cash_payable_cgst == Decimal("0.00")
    assert g3.cash_payable_sgst == Decimal("0.00")
    assert g3.cash_payable_igst == Decimal("0.00")
    assert g3.negative_liability_carried_forward == Decimal("1800.00")


def test_unposted_einvoice_triggers_audit_discrepancy(db_session, gst_fixture):
    """Verified e-invoice S2 that is not posted to ledger must trigger UNPOSTED_INVOICE discrepancy."""
    user, client = gst_fixture

    doc_s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="ABC/26-27/002",
        document_category="e_invoice",
        invoice_date="2026-07-12",
        amount=Decimal("236000.00"),
        taxable_amount=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        customer="Kannan Software LLP",
        gstin="29AABCK4321C1Z8",
        status="verified",
    )
    db_session.add(doc_s2)
    db_session.commit()

    # Draft accounting record exists, but NOT posted to ledger
    rec = AccountingRecord(
        id=uuid.uuid4(),
        client_id=client.id,
        document_id=doc_s2.id,
        transaction_date=date(2026, 7, 12),
        voucher_type="sales",
        debit=Decimal("0.00"),
        credit=Decimal("236000.00"),
        status="draft",
        reference_number="ABC/26-27/002",
    )
    db_session.add(rec)
    db_session.commit()

    report = GstReconciliationService.detect_discrepancies(db_session, client.id, user, period="2026-Q2")

    assert report.total_discrepancies == 1
    assert report.medium_count == 1
    unposted_disc = [d for d in report.discrepancies if d.rule_code == "UNPOSTED_INVOICE"]
    assert len(unposted_disc) == 1
    assert unposted_disc[0].invoice_number == "ABC/26-27/002"
    assert unposted_disc[0].variance_amount == Decimal("36000.00")


def test_zero_audit_exceptions_when_fully_reconciled(db_session, gst_fixture):
    """When all verified documents are posted, total_discrepancies is cleanly 0."""
    user, client = gst_fixture

    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="INV-CLEAN-001",
        document_category="sales_records",
        invoice_date="2026-07-20",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        customer="Retail Client",
        status="verified",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
    AccountingDraftService.post_draft_to_ledger(db_session, draft.record.id, user)

    report = GstReconciliationService.detect_discrepancies(db_session, client.id, user, period="2026-Q2")
    assert report.total_discrepancies == 0
    assert len(report.discrepancies) == 0


def test_reversed_vouchers_excluded_from_gstr3b(db_session, gst_fixture):
    """Reversed journal entries must not pollute GSTR-3B tax calculations."""
    user, client = gst_fixture

    # Post an entry and then reverse it
    doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        invoice_number="INV-REV-001",
        document_category="sales_records",
        invoice_date="2026-07-15",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        customer="Party A",
        status="verified",
    )
    db_session.add(doc)
    db_session.commit()

    draft = AccountingDraftService.generate_or_update_draft(db_session, doc.id)
    res = AccountingDraftService.post_draft_to_ledger(db_session, draft.record.id, user)
    assert res.success is True

    # Mark JE as reversed
    je = db_session.query(JournalEntry).filter(JournalEntry.document_id == doc.id).first()
    je.status = "reversed"
    je.is_reversed = True
    db_session.commit()

    g3 = GstReconciliationService.generate_gstr3b(db_session, client.id, user, period="2026-Q2")
    assert g3.table_3_1_outward.taxable_value == Decimal("0.00")
    assert g3.table_3_1_outward.cgst == Decimal("0.00")
    assert g3.table_3_1_outward.sgst == Decimal("0.00")
    assert g3.table_3_1_outward.igst == Decimal("0.00")
    assert g3.tax_payable_in_cash == Decimal("0.00")
