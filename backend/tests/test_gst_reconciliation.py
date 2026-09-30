import sys
import os
import uuid
import pytest
from datetime import date, datetime
from decimal import Decimal
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
from app.services.accounting_draft_service import AccountingDraftService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.core.exceptions import ForbiddenException, NotFoundException


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
def gst_test_setup(db_session):
    """Fixture providing user, client, COA, and test accounts."""
    user = User(
        id=uuid.uuid4(),
        email=f"gst_ca_{uuid.uuid4().hex[:6]}@example.com",
        full_name="GST Chartered Accountant",
        password_hash="mock_hash",
        role="accountant",
        is_active=True,
    )
    unauth_user = User(
        id=uuid.uuid4(),
        email=f"unauth_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Unauthorized User",
        password_hash="mock_hash",
        role="accountant",
        is_active=True,
    )
    db_session.add_all([user, unauth_user])
    db_session.commit()

    client = Client(
        id=uuid.uuid4(),
        company_name="Apex Logistics Corp",
        client_code=f"ALC-{uuid.uuid4().hex[:4].upper()}",
        contact_person="Vikram Malhotra",
        email="compliance@apexlogistics.in",
        status="active",
        user_id=user.id,
    )
    db_session.add(client)
    db_session.commit()

    # Initialize standard Indian Accounting Chart of Accounts
    ChartOfAccountsService.initialize_default_accounts(db=db_session, client_id=client.id, user=user)

    # Fetch accounts map
    coa_list = db_session.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()
    accounts = {a.account_code: a for a in coa_list}

    return {
        "user": user,
        "unauth_user": unauth_user,
        "client": client,
        "accounts": accounts,
    }


def test_gstr1_outward_reconciliation(db_session, gst_test_setup):
    """Test GSTR-1 outward reconciliation against General Ledger sales and output GST."""
    data = gst_test_setup
    client = data["client"]
    user = data["user"]

    # 1. B2B Outward Invoice
    doc_b2b = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        status="verified",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Zenith Enterprises Ltd",
        gstin="27AABCZ1234F1Z5",
        invoice_number="INV-B2B-001",
        invoice_date="2026-07-10",
    )
    db_session.add(doc_b2b)
    db_session.commit()

    draft_b2b = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_b2b.id,
        transaction_date=date(2026, 7, 10), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("23600.00"), status="draft",
        reference_number="INV-B2B-001",
    )
    db_session.add(draft_b2b)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_b2b.id, user=user)

    # 2. B2CS Outward Invoice (No GSTIN)
    doc_b2cs = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2c_invoice",
        status="verified",
        amount=Decimal("1180.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        customer="Retail Consumer",
        gstin=None,
        invoice_number="INV-B2C-002",
        invoice_date="2026-07-15",
    )
    db_session.add(doc_b2cs)
    db_session.commit()

    draft_b2cs = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_b2cs.id,
        transaction_date=date(2026, 7, 15), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("1180.00"), status="draft",
        reference_number="INV-B2C-002",
    )
    db_session.add(draft_b2cs)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_b2cs.id, user=user)

    # Reconcile GSTR-1
    gstr1 = GstReconciliationService.reconcile_gstr1(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-07",
    )

    # B2B Section check
    assert gstr1.b2b_summary.invoice_count == 1
    assert gstr1.b2b_summary.taxable_amount == Decimal("20000.00")
    assert gstr1.b2b_summary.cgst == Decimal("1800.00")
    assert gstr1.b2b_summary.sgst == Decimal("1800.00")

    # B2CS Section check
    assert gstr1.b2cs_summary.invoice_count == 1
    assert gstr1.b2cs_summary.taxable_amount == Decimal("1000.00")
    assert gstr1.b2cs_summary.cgst == Decimal("90.00")
    assert gstr1.b2cs_summary.sgst == Decimal("90.00")

    # General Ledger Match Check
    assert gstr1.total_outward_taxable == Decimal("21000.00")
    assert gstr1.ledger_sales_turnover == Decimal("21000.00")
    assert gstr1.turnover_variance == Decimal("0.00")

    assert gstr1.ledger_output_cgst == Decimal("1890.00")
    assert gstr1.ledger_output_sgst == Decimal("1890.00")
    assert gstr1.tax_variance == Decimal("0.00")
    assert gstr1.is_reconciled is True


def test_gstr2b_inward_itc_reconciliation(db_session, gst_test_setup):
    """Test GSTR-2B inward ITC reconciliation against GL input tax accounts."""
    data = gst_test_setup
    client = data["client"]
    user = data["user"]

    # Inward Purchase Invoice
    doc_pur = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        vendor="Global Supplies Pvt Ltd",
        gstin="27XYZAB9876K1Z3",
        invoice_number="PUR-001",
        invoice_date="2026-07-12",
    )
    db_session.add(doc_pur)
    db_session.commit()

    draft_pur = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_pur.id,
        transaction_date=date(2026, 7, 12), voucher_type="purchase",
        debit=Decimal("11800.00"), credit=Decimal("0.00"), status="draft",
        reference_number="PUR-001",
    )
    db_session.add(draft_pur)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_pur.id, user=user)

    # Reconcile GSTR-2B
    gstr2b = GstReconciliationService.reconcile_gstr2b(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-07",
    )

    assert gstr2b.total_inward_taxable == Decimal("10000.00")
    assert gstr2b.eligible_itc_cgst == Decimal("900.00")
    assert gstr2b.eligible_itc_sgst == Decimal("900.00")
    assert gstr2b.total_eligible_itc == Decimal("1800.00")
    assert gstr2b.ineligible_itc == Decimal("0.00")

    # General Ledger Match Check (Accounts 1060 & 1070)
    assert gstr2b.ledger_input_cgst == Decimal("900.00")
    assert gstr2b.ledger_input_sgst == Decimal("900.00")
    assert gstr2b.ledger_total_input_tax == Decimal("1800.00")
    assert gstr2b.itc_variance == Decimal("0.00")
    assert gstr2b.is_reconciled is True


def test_gstr3b_consolidated_calculation(db_session, gst_test_setup):
    """Test GSTR-3B monthly return computation (Outward, ITC, and net cash liability)."""
    data = gst_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Post Sales Invoice (Output Tax: CGST ₹1,800 + SGST ₹1,800 = ₹3,600)
    doc_sales = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("23600.00"),
        taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"),
        sgst=Decimal("1800.00"),
        customer="Client Buyer",
        gstin="27ABCDE1234F1Z5",
        invoice_number="INV-3B-01",
        invoice_date="2026-07-05",
    )
    db_session.add(doc_sales)
    db_session.commit()

    draft_sales = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_sales.id,
        transaction_date=date(2026, 7, 5), voucher_type="sales",
        debit=Decimal("0.00"), credit=Decimal("23600.00"), status="draft",
        reference_number="INV-3B-01",
    )
    db_session.add(draft_sales)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_sales.id, user=user)

    # 2. Post Purchase Invoice (Input ITC: CGST ₹900 + SGST ₹900 = ₹1,800)
    doc_pur = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="purchase_records",
        status="verified",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        cgst=Decimal("900.00"),
        sgst=Decimal("900.00"),
        vendor="Supplier Partner",
        gstin="27KLMNO5678P1Z2",
        invoice_number="PUR-3B-01",
        invoice_date="2026-07-08",
    )
    db_session.add(doc_pur)
    db_session.commit()

    draft_pur = AccountingRecord(
        id=uuid.uuid4(), client_id=client.id, document_id=doc_pur.id,
        transaction_date=date(2026, 7, 8), voucher_type="purchase",
        debit=Decimal("11800.00"), credit=Decimal("0.00"), status="draft",
        reference_number="PUR-3B-01",
    )
    db_session.add(draft_pur)
    db_session.commit()
    AccountingDraftService.post_draft_to_ledger(db_session, draft_pur.id, user=user)

    # 3. Generate GSTR-3B
    gstr3b = GstReconciliationService.generate_gstr3b(
        db=db_session,
        client_id=client.id,
        user=user,
        period="2026-07",
    )

    # Table 3.1 Outward
    assert gstr3b.table_3_1_outward.taxable_value == Decimal("20000.00")
    assert gstr3b.table_3_1_outward.cgst == Decimal("1800.00")
    assert gstr3b.table_3_1_outward.sgst == Decimal("1800.00")

    # Table 4 Net ITC
    assert gstr3b.table_4_net_itc.taxable_value == Decimal("10000.00")
    assert gstr3b.table_4_net_itc.cgst == Decimal("900.00")
    assert gstr3b.table_4_net_itc.sgst == Decimal("900.00")

    # Net Cash Payable = (1800 - 900) CGST + (1800 - 900) SGST = ₹1,800.00
    assert gstr3b.tax_payable_in_cash == Decimal("1800.00")
    assert gstr3b.excess_credit_carried_forward == Decimal("0.00")


def test_discrepancy_detection_engine(db_session, gst_test_setup):
    """Test automated discrepancy detection: Missing GSTIN, Math mismatch, Unposted, Duplicate."""
    data = gst_test_setup
    client = data["client"]
    user = data["user"]

    # 1. Missing GSTIN on B2B customer
    doc_missing_gstin = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="b2b_invoice",
        status="processed",
        amount=Decimal("5000.00"),
        taxable_amount=Decimal("5000.00"),
        customer="Omega Enterprise Pvt Ltd",
        gstin="",  # Missing GSTIN!
        invoice_number="INV-NO-GSTIN",
    )

    # 2. Mathematical mismatch (amount 1500 != taxable 1000 + cgst 100 + sgst 100 = 1200)
    doc_math = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="processed",
        amount=Decimal("1500.00"),
        taxable_amount=Decimal("1000.00"),
        cgst=Decimal("100.00"),
        sgst=Decimal("100.00"),
        customer="Individual Buyer",
        invoice_number="INV-MATH-ERR",
    )

    # 3. Unposted verified invoice
    doc_unposted = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="verified",
        amount=Decimal("2000.00"),
        taxable_amount=Decimal("2000.00"),
        customer="Direct Buyer",
        invoice_number="INV-UNPOSTED-01",
    )

    # 4 & 5. Duplicate Invoices
    doc_dup1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="processed",
        amount=Decimal("3000.00"),
        taxable_amount=Decimal("3000.00"),
        customer="Duplicate Customer Ltd",
        gstin="27DUP12345678Z9",
        invoice_number="INV-DUPLICATE-01",
    )
    doc_dup2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client.id,
        document_category="sales_records",
        status="processed",
        amount=Decimal("3000.00"),
        taxable_amount=Decimal("3000.00"),
        customer="Duplicate Customer Ltd",
        gstin="27DUP12345678Z9",
        invoice_number="INV-DUPLICATE-01",
    )

    db_session.add_all([doc_missing_gstin, doc_math, doc_unposted, doc_dup1, doc_dup2])
    db_session.commit()

    # Run Discrepancy Engine
    report = GstReconciliationService.detect_discrepancies(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    rule_codes = {d.rule_code for d in report.discrepancies}
    assert "MISSING_GSTIN" in rule_codes
    assert "TAX_MATH_MISMATCH" in rule_codes
    assert "UNPOSTED_INVOICE" in rule_codes
    assert "DUPLICATE_INVOICE" in rule_codes

    assert report.high_count >= 3
    assert report.total_discrepancies >= 4


def test_ca_financial_insights_and_scoring(db_session, gst_test_setup):
    """Test CA review insights, dynamic risk scoring, and filing checklist."""
    data = gst_test_setup
    client = data["client"]
    user = data["user"]

    insights = GstReconciliationService.get_financial_insights(
        db=db_session,
        client_id=client.id,
        user=user,
    )

    assert 0 <= insights.compliance_score <= 100
    assert insights.risk_level in ["LOW", "MEDIUM", "HIGH"]
    assert len(insights.action_checklist) > 0
    assert any(item.check_name.startswith("GSTR-1") for item in insights.action_checklist)


def test_gst_client_tenant_isolation(db_session, gst_test_setup):
    """Test unauthorized accountant cannot view another client's GST reconciliation."""
    data = gst_test_setup
    client = data["client"]
    unauth_user = data["unauth_user"]

    with pytest.raises(ForbiddenException):
        GstReconciliationService.reconcile_gstr1(
            db=db_session,
            client_id=client.id,
            user=unauth_user,
        )

    with pytest.raises(ForbiddenException):
        GstReconciliationService.reconcile_gstr2b(
            db=db_session,
            client_id=client.id,
            user=unauth_user,
        )

    with pytest.raises(ForbiddenException):
        GstReconciliationService.detect_discrepancies(
            db=db_session,
            client_id=client.id,
            user=unauth_user,
        )
