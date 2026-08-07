"""
OCR API Router
==============
POST /api/v1/ocr/extract

Accepts any image or PDF.
Runs Tesseract OCR (multi-PSM, LSTM, with image pre-processing).
Dispatches to one of 13 category-specific parsers.
Each field is returned with a confidence tag:
  "extracted"    — found and looks valid
  "needs_review" — found but OCR may have errors, or validation failed
  "missing"      — not detected in the document

Response also includes:
  validation.gstin    — GSTIN format check result
  validation.amounts  — amount math consistency check
  validation.warnings — list of human-readable warnings
  metadata_fields     — category-specific fields that go to metadata_ JSON column
"""

import io
import re
import os
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from app.services.document_validator import validate_gstin, validate_amounts

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Tesseract path (Windows)
# ---------------------------------------------------------------------------

_TESSERACT_WINDOWS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    import pytesseract

    if os.name == "nt" and os.path.isfile(_TESSERACT_WINDOWS_PATH):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WINDOWS_PATH
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Shared regex constants
# ---------------------------------------------------------------------------

GSTIN_RE = re.compile(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)?\s*([0-9]{1,3}(?:,\s*[0-9]{2,3})*(?:\.[0-9]{1,2})?)")
DATE_RE = re.compile(
    r"""
    (?:
        \b(\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})\b       # DD-MM-YYYY variants
        | \b(\d{4}-\d{2}-\d{2})\b                       # ISO
        | \b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Field confidence helpers
# ---------------------------------------------------------------------------

def _field(value: str, confidence: str = "extracted") -> Dict[str, str]:
    """Create a field object with value and confidence tag."""
    if not value or not str(value).strip():
        return {"value": "", "confidence": "missing"}
    return {"value": str(value).strip(), "confidence": confidence}


def _missing() -> Dict[str, str]:
    return {"value": "", "confidence": "missing"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find(patterns, text: str, flags=re.IGNORECASE) -> str:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return _clean(m.group(1))
    return ""


def _find_amount(patterns, text: str) -> str:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "").strip()
            try:
                return f"{float(raw):.2f}"
            except ValueError:
                pass
    return ""


def _conf_gstin(value: str) -> str:
    if not value:
        return "missing"
    if GSTIN_RE.match(value):
        return "extracted"
    return "needs_review"


def _conf_amount(value: str) -> str:
    if not value:
        return "missing"
    try:
        float(value.replace(",", ""))
        return "extracted"
    except ValueError:
        return "needs_review"


def _conf_text(value: str, min_len: int = 3) -> str:
    if not value or not value.strip():
        return "missing"
    return "extracted" if len(value.strip()) >= min_len else "needs_review"


def _field_gstin(raw_text: str) -> Dict[str, str]:
    m = GSTIN_RE.search(raw_text)
    if m:
        v = m.group(1)
        return _field(v, _conf_gstin(v))
    return _missing()


def _field_amount(patterns, text: str) -> Dict[str, str]:
    v = _find_amount(patterns, text)
    return _field(v, _conf_amount(v)) if v else _missing()


def _field_date(patterns, text: str) -> Dict[str, str]:
    v = _find(patterns, text)
    if not v:
        # Try generic date regex
        m = DATE_RE.search(text)
        if m:
            v = _clean(next(g for g in m.groups() if g))
    return _field(v, "extracted") if v else _missing()


def _normalise_date(v: str) -> str:
    """Try to normalise a date string to YYYY-MM-DD."""
    from datetime import datetime
    for fmt in (
        "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m-%d-%Y", "%m/%d/%Y",
        "%Y-%m-%d", "%d %B %Y", "%d %b %Y",
    ):
        try:
            clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", v)
            return datetime.strptime(clean.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return v


# ---------------------------------------------------------------------------
# Image OCR (multi-PSM + pre-processing)
# ---------------------------------------------------------------------------

_PSM_MODES = [6, 11, 3, 13]


def _preprocess(img):
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        img = ImageOps.autocontrast(img, cutoff=1)
        img = img.filter(ImageFilter.SHARPEN)
        return img
    except Exception:
        return img


def _ocr_image(content: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OCR engine not installed. Install pytesseract + Tesseract-OCR.",
        )
    try:
        raw_img = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    images = [raw_img, _preprocess(raw_img)]
    best = ""
    for img in images:
        for psm in _PSM_MODES:
            try:
                text = pytesseract.image_to_string(
                    img, lang="eng", config=f"--oem 1 --psm {psm}"
                ).strip()
                if len(text) > len(best):
                    best = text
                if len(best) > 100:
                    break
            except Exception as e:
                logger.debug("OCR psm=%d failed: %s", psm, e)
        if len(best) > 100:
            break
    return best


def _ocr_pdf(content: bytes) -> str:
    parts = []
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        combined = "\n".join(parts).strip()
        if combined:
            return combined
    except ImportError:
        pass
    except Exception as e:
        logger.warning("pypdf error: %s", e)

    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            parts.append(_ocr_image(pix.tobytes("png")))
        return "\n".join(parts)
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF library not installed. Install pypdf or PyMuPDF.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF OCR failed: {e}")


def _is_meaningful(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return False
    return len(re.findall(r"[A-Za-z]{3,}", text)) >= 3


# ---------------------------------------------------------------------------
# Category-specific parsers
# Each returns:
#   core_fields: dict[str, {"value": str, "confidence": str}]
#   metadata_fields: dict[str, {"value": str, "confidence": str}]
# ---------------------------------------------------------------------------

def _parse_invoice(t: str) -> tuple:
    """
    Shared parser for: sales_records, purchase_records, b2b_invoice.
    """
    inv_no = _find([
        r"invoice\s*(?:no|number|num|#|:)[:\s.#]*([A-Z0-9][\w\-/]{2,})",
        r"bill\s*(?:no|number|#|:)[:\s.#]*([A-Z0-9][\w\-/]{2,})",
        r"(?:INV|BILL|TAX\s*INV)\s*[-/]?\s*([A-Z0-9]{4,})",
        r"(?:Inv\.?\s*No\.?|Invoice\s*#)\s*[:\-]?\s*([A-Z0-9][\w\-/]{2,})",
    ], t)

    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)

    vendor = _find([
        r"(?:from|sold\s+by|vendor|supplier|billed\s+from|party\s+name|firm\s+name)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"^([A-Z][A-Za-z0-9 &.,()-]{3,60}(?:Pvt\.?\s*Ltd|Ltd|LLP|Inc|Corp|Co|Enterprises|Trading)\.?)",
    ], t, re.MULTILINE)

    customer = _find([
        r"(?:to|bill\s+to|ship\s+to|customer|buyer|consignee)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"(?:M/s\.?\s*)([A-Za-z0-9 &.,()-]{3,60})",
    ], t)

    date_raw = _find([
        r"(?:invoice\s+date|bill\s+date|dt\.?|date)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|\d{4}-\d{2}-\d{2})",
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    ], t)
    date_norm = _normalise_date(date_raw) if date_raw else ""

    amount = _find_amount([
        r"(?:grand\s+total|total\s+amount|total\s+due|net\s+total|amount\s+due|total)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:₹|Rs\.?)\s*([0-9,]{4,}\.?[0-9]{0,2})",
    ], t)
    taxable = _find_amount([
        r"(?:taxable\s+(?:value|amount)|assessable\s+value|basic\s+amount)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:sub\s*total|subtotal)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
    ], t)
    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    cess = _find_amount([r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    hsn = _find([r"H\.?S\.?N\.?[/\s]*(?:SAC)?[:\s]*([0-9]{4,8})", r"SAC[:\s]*([0-9]{4,8})"], t)

    core = {
        "invoice_number": _field(inv_no, _conf_text(inv_no, 3)),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(vendor, _conf_text(vendor, 3)),
        "customer": _field(customer, _conf_text(customer, 3)),
        "invoice_date": _field(date_norm, "extracted") if date_norm else _missing(),
        "amount": _field(amount, _conf_amount(amount)),
        "taxable_amount": _field(taxable, _conf_amount(taxable)),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _field(hsn, _conf_text(hsn, 4)),
    }

    place_of_supply = _find([
        r"(?:place\s+of\s+supply|pos)[:\s]+([A-Za-z ]{3,30})",
        r"(?:state)[:\s]+([A-Za-z ]{3,20})",
    ], t)
    reverse_charge = "Yes" if re.search(r"reverse\s+charge", t, re.IGNORECASE) else ""
    irn = _find([r"\bIRN[:\s]*([A-Za-z0-9]{64})\b"], t)
    ack_no = _find([r"(?:ack(?:nowledgement)?\s*(?:no|number))[:\s]*([0-9]{15,20})"], t)

    meta = {
        "place_of_supply": _field(place_of_supply, _conf_text(place_of_supply, 3)),
        "reverse_charge": _field(reverse_charge),
        "irn": _field(irn, _conf_text(irn, 60)),
        "ack_number": _field(ack_no, _conf_text(ack_no, 14)),
    }
    return core, meta


def _parse_b2c(t: str) -> tuple:
    """B2C invoice — GSTIN not required for customer."""
    core, meta = _parse_invoice(t)
    # GSTIN missing for customer is OK in B2C — downgrade from missing to OK
    # The supplier GSTIN is still expected
    return core, meta


def _parse_credit_debit_note(t: str, doc_type: str) -> tuple:
    """Credit Note (Sales Return) or Debit Note (Purchase Return)."""
    note_no = _find([
        r"(?:credit|debit)\s*note\s*(?:no|number|#)[:\s.]*([A-Z0-9][\w\-/]{2,})",
        r"(?:CN|DN|CRN|DBN)\s*[-/]?\s*([A-Z0-9]{3,})",
        r"note\s*(?:no|number)[:\s.]*([A-Z0-9][\w\-/]{2,})",
    ], t)
    note_date = _find([
        r"(?:credit|debit)\s*note\s*date[:\s]*([\d\-/. ]+)",
        r"(?:date)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|\d{4}-\d{2}-\d{2})",
    ], t)
    if note_date:
        note_date = _normalise_date(note_date)

    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)
    vendor = _find([r"(?:supplier|seller|from|party)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    customer = _find([r"(?:buyer|customer|to|bill\s+to)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)

    amount = _find_amount([r"(?:total|net\s+amount|value)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    cess = _find_amount([r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    hsn = _find([r"H\.?S\.?N\.?[:\s]*([0-9]{4,8})"], t)

    orig_inv_no = _find([
        r"(?:original|orig\.?)\s*invoice\s*(?:no|number|#)[:\s.]*([A-Z0-9][\w\-/]{2,})",
        r"(?:against\s+invoice|ref(?:erence)?\s+invoice)[:\s.]*([A-Z0-9][\w\-/]{2,})",
    ], t)
    orig_inv_date = _find([
        r"(?:original|orig\.?)\s*invoice\s*date[:\s]*([\d\-/. ]+)",
    ], t)
    if orig_inv_date:
        orig_inv_date = _normalise_date(orig_inv_date)

    reason = _find([
        r"(?:reason|purpose)[:\s]+([A-Za-z ]{3,50})",
    ], t)

    core = {
        "invoice_number": _field(note_no, _conf_text(note_no, 3)),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(vendor, _conf_text(vendor, 3)),
        "customer": _field(customer, _conf_text(customer, 3)),
        "invoice_date": _field(note_date, "extracted") if note_date else _missing(),
        "amount": _field(amount, _conf_amount(amount)),
        "taxable_amount": _missing(),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _field(hsn, _conf_text(hsn, 4)),
    }
    meta = {
        "document_type": _field(doc_type),
        "original_invoice_number": _field(orig_inv_no, _conf_text(orig_inv_no, 3)),
        "original_invoice_date": _field(orig_inv_date, "extracted") if orig_inv_date else _missing(),
        "reason": _field(reason, _conf_text(reason, 3)),
    }
    return core, meta


def _parse_e_invoice(t: str) -> tuple:
    irn = _find([r"\bIRN[:\s]*([A-Za-z0-9]{60,})\b"], t)
    ack_no = _find([r"(?:ack(?:nowledgement)?\s*(?:no|number))[:\s]*([0-9]{10,20})"], t)
    ack_date = _find([r"(?:ack(?:nowledgement)?\s*date)[:\s]*([\d\-/. ]+)"], t)
    if ack_date:
        ack_date = _normalise_date(ack_date)

    doc_type = _find([r"\b(INV|CRN|DBN)\b"], t)
    inv_no = _find([
        r"(?:document\s*no|doc\s*no|invoice\s*no)[:\s.]*([A-Z0-9][\w\-/]{2,})",
    ], t)
    inv_date = _find([r"(?:document\s*date|invoice\s*date|doc\s*date)[:\s]*([\d\-/. ]+)"], t)
    if inv_date:
        inv_date = _normalise_date(inv_date)

    gstin_matches = re.findall(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", t)
    supplier_gstin = gstin_matches[0] if gstin_matches else ""
    recipient_gstin = gstin_matches[1] if len(gstin_matches) > 1 else ""

    amount = _find_amount([r"(?:total\s+invoice\s+value|grand\s+total|total)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    taxable = _find_amount([r"(?:taxable\s+value|assessable)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    cess = _find_amount([r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    hsn = _find([r"H\.?S\.?N\.?[:\s]*([0-9]{4,8})"], t)

    core = {
        "invoice_number": _field(inv_no, _conf_text(inv_no, 3)),
        "gstin": _field(supplier_gstin, _conf_gstin(supplier_gstin)),
        "vendor": _missing(),
        "customer": _missing(),
        "invoice_date": _field(inv_date, "extracted") if inv_date else _missing(),
        "amount": _field(amount, _conf_amount(amount)),
        "taxable_amount": _field(taxable, _conf_amount(taxable)),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _field(hsn, _conf_text(hsn, 4)),
    }
    meta = {
        "irn": _field(irn, "extracted" if len(irn) >= 60 else "needs_review"),
        "ack_number": _field(ack_no, _conf_text(ack_no, 10)),
        "ack_date": _field(ack_date, "extracted") if ack_date else _missing(),
        "document_type": _field(doc_type),
        "recipient_gstin": _field(recipient_gstin, _conf_gstin(recipient_gstin)),
    }
    return core, meta


def _parse_e_way_bill(t: str) -> tuple:
    ewb_no = _find([
        r"e-?way\s*bill\s*(?:no|number)[:\s]*([0-9]{12})",
        r"\bEWB\s*[-/]?\s*([0-9]{12})\b",
        r"\b([0-9]{12})\b",  # EWB number is always 12 digits
    ], t)
    ewb_date = _find([r"(?:e-?way\s*bill\s*date|generated\s+on)[:\s]*([\d\-/. ]+)"], t)
    if ewb_date:
        ewb_date = _normalise_date(ewb_date)
    valid_until = _find([r"(?:valid\s+(?:till|until|upto))[:\s]*([\d\-/. ]+)"], t)
    if valid_until:
        valid_until = _normalise_date(valid_until)

    supply_type = _find([r"(?:supply\s+type|transaction\s+type)[:\s]+([A-Za-z ]{3,30})"], t)
    doc_no = _find([r"(?:document\s+no|invoice\s+no)[:\s]*([A-Z0-9][\w\-/]{2,})"], t)

    gstin_matches = re.findall(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", t)
    from_gstin = gstin_matches[0] if gstin_matches else ""
    to_gstin = gstin_matches[1] if len(gstin_matches) > 1 else ""

    from_name = _find([r"(?:from|dispatch\s+from|consignor)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    to_name = _find([r"(?:to|deliver\s+to|consignee)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)

    vehicle_no = _find([
        r"(?:vehicle\s*(?:no|number))[:\s]*([A-Z]{2}\s*[0-9]{1,2}\s*[A-Z]{1,2}\s*[0-9]{4})",
        r"\b([A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4})\b",
    ], t)
    transport_mode = _find([r"(?:transport\s+mode|mode\s+of\s+transport)[:\s]+([A-Za-z ]{3,20})"], t)
    distance = _find([r"(?:distance)[:\s]*([0-9]+ *(?:km|KM)?)"], t)

    amount = _find_amount([r"(?:taxable\s+value|total\s+value)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    hsn = _find([r"H\.?S\.?N\.?[:\s]*([0-9]{4,8})"], t)

    core = {
        "invoice_number": _field(ewb_no, "extracted" if len(ewb_no) == 12 else "needs_review"),
        "gstin": _field(from_gstin, _conf_gstin(from_gstin)),
        "vendor": _field(from_name, _conf_text(from_name, 3)),
        "customer": _field(to_name, _conf_text(to_name, 3)),
        "invoice_date": _field(ewb_date, "extracted") if ewb_date else _missing(),
        "amount": _field(amount, _conf_amount(amount)),
        "taxable_amount": _missing(),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _missing(),
        "hsn": _field(hsn, _conf_text(hsn, 4)),
    }
    meta = {
        "valid_until": _field(valid_until, "extracted") if valid_until else _missing(),
        "supply_type": _field(supply_type, _conf_text(supply_type, 3)),
        "document_number": _field(doc_no, _conf_text(doc_no, 3)),
        "from_gstin": _field(from_gstin, _conf_gstin(from_gstin)),
        "to_gstin": _field(to_gstin, _conf_gstin(to_gstin)),
        "vehicle_number": _field(vehicle_no, _conf_text(vehicle_no, 6)),
        "transport_mode": _field(transport_mode, _conf_text(transport_mode, 3)),
        "distance": _field(distance, _conf_text(distance, 2)),
    }
    return core, meta


def _parse_gst_challan(t: str) -> tuple:
    cpin = _find([r"\bCPIN[:\s]*([0-9]{14,})\b"], t)
    cin = _find([r"\bCIN[:\s]*([A-Z0-9]{14,20})\b"], t)
    challan_no = cpin or cin or _find([r"challan\s*(?:no|number)[:\s]*([A-Z0-9]{6,})"], t)

    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)
    legal_name = _find([r"(?:legal\s+name|taxpayer\s+name|name\s+of\s+taxpayer)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    tax_period = _find([r"(?:tax\s+period|period)[:\s]+([A-Za-z0-9\- ]{3,20})"], t)
    payment_date = _find([r"(?:payment\s+date|date\s+of\s+payment|challan\s+date)[:\s]*([\d\-/. ]+)"], t)
    if payment_date:
        payment_date = _normalise_date(payment_date)
    bank = _find([r"(?:bank|bank\s+name|paid\s+(?:at|via))[:\s]+([A-Za-z ]{3,40})"], t)
    txn_ref = _find([r"(?:transaction\s+(?:id|ref)|UTR|BRN)[:\s]*([A-Z0-9]{8,22})"], t)

    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    cess = _find_amount([r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    interest = _find_amount([r"INTEREST[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    penalty = _find_amount([r"PENALTY[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    total = _find_amount([r"(?:total\s+amount|grand\s+total|amount\s+paid)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)

    core = {
        "invoice_number": _field(challan_no, _conf_text(challan_no, 6)),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(legal_name, _conf_text(legal_name, 3)),
        "customer": _missing(),
        "invoice_date": _field(payment_date, "extracted") if payment_date else _missing(),
        "amount": _field(total, _conf_amount(total)),
        "taxable_amount": _missing(),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _missing(),
    }
    meta = {
        "cpin": _field(cpin, "extracted" if len(cpin) >= 14 else "needs_review"),
        "cin": _field(cin, _conf_text(cin, 14)),
        "tax_period": _field(tax_period, _conf_text(tax_period, 3)),
        "bank": _field(bank, _conf_text(bank, 3)),
        "transaction_reference": _field(txn_ref, _conf_text(txn_ref, 8)),
        "interest": _field(interest, _conf_amount(interest)),
        "penalty": _field(penalty, _conf_amount(penalty)),
    }
    return core, meta


def _parse_gst_return(t: str) -> tuple:
    return_type = _find([r"\b(GSTR-[0-9A-Z]+(?:\s*Annual\s*Return)?)\b"], t)
    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)
    legal_name = _find([r"(?:legal\s+name|trade\s+name|taxpayer\s+name)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    fy = _find([r"(?:financial\s+year|FY|F\.Y\.?)[:\s]*([0-9]{4}[-–][0-9]{2,4})"], t)
    period = _find([r"(?:tax\s+period|period|month)[:\s]+([A-Za-z0-9\- ]{3,20})"], t)
    filing_date = _find([r"(?:filing\s+date|date\s+of\s+filing|filed\s+on)[:\s]*([\d\-/. ]+)"], t)
    if filing_date:
        filing_date = _normalise_date(filing_date)
    arn = _find([r"\bARN[:\s]*([A-Z0-9]{15,20})\b"], t)
    status = _find([r"(?:filing\s+status|return\s+status)[:\s]+([A-Za-z ]{3,20})"], t)

    taxable = _find_amount([r"(?:taxable\s+(?:value|turnover))[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    cgst = _find_amount([r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    sgst = _find_amount([r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    igst = _find_amount([r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    cess = _find_amount([r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)"], t)
    total_tax = _find_amount([r"(?:total\s+tax|tax\s+payable|net\s+tax)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    itc = _find_amount([r"(?:ITC|input\s+tax\s+credit)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)
    late_fee = _find_amount([r"(?:late\s+fee)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)

    core = {
        "invoice_number": _missing(),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(legal_name, _conf_text(legal_name, 3)),
        "customer": _missing(),
        "invoice_date": _field(filing_date, "extracted") if filing_date else _missing(),
        "amount": _field(total_tax, _conf_amount(total_tax)),
        "taxable_amount": _field(taxable, _conf_amount(taxable)),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _missing(),
    }
    # Also fill GST-return-specific columns
    core["gst_return_type"] = _field(return_type, _conf_text(return_type, 4))
    core["financial_year"] = _field(fy, _conf_text(fy, 6))
    core["month"] = _field(period, _conf_text(period, 3))
    core["filed_date"] = _field(filing_date, "extracted") if filing_date else _missing()
    core["arn"] = _field(arn, _conf_text(arn, 15))

    meta = {
        "status": _field(status, _conf_text(status, 3)),
        "itc_claimed": _field(itc, _conf_amount(itc)),
        "late_fee": _field(late_fee, _conf_amount(late_fee)),
    }
    return core, meta


def _parse_gst_notice(t: str) -> tuple:
    notice_no = _find([
        r"(?:notice\s*(?:no|ref(?:erence)?|number))[:\s.]*([A-Z0-9/\-]{4,})",
        r"(?:ref(?:erence)?\s*(?:no|number))[:\s.]*([A-Z0-9/\-]{4,})",
    ], t)
    notice_date = _find([
        r"(?:notice\s+date|date\s+of\s+notice|issued\s+on)[:\s]*([\d\-/. ]+)",
        r"(?:date)[:\s]*([\d\-/. ]+)",
    ], t)
    if notice_date:
        notice_date = _normalise_date(notice_date)
    due_date = _find([
        r"(?:due\s+date|respond\s+by|reply\s+by|last\s+date)[:\s]*([\d\-/. ]+)",
    ], t)
    if due_date:
        due_date = _normalise_date(due_date)

    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)
    legal_name = _find([r"(?:legal\s+name|taxpayer|M/s\.?)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    notice_type = _find([r"(?:notice\s+type|type\s+of\s+notice)[:\s]+([A-Za-z0-9 \-]{3,40})"], t)
    authority = _find([r"(?:issuing\s+authority|issued\s+by|from)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)
    section = _find([r"(?:section|rule|under\s+section)[:\s]+([A-Za-z0-9\(\) ,\-]{3,30})"], t)
    subject = _find([r"(?:subject)[:\s]+([A-Za-z0-9 &.,\-]{3,80})"], t)
    tax_period = _find([r"(?:tax\s+period|period)[:\s]+([A-Za-z0-9\- ]{3,20})"], t)
    amount_involved = _find_amount([r"(?:amount\s+involved|demand\s+amount|tax\s+demand)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)"], t)

    # Determine priority from keywords
    priority = "medium"
    if re.search(r"(?:immediate|urgent|compulsory)", t, re.IGNORECASE):
        priority = "high"
    elif re.search(r"(?:routine|general|information)", t, re.IGNORECASE):
        priority = "low"

    core = {
        "invoice_number": _missing(),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(legal_name, _conf_text(legal_name, 3)),
        "customer": _missing(),
        "invoice_date": _missing(),
        "amount": _field(amount_involved, _conf_amount(amount_involved)),
        "taxable_amount": _missing(),
        "cgst": _missing(),
        "sgst": _missing(),
        "igst": _missing(),
        "cess": _missing(),
        "hsn": _missing(),
    }
    # Fill notice-specific columns
    core["notice_number"] = _field(notice_no, _conf_text(notice_no, 4))
    core["notice_date"] = _field(notice_date, "extracted") if notice_date else _missing()
    core["response_due_date"] = _field(due_date, "extracted") if due_date else _missing()
    core["priority"] = _field(priority)

    meta = {
        "notice_type": _field(notice_type, _conf_text(notice_type, 3)),
        "issuing_authority": _field(authority, _conf_text(authority, 3)),
        "section_rule": _field(section, _conf_text(section, 3)),
        "subject": _field(subject, _conf_text(subject, 3)),
        "tax_period": _field(tax_period, _conf_text(tax_period, 3)),
    }
    return core, meta


def _parse_hsn_sac(t: str) -> tuple:
    hsn_code = _find([r"(?:HSN|SAC)[:\s]*([0-9]{4,8})"], t)
    description = _find([r"(?:description|goods|services)[:\s]+([A-Za-z0-9 ,\-]{3,60})"], t)
    gst_rate = _find([r"(?:GST\s+rate|rate)[:\s]*([0-9]{1,2}(?:\.[0-9]{1,2})?\s*%)"], t)
    code_type = "HSN" if re.search(r"\bHSN\b", t, re.IGNORECASE) else "SAC"

    core = {
        "invoice_number": _missing(),
        "gstin": _missing(),
        "vendor": _field(description, _conf_text(description, 3)),
        "customer": _missing(),
        "invoice_date": _missing(),
        "amount": _missing(),
        "taxable_amount": _missing(),
        "cgst": _missing(),
        "sgst": _missing(),
        "igst": _missing(),
        "cess": _missing(),
        "hsn": _field(hsn_code, _conf_text(hsn_code, 4)),
    }
    meta = {
        "code_type": _field(code_type),
        "gst_rate": _field(gst_rate, _conf_text(gst_rate, 2)),
        "requires_verification": _field("Yes"),
    }
    return core, meta


def _parse_document_list(t: str) -> tuple:
    doc_number = _find([r"(?:certificate\s+no|reg(?:istration)?\s+no|doc(?:ument)?\s+no)[:\s]*([A-Z0-9/\-]{4,})"], t)
    issue_date = _find([r"(?:issue\s+date|date\s+of\s+issue|valid\s+from)[:\s]*([\d\-/. ]+)"], t)
    if issue_date:
        issue_date = _normalise_date(issue_date)
    expiry = _find([r"(?:expiry|expiration|valid\s+(?:till|until|upto))[:\s]*([\d\-/. ]+)"], t)
    if expiry:
        expiry = _normalise_date(expiry)
    gstin_raw = _find([r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"], t)
    entity_name = _find([r"(?:name\s+of|taxpayer|holder)[:\s]+([A-Za-z0-9 &.,()-]{3,60})"], t)

    core = {
        "invoice_number": _field(doc_number, _conf_text(doc_number, 4)),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(entity_name, _conf_text(entity_name, 3)),
        "customer": _missing(),
        "invoice_date": _field(issue_date, "extracted") if issue_date else _missing(),
        "amount": _missing(),
        "taxable_amount": _missing(),
        "cgst": _missing(),
        "sgst": _missing(),
        "igst": _missing(),
        "cess": _missing(),
        "hsn": _missing(),
    }
    meta = {
        "expiry_date": _field(expiry, "extracted") if expiry else _missing(),
        "verification_status": _field("Pending Verification"),
    }
    return core, meta


# ---------------------------------------------------------------------------
# Category dispatcher
# ---------------------------------------------------------------------------

CATEGORY_PARSERS = {
    "sales_records": lambda t: _parse_invoice(t),
    "purchase_records": lambda t: _parse_invoice(t),
    "b2b_invoice": lambda t: _parse_invoice(t),
    "b2c_invoice": lambda t: _parse_b2c(t),
    "credit_note": lambda t: _parse_credit_debit_note(t, "Credit Note"),
    "debit_note": lambda t: _parse_credit_debit_note(t, "Debit Note"),
    "e_invoice": lambda t: _parse_e_invoice(t),
    "e_way_bill": lambda t: _parse_e_way_bill(t),
    "gst_challan": lambda t: _parse_gst_challan(t),
    "gst_return": lambda t: _parse_gst_return(t),
    "gst_notice": lambda t: _parse_gst_notice(t),
    "hsn_sac": lambda t: _parse_hsn_sac(t),
    "document_list": lambda t: _parse_document_list(t),
}


# ---------------------------------------------------------------------------
# Post-extraction validation
# ---------------------------------------------------------------------------

def _validate_extraction(core_fields: dict, meta_fields: dict, category: str) -> dict:
    """Run GSTIN + amount validation and return a validation summary."""
    warnings = []

    # Extract plain values for validation
    def val(f: dict) -> str:
        return f.get("value", "") if isinstance(f, dict) else str(f or "")

    flat = {k: val(v) for k, v in {**core_fields, **meta_fields}.items()}

    # GSTIN validation
    gstin_result = validate_gstin(flat.get("gstin"))
    if gstin_result["valid"] is False:
        warnings.append(f"GSTIN: {gstin_result['message']}")

    # Amount validation (only for categories with financial data)
    amount_result = {"ok": None, "message": "Not applicable for this category"}
    financial_cats = {
        "sales_records", "purchase_records", "b2b_invoice", "b2c_invoice",
        "credit_note", "debit_note", "e_invoice", "gst_challan",
    }
    if category in financial_cats:
        amount_result = validate_amounts(flat)
        if amount_result["ok"] is False:
            warnings.append(f"Amount mismatch: {amount_result['message']}")
        if amount_result.get("supply_type") == "mixed_warning":
            warnings.append("Both IGST and CGST/SGST are non-zero — verify supply type")

    return {
        "gstin": gstin_result,
        "amounts": amount_result,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# File type constants
# ---------------------------------------------------------------------------

IMAGE_EXTS = {
    "jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif",
    "heic", "heif", "jfif", "avif",
}
PDF_EXTS = {"pdf"}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/extract", summary="Extract fields from a scanned document via OCR")
async def extract_ocr(
    file: UploadFile = File(...),
    category: str = Form(default="sales_records"),
):
    """
    Accept any image or PDF.
    Run OCR and return category-specific extracted fields with confidence tags.

    Response shape:
      has_content: bool           — False = no document text, frontend must block save
      fields: dict                — core DB fields with {value, confidence}
      metadata_fields: dict       — category-specific extra fields with {value, confidence}
      validation: dict            — GSTIN check, amount check, warnings list
      message: str
    """
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB for OCR).")

    # ── OCR ──────────────────────────────────────────────────
    if ext in PDF_EXTS or (file.content_type or "").lower() == "application/pdf":
        raw_text = _ocr_pdf(content)
    elif ext in IMAGE_EXTS or (file.content_type or "").lower().startswith("image/"):
        raw_text = _ocr_image(content)
    else:
        try:
            raw_text = _ocr_image(content)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '.{ext}'. Upload an image or PDF.",
            )

    # ── Meaningful-content check ─────────────────────────────
    if not _is_meaningful(raw_text):
        return {
            "success": True,
            "has_content": False,
            "category": category,
            "fields": {},
            "metadata_fields": {},
            "validation": {"gstin": {}, "amounts": {}, "warnings": []},
            "raw_text": "",
            "message": (
                "No document text was detected. "
                "This appears to be a photo or image without readable document content. "
                "Please upload a clear photo of an invoice, receipt, bill, or notice."
            ),
        }

    # ── Parse ─────────────────────────────────────────────────
    parser = CATEGORY_PARSERS.get(category, lambda t: _parse_invoice(t))
    core_fields, meta_fields = parser(raw_text)

    # ── Validate ──────────────────────────────────────────────
    validation = _validate_extraction(core_fields, meta_fields, category)

    # Mark fields that failed validation as needs_review
    gstin_val = validation["gstin"]
    if gstin_val.get("valid") is False and "gstin" in core_fields:
        core_fields["gstin"]["confidence"] = "needs_review"
    if gstin_val.get("normalized") and "gstin" in core_fields:
        core_fields["gstin"]["value"] = gstin_val["normalized"]

    if validation["amounts"].get("ok") is False:
        for f in ("amount", "taxable_amount", "cgst", "sgst", "igst"):
            if f in core_fields and core_fields[f]["confidence"] == "extracted":
                core_fields[f]["confidence"] = "needs_review"

    has_any_field = any(
        v.get("value") for v in {**core_fields, **meta_fields}.values()
        if isinstance(v, dict)
    )

    return {
        "success": True,
        "has_content": True,
        "category": category,
        "fields": core_fields,
        "metadata_fields": meta_fields,
        "validation": validation,
        "raw_text": raw_text[:3000],
        "message": (
            "OCR extraction complete."
            if has_any_field
            else (
                "Text detected but no structured fields found. "
                "Fill in fields manually or try a clearer image."
            )
        ),
    }
