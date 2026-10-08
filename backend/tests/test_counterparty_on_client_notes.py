"""
Test F2: Counterparty on Client-Issued Notes and SELF_PARTY Validation.
Verifies:
1. For every document, counterparty is the side whose GSTIN is NOT the client's.
2. PDN1 shows TN Raw Materials Ltd / 33AABCT1111E1Z6 in voucher header, creditor line, and purchase register.
3. Validation SELF_PARTY: counterparty GSTIN equal to client's own GSTIN raises BadRequestException.
"""

import uuid
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.gst_reconciliation_service import GstReconciliationService
from app.core.exceptions import BadRequestException


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_client_issued_debit_note_counterparty_and_purchase_register(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-F2",
        company_name="ABC Traders Pvt Ltd",
        gst_number="27AABCA1234A1Z5",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@f2.com", full_name="CA F2 User", password_hash="hashed_pw", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Accounts
    creditor_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2010", account_name="Sundry Creditors", account_type="liability", role="CREDITORS")
    pur_ret_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="5020", account_name="Purchase Return", account_type="expense", role="PURCHASE_RETURN")
    igst_in_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1230", account_name="Input IGST", account_type="asset", role="INPUT_IGST")
    pur_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="5010", account_name="Purchase Account", account_type="expense", role="PURCHASE")
    cgst_in_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1210", account_name="Input CGST", account_type="asset", role="INPUT_CGST")
    sgst_in_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1220", account_name="Input SGST", account_type="asset", role="INPUT_SGST")

    db_session.add_all([creditor_acc, pur_ret_acc, igst_in_acc, pur_acc, cgst_in_acc, sgst_in_acc])
    db_session.commit()

    # Client-issued debit note PDN1 (Issuer = ABC Traders, Recipient = TN Raw Materials Ltd)
    pdn_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="debit_note",
        file_name="PDN1.pdf",
        invoice_number="ABC/PDN/26-27/001",
        invoice_date="2026-08-12",
        amount=Decimal("11800.00"),
        taxable_amount=Decimal("10000.00"),
        igst=Decimal("1800.00"),
        vendor="ABC Traders Pvt Ltd",
        customer="TN Raw Materials Ltd",
        gstin="27AABCA1234A1Z5",
        status="verified",
        metadata_='{"fields": {"customer_gstin": "33AABCT1111E1Z6", "customer": "TN Raw Materials Ltd", "supplier_gstin": "27AABCA1234A1Z5"}}',
    )
    db_session.add(pdn_doc)
    db_session.commit()

    # 1. Map document to journal entry
    je_payload = AccountingMappingService.map_document_to_journal_entry(db_session, pdn_doc, user)

    assert je_payload.counterparty_name == "TN Raw Materials Ltd"
    assert je_payload.counterparty_gstin == "33AABCT1111E1Z6"
    assert je_payload.voucher_template == "T6"

    # Check creditor line party
    cred_line = next(l for l in je_payload.lines if l.account_id == creditor_acc.id)
    assert cred_line.party_name == "TN Raw Materials Ltd"
    assert cred_line.party_gstin == "33AABCT1111E1Z6"

    # 2. Post voucher
    repost_je = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=pdn_doc.id,
        entry_number="JV-2026-0002-CORR",
        entry_date=date(2026, 8, 12),
        entry_type="journal",
        status="posted",
        total_debit=Decimal("11800.00"),
        total_credit=Decimal("11800.00"),
        counterparty_name="TN Raw Materials Ltd",
        counterparty_gstin="33AABCT1111E1Z6",
        voucher_template="T6",
    )
    db_session.add(repost_je)
    db_session.flush()

    line1 = JournalEntryLine(journal_entry_id=repost_je.id, line_number=1, account_id=creditor_acc.id, debit_amount=Decimal("11800.00"), credit_amount=Decimal("0.00"), party_name="TN Raw Materials Ltd", party_gstin="33AABCT1111E1Z6")
    line2 = JournalEntryLine(journal_entry_id=repost_je.id, line_number=2, account_id=pur_ret_acc.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("10000.00"))
    line3 = JournalEntryLine(journal_entry_id=repost_je.id, line_number=3, account_id=igst_in_acc.id, debit_amount=Decimal("0.00"), credit_amount=Decimal("1800.00"), tax_head="igst", tax_rate=Decimal("18.00"))
    db_session.add_all([line1, line2, line3])
    db_session.commit()

    # 3. Check purchase register
    gstr2b = GstReconciliationService.reconcile_gstr2b(db_session, client_id, user, period="2026-Q2")
    pdn_row = next(r for r in gstr2b.invoices if r.invoice_number == "ABC/PDN/26-27/001")
    assert pdn_row.party_name == "TN Raw Materials Ltd"
    assert pdn_row.party_gstin == "33AABCT1111E1Z6"
    assert pdn_row.taxable_amount == Decimal("-10000.00")
    assert pdn_row.igst == Decimal("-1800.00")


def test_self_party_validation_blocks_posting(db_session):
    client_id = uuid.uuid4()
    client = Client(
        id=client_id,
        client_code="CLI-SELF",
        company_name="Self Party Corp",
        gst_number="27AABCS9999A1Z1",
        return_frequency="Monthly",
        contact_person="Admin",
    )
    user = User(id=uuid.uuid4(), email="ca@self.com", full_name="CA Self User", password_hash="hashed_pw", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Accounts
    sales_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="4010", account_name="Sales", account_type="income", role="SALES")
    debtor_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="1100", account_name="Debtors", account_type="asset", role="DEBTORS")
    cgst_out_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2110", account_name="Output CGST", account_type="liability", role="OUTPUT_CGST")
    sgst_out_acc = ChartOfAccounts(id=uuid.uuid4(), client_id=client_id, account_code="2120", account_name="Output SGST", account_type="liability", role="OUTPUT_SGST")
    db_session.add_all([sales_acc, debtor_acc, cgst_out_acc, sgst_out_acc])
    db_session.commit()

    # Document where customer GSTIN is accidentally equal to client's own GSTIN
    self_doc = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="b2b_invoice",
        invoice_number="INV-SELF-001",
        invoice_date="2026-08-10",
        amount=Decimal("118.00"),
        taxable_amount=Decimal("100.00"),
        cgst=Decimal("9.00"),
        sgst=Decimal("9.00"),
        vendor="Self Party Corp",
        customer="Self Party Corp Branch",
        status="verified",
        metadata_='{"fields": {"customer_gstin": "27AABCS9999A1Z1", "supplier_gstin": "27AABCS9999A1Z1"}}',
    )
    db_session.add(self_doc)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc_info:
        AccountingMappingService.map_document_to_journal_entry(db_session, self_doc, user, allow_client_mismatch=True)

    assert "SELF_PARTY" in str(exc_info.value.detail)
