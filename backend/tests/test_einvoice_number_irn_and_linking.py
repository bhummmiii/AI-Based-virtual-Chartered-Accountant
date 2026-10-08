"""
Test F5: E-Invoice & E-Way Bill Numbering, IRN, and Linking.
Verifies:
1. OCR parses printed Document No into invoice_number and 64-char hex string into irn.
2. Auto-linking links strictly by printed document number and direction (never cross-number).
3. Candidate without matching document number is left unlinked.
4. E-invoice linked to a posted commercial invoice never raises UNPOSTED_INVOICE.
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
from app.models.journal_entry import JournalEntry
from app.api.routers.ocr.router import _parse_e_invoice, _parse_e_way_bill
from app.services.gst_reconciliation_service import GstReconciliationService
from scripts.relink_compliance_docs import relink_for_client


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_ocr_parse_einvoice_doc_no_and_irn():
    sample_einvoice_text = """
    e-INVOICE
    Tax Invoice under Rule 48(4) of CGST Rules
    IRN:
    3025278422a1084f9e226a33d0527b65
    662e4c0a3c1d0b8a087f7d506021f2a4
    Ack No: 132610123456789
    Ack Date: 12-Jul-2026 10:32:00
    Supply Type: B2B   Doc Type: INV
    Supplier: ABC Traders Pvt Ltd
    GSTIN: 27AABCA1234A1Z5
    Recipient: Kannan Software LLP
    GSTIN: 29AABCK4321C1Z8
    Document No: ABC/26-27/002
    Document Date: 12-Jul-2026
    Total Taxable Value: 2,00,000.00
    IGST @ 18%: 36,000.00
    Invoice Total (INR): 2,36,000.00
    """
    core, meta = _parse_e_invoice(sample_einvoice_text)
    assert core.get("invoice_number", {}).get("value") == "ABC/26-27/002"
    assert core.get("irn", {}).get("value") == "3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4"


def test_autolink_compliance_docs_by_number_and_direction(db_session):
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client = Client(
        id=client_id,
        user_id=user_id,
        client_code="CLI-F5-1",
        company_name="ABC Traders Pvt Ltd",
        gst_number="27AABCA1234A1Z5",
        state="Maharashtra",
        return_frequency="Quarterly",
        contact_person="Admin",
    )
    user = User(id=user_id, email="ca@f5.com", full_name="CA F5 User", password_hash="hash", role="admin")
    db_session.add_all([client, user])
    db_session.commit()

    # Commercial Invoices:
    # S1 (ABC/26-27/001 - Outward Sales, amount 118,000)
    s1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="sales_records",
        invoice_number="ABC/26-27/001",
        gstin="27AABCA1234A1Z5",
        amount=Decimal("118000.00"),
        status="verified",
    )
    # S2 (ABC/26-27/002 - Outward Sales, amount 236,000)
    s2 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="sales_records",
        invoice_number="ABC/26-27/002",
        gstin="27AABCA1234A1Z5",
        amount=Decimal("236000.00"),
        status="verified",
    )
    # P1 (PCT/2026/0456 - Inward Purchase, also amount 118,000)
    p1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="purchase_records",
        invoice_number="PCT/2026/0456",
        gstin="27AABCP9876D1Z4",
        amount=Decimal("118000.00"),
        status="verified",
    )

    # Compliance Docs:
    # EWB1 (printed Doc No ABC/26-27/001, outward, amount 118,000)
    ewb1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="e_way_bill",
        invoice_number="381012345678",
        gstin="27AABCA1234A1Z5",
        amount=Decimal("118000.00"),
        ocr_text="e-WAY BILL Document No: ABC/26-27/001 Supply Type: Outward Total Invoice Value: 1,18,000.00",
        status="verified",
    )

    # E1 (printed Doc No ABC/26-27/002, outward, amount 236,000, initial invoice_number is IRN)
    e1 = UploadedDocument(
        id=uuid.uuid4(),
        client_id=client_id,
        document_category="e_invoice",
        invoice_number="3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4",
        gstin="27AABCA1234A1Z5",
        amount=Decimal("236000.00"),
        taxable_amount=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        ocr_text="""IRN:
        3025278422a1084f9e226a33d0527b65
        662e4c0a3c1d0b8a087f7d506021f2a4
        Document No: ABC/26-27/002
        Total Taxable Value: 2,00,000.00
        IGST @ 18%: 36,000.00
        Invoice Total: 2,36,000.00""",
        status="verified",
    )

    # Posted voucher for S2
    je_s2 = JournalEntry(
        id=uuid.uuid4(),
        client_id=client_id,
        document_id=s2.id,
        entry_number="SV-2026-0002",
        entry_date=date(2026, 7, 12),
        entry_type="sales",
        status="posted",
        is_reversed=False,
    )

    db_session.add_all([s1, s2, p1, ewb1, e1, je_s2])
    db_session.commit()

    # Run relinking script in apply mode
    relink_for_client(db_session, client, apply=True)

    db_session.refresh(ewb1)
    db_session.refresh(e1)

    # EWB1 MUST link to S1 (ABC/26-27/001), NEVER to P1 (even though amounts are identical 118,000)
    assert ewb1.linked_document_id == s1.id

    # E1 MUST link to S2 (ABC/26-27/002)
    assert e1.linked_document_id == s2.id
    assert e1.invoice_number == "ABC/26-27/002"
    assert e1.irn == "3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4"

    # E1 companion S2 is posted -> E1 must NOT raise UNPOSTED_INVOICE
    res = GstReconciliationService.detect_discrepancies(db_session, client_id, user, period="2026-Q2")
    unposted = [d for d in res.discrepancies if d.rule_code == "UNPOSTED_INVOICE" and d.document_id == e1.id]
    assert len(unposted) == 0
