import sys
import os
import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.invoice_router import _parse_decimal_safe, update_document
from app.models.uploaded_document import UploadedDocument
from app.models.user import User
from app.schemas.uploaded_document import DocumentUpdateRequest


def test_parse_decimal_safe():
    assert _parse_decimal_safe("1250.50") == Decimal("1250.50")
    assert _parse_decimal_safe("₹1,250.50") == Decimal("1250.50")
    assert _parse_decimal_safe("Rs. 50,000") == Decimal("50000")
    assert _parse_decimal_safe("$99.99") == Decimal("99.99")
    assert _parse_decimal_safe("  ") is None
    assert _parse_decimal_safe("None") is None
    assert _parse_decimal_safe("—") is None
    assert _parse_decimal_safe("invalid") is None


from datetime import datetime, timezone

def test_update_document_logic():
    doc_id = uuid.uuid4()
    client_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    mock_doc = UploadedDocument(
        id=doc_id,
        client_id=client_id,
        document_category="purchase_records",
        document_type="scan",
        invoice_number="OLD_INV_123",
        vendor="Old Vendor",
        amount=Decimal("100.00"),
        taxable_amount=None,
        cgst=None,
        sgst=None,
        uploaded_at=now,
        created_at=now,
        updated_at=now,
        metadata_=json.dumps({
            "fields": {
                "invoice_number": "OLD_INV_123",
                "vendor": "Old Vendor",
                "amount": "100.00"
            }
        })
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_doc
    mock_user = User(email="ca@example.com", role="ca")

    # Update invoice number, fix amount, and add missing taxable_amount & cgst
    payload = DocumentUpdateRequest(
        fields={
            "invoice_number": "NEW_INV_999",
            "amount": "₹ 1,500.00",
            "taxable_amount": "1271.18",
            "cgst": "114.41",
            "place_of_supply": "27-Maharashtra",
            "vendor": "Updated Vendor Ltd",
        }
    )

    resp = update_document(
        doc_id=doc_id,
        payload=payload,
        db=mock_db,
        current_user=mock_user,
    )

    assert resp.data.invoice_number == "NEW_INV_999"
    assert resp.data.amount == Decimal("1500.00")
    assert resp.data.taxable_amount == Decimal("1271.18")
    assert resp.data.cgst == Decimal("114.41")
    assert resp.data.vendor == "Updated Vendor Ltd"

    # Verify metadata_ has place_of_supply and all updated fields
    meta = json.loads(mock_doc.metadata_)
    assert meta["fields"]["place_of_supply"] == "27-Maharashtra"
    assert meta["fields"]["invoice_number"] == "NEW_INV_999"
    assert meta["fields"]["amount"] == "₹ 1,500.00"

    mock_db.commit.assert_called_once()
