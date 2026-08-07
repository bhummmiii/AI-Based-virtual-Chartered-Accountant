"""
Document Validation Service
============================
Provides:
  - GSTIN format validation (format-only; not government-verified)
  - Amount consistency check (taxable + taxes ≈ total, intra vs inter-state)
  - Date normalisation helpers
  - Duplicate document detection before save
"""

import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
# Allow ₹2 rounding tolerance for amount checks
ROUNDING_TOLERANCE = Decimal("2.00")


# ---------------------------------------------------------------------------
# GSTIN Validation
# ---------------------------------------------------------------------------

def validate_gstin(gstin: Optional[str]) -> Dict[str, Any]:
    """
    Returns:
      {"valid": True|False|None, "normalized": str|None,
       "message": str, "government_verified": False}
    None means "not provided" — not an error for B2C invoices.
    """
    if not gstin or not str(gstin).strip():
        return {
            "valid": None,
            "normalized": None,
            "message": "Not provided",
            "government_verified": False,
        }
    # Strip spaces, hyphens, special chars that OCR might introduce
    normalized = re.sub(r"[^A-Z0-9]", "", str(gstin).strip().upper())
    if GSTIN_RE.match(normalized):
        return {
            "valid": True,
            "normalized": normalized,
            "message": "Format valid — not government-verified",
            "government_verified": False,
        }
    # Common OCR confusions: 0/O, 1/I, 5/S, 8/B
    corrected = (
        normalized
        .replace("O", "0", 2)  # first 2 chars are state code digits
    )
    if GSTIN_RE.match(corrected):
        return {
            "valid": True,
            "normalized": corrected,
            "message": "OCR correction applied (O→0); please verify — not government-verified",
            "government_verified": False,
        }
    return {
        "valid": False,
        "normalized": None,
        "message": f"Invalid GSTIN format: '{gstin}'. Expected: 27AABCN1234R1Z5",
        "government_verified": False,
    }


# ---------------------------------------------------------------------------
# Amount Validation
# ---------------------------------------------------------------------------

def _dec(v: Any) -> Optional[Decimal]:
    if v is None or str(v).strip() in ("", "None"):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def validate_amounts(fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check: taxable_amount + relevant_taxes ≈ total_amount.

    Intra-state: CGST + SGST used (IGST should be 0)
    Inter-state: IGST used (CGST + SGST should be 0)
    Cess: always added separately.

    Returns:
      {"ok": True|False|None, "supply_type": str, "discrepancy": float|None,
       "calculated": float|None, "declared": float|None, "message": str,
       "needs_review": bool}
    """
    taxable = _dec(fields.get("taxable_amount"))
    cgst = _dec(fields.get("cgst")) or Decimal("0")
    sgst = _dec(fields.get("sgst")) or Decimal("0")
    igst = _dec(fields.get("igst")) or Decimal("0")
    cess = _dec(fields.get("cess")) or Decimal("0")
    total = _dec(fields.get("amount"))

    if taxable is None or total is None:
        return {
            "ok": None,
            "supply_type": "unknown",
            "discrepancy": None,
            "calculated": None,
            "declared": None,
            "message": "Taxable amount or total not available — cannot verify",
            "needs_review": False,
        }

    # Determine supply type
    if igst > 0 and cgst == 0 and sgst == 0:
        supply_type = "inter_state"
        tax_sum = igst + cess
    elif igst == 0 and (cgst > 0 or sgst > 0):
        supply_type = "intra_state"
        tax_sum = cgst + sgst + cess
    elif igst > 0 and (cgst > 0 or sgst > 0):
        supply_type = "mixed_warning"
        tax_sum = cgst + sgst + igst + cess
    else:
        supply_type = "unknown"
        tax_sum = cgst + sgst + igst + cess

    calculated = taxable + tax_sum
    discrepancy = abs(calculated - total)

    if discrepancy <= ROUNDING_TOLERANCE:
        return {
            "ok": True,
            "supply_type": supply_type,
            "discrepancy": float(discrepancy),
            "calculated": float(calculated),
            "declared": float(total),
            "message": f"Amount check passed (diff: ₹{discrepancy:.2f})",
            "needs_review": supply_type == "mixed_warning",
        }
    return {
        "ok": False,
        "supply_type": supply_type,
        "discrepancy": float(discrepancy),
        "calculated": float(calculated),
        "declared": float(total),
        "message": (
            f"Amount mismatch: calculated ₹{calculated:.2f} "
            f"vs declared ₹{total:.2f} — difference ₹{discrepancy:.2f}"
        ),
        "needs_review": True,
    }


# ---------------------------------------------------------------------------
# Duplicate Detection
# ---------------------------------------------------------------------------

def detect_duplicate(
    db,
    client_id: Any,
    document_category: str,
    invoice_number: Optional[str] = None,
    notice_number: Optional[str] = None,
    arn: Optional[str] = None,
    gstin: Optional[str] = None,
    invoice_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check if a likely duplicate already exists for this client.
    Returns a dict with the duplicate's info, or None if no duplicate found.

    Checks (in order of specificity):
      1. Same client + category + invoice_number  (invoices, notes)
      2. Same client + category + notice_number   (GST notices, challans)
      3. Same client + category + ARN             (GST returns)
    """
    from app.models.uploaded_document import UploadedDocument

    def _fmt_result(doc) -> Dict[str, Any]:
        return {
            "id": str(doc.id),
            "invoice_number": doc.invoice_number,
            "notice_number": doc.notice_number,
            "arn": doc.arn,
            "invoice_date": doc.invoice_date,
            "status": doc.status,
            "uploaded_at": str(doc.uploaded_at),
        }

    base_q = db.query(UploadedDocument).filter(
        UploadedDocument.client_id == client_id,
        UploadedDocument.document_category == document_category,
    )

    # 1. Invoice number match
    if invoice_number and invoice_number.strip():
        doc = base_q.filter(
            UploadedDocument.invoice_number == invoice_number.strip()
        ).first()
        if doc:
            logger.info(
                "Duplicate detected: client=%s cat=%s inv=%s",
                client_id,
                document_category,
                invoice_number,
            )
            return _fmt_result(doc)

    # 2. Notice number match
    if notice_number and notice_number.strip():
        doc = base_q.filter(
            UploadedDocument.notice_number == notice_number.strip()
        ).first()
        if doc:
            return _fmt_result(doc)

    # 3. ARN match (GST returns)
    if arn and arn.strip():
        doc = base_q.filter(UploadedDocument.arn == arn.strip()).first()
        if doc:
            return _fmt_result(doc)

    return None
