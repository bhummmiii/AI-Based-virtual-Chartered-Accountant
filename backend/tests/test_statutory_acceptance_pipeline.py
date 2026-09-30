"""
Statutory Acceptance Test Suite (Section 6 & Section 9):
Pipeline Scenarios, Negative Tests, and Audit Invariants.
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
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.journal_entry_service import JournalEntryService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.core.exceptions import BadRequestException


@pytest.fixture
def pipe_db():
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
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def pipe_client(pipe_db):
    user = User(
        id=uuid.uuid4(),
        email="lead_ca@finledger.ai",
        full_name="CA Lead Partner",
        password_hash="mockpass",
        role="ca",
        is_active=True,
    )
    pipe_db.add(user)
    pipe_db.flush()

    # ABC Traders Pvt Ltd, GSTIN 27AABCA1234A1Z5, Maharashtra
    client = Client(
        id=uuid.uuid4(),
        company_name="ABC Traders Pvt Ltd",
        client_code="ABC-MUM",
        contact_person="Director ABC",
        gst_number="27AABCA1234A1Z5",
        email="contact@abctraders.in",
        status="active",
        user_id=user.id,
    )
    pipe_db.add(client)
    pipe_db.flush()

    ChartOfAccountsService.initialize_default_accounts(db=pipe_db, client_id=client.id, user=user)
    coa_map = {acc.account_code: acc for acc in pipe_db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client.id).all()}

    return {"user": user, "client": client, "coa": coa_map}


# ── Scenario A ────────────────────────────────────────────────────────────────

def test_scenario_a_outward_supplies_and_notes(pipe_db, pipe_client):
    """
    Scenario A: S1, S2, S3, CN1, DN1
    - S1 B2B intra: 100,000 / CGST 9,000 + SGST 9,000 / 118,000
    - S2 B2B inter: 200,000 / IGST 36,000 / 236,000
    - S3 B2C intra: 20,000 / CGST 500 + SGST 500 / 21,000
    - CN1 credit note on S1: 20,000 / CGST 1,800 + SGST 1,800 / 23,600
    - DN1 debit note on S2: 10,000 / IGST 1,800 / 11,800
    """
    data = pipe_client
    client = data["client"]
    user = data["user"]

    doc_s1 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="b2b_invoice",
        status="verified", amount=Decimal("118000.00"), taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"), sgst=Decimal("9000.00"), customer="Mehta Enterprises",
        gstin="27AAAPM5678B1Z2", invoice_number="ABC/26-27/001", invoice_date="2026-07-05",
    )
    doc_s2 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="b2b_invoice",
        status="verified", amount=Decimal("236000.00"), taxable_amount=Decimal("200000.00"),
        igst=Decimal("36000.00"), customer="Kannan Software LLP",
        gstin="29AABCK4321C1Z8", invoice_number="ABC/26-27/002", invoice_date="2026-07-12",
    )
    doc_s3 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="b2c_invoice",
        status="verified", amount=Decimal("21000.00"), taxable_amount=Decimal("20000.00"),
        cgst=Decimal("500.00"), sgst=Decimal("500.00"), customer="Walk-in Customer (Unregistered)",
        gstin="", invoice_number="ABC/26-27/003", invoice_date="2026-07-20",
    )
    doc_cn1 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="credit_note",
        status="verified", amount=Decimal("23600.00"), taxable_amount=Decimal("20000.00"),
        cgst=Decimal("1800.00"), sgst=Decimal("1800.00"), customer="Mehta Enterprises",
        gstin="27AAAPM5678B1Z2", invoice_number="ABC/CN/26-27/001", invoice_date="2026-08-10",
        ocr_text="Against Invoice ABC/26-27/001 dt 05-Jul-2026",
    )
    doc_dn1 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="debit_note",
        status="verified", amount=Decimal("11800.00"), taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"), customer="Kannan Software LLP",
        gstin="29AABCK4321C1Z8", invoice_number="ABC/DN/26-27/001", invoice_date="2026-08-15",
        ocr_text="Against Invoice ABC/26-27/002 dt 12-Jul-2026",
    )
    pipe_db.add_all([doc_s1, doc_s2, doc_s3, doc_cn1, doc_dn1])
    pipe_db.commit()

    for doc in [doc_s1, doc_s2, doc_s3, doc_cn1, doc_dn1]:
        d_res = AccountingDraftService.generate_or_update_draft(pipe_db, doc.id)
        assert d_res.status in ("created", "updated")
        assert d_res.record is not None
        res = AccountingDraftService.post_draft_to_ledger(pipe_db, d_res.record.id, user)
        assert res.success is True

    gstr1 = GstReconciliationService.reconcile_gstr1(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
    gstr2b = GstReconciliationService.reconcile_gstr2b(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
    gstr3b = GstReconciliationService.generate_gstr3b(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))

    # Assert Output Tax Balances
    assert gstr1.total_outward_cgst == Decimal("7700.00")
    assert gstr1.total_outward_sgst == Decimal("7700.00")
    assert gstr1.total_outward_igst == Decimal("37800.00")
    assert gstr1.total_outward_tax == Decimal("53200.00")
    assert gstr1.total_outward_taxable == Decimal("310000.00")

    # Inward Register is EMPTY in Scenario A
    assert gstr2b.total_eligible_itc == Decimal("0.00")
    assert len(gstr2b.invoices) == 0

    # GSTR-3B Cash Payable: 53,200 (IGST 37,800, CGST 7,700, SGST 7,700)
    assert gstr3b.tax_payable_in_cash == Decimal("53200.00")
    assert gstr3b.table_3_1_outward.taxable_value == Decimal("310000.00")


# ── Scenario B ────────────────────────────────────────────────────────────────

def test_scenario_b_full_pack_with_itc_and_setoff(pipe_db, pipe_client):
    """
    Scenario B (Tier 1 Acceptance):
    Additionally post S4, S5, P1, P2, PDN1, PCN1.
    Output: CGST 7,700 | SGST 7,700 | IGST 93,600 | Total 109,000
    Net Taxable Outward: 620,000
    Input (ITC): CGST 8,550 | SGST 8,550 | IGST 7,200 | Total 24,300
    Set-off:
      IGST credit 7,200 against 93,600 -> 86,400 left.
      CGST credit 8,550 pays 7,700 -> surplus 850 pays IGST.
      SGST credit 8,550 pays 7,700 -> surplus 850 pays IGST.
      IGST cash left = 86,400 - 850 - 850 = 84,700.
      Cash payable: CGST 0, SGST 0, IGST 84,700, Total 84,700.
    """
    data = pipe_client
    client = data["client"]
    user = data["user"]

    # Post Scenario A documents first
    docs_a = [
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="b2b_invoice",
            status="verified", amount=Decimal("118000.00"), taxable_amount=Decimal("100000.00"),
            cgst=Decimal("9000.00"), sgst=Decimal("9000.00"), customer="Mehta Enterprises",
            gstin="27AAAPM5678B1Z2", invoice_number="ABC/26-27/001", invoice_date="2026-07-05",
        ),
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="b2b_invoice",
            status="verified", amount=Decimal("236000.00"), taxable_amount=Decimal("200000.00"),
            igst=Decimal("36000.00"), customer="Kannan Software LLP",
            gstin="29AABCK4321C1Z8", invoice_number="ABC/26-27/002", invoice_date="2026-07-12",
        ),
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="b2c_invoice",
            status="verified", amount=Decimal("21000.00"), taxable_amount=Decimal("20000.00"),
            cgst=Decimal("500.00"), sgst=Decimal("500.00"), customer="Walk-in Customer (Unregistered)",
            gstin="", invoice_number="ABC/26-27/003", invoice_date="2026-07-20",
        ),
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="credit_note",
            status="verified", amount=Decimal("23600.00"), taxable_amount=Decimal("20000.00"),
            cgst=Decimal("1800.00"), sgst=Decimal("1800.00"), customer="Mehta Enterprises",
            gstin="27AAAPM5678B1Z2", invoice_number="ABC/CN/26-27/001", invoice_date="2026-08-10",
            ocr_text="Against Invoice ABC/26-27/001 dt 05-Jul-2026",
        ),
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="debit_note",
            status="verified", amount=Decimal("11800.00"), taxable_amount=Decimal("10000.00"),
            igst=Decimal("1800.00"), customer="Kannan Software LLP",
            gstin="29AABCK4321C1Z8", invoice_number="ABC/DN/26-27/001", invoice_date="2026-08-15",
            ocr_text="Against Invoice ABC/26-27/002 dt 12-Jul-2026",
        ),
    ]

    # Additional Scenario B documents
    docs_b = [
        # S4 B2C inter GJ, unregistered: 10,000 / IGST 1,800 / 11,800
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="b2c_invoice",
            status="verified", amount=Decimal("11800.00"), taxable_amount=Decimal("10000.00"),
            igst=Decimal("1800.00"), customer="Gujarat Customer",
            gstin="", invoice_number="ABC/26-27/004", invoice_date="2026-07-25",
            metadata_='{"fields": {"place_of_supply": {"value": "24"}}}',
        ),
        # S5 B2C Large inter GJ (> 1,00,000): 300,000 / IGST 54,000 / 354,000
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="b2c_invoice",
            status="verified", amount=Decimal("354000.00"), taxable_amount=Decimal("300000.00"),
            igst=Decimal("54000.00"), customer="Large Retail Buyer",
            gstin="", invoice_number="ABC/26-27/005", invoice_date="2026-07-30",
            metadata_='{"fields": {"place_of_supply": {"value": "24"}}}',
        ),
        # P1 purchase intra: 100,000 / CGST 9,000 + SGST 9,000 / 118,000
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="purchase_records",
            status="verified", amount=Decimal("118000.00"), taxable_amount=Decimal("100000.00"),
            cgst=Decimal("9000.00"), sgst=Decimal("9000.00"), vendor="Pune Compu Traders",
            gstin="27AABCP9876D1Z4", invoice_number="PCT/2026/0456", invoice_date="2026-07-03",
        ),
        # P2 purchase inter: 50,000 / IGST 9,000 / 59,000
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="purchase_records",
            status="verified", amount=Decimal("59000.00"), taxable_amount=Decimal("50000.00"),
            igst=Decimal("9000.00"), vendor="TN Raw Materials",
            gstin="33AABCT1111E1Z6", invoice_number="TNRM/INV/0912", invoice_date="2026-07-08",
        ),
        # PDN1 debit note issued by client against P2 (purchase return): 10,000 / IGST 1,800 / 11,800
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="debit_note",
            status="verified", amount=Decimal("11800.00"), taxable_amount=Decimal("10000.00"),
            igst=Decimal("1800.00"), vendor="TN Raw Materials",
            gstin="33AABCT1111E1Z6", invoice_number="ABC/PDN/26-27/001", invoice_date="2026-08-12",
            ocr_text="Against Invoice TNRM/INV/0912 dt 08-Jul-2026",
        ),
        # PCN1 credit note received from Pune Compu Traders against P1: 5,000 / CGST 450 + SGST 450 / 5,900
        UploadedDocument(
            id=uuid.uuid4(), client_id=client.id, document_category="credit_note",
            status="verified", amount=Decimal("5900.00"), taxable_amount=Decimal("5000.00"),
            cgst=Decimal("450.00"), sgst=Decimal("450.00"), vendor="Pune Compu Traders",
            gstin="27AABCP9876D1Z4", invoice_number="PCT/CN/2026/009", invoice_date="2026-08-20",
            ocr_text="Against Invoice PCT/2026/0456 dt 03-Jul-2026",
        ),
    ]

    all_docs = docs_a + docs_b
    pipe_db.add_all(all_docs)
    pipe_db.commit()

    for doc in all_docs:
        d_res = AccountingDraftService.generate_or_update_draft(pipe_db, doc.id)
        assert d_res.status in ("created", "updated")
        assert d_res.record is not None
        res = AccountingDraftService.post_draft_to_ledger(pipe_db, d_res.record.id, user)
        assert res.success is True

    gstr1 = GstReconciliationService.reconcile_gstr1(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
    gstr2b = GstReconciliationService.reconcile_gstr2b(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
    gstr3b = GstReconciliationService.generate_gstr3b(pipe_db, client.id, user, from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))

    # Output assertions
    assert gstr1.total_outward_cgst == Decimal("7700.00")
    assert gstr1.total_outward_sgst == Decimal("7700.00")
    assert gstr1.total_outward_igst == Decimal("93600.00")
    assert gstr1.total_outward_tax == Decimal("109000.00")
    assert gstr1.total_outward_taxable == Decimal("620000.00")

    # Input ITC assertions
    assert gstr2b.eligible_itc_cgst == Decimal("8550.00")
    assert gstr2b.eligible_itc_sgst == Decimal("8550.00")
    assert gstr2b.eligible_itc_igst == Decimal("7200.00")
    assert gstr2b.total_eligible_itc == Decimal("24300.00")

    # Inward register must contain P1, P2, PDN1, PCN1. CN1 and DN1 must NOT appear.
    inv_nums = {inv.invoice_number for inv in gstr2b.invoices}
    assert "PCT/2026/0456" in inv_nums
    assert "TNRM/INV/0912" in inv_nums
    assert "ABC/CN/26-27/001" not in inv_nums
    assert "ABC/DN/26-27/001" not in inv_nums

    # Statutory Set-off & Cash Payable
    assert gstr3b.tax_payable_in_cash == Decimal("84700.00")
    assert gstr3b.excess_credit_carried_forward == Decimal("0.00")


# ── Negative Tests ────────────────────────────────────────────────────────────

def test_negative_n1_total_mismatch(pipe_db, pipe_client):
    """N1: printed total 119,000 vs components 118,000 -> TOTAL_MISMATCH."""
    client = pipe_client["client"]
    user = pipe_client["user"]

    doc_n1 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="purchase_records",
        status="verified", amount=Decimal("119000.00"), taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"), sgst=Decimal("9000.00"), vendor="Pune Compu Traders",
        gstin="27AABCP9876D1Z4", invoice_number="NEG/0001", invoice_date="2026-07-06",
    )
    pipe_db.add(doc_n1)
    pipe_db.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(pipe_db, doc_n1, user)
    assert "TOTAL_MISMATCH" in str(exc.value) or "differs from printed total" in str(exc.value).lower()


def test_negative_n2_tax_type_mismatch(pipe_db, pipe_client):
    """N2: both parties in MH (27) but IGST charged -> TAX_TYPE_MISMATCH."""
    client = pipe_client["client"]
    user = pipe_client["user"]

    doc_n2 = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="purchase_records",
        status="verified", amount=Decimal("118000.00"), taxable_amount=Decimal("100000.00"),
        igst=Decimal("18000.00"), cgst=Decimal("0.00"), sgst=Decimal("0.00"), vendor="Pune Compu Traders",
        gstin="27AABCP9876D1Z4", invoice_number="NEG/0002", invoice_date="2026-07-07",
    )
    pipe_db.add(doc_n2)
    pipe_db.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(pipe_db, doc_n2, user)
    assert "TAX_TYPE_MISMATCH" in str(exc.value) or "intra-state supply" in str(exc.value).lower()


def test_negative_client_mismatch(pipe_db, pipe_client):
    """Document where neither GSTIN matches client's GSTIN -> CLIENT_MISMATCH."""
    client = pipe_client["client"]  # 27AABCA1234A1Z5
    user = pipe_client["user"]

    doc_foreign = UploadedDocument(
        id=uuid.uuid4(), client_id=client.id, document_category="b2b_invoice",
        status="verified", amount=Decimal("118000.00"), taxable_amount=Decimal("100000.00"),
        cgst=Decimal("9000.00"), sgst=Decimal("9000.00"),
        gstin="27XYZAB9999R1Z1", customer="Third Party Ltd",
        metadata_='{"fields": {"supplier_gstin": {"value": "27OTHER1111F1Z1"}, "customer_gstin": {"value": "27OTHER2222F1Z2"}}}',
    )
    pipe_db.add(doc_foreign)
    pipe_db.commit()

    with pytest.raises(BadRequestException) as exc:
        AccountingMappingService.map_document_to_journal_entry(pipe_db, doc_foreign, user)
    assert "CLIENT_MISMATCH" in str(exc.value) or "does not belong to this client" in str(exc.value).lower()
