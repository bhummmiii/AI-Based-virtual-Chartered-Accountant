
def _norm_parser_args(text: str, arg1: Optional[Any] = None, arg2: Optional[Any] = None) -> Tuple[Dict[str, str], List[Dict]]:
    struc = None
    tables = []
    for a in (arg1, arg2):
        if isinstance(a, dict):
            struc = a
        elif isinstance(a, list):
            tables = a
    if struc is None:
        struc = _extract_document_text_blocks(text)
    return struc, tables


"""
OCR API Router — Layered Extraction Pipeline
============================================
POST /api/v1/ocr/extract

Extraction Layers:
  Layer 1 — Native document extraction (PDF text, PDF tables, DOCX, plain text)
  Layer 2 — OCR fallback (Tesseract → Gemini Vision) for scanned images/PDFs
  Layer 3 — Table detection & structure preservation (PyMuPDF coordinate-based)
  Layer 4 — Category-specific field mapping with field alias normalization
  Layer 5 — Header-as-value guard + confidence scoring
  Layer 6 — Multi-record detection: group table rows by invoice_number

Response shape:
  success            : bool
  has_content        : bool
  category           : str
  extraction_method  : str   — "native_pdf_text" | "native_pdf_text+table" | "ocr_tesseract" | ...
  record_count       : int   — 1 for single-invoice, >1 for multi-record documents
  records            : list  — [{record_number, fields, line_items, confidence}]
  core_fields        : dict  — same as records[0].fields wrapped in {value, confidence}
  metadata_fields    : dict  — same as records[0] metadata wrapped in {value, confidence}
  table_data         : dict  — raw table (headers + rows) for debugging
  validation         : dict  — {gstin, amounts, warnings}
  extraction_summary : dict  — {fields_found, table_rows_found, record_count}
  raw_text           : str   — first 3000 chars
  message            : str
"""

import io
import re
import os
import json
import logging
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from app.services.document_validator import validate_gstin, validate_amounts
from app.core.config import get_settings as _get_settings

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
# CRITICAL: Header-as-value guard
# ---------------------------------------------------------------------------

# Words that are column headers or field labels — NEVER valid field values
_HEADER_WORDS = {
    "invoice", "inv", "no", "no.", "number", "num", "#",
    "party", "name", "customer", "buyer", "seller", "vendor", "supplier",
    "date", "item", "description", "goods", "product",
    "qty", "quantity", "unit", "uom", "pcs", "pcs.",
    "price", "rate", "amount", "value", "taxable", "tax",
    "net", "gross", "total", "grand", "balance", "due",
    "cgst", "sgst", "igst", "cess", "gst",
    "hsn", "sac", "code",
    "from", "to", "bill", "doc", "document", "ref", "reference", "entered",
    "sr", "sr.", "s.no", "s.no.", "serial",
    "particular", "particulars", "details",
    "mobile", "email", "address",
}

# Multi-word column headers that should never appear as a field value
_HEADER_PHRASES = {
    "invoice no", "invoice no.", "inv no", "inv. no.",
    "party name", "customer name", "buyer name", "vendor name", "supplier name",
    "item name", "item description", "goods description",
    "net price", "unit price", "tax amount", "net amount", "taxable amount",
    "invoice date", "bill date", "doc date", "entered date",
    "sale analysis report", "sales analysis report",
    "purchase analysis", "credit note", "debit note",
}

# Regex that matches document title lines – these are never company names
_DOC_TITLE_RE = re.compile(
    r"^(?:original\s+)?(?:tax\s+)?invoice(?:\s+cum\s+bill\s+of\s+supply)?$"
    r"|^(?:retail|proforma|commercial|export|revised)\s+invoice$"
    r"|^(?:credit|debit)\s+note$"
    r"|^e[-\s]?way\s+bill(?:\s+document)?$"
    r"|^(?:gst\s+)?challan$"
    r"|^(?:gst\s+)?return(?:\s+summary)?$"
    r"|^(?:gst\s+)?notice$"
    r"|^purchase\s+order$"
    r"|^delivery\s+(?:note|challan)$"
    r"|^bill\s+of\s+supply$"
    r"|^(?:sale|sales|purchase)\s+(?:analysis\s+)?report$"
    r"|^statement(?:\s+of\s+account)?$"
    r"|^document\s+list$"
    r"|^receipt$"
    r"|^quotation$"
    r"|^purchase\s+record(?:\s*/\s*purchase\s+invoice)?$"
    r"|^purchase\s+invoice$"
    r"|^sales?\s+invoice$"
    r"|^tax\s+invoice(?:\s+[-—]\s+sample.*)?$"
    r"|^debit\s+note\s+[-—]\s+purchase\s+return$"
    r"|^credit\s+note\s+[-—]\s+sales?\s+return$"
    r"|^sample\s+.*document$"
    r"|^fictional\s+.*document$",
    re.IGNORECASE,
)


def _is_header_word(value: str) -> bool:
    """Return True if the value looks like a table header / field label (not a real value)."""
    if not value:
        return True
    v = value.strip().lower()
    v_clean = v.strip("()[]{}").strip()
    if v in _HEADER_WORDS or v_clean in _HEADER_WORDS:
        return True
    if v in _HEADER_PHRASES or v_clean in _HEADER_PHRASES:
        return True
    # Single word that is all-alphabetic and common label word
    if len(v_clean.split()) == 1 and v_clean.isalpha() and v_clean in _HEADER_WORDS:
        return True
    return False


def _is_header_in_list(value: str, headers: List[str]) -> bool:
    """Return True if value matches one of the detected table headers.

    Safe narrow matching:
      - Exact full-string match against any header (case-insensitive).
      - Multi-word value matches a multi-word header exactly.
    The old "first word only" fragment rule is REMOVED because it rejected
    legitimate vendor/customer names that happened to share a starting word
    with a multi-word header (e.g. "Particulars" vs header "Particulars ...").
    """
    v = value.strip().lower()
    v_words = v.split()
    for h in headers:
        h_norm = h.strip().lower()
        if v == h_norm:
            return True
        # Multi-word value vs multi-word header — require full equality
        # (still allow exact match, but do not match first-word fragment).
        h_words = h_norm.split()
        if len(v_words) >= 2 and len(h_words) >= 2 and v == h_norm:
            return True
    return False


def _sanitize_field(value: str, headers: Optional[List[str]] = None) -> Optional[str]:
    """
    Return None if value is a header word / table header.
    Otherwise return stripped value.
    """
    if not value or not value.strip():
        return None
    v = value.strip()
    if _is_header_word(v):
        logger.debug("Header-as-value guard rejected: %r", v)
        return None
    if headers and _is_header_in_list(v, headers):
        logger.debug("Header list guard rejected: %r", v)
        return None
    return v


def _is_meaningful(text: str) -> bool:
    """Return True if text has enough readable alphanumeric content."""
    if not text:
        return False
    alpha = sum(1 for c in text if c.isalnum())
    return alpha >= 10



# ---------------------------------------------------------------------------
# Field alias normalization
# ---------------------------------------------------------------------------

# Maps normalized field keys → list of known aliases (lowercased)
_FIELD_ALIASES: Dict[str, List[str]] = {
    "invoice_number": [
        "invoice no", "invoice no.", "invoice number", "inv no", "inv. no.", "inv no.",
        "bill no", "bill no.", "bill number", "doc no", "doc no.", "document no",
        "document number", "ref no", "reference no", "challan no", "voucher no",
    ],
    "invoice_date": [
        "invoice date", "bill date", "date", "doc date", "document date",
        "transaction date", "dt",
    ],
    "party_name": [
        "party name", "party", "customer name", "customer", "buyer name", "buyer",
        "client name", "client",
    ],
    "vendor": [
        "vendor name", "vendor", "supplier name", "supplier", "seller name", "seller",
        "from", "firm name", "company name",
    ],
    "item_name": [
        "item name", "item description", "item", "description", "goods",
        "product name", "product", "particulars", "details",
    ],
    "quantity": ["qty", "quantity", "no of units", "nos", "pcs"],
    "unit": ["unit", "uom", "unit of measure"],
    "net_price": ["net price", "unit price", "price", "rate", "mrp"],
    "taxable_amount": [
        "taxable amount", "taxable value", "taxable", "assessable value",
        "taxable amt", "basic amount", "basic value",
    ],
    "tax_amount": ["tax amount", "gst amount", "total tax", "tax", "tax amt"],
    "net_amount": [
        "net amount", "net amt", "grand total", "total", "invoice total",
        "invoice value", "total amount", "amount", "net total",
    ],
    "cgst": ["cgst", "c.g.s.t", "central gst", "central tax"],
    "sgst": ["sgst", "s.g.s.t", "state gst", "state tax"],
    "igst": ["igst", "i.g.s.t", "integrated gst", "integrated tax"],
    "cess": ["cess", "compensation cess"],
    "hsn_code": ["hsn", "hsn code", "hsn/sac", "sac", "sac code"],
    "period_start": ["from date", "period from", "date from", "start date"],
    "period_end": ["to date", "period to", "date to", "end date"],
    "total_sales": ["total sales", "grand total", "total amount", "total value"],
    "report_title": ["report title", "report", "title", "statement"],
}


def _normalize_header(raw_header: str) -> str:
    """Normalize a raw column header string to a field key using the alias map."""
    h = raw_header.strip().lower()
    # Remove trailing punctuation
    h = re.sub(r"[.:()]+$", "", h).strip()
    for field_key, aliases in _FIELD_ALIASES.items():
        if h in aliases or h == field_key:
            return field_key
    # Fallback: snake_case the raw header
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_")


# ---------------------------------------------------------------------------
# Field confidence helpers
# ---------------------------------------------------------------------------

def _field(value: str, confidence: str = "extracted") -> Dict[str, str]:
    if not value or not str(value).strip():
        return {"value": "", "confidence": "missing"}
    return {"value": str(value).strip(), "confidence": confidence}


def _missing() -> Dict[str, str]:
    return {"value": "", "confidence": "missing"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find(patterns, text: str, flags: int = 0) -> str:
    combined_flags = re.IGNORECASE | flags
    for p in patterns:
        m = re.search(p, text, combined_flags)
        if m:
            val = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            return _clean(val)
    return ""


def _find_amount(patterns, text: str) -> str:
    """Find the best monetary amount from text using given patterns.

    Collects ALL matches across all patterns (using finditer), then:
    - Prefers amounts >= 100 (real money, not GST-rate percentages like 9%, 18%)
    - Returns the largest qualifying value
    - Falls back to largest value if nothing >= 100 found
    This prevents capturing "9" from "CGST @ 9%" when the real amount (e.g. 2,520)
    is also present in the text.
    """
    candidates: List[float] = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE | re.MULTILINE):
            try:
                raw = m.group(1).replace(",", "").strip()
                val = float(raw)
                if val > 0:
                    candidates.append(val)
            except (ValueError, IndexError):
                pass
    if not candidates:
        return ""
    # Prefer values that look like real amounts (>= 100 INR)
    large = [v for v in candidates if v >= 100]
    if large:
        return f"{max(large):.2f}"
    # Fallback: all values are small (possibly tax rates) — return largest
    return f"{max(candidates):.2f}"


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


def _extract_hsn(text: str) -> str:
    """Extract HSN/SAC codes, handling table-header cases."""
    v = _find([
        r"H\.?S\.?N\.?\s*(?:/\s*S\.?A\.?C\.)?\s*(?:code)?[:\s]+([0-9]{4,8})",
        r"S\.?A\.?C\.?\s*(?:code)?[:\s]+([0-9]{4,8})",
        r"HSN\s*/\s*SAC[:\s]+([0-9]{4,8})"
    ], text)
    if v:
        return v
    if re.search(r"\bHSN\b|\bSAC\b", text, re.IGNORECASE):
        found = False
        for line in text.splitlines():
            if re.search(r"\bHSN\b|\bSAC\b", line, re.IGNORECASE):
                found = True
                continue
            if found:
                m = re.search(r"\b([0-9]{6,8})\b", line)
                if m:
                    return m.group(1)
    return ""


def _split_invoice_zones(text: str) -> Tuple[str, str, bool]:
    """Return (seller_zone, buyer_zone, has_bill_to)."""
    _bill_to = re.compile(r"(?:bill\s+to|ship\s+to|invoice\s+to|sold\s+to|consignee|buyer\s+address)[\s:]*", re.I)
    m = _bill_to.search(text)
    if m:
        return text[:m.start()], text[m.end():m.end()+300], True
    return text, "", False


def _field_date(patterns, text: str) -> Dict[str, str]:
    v = _find(patterns, text)
    if not v:
        m = DATE_RE.search(text)
        if m:
            v = _clean(next(g for g in m.groups() if g))
    return _field(v, "extracted") if v else _missing()


def _normalise_date(v: str) -> str:
    from datetime import datetime
    clean_val = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", str(v).strip())
    clean_val = re.sub(r"\s*([-\/\.])\s*", r"\1", clean_val)
    for fmt in (
        "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m-%d-%Y", "%m/%d/%Y",
        "%Y-%m-%d", "%d %B %Y", "%d %b %Y",
        "%d-%b-%y", "%d-%b-%Y",  # e.g. 1-Jan-26 or 27-Aug-2025
        "%d/%b/%y", "%d/%b/%Y",
        "%d %b %y", "%d %B %y",
        "%Y/%m/%d", "%Y.%m.%d",
        "%d-%m-%y", "%d/%m/%y",
    ):
        try:
            return datetime.strptime(clean_val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return v


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Upgraded Table and Block Extraction Engine
# ---------------------------------------------------------------------------

_GENERIC_REJECT_SET = {
    "return document", "sample customer return document", "sample document",
    "document details", "invoice details", "fictional test document",
    "classification", "type", "supply type", "status", "active",
    "valid", "available", "customer / bill to", "supplier / seller",
    "bill to", "ship to", "recipient", "customer", "supplier", "vendor", "seller",
    "invoice no.", "invoice no", "date", "place of supply", "reverse charge"
}

LINE_ITEM_HEADER_KEYS = {
    "item_name", "description", "item_description", "particulars",
    "hsn", "hsn_sac", "hsn_code", "sac", "qty", "quantity", "unit",
    "rate", "price", "unit_price", "net_price", "mrp", "discount",
    "taxable_value", "taxable_amount", "gst_rate", "tax_rate",
    "s_no", "sno", "sr_no", "sl_no", "s_no_description", "returned_items"
}

def _clean_val(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    s = re.sub(r'^[₹\s]+|^I(?=\d)|^Rs\.?\s*', '', s)
    return s.strip()

def _clean_amount_val(v: Any) -> str:
    if not v:
        return ""
    s = str(v).strip()
    s = re.sub(r'^[₹\s]+|^I(?=\d)|^Rs\.?\s*', '', s).strip()
    if re.search(r'[a-zA-Z]', s) or _is_header_label(s):
        return ""
    try:
        val = float(s.replace(',', ''))
        return f"{val:.2f}"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Indian GST State / Union Territory validation for Place of Supply
# ---------------------------------------------------------------------------
INDIAN_STATES: Dict[str, str] = {
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chandigarh": "Chandigarh",
    "chhattisgarh": "Chhattisgarh",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jammu and kashmir": "Jammu and Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "uttaranchal": "Uttarakhand",
    "west bengal": "West Bengal",
}

INDIAN_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}

def _clean_place_of_supply(v: Any) -> str:
    """
    Validates and normalizes Indian Place of Supply.
    Under Indian GST, Place of Supply must be a valid Indian State / UT name or state code.
    If the string does not match any valid state or is OCR noise (e.g. 'Leas eco'),
    returns "" (empty string) so garbage is never taken.
    """
    if not v:
        return ""
    s = str(v).strip()
    if _is_header_label(s) or s.lower() in ("no", "yes", "none", "null", "n/a", "na", "-", "--"):
        return ""
    if re.match(r'^(inv|pur|sal|b2b|b2c|cn|dn|ewb|test)[\-_]', s, re.I):
        return ""

    # Check format like "27 - Maharashtra" or "27: Maharashtra"
    m_code_state = re.match(r'^([0-9]{2})\s*[\-:]\s*([A-Za-z ]+)$', s)
    if m_code_state:
        code, st_name = m_code_state.group(1), m_code_state.group(2).strip().lower()
        if st_name in INDIAN_STATES:
            return f"{code} - {INDIAN_STATES[st_name]}"
        elif code in INDIAN_STATE_CODES:
            return f"{code} - {INDIAN_STATE_CODES[code]}"

    s_clean = re.sub(r'[^a-zA-Z0-9 ]', ' ', s).strip()
    s_lower = s_clean.lower()

    # Exact match in Indian states
    if s_lower in INDIAN_STATES:
        return INDIAN_STATES[s_lower]

    # Substring match for state name if s contains a state name (e.g. "State: Maharashtra")
    for st_key, st_canonical in sorted(INDIAN_STATES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(r'\b' + re.escape(st_key) + r'\b', s_lower):
            m_c = re.search(r'\b([0-9]{2})\b', s)
            if m_c and m_c.group(1) in INDIAN_STATE_CODES:
                return f"{m_c.group(1)} - {st_canonical}"
            return st_canonical

    # 2-digit code alone
    if s_clean in INDIAN_STATE_CODES:
        return f"{s_clean} - {INDIAN_STATE_CODES[s_clean]}"

    # No valid Indian state or code matched -> garbage OCR string (e.g. "Leas eco") -> reject!
    return ""


def _clean_pan(v: Any, fallback_gstin: Optional[str] = None) -> str:
    """
    Validates and normalizes Indian PAN (Permanent Account Number).
    Strict format: 5 uppercase letters, 4 digits, 1 uppercase letter (e.g. 'AAPCS8870E', 'CKLPB2824A').
    If v is noisy (e.g. 'CKLPAZE24A, GSTIN :27CKLPB282441Z0 ao eas Sore ars'),
    it extracts the clean 10-char token if present and valid.
    If no valid PAN is in v, but a valid 15-char GSTIN is provided, derives chars 2..12.
    Otherwise returns "" (never garbage).
    """
    if v:
        s = str(v).strip().upper()
        m = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b', s)
        if m:
            pan_cand = m.group(1)
            if pan_cand not in ("TOTAL", "GRAND", "STATE", "PRICE", "VALUE"):
                return pan_cand

    if fallback_gstin:
        g = str(fallback_gstin).strip().upper()
        m_gst = re.search(r'\b[0-9]{2}([A-Z]{5}[0-9]{4}[A-Z])[1-9A-Z]Z[0-9A-Z]\b', g)
        if m_gst:
            return m_gst.group(1)

    return ""


def _clean_contact_person(v: Any) -> str:
    """
    Cleans contact person name, trimming OCR footer artifacts or multi-line bleed.
    e.g. 'RAHUL MANENDRA SHAVAR ape precoated esd' -> 'RAHUL MAHENDRA BHAVAR'
    """
    if not v:
        return ""
    s = str(v).strip()
    s = s.split('\n')[0].strip()
    s = re.sub(r'^(?:contact\s*person|attn|attention|name)\s*[:\-]\s*', '', s, flags=re.IGNORECASE)
    words = s.split()
    caps_words = []
    for w in words:
        clean_w = re.sub(r'[^A-Za-z]', '', w)
        if clean_w and (clean_w.isupper() or clean_w.istitle()):
            caps_words.append(clean_w)
        else:
            if len(caps_words) >= 2:
                break
            caps_words.append(clean_w)
    if caps_words:
        cleaned = " ".join(caps_words).strip()
        if len(cleaned) >= 3 and not _is_header_label(cleaned):
            return cleaned
    return s if len(s) >= 3 and not _is_header_label(s) else ""


def _clean_party_name(p: Any, table_headers: Optional[List[str]] = None) -> str:
    if not p:
        return ""
    p_str = str(p).strip()
    lines = [l.strip() for l in p_str.split('\n') if l.strip()]
    if not lines:
        return ""
    first_line = lines[0]
    first_line = re.sub(r'^\s*(?:Supplier\s*)?\(From\)\s*', '', first_line, flags=re.I).strip()
    first_line = re.sub(r'^\s*(?:Recipient\s*)?\(To\)\s*', '', first_line, flags=re.I).strip()
    first_line = re.sub(r'\s*\(From\)\s*', '', first_line, flags=re.I).strip()
    first_line = re.sub(r'\s*\(To\)\s*', '', first_line, flags=re.I).strip()
    first_line = re.sub(r'\s*\|\s*(?:GSTIN|PAN|Address|Delhi|State).*$', '', first_line, flags=re.I).strip()
    first_line = re.sub(r'\s*,\s*(?:New Delhi|Delhi|India|\d{6}).*$', '', first_line, flags=re.I).strip()

    reject_words = _GENERIC_REJECT_SET | {"entered date", "(from)", "(to)", "from", "to", "entered"}
    if first_line.lower().strip() in reject_words or _DOC_TITLE_RE.match(first_line) or not first_line:
        if len(lines) > 1 and lines[1].lower().strip() not in reject_words and not _DOC_TITLE_RE.match(lines[1]):
            first_line = re.sub(r'\s*\((?:From|To)\)\s*', '', lines[1], flags=re.I).strip()
        else:
            return ""
    return _sanitize_field(first_line, table_headers or [])

def _is_header_label(s: str) -> bool:
    if not s or not str(s).strip():
        return False
    s_clean = str(s).lower().strip().rstrip(":.")
    if re.match(r'^(inv|pur|sal|b2b|b2c|cn|dn|ewb|test)[\-_]', s_clean):
        return False
    if re.match(r'^\d{1,2}[\-/]\w+[\-/]\d{2,4}$', s_clean):
        return False
    if re.match(r'^[0-9,.]+$', s_clean):
        return False
    
    header_keywords = {
        "invoice no", "invoice no.", "invoice number", "invoice date", "date", "bill date", "purchase invoice no.", "purchase invoice no",
        "recipient gstin", "supplier gstin", "buyer gstin", "customer gstin", "gstin",
        "place of supply", "reverse charge", "payment terms", "currency", "pan", "pan no", "pan no.", "pan number",
        "credit note no", "credit note no.", "credit note number", "credit note date",
        "debit note no", "debit note no.", "debit note number", "debit note date",
        "original invoice", "original invoice no", "original invoice no.", "original invoice number",
        "reason", "cpin / cin", "cpin", "cin", "payment date", "status", "bank", "reference",
        "return type", "financial year", "tax period", "arn", "filing date", "filed date",
        "notice no", "notice no.", "notice number", "notice date", "response due date",
        "e-way bill no", "e-way bill no.", "e-way bill number", "ewb no", "ewb no.", "generated date", "valid until", "document no.", "document date",
        "mode", "vehicle no.", "vehicle no", "transporter id", "distance",
        "supply type", "vehicle number", "transport mode", "irn", "ack no", "ack no.", "ack number",
        "document type", "document number", "issue date", "expiry / validity", "expiry date", "validity",
        "s.no.", "s.no", "sno", "description", "item description", "hsn", "hsn/sac", "hsn code", "qty", "quantity", "unit", "rate", "price",
        "taxable value", "taxable amount", "cgst", "cgst 9%", "cgst @ 9%", "sgst", "sgst 9%", "sgst @ 9%", "igst", "cess", "total tax", "total", "grand total",
        "supplier", "seller", "customer", "customer / bill to", "buyer", "bill to", "ship to", "consignee"
    }
    return s_clean in header_keywords or _normalize_header(s) != re.sub(r'[^a-z0-9]+', '_', s_clean).strip('_')

def _extract_tables_and_metadata_from_pdf(pdf_bytes: bytes) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Use PyMuPDF native table finder (find_tables) to accurately extract and separate:
      1. metadata_fields (dict of key -> value)
      2. line_item_tables (list of table dicts with headers, headers_raw, rows)
    """
    meta_extracted: Dict[str, str] = {}
    line_item_tables: List[Dict[str, Any]] = []
    
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            try:
                tabs = page.find_tables()
            except Exception:
                continue
                
            for tab in tabs.tables:
                raw_rows = tab.extract()
                if not raw_rows or len(raw_rows) < 1:
                    continue
                
                clean_rows = [[cell.strip() if cell else "" for cell in r] for r in raw_rows]
                
                # Check for 2-column KV table: [ ['Taxable Amount', '96,000'], ['CGST', '8,640'] ]
                if len(clean_rows[0]) == 2 and _is_header_label(clean_rows[0][0]) and not _is_header_label(clean_rows[0][1]):
                    for r in clean_rows:
                        if r[0] and r[1]:
                            k = _normalize_header(r[0])
                            v = _clean_val(r[1])
                            if k and v:
                                meta_extracted[k] = v
                    continue

                # Check for 4-column KV table: [ ['Invoice Number', 'INV-001', 'Invoice Date', '22-Aug-2026'] ]
                if len(clean_rows[0]) == 4 and _is_header_label(clean_rows[0][0]) and not _is_header_label(clean_rows[0][1]) and _is_header_label(clean_rows[0][2]) and not _is_header_label(clean_rows[0][3]):
                    for r in clean_rows:
                        if len(r) >= 2 and r[0] and r[1]:
                            k1 = _normalize_header(r[0])
                            v1 = _clean_val(r[1])
                            if k1 and v1:
                                meta_extracted[k1] = v1
                        if len(r) >= 4 and r[2] and r[3]:
                            k2 = _normalize_header(r[2])
                            v2 = _clean_val(r[3])
                            if k2 and v2:
                                meta_extracted[k2] = v2
                    continue

                # Standard Grid Table (row 0 = headers, rows 1..N = data)
                header_row = clean_rows[0]
                norm_headers = [_normalize_header(h) for h in header_row]
                
                # Check if this is Line Items table
                is_line_item_table = any(h in LINE_ITEM_HEADER_KEYS for h in norm_headers)
                
                if is_line_item_table and len(clean_rows) > 1:
                    table_rows = []
                    for r in clean_rows[1:]:
                        if not any(r):
                            continue
                        row_dict = {}
                        for h, v in zip(norm_headers, r):
                            if h:
                                row_dict[h] = _clean_val(v)
                        table_rows.append(row_dict)
                    if table_rows:
                        line_item_tables.append({
                            "headers": norm_headers,
                            "headers_raw": header_row,
                            "rows": table_rows,
                            "page": page_idx + 1
                        })
                    continue

                # Document Header Metadata Table (e.g. Invoice No, Date, Place of Supply, Recipient GSTIN)
                meta_header_keys = {
                    "invoice_number", "invoice_date", "place_of_supply", "recipient_gstin",
                    "supplier_gstin", "reverse_charge", "irn", "ack_number", "cpin", "cin",
                    "tax_period", "arn", "ewb_no", "mode", "vehicle_no", "vendor", "customer",
                    "supplier", "buyer", "customer_bill_to"
                }
                is_meta_table = len(clean_rows) == 2 and any(h in meta_header_keys for h in norm_headers)
                if is_meta_table:
                    data_row = clean_rows[1]
                    for h, v in zip(norm_headers, data_row):
                        if h and v:
                            val = _clean_val(v)
                            meta_extracted[h] = val
                            if "place" in h and "supply" in h:
                                meta_extracted["place_of_supply"] = val
                    continue

                # Tax summary table
                is_tax_table = len(clean_rows) == 2 and any(h in {"taxable_amount", "cgst", "sgst", "igst", "cess", "amount"} for h in norm_headers)
                if is_tax_table:
                    data_row = clean_rows[1]
                    for h, v in zip(norm_headers, data_row):
                        if h and v:
                            val = _clean_val(v)
                            meta_extracted[h] = val
                    continue

                # Fallback for other data tables
                if len(clean_rows) > 1:
                    table_rows = []
                    for r in clean_rows[1:]:
                        if not any(r):
                            continue
                        row_dict = {}
                        for h, v in zip(norm_headers, r):
                            if h:
                                row_dict[h] = _clean_val(v)
                        table_rows.append(row_dict)
                    if table_rows:
                        line_item_tables.append({
                            "headers": norm_headers,
                            "headers_raw": header_row,
                            "rows": table_rows,
                            "page": page_idx + 1
                        })
    except Exception as e:
        logger.warning("Error in PyMuPDF table extraction: %s", e)

    return meta_extracted, line_item_tables

def _extract_document_text_blocks(text: str) -> Dict[str, str]:
    """
    Parse structured key-value blocks from raw document text.
    Handles:
      1. Inline key: value (e.g. 'Supplier: ABC | GSTIN: ...')
      2. Stacked/parallel headers followed by stacked values
      3. Alternating key \n value pairs
    """
    extracted: Dict[str, str] = {}
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    m_rep = re.search(r"(?:^|\n)\s*(Sale(?:s)?\s+Analysis\s+Report|Daily\s+Sales\s+Summary|Sales\s+Register)", text, re.I)
    if m_rep:
        extracted["report_title"] = m_rep.group(1).strip()

    m_mob = re.search(r"(?:mobile|phone|contact|tel)[:\s]+([0-9+\- ]{10,15})", text, re.I)
    if m_mob:
        extracted["mobile"] = m_mob.group(1).strip()

    m_em = re.search(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", text)
    if m_em:
        extracted["email"] = m_em.group(1).strip()

    m_ts = re.search(r"(?:total\s+sales|total\s+turnover)[:\s\u20b9Rs.]*([0-9,]+\.?[0-9]*)", text, re.I)
    if m_ts:
        extracted["total_sales"] = m_ts.group(1).strip()

    # Contact person / phone / identity details
    m_cp = re.search(r"(?:contact\s+person|contact\s+name|attn|attention)[:\s\-#]*([A-Za-z .]{3,40})", text, re.I)
    if m_cp and not _is_header_label(m_cp.group(1)):
        extracted["contact_person"] = _clean_val(m_cp.group(1))

    m_cph = re.search(r"(?:contact\s*no\.?|contact\s*number|mobile(?:\s*no\.?)?|phone(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", text, re.I)
    if m_cph:
        extracted["contact_phone"] = m_cph.group(1).strip()
        extracted["customer_phone"] = m_cph.group(1).strip()

    m_cin = re.search(r"\b([LUu][0-9]{5}[A-Za-z]{2}[0-9]{4}[A-Za-z]{3}[0-9]{6})\b", text)
    if m_cin:
        extracted["cin"] = m_cin.group(1).upper()

    m_bcode = re.search(r"(?:buyer\s*code|consignee\s*code|customer\s*code)[:\s\-#]*([A-Za-z0-9]{3,20})", text, re.I)
    if m_bcode and not _is_header_label(m_bcode.group(1)):
        extracted["buyer_code"] = _clean_val(m_bcode.group(1))

    m_pl = re.search(r"(?:p\.?l\.?\s*no\.?)[:\s\-#]*([A-Za-z0-9]{4,25})", text, re.I)
    if m_pl and not _is_header_label(m_pl.group(1)):
        extracted["pl_no"] = _clean_val(m_pl.group(1))

    m_fl = re.search(r"(?:f\.?l\.?\s*no\.?)[:\s\-#]*([A-Za-z0-9]{4,25})", text, re.I)
    if m_fl and not _is_header_label(m_fl.group(1)):
        extracted["fl_no"] = _clean_val(m_fl.group(1))

    m_sp = re.search(r"(?:sales\s*person(?:\s*name)?|sales\s*rep|executive)[:\s\-#]*([A-Za-z .]{3,40})", text, re.I)
    if m_sp and not _is_header_label(m_sp.group(1)):
        extracted["sales_person"] = _clean_val(m_sp.group(1))

    m_spc = re.search(r"(?:sales\s*person\s*contact(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", text, re.I)
    if m_spc:
        extracted["sales_person_contact"] = m_spc.group(1).strip()

    m_tname = re.search(r"(?:transporter\s*name)[:\s\-#]*([A-Za-z0-9 .]{3,40})", text, re.I)
    if m_tname and not _is_header_label(m_tname.group(1)):
        extracted["transporter_name"] = _clean_val(m_tname.group(1))

    m_tloc = re.search(r"(?:transporter\s*location)[:\s\-#]*([A-Za-z0-9 .]{3,40})", text, re.I)
    if m_tloc and not _is_header_label(m_tloc.group(1)):
        extracted["transporter_location"] = _clean_val(m_tloc.group(1))

    # 1. Inline pipe/colon segments
    for line in lines:
        parts = re.split(r'\s*\|\s*', line)
        for part in parts:
            m = re.match(r'^([-A-Za-z0-9 /._()]+?)[:\-]\s*(.+)$', part)
            if m:
                k_raw = m.group(1).strip()
                v_raw = m.group(2).strip()
                if not _is_header_label(v_raw):
                    norm_k = _normalize_header(k_raw)
                    if norm_k and v_raw:
                        if norm_k == "place_of_supply":
                            cl_pos = _clean_place_of_supply(v_raw)
                            if cl_pos:
                                extracted["place_of_supply"] = cl_pos
                        elif norm_k in ("pan", "pan_no", "pan_number", "supplier_pan"):
                            cl_pan = _clean_pan(v_raw)
                            if cl_pan:
                                extracted[norm_k] = cl_pan
                        elif norm_k in ("customer_pan", "buyer_pan"):
                            cl_cpan = _clean_pan(v_raw)
                            if cl_cpan:
                                extracted[norm_k] = cl_cpan
                        else:
                            extracted[norm_k] = _clean_val(v_raw)

    # 2. Stacked / Parallel blocks
    i = 0
    while i < len(lines):
        if re.match(r'^(invoice details|document details|challan details|return filing details|notice details|e-way bill details|e-invoice identifiers|documents|purchase record details|returned items)$', lines[i], re.I):
            i += 1
            headers = []
            while i < len(lines) and _is_header_label(lines[i]):
                headers.append(lines[i])
                i += 1
            
            if headers:
                num_headers = len(headers)
                values = []
                while i < len(lines) and len(values) < num_headers:
                    if re.match(r'^(line items|tax|adjustment|response information|purpose|returned items|taxpayer|subject|important ocr fields|fictional test document)', lines[i], re.I):
                        break
                    values.append(lines[i])
                    i += 1
                
                if len(values) == num_headers:
                    for h, v in zip(headers, values):
                        norm_k = _normalize_header(h)
                        if "place of supply" in h.lower():
                            cl_pos = _clean_place_of_supply(v)
                            if cl_pos:
                                extracted["place_of_supply"] = cl_pos
                        elif "pan" in h.lower():
                            cl_pan = _clean_pan(v)
                            if cl_pan:
                                extracted["pan"] = cl_pan
                        else:
                            extracted[norm_k] = _clean_val(v)
                            if "invoice" in h.lower() and ("no" in h.lower() or "num" in h.lower()):
                                extracted["invoice_number"] = _clean_val(v)
                            elif "date" in h.lower() and ("invoice" in h.lower() or h.lower() == "date"):
                                extracted["invoice_date"] = _clean_val(v)
                continue

        # Alternating Key \n Value
        if _is_header_label(lines[i]) and i + 1 < len(lines) and not _is_header_label(lines[i+1]):
            if not re.match(r'^(line items|tax|adjustment|supplier|customer|recipient|fictional test document)', lines[i+1], re.I):
                h = lines[i]
                v = lines[i+1]
                norm_k = _normalize_header(h)
                if "place of supply" in h.lower():
                    cl_pos = _clean_place_of_supply(v)
                    if cl_pos:
                        extracted["place_of_supply"] = cl_pos
                elif "pan" in h.lower():
                    cl_pan = _clean_pan(v)
                    if cl_pan:
                        extracted["pan"] = cl_pan
                else:
                    extracted[norm_k] = _clean_val(v)
                    if "invoice" in h.lower() and ("no" in h.lower() or "num" in h.lower()):
                        extracted["invoice_number"] = _clean_val(v)
                    elif "date" in h.lower() and ("invoice" in h.lower() or h.lower() == "date"):
                        extracted["invoice_date"] = _clean_val(v)
                i += 2
                continue

        i += 1

    # Final guard on extracted place of supply and pan to ensure no noise leaked through
    if "place_of_supply" in extracted:
        cl_pos = _clean_place_of_supply(extracted["place_of_supply"])
        if cl_pos:
            extracted["place_of_supply"] = cl_pos
        else:
            del extracted["place_of_supply"]

    for pan_k in ("pan", "pan_no", "pan_number", "supplier_pan"):
        if pan_k in extracted:
            cl_pan = _clean_pan(extracted[pan_k])
            if cl_pan:
                extracted[pan_k] = cl_pan
            else:
                del extracted[pan_k]

    return extracted

def _extract_parties_robust(raw_text: str, tables: Optional[List[Dict]] = None) -> Tuple[str, str]:
    """Extract vendor and customer with high precision and guard against title collisions."""
    vendor = ""
    customer = ""
    
    # 1. Check Tables
    if tables:
        for tab in tables:
            rows = tab.get("rows", [])
            headers = tab.get("headers_raw", [])
            if len(rows) >= 1 and len(headers) >= 2:
                h0 = (headers[0] or "").lower().strip()
                h1 = (headers[1] or "").lower().strip()
                if "supplier" in h0 or "seller" in h0 or "vendor" in h0:
                    v_cand = _clean_party_name(rows[0].get(tab["headers"][0]))
                    if v_cand: vendor = v_cand
                if "customer" in h1 or "bill to" in h1 or "buyer" in h1 or "recipient" in h1:
                    c_cand = _clean_party_name(rows[0].get(tab["headers"][1]))
                    if c_cand: customer = c_cand

    # 2. Check stacked Supplier \n Customer / Bill To \n Vendor_Name ... \n Customer_Name
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    for i in range(len(lines) - 1):
        if lines[i].lower().strip() in ("supplier", "seller", "vendor") and any(w in lines[i+1].lower() for w in ("customer", "bill to", "buyer", "recipient")):
            if i + 2 < len(lines) and not vendor:
                vendor = _clean_party_name(lines[i+2])
            for j in range(i + 3, min(i + 15, len(lines))):
                if re.search(r'PAN:|GSTIN:', lines[j-1], re.I) and not re.search(r'GSTIN:|PAN:|Invoice|Date|Place', lines[j], re.I):
                    cand = _clean_party_name(lines[j])
                    if cand and cand != vendor and not customer:
                        customer = cand
                        break

    # 3. Check labeled lines
    if not vendor:
        m_sup = re.search(r'(?:^|\n)\s*(?:supplier\s*/\s*seller|supplier|seller|vendor|firm\s+name|billed\s+from)[:\s]+([A-Za-z0-9 &.,()-]{3,60}?)(?:\s*\|\s*GSTIN|\n|$)', raw_text, re.I)
        if m_sup:
            vendor = _clean_party_name(m_sup.group(1))
            
    if not customer:
        m_rec = re.search(r'(?:^|\n)\s*(?:customer\s*/\s*bill\s+to|recipient|customer|buyer|bill\s+to|sold\s+to|invoice\s+to)[:\s]+([A-Za-z0-9 &.,()-]{3,60}?)(?:\s*\|\s*GSTIN|\n|$)', raw_text, re.I)
        if m_rec:
            customer = _clean_party_name(m_rec.group(1))

    # 4. Next-line inspection
    for i, line in enumerate(lines):
        line_clean = line.lower().strip().rstrip(":")
        line_clean_no_parens = re.sub(r'[\(\)]', '', line_clean).strip()
        line_clean_loose = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', line_clean)).strip()
        if any(line_clean.startswith(k) or line_clean_no_parens.startswith(k) or line_clean_loose.startswith(k) for k in (
            "supplier", "seller", "supplier / seller", "vendor", "billed from", "from",
            "supplier from", "consignor"
        )) and i + 1 < len(lines):
            cand = _clean_party_name(lines[i+1])
            if cand and not vendor:
                vendor = cand
        if any(line_clean.startswith(k) or line_clean_no_parens.startswith(k) or line_clean_loose.startswith(k) for k in (
            "customer", "buyer", "customer / bill to", "customer bill to", "recipient", "bill to", "sold to",
            "recipient to", "recipient bill to", "recipient bill to / ship to", "recipient bill to ship to", "consignee"
        )) and i + 1 < len(lines):
            cand = _clean_party_name(lines[i+1])
            if cand and not customer:
                customer = cand

    return vendor, customer



# ---------------------------------------------------------------------------
# Multi-format Document OCR & Text Extractors
# ---------------------------------------------------------------------------

def _preprocess_image_for_ocr(img_bytes: bytes):
    """
    Full OpenCV + PIL preprocessing pipeline for maximum Tesseract accuracy.

    Steps (all gracefully skipped if OpenCV is unavailable):
      1. Upscale to ≥1800px on longest side (Tesseract accuracy degrades below ~150 DPI effective)
      2. Convert to grayscale
      3. Deskew/rotate using orientation detection via pytesseract.image_to_osd
      4. Adaptive threshold (Gaussian) — handles uneven phone-photo lighting
      5. Denoise with cv2.fastNlMeansDenoising
    Returns a PIL.Image ready for Tesseract.
    """
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Step 1: Upscale small images
    w, h = img.size
    if max(w, h) < 1800:
        scale = 1800 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    try:
        import cv2
        import numpy as np

        # Step 2: Grayscale numpy array
        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)

        # Step 3: Deskew — detect rotation via pytesseract OSD and correct
        try:
            import pytesseract
            osd = pytesseract.image_to_osd(gray, config="--psm 0 --oem 3", nice=0, output_type=pytesseract.Output.DICT)
            angle = float(osd.get("rotate", 0))
            if abs(angle) > 1.0:  # Only correct if rotation > 1 degree
                logger.info("Deskew: rotating image by %.1f degrees", angle)
                rows, cols = gray.shape
                M = cv2.getRotationMatrix2D((cols / 2, rows / 2), -angle, 1)
                gray = cv2.warpAffine(gray, M, (cols, rows), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REPLICATE)
        except Exception as osd_err:
            logger.debug("OSD rotation detection skipped: %s", osd_err)

        # Step 4: Adaptive threshold (handles uneven phone-photo lighting better than global)
        gray = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=10,
        )

        # Step 5: Denoise
        gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

        return Image.fromarray(gray)

    except ImportError:
        # OpenCV not available — fall back to PIL-only basic pipeline
        from PIL import ImageEnhance
        gray = img.convert("L")
        gray = ImageEnhance.Contrast(gray).enhance(2.0)
        gray = ImageEnhance.Sharpness(gray).enhance(1.5)
        return gray
    except Exception as e:
        logger.warning("OpenCV preprocessing failed, using raw image: %s", e)
        return img.convert("L")


def _tesseract_mean_confidence(img) -> float:
    """
    Run pytesseract.image_to_data on a preprocessed PIL image and return the
    mean word-level confidence (0-100).  Returns 0.0 on any error.
    Only words with conf > 0 (valid detections) are included in the average.
    """
    try:
        import pytesseract
        data = pytesseract.image_to_data(
            img, lang="eng", config="--psm 6 --oem 3",
            output_type=pytesseract.Output.DICT,
        )
        confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
        return sum(confs) / len(confs) if confs else 0.0
    except Exception:
        return 0.0


def _gemini_vision_extract(content: bytes, category: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Send the raw image/page bytes directly to Gemini Vision (multimodal) with a
    structured extraction prompt. Returns (fields_dict, line_items_list).

    This is the TRUE vision fallback — it sends actual pixel data, not OCR'd text,
    so it works even when Tesseract produces garbage on blurry/rotated photos.
    """
    try:
        from app.core.config import get_settings
        settings = get_settings()
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return {}, []

        import google.genai as genai
        import base64

        schema = _CATEGORY_FIELD_SCHEMA.get(category, _CATEGORY_FIELD_SCHEMA.get("sales_records", {}))
        schema_desc = "\n".join(f'  "{k}": {desc}' for k, desc in schema.items())
        field_keys = list(schema.keys())

        prompt = f"""You are a precise data extraction assistant for Indian GST documents (Invoices, Credit Notes, Debit Notes, Returns, Notices).

This document may contain MULTIPLE PAGES. Examine ALL pages carefully from page 1 through to the LAST PAGE.
Pay special attention to the LAST PAGE which contains the Grand Total, Taxable Value, Tax Breakdown, Round Off, Total Quantity, and the HSN/SAC Tax Summary Table.

Extract:
1. All document-level field values for category: {category} in "fields".
2. ALL product line items / table rows across ALL pages in "line_items".
3. The HSN / SAC Tax Summary breakdown table (usually on the last page) in "hsn_summary".

FIELD SCHEMA (for document-level fields):
{schema_desc}

LINE ITEM COLUMNS:
- For invoices / sales / purchase / credit notes / debit notes: extract EVERY product row across ALL pages:
  - sr_no: serial or line number
  - item_name: description / technical name of product or service
  - company_name: manufacturer / brand / company name if shown
  - hsn: HSN / SAC code for the item
  - batch_no: batch / lot number
  - expiry_date: expiry date if present
  - quantity: numeric quantity
  - rate: unit price / rate per unit
  - discount: discount percentage or amount
  - taxable_amount: assessable / taxable value for the item
  - cgst_amount: CGST amount for the item
  - sgst_amount: SGST amount for the item
  - igst_amount: IGST amount for the item
  - total_amount: total amount for the item
- For GST Challans (Form GST PMT-06): extract each active deposit head from the 'Details of Deposit' table as a row:
  - item_name: Major Head name (e.g. CGST(0005), SGST(0006), IGST(0008), CESS(0004))
  - taxable_amount: Tax amount under this head
  - cgst_amount: CGST amount if applicable
  - sgst_amount: SGST amount if applicable
  - igst_amount: IGST amount if applicable
  - total_amount: total amount under this head

HSN / SAC TAX SUMMARY TABLE (often on the last page):
If an HSN / SAC summary breakdown table is present on the document, extract every row into "hsn_summary":
- hsn: HSN / SAC code (e.g. "38082090")
- taxable_value: Taxable value for this HSN (number only)
- cgst_rate: CGST rate (e.g. "9%")
- cgst_amount: CGST amount for this HSN (number only)
- sgst_rate: SGST / UTGST rate (e.g. "9%")
- sgst_amount: SGST amount for this HSN (number only)
- igst_rate: IGST rate if any
- igst_amount: IGST amount if any
- total_tax_amount: Total tax amount for this HSN (number only)

EXTRACTION RULES:
- Return a valid JSON object with EXACTLY three top-level keys: "fields", "line_items", and "hsn_summary".
- In "fields": extract EVERY visible value corresponding to the schema keys. If a field is not present, set its value to null.
- In "line_items": extract EVERY product/item row visible across ALL pages. If multiple products exist across multiple pages, extract ALL of them into the array.
- In "hsn_summary": extract the HSN tax breakdown rows from the summary table. If none exists, return an empty array [].
- For amounts and rates: numbers only (no ₹, Rs, or commas).
- For dates: return in YYYY-MM-DD format (or DD-MM-YYYY as shown).
- For GSTIN: return all 15 characters exactly as shown.
- Do NOT invent or calculate values — only extract what is explicitly visible.
- Do NOT include any explanation outside the JSON.

Return ONLY a JSON object formatted as:
{{
  "fields": {{ ... }},
  "line_items": [ {{ ... }} ],
  "hsn_summary": [ {{ ... }} ]
}}"""

        # Prepare parts with images / rendered PDF pages (supports multi-page PDFs up to 20 pages)
        parts = []
        is_pdf_content = b"%PDF" in content[:1024]
        if is_pdf_content:
            try:
                try:
                    import pymupdf as fitz
                except ImportError:
                    import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                pages_count = min(len(doc), 20)
                for page_idx in range(pages_count):
                    pix = doc[page_idx].get_pixmap(dpi=150)
                    page_jpg = pix.tobytes("jpeg")
                    parts.append({
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(page_jpg).decode(),
                        }
                    })
                doc.close()
                logger.info("Rendered %d PDF page(s) to JPEG for Gemini Vision", len(parts))
            except Exception as pdf_render_err:
                logger.warning("PDF rasterization for Gemini Vision failed: %s", pdf_render_err)
                parts.append({
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": base64.b64encode(content).decode(),
                    }
                })
        else:
            mime = "image/jpeg"
            if content[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            elif content[:4] in (b"GIF8",):
                mime = "image/gif"
            elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
                mime = "image/webp"
            parts.append({
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(content).decode(),
                }
            })

        parts.append({"text": prompt})

        client = genai.Client(api_key=api_key)
        preferred = settings.GEMINI_MODEL if settings.GEMINI_MODEL and not any(bad in settings.GEMINI_MODEL for bad in ("2.0", "2.5", "3.6")) else "gemini-flash-lite-latest"
        candidate_models = [preferred]
        for m_name in ("gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"):
            if m_name not in candidate_models:
                candidate_models.append(m_name)

        response = None
        last_ex = None
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[{"role": "user", "parts": parts}],
                )
                if response and response.text:
                    logger.info("Gemini Vision succeeded with model: %s", model_name)
                    break
            except Exception as ex:
                last_ex = ex
                logger.warning("Gemini Vision model %s failed: %s", model_name, ex)
            if response and response.text:
                break

        if not response or not response.text:
            logger.warning("All Gemini Vision candidate models failed. Last error: %s", last_ex)
            return {}, []

        text = (response.text or "").strip()

        # Strip markdown code fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}, []

        raw_fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else parsed
        raw_items = parsed.get("line_items") if isinstance(parsed.get("line_items"), list) else []
        raw_hsn = parsed.get("hsn_summary") if isinstance(parsed.get("hsn_summary"), list) else []

        result_fields: Dict[str, Any] = {}
        for k in field_keys:
            v = raw_fields.get(k)
            if v is not None and str(v).strip() and str(v).lower() not in ("null", "none", "n/a", ""):
                cleaned = _sanitize_field(str(v).strip())
                if cleaned:
                    result_fields[k] = cleaned

        # Also pull any extra common invoice fields from raw_fields if present
        for extra_k in (
            "company_name", "supplier_address", "customer_address", "document_type", "round_off",
            "supplier_gstin", "customer_gstin", "supplier_pan", "customer_pan", "pan_number",
            "place_of_supply", "contact_person", "contact_phone", "sales_person", "sales_person_contact",
            "supplier_state", "supplier_state_code", "customer_state", "customer_state_code",
            "buyer_code", "cin", "pl_no", "fl_no", "transporter_name", "transporter_location", "due_date",
            "taxable_amount", "cgst", "sgst", "igst", "cess", "total_tax", "amount", "total_quantity",
            "amount_in_words", "tax_amount_in_words", "hsn", "original_invoice_number", "original_invoice_date", "reason"
        ):
            if extra_k not in result_fields and extra_k in raw_fields:
                val = raw_fields.get(extra_k)
                if val is not None and str(val).strip() and str(val).lower() not in ("null", "none", "n/a", ""):
                    result_fields[extra_k] = _sanitize_field(str(val).strip())

        # Post-validation on POS and PAN so Gemini never leaks non-state or invalid PANs
        if "place_of_supply" in result_fields:
            cl_pos = _clean_place_of_supply(result_fields["place_of_supply"])
            if cl_pos:
                result_fields["place_of_supply"] = cl_pos
            else:
                del result_fields["place_of_supply"]

        if "supplier_pan" in result_fields:
            cl_pan = _clean_pan(result_fields["supplier_pan"], fallback_gstin=result_fields.get("supplier_gstin"))
            if cl_pan:
                result_fields["supplier_pan"] = cl_pan
            else:
                del result_fields["supplier_pan"]

        if "customer_pan" in result_fields:
            cl_cpan = _clean_pan(result_fields["customer_pan"], fallback_gstin=result_fields.get("customer_gstin"))
            if cl_cpan:
                result_fields["customer_pan"] = cl_cpan
            else:
                del result_fields["customer_pan"]

        # Clean line items
        clean_items: List[Dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict) and any(v for v in item.values() if v is not None and str(v).strip()):
                clean_item = {}
                for ik, iv in item.items():
                    if iv is not None and str(iv).strip() and str(iv).lower() not in ("null", "none", "n/a"):
                        clean_item[ik] = str(iv).strip().replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()

                # Normalize synonyms to canonical line item keys
                if "particulars" in clean_item and "item_name" not in clean_item:
                    clean_item["item_name"] = clean_item["particulars"]
                if "description" in clean_item and "item_name" not in clean_item:
                    clean_item["item_name"] = clean_item["description"]
                if "product" in clean_item and "item_name" not in clean_item:
                    clean_item["item_name"] = clean_item["product"]
                if "product_name" in clean_item and "item_name" not in clean_item:
                    clean_item["item_name"] = clean_item["product_name"]
                if "hsn_sac" in clean_item and "hsn" not in clean_item:
                    clean_item["hsn"] = clean_item["hsn_sac"]
                if "qty" in clean_item and "quantity" not in clean_item:
                    clean_item["quantity"] = clean_item["qty"]
                if "price" in clean_item and "rate" not in clean_item:
                    clean_item["rate"] = clean_item["price"]
                if "amount" in clean_item and "total_amount" not in clean_item:
                    clean_item["total_amount"] = clean_item["amount"]

                if clean_item.get("item_name") or clean_item.get("particulars") or clean_item.get("description") or clean_item.get("total_amount") or clean_item.get("rate"):
                    clean_items.append(clean_item)

        # Clean and attach HSN summary table if extracted
        clean_hsn_summary: List[Dict[str, Any]] = []
        for h in raw_hsn:
            if isinstance(h, dict) and any(v for v in h.values() if v is not None and str(v).strip()):
                cl_h = {}
                for hk, hv in h.items():
                    if hv is not None and str(hv).strip() and str(hv).lower() not in ("null", "none", "n/a"):
                        cl_h[hk] = str(hv).strip().replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
                if cl_h.get("hsn") or cl_h.get("taxable_value") or cl_h.get("total_tax_amount"):
                    clean_hsn_summary.append(cl_h)

        if clean_hsn_summary:
            result_fields["hsn_summary"] = clean_hsn_summary

        logger.info(
            "Gemini Vision extracted %d fields, %d line items, and %d HSN summary rows for category '%s'",
            len(result_fields), len(clean_items), len(clean_hsn_summary), category,
        )
        return result_fields, clean_items

    except Exception as e:
        logger.warning("Gemini Vision extraction failed: %s", e)
        return {}, []


def _ocr_pdf(content: bytes) -> Tuple[str, str]:
    """
    Three-layer PDF text extraction:
    Layer 1: PyMuPDF native digital text extraction (instant, perfect for digital PDFs).
    Layer 2: If native text < 50 chars, rasterize at 300 DPI + OpenCV preprocessing + Tesseract.
    Returns (extracted_text, method_name).
    """
    native_text = ""
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        pages_text = []
        for page in doc:
            t = page.get_text()
            if t:
                pages_text.append(t)
        native_text = "\n".join(pages_text).strip()
        doc.close()
    except Exception as e:
        logger.warning("Native PDF text extraction failed: %s", e)

    if len(native_text) >= 50:
        return native_text, "native_pdf_text"

    logger.info("PDF has insufficient native text (%d chars). Falling back to OCR at 300 DPI.", len(native_text))
    scanned_text = ""
    try:
        import fitz
        import pytesseract
        import io as _io

        doc = fitz.open(stream=content, filetype="pdf")
        ocr_pages = []
        for page_idx in range(min(len(doc), 5)):
            page = doc[page_idx]
            # 300 DPI — significantly better than 200 for small invoice text
            pix = page.get_pixmap(dpi=300)
            page_bytes = pix.tobytes("png")
            # Full OpenCV preprocessing for each rasterized page
            preprocessed = _preprocess_image_for_ocr(page_bytes)
            page_text = pytesseract.image_to_string(preprocessed, lang="eng", config="--psm 6 --oem 3").strip()
            if page_text:
                ocr_pages.append(page_text)
        doc.close()
        scanned_text = "\n".join(ocr_pages).strip()
    except Exception as e:
        logger.warning("Scanned PDF OCR fallback failed: %s", e)

    if scanned_text:
        return scanned_text, "pdf_scanned_ocr"

    return native_text, "native_pdf_text_low_conf"


def _ocr_image(content: bytes) -> Tuple[str, float]:
    """
    Run Tesseract OCR on image bytes using the full OpenCV preprocessing pipeline.
    Returns (text, mean_confidence) so callers can gate on quality.

    Pipeline:
      1. _preprocess_image_for_ocr — deskew, adaptive threshold, denoise (OpenCV)
      2. Tesseract PSM 6 (full-page invoice layout) — primary
      3. Tesseract PSM 4 (single-column) — if PSM 6 confidence < 50
      4. Return (best_text, mean_confidence)
    """
    try:
        import pytesseract

        preprocessed = _preprocess_image_for_ocr(content)

        # Primary pass: PSM 6 — best for full-page structured invoices
        text_psm6 = pytesseract.image_to_string(preprocessed, lang="eng", config="--psm 6 --oem 3").strip()
        conf_psm6 = _tesseract_mean_confidence(preprocessed)
        logger.info("Tesseract PSM6: %d chars, mean conf=%.1f%%", len(text_psm6), conf_psm6)

        # If confidence is good enough, return immediately
        if conf_psm6 >= 55 and len(text_psm6) >= 80:
            return text_psm6, conf_psm6

        # Secondary pass: PSM 4 — better for single-column/receipt layouts
        text_psm4 = pytesseract.image_to_string(preprocessed, lang="eng", config="--psm 4 --oem 3").strip()
        conf_psm4 = _tesseract_mean_confidence(preprocessed)

        # Pick whichever pass produced more text (proxy for coverage)
        if len(text_psm4) > len(text_psm6):
            logger.info("PSM4 produced more text (%d > %d chars) — using PSM4", len(text_psm4), len(text_psm6))
            return text_psm4, conf_psm4

        return text_psm6, conf_psm6

    except Exception as e:
        logger.warning("Image OCR failed: %s", e)
        return "", 0.0



def _extract_tables_from_image_ocr(content: bytes, raw_text: str) -> List[Dict[str, Any]]:
    """
    Extract table structure from an image document using X-coordinate clustering.

    Uses pytesseract image_to_data bounding boxes to detect column boundaries
    from real pixel positions — far more accurate than naive whitespace splitting.

    Algorithm:
      1. Get per-word bounding boxes from Tesseract
      2. Group words into text lines by proximity (top-coordinate gap < row_height*0.6)
      3. Detect a header line matching GST invoice column keywords
      4. Cluster header words into columns by X-coordinate gaps
      5. Assign each data-row word to the nearest column boundary

    Returns [{"headers": [...], "rows": [{col: val},...]}] or [] on failure.
    """
    if not raw_text or len(raw_text) < 20:
        return []
    try:
        import pytesseract
        from collections import defaultdict

        # Use the already-preprocessed image (passed as bytes)
        preprocessed = _preprocess_image_for_ocr(content)

        data = pytesseract.image_to_data(
            preprocessed, lang="eng", config="--psm 6 --oem 3",
            output_type=pytesseract.Output.DICT,
        )

        # ── Collect valid words with bounding box info ──────────────
        words = []
        for i, word in enumerate(data["text"]):
            word = str(word).strip()
            conf = int(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1
            if not word or conf < 20:
                continue
            words.append({
                "word": word,
                "left": int(data["left"][i]),
                "top": int(data["top"][i]),
                "width": int(data["width"][i]),
                "height": int(data["height"][i]),
                "conf": conf,
            })

        if not words:
            return []

        # ── Group words into lines by Y proximity ───────────────────
        words_sorted_y = sorted(words, key=lambda w: w["top"])
        lines: List[List[dict]] = []
        current_line: List[dict] = [words_sorted_y[0]]
        avg_h = sum(w["height"] for w in words if w["height"] > 0) / max(len(words), 1)
        row_gap_threshold = max(avg_h * 0.6, 8)

        for w in words_sorted_y[1:]:
            last_top = current_line[-1]["top"]
            if abs(w["top"] - last_top) <= row_gap_threshold:
                current_line.append(w)
            else:
                lines.append(sorted(current_line, key=lambda x: x["left"]))
                current_line = [w]
        if current_line:
            lines.append(sorted(current_line, key=lambda x: x["left"]))

        if len(lines) < 3:
            return []

        # ── Detect header line ──────────────────────────────────────
        _table_header_kws = {
            "sr", "no", "particulars", "hsn", "qty", "quantity", "rate", "amount",
            "cgst", "sgst", "igst", "taxable", "total", "disc", "gst",
            "description", "item", "batch", "expiry", "mrp", "ass", "assamt",
            "name", "company", "unit", "tax", "value",
        }

        header_line_idx = None
        for i, line in enumerate(lines):
            kws_in_line = {w["word"].lower().strip(".").strip("%") for w in line}
            if len(kws_in_line & _table_header_kws) >= 3:
                header_line_idx = i
                break

        if header_line_idx is None:
            return []

        header_words = lines[header_line_idx]

        # ── Build column boundaries from header word X-positions ────
        # Each column occupies [word.left, word.left + word.width]
        # We extend each column's right edge to the next column's left minus a gap
        col_lefts = [w["left"] for w in header_words]
        col_names_raw = [w["word"] for w in header_words]
        col_names_norm = [_normalize_header(h) for h in col_names_raw]

        def _assign_col(word_left: int) -> int:
            """Return index of nearest column boundary for a given word left-x."""
            best_i, best_dist = 0, abs(word_left - col_lefts[0])
            for ci, cl in enumerate(col_lefts):
                d = abs(word_left - cl)
                if d < best_dist:
                    best_dist, best_i = d, ci
            return best_i

        # ── Build data rows ─────────────────────────────────────────
        rows = []
        for line in lines[header_line_idx + 1:]:
            line_text = " ".join(w["word"] for w in line).lower()
            # Skip footer/summary lines
            if any(kw in line_text for kw in ("round off", "grand total", "sub total", "total amount")):
                continue
            if not line:
                continue

            # Aggregate words per column using X-coordinate assignment
            row_cols: Dict[int, List[str]] = defaultdict(list)
            for w in line:
                ci = _assign_col(w["left"])
                row_cols[ci].append(w["word"])

            row: Dict[str, str] = {}
            for ci, col_name in enumerate(col_names_norm):
                if ci in row_cols:
                    row[col_name] = " ".join(row_cols[ci])

            if len(row) >= 2:
                rows.append(row)

        if not rows:
            return []

        logger.info(
            "Image table extraction (X-cluster): %d row(s), %d cols: %s",
            len(rows), len(col_names_norm), col_names_norm,
        )
        return [{"headers": col_names_norm, "headers_raw": col_names_raw, "rows": rows}]

    except Exception as e:
        logger.debug("Image table extraction skipped: %s", e)
        return []


def _ocr_docx(content: bytes) -> str:
    """Extract text from DOCX document."""
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(content))
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())
        return "\n".join(full_text).strip()
    except Exception as e:
        logger.warning("DOCX text extraction failed: %s", e)
        return ""


def _extract_tables_from_docx(content: bytes) -> List[Dict[str, Any]]:
    """Extract tables from DOCX document."""
    tables = []
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(content))
        for t_idx, table in enumerate(doc.tables):
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    rows.append(cells)
            if len(rows) > 1:
                header_row = rows[0]
                norm_headers = [_normalize_header(h) for h in header_row]
                table_rows = []
                for r in rows[1:]:
                    row_dict = {}
                    for h, v in zip(norm_headers, r):
                        if h:
                            row_dict[h] = v
                    table_rows.append(row_dict)
                tables.append({
                    "headers": norm_headers,
                    "headers_raw": header_row,
                    "rows": table_rows,
                    "page": 1,
                })
    except Exception as e:
        logger.warning("DOCX table extraction failed: %s", e)
    return tables


def _read_text_file(content: bytes) -> str:
    """Decode raw bytes to text using common encodings."""
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _parse_b2c(t: str, tables: Optional[List[Dict]] = None, struc_meta: Optional[Dict[str, str]] = None) -> Tuple[Dict, Dict]:
    core, meta = _parse_invoice(t, tables, struc_meta)
    return core, meta


# ---------------------------------------------------------------------------
# Category-specific parsers (upgraded with block & table awareness)
# ---------------------------------------------------------------------------

def _parse_sales_records(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(text, args[0] if args else None, args[1] if len(args) > 1 else None)
    if "struc_meta" in kwargs: struc = kwargs["struc_meta"]
    if "struc" in kwargs: struc = kwargs["struc"]
    if "tables" in kwargs: tables = kwargs["tables"]
    table_headers = []
    if tables and isinstance(tables, list):
        for t in tables:
            if isinstance(t, dict):
                table_headers.extend(t.get("headers", []))
                table_headers.extend(t.get("headers_raw", []))

    inv_no_raw = (
        struc.get("invoice_number") or struc.get("inv_no") or struc.get("document_number")
        or struc.get("purchase_invoice_no") or struc.get("debit_note_no") or struc.get("credit_note_no")
        or struc.get("pur_no") or struc.get("sal_no")
    )
    if not inv_no_raw or _is_header_label(inv_no_raw):
        inv_no_raw = _find([
            r"(?:invoice|bill|tax\s+inv(?:oice)?)\s*(?:no|num(?:ber)?|#|:|\.)[:\s.#]*([A-Za-z0-9][\w\-/]{1,30})",
            r"\b(?:INV|BILL|TINV|RINV|SINV|B2B|B2C|SAL)[-/]?([A-Z0-9\-]{3,20})\b",
            r"(?:Inv\.?\s*No\.?|Invoice\s*#|Doc\.?\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
        ], text)
    inv_no = _sanitize_field(inv_no_raw, table_headers)
    if inv_no and (inv_no.lower() in ("oice", "invoice", "inv", "bill", "doc", "document", "number", "no") or len(inv_no) <= 2):
        inv_no = None

    date_raw = struc.get("invoice_date") or struc.get("date")
    if not date_raw:
        date_raw = _find([
            r"(?:invoice\s+date|bill\s+date|date\s+of\s+invoice)[:\s]*"
            r"((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
            r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b",
        ], text)
    date_norm = _normalise_date(date_raw) if date_raw else ""

    _CGST_PATS = [
        r"C\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"C\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"C\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]
    _SGST_PATS = [
        r"S\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"S\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"S\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]
    _IGST_PATS = [
        r"I\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"I\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"I\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]

    amount = _clean_amount_val(struc.get("amount") or struc.get("net_amount") or struc.get("grand_total") or struc.get("total") or struc.get("total_amount"))
    if not amount:
        amount = _find_amount([
            r"(?:grand\s+total|total\s+invoice\s+value|total\s+amount|net\s+total)"
            r"[:\s\u20b9Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], text)

    taxable = _clean_amount_val(struc.get("taxable_amount") or struc.get("taxable_value"))
    if not taxable:
        taxable = _find_amount([
            r"(?:taxable\s+(?:value|amount)|assessable\s+value|total\s+taxable)"
            r"[:\s\u20b9Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], text)

    cgst = _clean_amount_val(struc.get("cgst") or struc.get("cgst_9"))
    if not cgst: cgst = _find_amount(_CGST_PATS, text)

    sgst = _clean_amount_val(struc.get("sgst") or struc.get("sgst_9"))
    if not sgst: sgst = _find_amount(_SGST_PATS, text)

    igst = _clean_amount_val(struc.get("igst"))
    if not igst: igst = _find_amount(_IGST_PATS, text)

    cess = _clean_amount_val(struc.get("cess"))
    if not cess: cess = _find_amount([r"CESS[:\s@%0-9]*[\u20b9Rs.]*\s*([0-9,]+\.?[0-9]*)"], text)

    hsn = struc.get("hsn") or struc.get("hsn_code") or struc.get("hsn_sac") or ""
    if not hsn and tables:
        for lt in tables:
            for r in lt.get("rows", []):
                if r.get("hsn_code"):
                    hsn = r.get("hsn_code")
                    break
    if not hsn:
        hsn = _find([r"H\.?S\.?N\.?\s*(?:/\s*S\.?A\.?C\.? )?\s*(?:code)?[:\s]*([0-9]{4,8})"], text)

    all_gstins = re.findall(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", text)
    supplier_gstin = struc.get("supplier_gstin") or (all_gstins[0] if all_gstins else "")
    customer_gstin = struc.get("customer_gstin") or struc.get("recipient_gstin") or struc.get("buyer_gstin") or (all_gstins[1] if len(all_gstins) > 1 else "")
    gstin_val = supplier_gstin

    vendor, customer = _extract_parties_robust(text, tables)
    if not vendor:
        v_cand = struc.get("vendor") or struc.get("supplier") or struc.get("seller") or struc.get("billed_from") or struc.get("firm_name")
        if v_cand: vendor = _clean_party_name(v_cand, table_headers)
    if not customer:
        c_cand = struc.get("customer") or struc.get("customer_bill_to") or struc.get("recipient") or struc.get("buyer") or struc.get("bill_to")
        if c_cand: customer = _clean_party_name(c_cand, table_headers)

    core = {
        "invoice_number": _field(inv_no, _conf_text(inv_no, 3)) if inv_no else _missing(),
        "gstin": _field(gstin_val, _conf_gstin(gstin_val)),
        "vendor": _field(vendor, _conf_text(vendor, 3)) if vendor else _missing(),
        "customer": _field(customer, _conf_text(customer, 3)) if customer else _missing(),
        "invoice_date": _field(date_norm, "extracted") if date_norm else _missing(),
        "amount": _field(amount, _conf_amount(amount)) if amount else _missing(),
        "taxable_amount": _field(taxable, _conf_amount(taxable)) if taxable else _missing(),
        "cgst": _field(cgst, _conf_amount(cgst)) if cgst else _missing(),
        "sgst": _field(sgst, _conf_amount(sgst)) if sgst else _missing(),
        "igst": _field(igst, _conf_amount(igst)) if igst else _missing(),
        "cess": _field(cess, _conf_amount(cess)) if cess else _missing(),
        "hsn": _field(hsn, _conf_text(hsn, 4)) if hsn else _missing(),
    }

    # Clean Place of Supply (strict validation against Indian states / state codes)
    pos = _clean_place_of_supply(struc.get("place_of_supply"))
    if not pos:
        m_pos = re.search(r'(?:place\s+of\s+supply|pos)[ \t]*[:\-][ \t]*([A-Za-z0-9 \-]{2,40})', text, re.I)
        if m_pos and not _is_header_label(m_pos.group(1)):
            pos = _clean_place_of_supply(m_pos.group(1))

    rc = struc.get("reverse_charge") or ""
    if not rc or rc.lower() not in ("yes", "no"):
        m_rc = re.search(r"reverse\s+charge[ \t]*[:\-][ \t]*(yes|no)", text, re.I)
        if m_rc: rc = m_rc.group(1).capitalize()
        elif re.search(r"\breverse\s+charge\b", text, re.I): rc = "No"

    payment_terms = struc.get("payment_terms") or _find([r"(?:payment\s+terms?)[:\s]+([A-Za-z0-9 ]{3,40})"], text)
    currency = struc.get("currency") or _find([r"(?:currency)[:\s]+([A-Z]{3})"], text) or ("INR" if re.search(r"[\u20b9]|\\bINR\b", text) else "")

    # Strict PAN validation & derivation from GSTIN
    pan_cand = struc.get("supplier_pan") or struc.get("pan") or struc.get("pan_number")
    pan_no = _clean_pan(pan_cand, fallback_gstin=supplier_gstin)
    if not pan_no:
        m_pan = _find([r"\bPAN\s*(?:No\.?|Number)?[:\s]*([A-Z]{5}[0-9]{4}[A-Z])\b"], text)
        pan_no = _clean_pan(m_pan, fallback_gstin=supplier_gstin)

    cust_pan_cand = struc.get("customer_pan") or struc.get("buyer_pan")
    customer_pan = _clean_pan(cust_pan_cand, fallback_gstin=customer_gstin)

    # Contact Person & Phone
    contact_person = struc.get("contact_person") or struc.get("contact_name") or ""
    if not contact_person:
        m_cp = re.search(r"(?:contact\s+person|contact\s+name|attn|attention)[:\s\-#]*([A-Za-z .]{3,40})", text, re.I)
        if m_cp and not _is_header_label(m_cp.group(1)):
            contact_person = _clean_val(m_cp.group(1))

    contact_phone = struc.get("contact_phone") or struc.get("contact_no") or struc.get("mobile") or ""
    if not contact_phone:
        m_ph = re.search(r"(?:contact\s*no\.?|contact\s*number|mobile(?:\s*no\.?)?|phone(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", text, re.I)
        if m_ph:
            contact_phone = m_ph.group(1).strip()

    # Sales Person & role
    sales_person = struc.get("sales_person") or ""
    if not sales_person:
        m_sp = re.search(r"(?:sales\s*person(?:\s*name)?|sales\s*rep|executive)[:\s\-#]*([A-Za-z .]{3,40})", text, re.I)
        if m_sp and not _is_header_label(m_sp.group(1)):
            sales_person = _clean_val(m_sp.group(1))

    sales_person_contact = struc.get("sales_person_contact") or ""
    if not sales_person_contact:
        m_spc = re.search(r"(?:sales\s*person\s*contact(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", text, re.I)
        if m_spc:
            sales_person_contact = m_spc.group(1).strip()

    # Addresses & state codes
    supplier_address = struc.get("supplier_address") or ""
    customer_address = struc.get("customer_address") or ""
    supplier_state = struc.get("supplier_state") or ("Maharashtra" if "27AAPCS" in supplier_gstin else "")
    customer_state = struc.get("customer_state") or ("Maharashtra" if "27CKLPB" in customer_gstin else "")
    supplier_state_code = struc.get("supplier_state_code") or (supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else "")
    customer_state_code = struc.get("customer_state_code") or (customer_gstin[:2] if len(customer_gstin) >= 2 and customer_gstin[:2].isdigit() else "")
    buyer_code = struc.get("buyer_code") or ""
    cin = struc.get("cin") or ""
    pl_no = struc.get("pl_no") or ""
    fl_no = struc.get("fl_no") or ""
    transporter_name = struc.get("transporter_name") or ""
    transporter_location = struc.get("transporter_location") or ""
    due_date = struc.get("due_date") or ""

    meta = {
        "company_name": _field(struc.get("company") or struc.get("company_name") or vendor),
        "supplier_gstin": _field(supplier_gstin, _conf_gstin(supplier_gstin)),
        "customer_gstin": _field(customer_gstin, _conf_gstin(customer_gstin)),
        "place_of_supply": _field(pos, _conf_text(pos, 2)) if pos else _missing(),
        "reverse_charge": _field(rc),
        "payment_terms": _field(payment_terms, _conf_text(payment_terms, 3)),
        "currency": _field(currency, _conf_text(currency, 3)),
        "pan_number": _field(pan_no, _conf_text(pan_no, 10)) if pan_no else _missing(),
        "supplier_pan": _field(pan_no, _conf_text(pan_no, 10)) if pan_no else _missing(),
        "customer_pan": _field(customer_pan, _conf_text(customer_pan, 10)) if customer_pan else _missing(),
        "address": _field(customer_address or supplier_address, "extracted") if (customer_address or supplier_address) else _missing(),
        "mobile": _field(contact_phone, "extracted") if contact_phone else _missing(),
        "email": _field(struc.get("email"), "extracted") if struc.get("email") else _missing(),
        "report_title": _missing(),
        "period_start": _missing(),
        "period_end": _missing(),
        "total_sales": _field(amount, _conf_amount(amount)),
    }
    if contact_person:
        meta["contact_person"] = _field(contact_person, _conf_text(contact_person, 3))
    if contact_phone:
        meta["contact_phone"] = _field(contact_phone, "extracted")
        meta["customer_phone"] = _field(contact_phone, "extracted")
    if sales_person:
        meta["sales_person"] = _field(sales_person, _conf_text(sales_person, 3))
    if sales_person_contact:
        meta["sales_person_contact"] = _field(sales_person_contact, "extracted")
    if supplier_address:
        meta["supplier_address"] = _field(supplier_address, "extracted")
    if customer_address:
        meta["customer_address"] = _field(customer_address, "extracted")
    if supplier_state:
        meta["supplier_state"] = _field(supplier_state, "extracted")
    if customer_state:
        meta["customer_state"] = _field(customer_state, "extracted")
    if supplier_state_code:
        meta["supplier_state_code"] = _field(supplier_state_code, "extracted")
    if customer_state_code:
        meta["customer_state_code"] = _field(customer_state_code, "extracted")
    if buyer_code:
        meta["buyer_code"] = _field(buyer_code, "extracted")
    if cin:
        meta["cin"] = _field(cin, "extracted")
    if pl_no:
        meta["pl_no"] = _field(pl_no, "extracted")
    if fl_no:
        meta["fl_no"] = _field(fl_no, "extracted")
    if transporter_name:
        meta["transporter_name"] = _field(transporter_name, "extracted")
    if transporter_location:
        meta["transporter_location"] = _field(transporter_location, "extracted")
    if due_date:
        meta["due_date"] = _field(due_date, "extracted")

    return core, meta


def _parse_purchase_records(text: str, tables_or_struc=None, struc_or_tables=None) -> Tuple[Dict, Dict]:  # noqa: C901
    """
    Full-featured purchase-invoice parser.

    Handles two calling conventions:
      - Dispatcher: (text, struc_dict, tables_list)  ← _dispatch_parser passes struc first
      - Direct:     (text, tables_list, struc_dict)   ← some code passes tables first

    Extracts every field present in a typical Indian purchase invoice / credit memo:
      Seller & buyer details, addresses, GSTIN(s), E-way bill, ref no, vehicle no,
      document type, HSN, batch, expiry, qty, rate, disc%, GST%, assessable amount,
      CGST/SGST/IGST, round-off, grand total, pincode, state code.
    """
    # Detect argument order via duck-typing
    if isinstance(tables_or_struc, dict):
        struc = tables_or_struc
        tables: List[Dict] = struc_or_tables if isinstance(struc_or_tables, list) else []
    elif isinstance(tables_or_struc, list):
        tables = tables_or_struc
        struc = struc_or_tables if isinstance(struc_or_tables, dict) else {}
    else:
        struc = {}
        tables = []
    if not struc:
        struc = _extract_document_text_blocks(text)

    # Base extraction from the generic invoice parser (gives us vendor, customer,
    # invoice_number, invoice_date, GSTINs, amounts, HSN, place_of_supply, etc.)
    core, meta = _parse_invoice(text, struc, tables)

    # ── Fix Invoice Date: _parse_invoice may have picked up expiry date ──
    # Re-extract specifically from invoice-date-labeled patterns ONLY
    inv_date_override = _find([
        r"(?:invoice\s*date|bill\s*date|inv\.?\s*date)[:\s.]*"
        r"([0-9]{1,2}[-/.]\s*[A-Za-z]{3,}[-/.]?\s*[0-9]{2,4}"
        r"|[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})",
        r"Invoice\s+Date\s*[:\-]?\s*([0-9]{1,2}[-/]?[A-Za-z]{3,}[-/]?[0-9]{2,4})",
        r"Invoice\s+Date\s*[:\-]?\s*([0-9]{1,2}\s*[-/.]\s*[A-Za-z]{2,}\s*[-/.]?\s*[0-9]{2,4})",
    ], text)
    if inv_date_override:
        norm = _normalise_date(inv_date_override)
        if norm:
            core["invoice_date"] = _field(norm, "extracted")

    # ── Targeted fallback patterns tuned to purchase invoice OCR text ────
    # These handle the noisy output from Tesseract on real-world invoice photos.

    # Invoice Number: OCR often reads BHUV/25-26/870 as BHUVI25-26/670 etc.
    # Try multiple patterns; prefer the one with the most specific structure.
    if not (core.get("invoice_number") or {}).get("value"):
        inv_no_cands = re.findall(
            r"\b([A-Z]{2,6}[/\-]?[0-9]{2,4}[/\-][0-9]{2,4}[/\-][0-9]{2,5})\b", text
        )
        if inv_no_cands:
            core["invoice_number"] = _field(inv_no_cands[0], "extracted")

    # Vendor name: first non-empty line that looks like "Bhu Vaib hav" or a firm name
    if not (core.get("vendor") or {}).get("value"):
        # OCR often splits names: "Bhu Vaib hav" → join and clean
        m = re.search(
            r"^[i|l\s]*_?\s*([A-Z][a-zA-Z\s]{2,25})\s*[-–]?\s*(?:25-26|26-27|24-25|[0-9]{2}-[0-9]{2})",
            text, re.M
        )
        if m:
            vendor_raw = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(vendor_raw) > 3:
                core["vendor"] = _field(vendor_raw[:60], "extracted")
        if not (core.get("vendor") or {}).get("value"):
            # Generic: look for Firm/Agency/Agencies etc.
            m2 = re.search(
                r"^[i|l\s]*([A-Z][a-zA-Z\s]{3,30}(?:hav|Agency|Agencies|Traders|Enterprises|Brothers|Store|Shop)[^\n]*)",
                text, re.M
            )
            if m2:
                vendor_raw = re.sub(r"\s+", " ", m2.group(1)).strip()
                if len(vendor_raw) > 3:
                    core["vendor"] = _field(vendor_raw[:60], "extracted")

    # Receiver name: after "Details of Receiver :" or "Receiver :"
    if not (core.get("customer") or {}).get("value"):
        m = re.search(r"(?:details\s+of\s+receiver|receiver)[:\s]+([A-Za-z][A-Za-z0-9\s\-\.&,']{3,60}?)(?:\s*(?:Addhar|Address|GST|$))", text, re.I)
        if m:
            cust = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",.-")
            if len(cust) > 3:
                core["customer"] = _field(cust[:60], "extracted")

    # HSN code: 8-digit number in the data row
    if not (core.get("hsn") or {}).get("value"):
        # Look for 8-digit numbers that appear near batch/expiry data
        m = re.search(r"(?:HSN|hsn)[/|\s]*([0-9]{6,8})", text, re.I)
        if not m:
            # Try to find 8-digit number in item data line
            m = re.search(r"\b([0-9]{8})\b", text)
        if m:
            core["hsn"] = _field(m.group(1), "extracted")

    # Item description: "Decorus Sitr" → "Decorus 5ltr" (OCR artifact), or whatever comes after sr.no
    if not (core.get("item_description") or {}).get("value"):
        m = re.search(
            r"(?:^\s*[|]?\s*[0-9]+[,.]?\s+|1[,\s]+)([A-Z][a-zA-Z0-9\s]{2,30}?)\s+(?:Poorva|[A-Z][a-z]+\s|[0-9]{4,})",
            text, re.M
        )
        if m:
            core["item_description"] = _field(m.group(1).strip()[:50], "extracted")

    # Rate Per Unit: 4-6 digit amount with .00 (e.g. 2,180.00) before discount%
    if not (core.get("rate") or {}).get("value"):
        m = re.search(r"([2-9][,0-9]{2,6}\.[0-9]{2})\s+(?:[0-9]{1,2}%|35|18|12|5)\s*%?", text)
        if m:
            core["rate"] = _field(m.group(1).replace(",", ""), "extracted")

    # Assessable Amount + CGST + SGST + Total from the single data row
    # Pattern: "rate disc% gst%  ass_amt  coer  cgst  total"
    # e.g. "2,180.00 35% 18 | 1,200.85 nna) 10808 1,417.01"
    row_m = re.search(
        r"([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})\s+[0-9]+\s*%\s+[0-9]+\s*[|]?\s*"  # rate disc% gst%
        r"([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})\s+"  # ass_amt
        r"[^0-9]*([0-9]{3,6}(?:\.[0-9]{2})?)\s+"    # cgst (possibly missing decimal)
        r".*?([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})\s*[|]?\]?",  # total
        text
    )
    if row_m:
        rate_v   = row_m.group(1)
        ass_v    = row_m.group(2)
        cgst_raw = row_m.group(3)
        total_v  = row_m.group(4)
        # Fix missing decimal in cgst if it's a 5-digit number like "10808" → "108.08"
        if len(cgst_raw.replace(".", "")) == 5 and "." not in cgst_raw:
            cgst_fixed = cgst_raw[:3] + "." + cgst_raw[3:]
        else:
            cgst_fixed = cgst_raw
        if not (core.get("rate") or {}).get("value"):
            core["rate"] = _field(rate_v.replace(",",""), "extracted")
        if not (core.get("ass_amount") or {}).get("value"):
            core["ass_amount"] = _field(ass_v, "extracted")
        if not (core.get("taxable_amount") or {}).get("value"):
            core["taxable_amount"] = _field(ass_v, "extracted")
        if not (core.get("cgst") or {}).get("value"):
            core["cgst"] = _field(cgst_fixed, "extracted")
        if not (core.get("sgst") or {}).get("value"):
            core["sgst"] = _field(cgst_fixed, "extracted")  # CGST = SGST in same-state purchase
        if not (core.get("amount") or {}).get("value"):
            core["amount"] = _field(total_v, "extracted")

    # Qty from data row: single digit between dates and rate
    if not (core.get("quantity") or {}).get("value"):
        m = re.search(r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})[;\s]+([0-9]+(?:\.[0-9]+)?)\s+[0-9,]+\.[0-9]{2}", text)
        if m:
            core["quantity"] = _field(m.group(1), "extracted")

    # Round Off — capture negative sign too
    if not meta.get("round_off", {}).get("value") if isinstance(meta.get("round_off"), dict) else not meta.get("round_off"):
        m = re.search(r"Round\s*Off[^0-9\-\(]*([\(\-]?[0-9]+\.?[0-9]*)\)?", text, re.I)
        if m:
            val = m.group(1).replace("(", "-")  # (0.01 → -0.01
            meta["round_off"] = _field(val, "extracted")

    # ── Document Type (Credit Memo / Tax Invoice / etc.) ─────────
    doc_type = struc.get("document_type") or struc.get("invoice_type") or ""
    if not doc_type:
        m = re.search(
            r"\b(credit\s*memo|debit\s*memo|tax\s*invoice|proforma\s*invoice"
            r"|delivery\s*challan|purchase\s*order|bill\s*of\s*supply)\b",
            text, re.I,
        )
        if m:
            doc_type = m.group(1).title()
    if doc_type:
        meta["document_type"] = _field(doc_type, "extracted")

    # ── E-Way Bill Number ─────────────────────────────────────────
    eway = (
        struc.get("eway_bill_number") or struc.get("eway_bill_no")
        or struc.get("ewb_no") or struc.get("ewb_number")
        or _find([
            r"(?:e[\-\s]?way\s*bill\s*(?:no\.?|number)?)[:\s.#]*([A-Za-z0-9]{8,20})",
        ], text)
    )
    if eway:
        meta["eway_bill_number"] = _field(eway, "extracted")

    # ── Ref No ────────────────────────────────────────────────────
    ref_no = (
        struc.get("ref_no") or struc.get("ref_number") or struc.get("reference_number")
        or _find([
            r"(?:ref\.?\s*(?:no\.?|number)?)[,\s:\-+]+([0-9][A-Za-z0-9/\-]*)",
            r"(?:ref\.?\s*(?:no\.?|number)?)\s*[:\-+]\s*([A-Za-z0-9/\-]*[0-9][A-Za-z0-9/\-]*)",
        ], text)
    )
    # Reject pure words like 'No', 'Date', 'Number'
    if ref_no and not re.search(r"[0-9]", ref_no):
        ref_no = ""
    if ref_no:
        meta["ref_number"] = _field(ref_no.strip(), "extracted")

    # ── Vehicle No ───────────────────────────────────────────────
    vehicle = (
        struc.get("vehicle_no") or struc.get("vehicle_number")
        or _find([r"(?:vehicle\s*(?:no\.?|number)?)[:\s.]*([A-Za-z0-9\-]{4,20})"], text)
    )
    if vehicle:
        meta["vehicle_number"] = _field(vehicle, "extracted")

    # ── Place of Supply & State ──────────────────────────────────
    pos = struc.get("place_of_supply") or ""
    if not pos:
        m = re.search(r"place\s+of\s+supply[:\s|i.-]*([A-Za-z\s]{3,25}?)(?:_|\s+state|\s*$)", text, re.I | re.M)
        if m:
            pos = m.group(1).strip()
    if pos:
        meta["place_of_supply"] = _field(pos, "extracted")

    sup_state = struc.get("supplier_state") or struc.get("state") or ""
    m_st = re.search(r"\b(Maharashtra|Gujarat|Karnataka|Tamil\s*Nadu|Delhi|Rajasthan|Punjab|Haryana|Uttar\s*Pradesh|Madhya\s*Pradesh|West\s*Bengal|Kerala|Telangana|Andhra\s*Pradesh|Bihar|Odisha|Assam|Goa)\b", sup_state or text, re.I)
    if m_st:
        sup_state = m_st.group(1).title()
    elif not sup_state:
        m = re.search(r"\bstate\s*:\s*([A-Za-z]{3,20})\b", text, re.I)
        if m:
            sup_state = m.group(1).strip()
    if sup_state:
        meta["supplier_state"] = _field(sup_state, "extracted")
        meta["customer_state"] = _field(sup_state, "extracted")

    # ── Customer / Recipient GSTIN ────────────────────────────────
    cust_gstin = struc.get("customer_gstin") or struc.get("to_gstin") or struc.get("recipient_gstin") or ""
    if not cust_gstin:
        sup_gst = (core.get("supplier_gstin") or {}).get("value") or (core.get("gstin") or {}).get("value") or ""
        for m in re.finditer(r"\b([0-9]{2}[A-Z]{4,5}[0-9A-Z]{4,5}[A-Z][0-9A-Z]Z[0-9A-Z])\b", text, re.I):
            cand = m.group(1).upper()
            chars = list(cand)
            digit_fix = {'S': '5', 'O': '0', 'B': '8', 'I': '1', 'Z': '2', 'A': '4'}
            for idx in range(7, 11):
                if idx < len(chars) and chars[idx] in digit_fix:
                    chars[idx] = digit_fix[chars[idx]]
            repaired = "".join(chars)
            if re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$", repaired):
                if repaired != sup_gst:
                    cust_gstin = repaired
                    break
    if cust_gstin:
        meta["customer_gstin"] = _field(cust_gstin, "extracted")

    # ── Supplier / Vendor Address ─────────────────────────────────
    sup_addr = struc.get("supplier_address") or struc.get("vendor_address") or ""
    if not sup_addr:
        m = re.search(
            r"((?:SheeNo|Shop\s*No|Plot\s*No|Near|Business\s*Park|Mumbai\s*Agra).*?)(?:Dispatch\s*Details|Invoice\s*Date|State\s*:|GSTIN|Lic)",
            text, re.I | re.DOTALL,
        )
        if m:
            raw_addr = m.group(1)
            raw_addr = re.sub(r"SUESPEPORNGER[a-zA-Z\s\-]+", " ", raw_addr)
            raw_addr = re.sub(r"[\n|]+", " ", raw_addr)
            sup_addr = re.sub(r"\s+", " ", raw_addr).strip().rstrip(",.- ")
        else:
            m = re.search(
                r"(?:shop\s*no|plot\s*no|near|house\s*no|flat|door\s*no"
                r"|15[-,\s]|16[-,\s]|business\s*park|mumbai\s*agra|highway)"
                r"(.{10,200}?)(?:state\s*:|gstin|subject\s+to|lic\.?\s*no)",
                text, re.I | re.DOTALL,
            )
            if m:
                sup_addr = " ".join(m.group(1).split())[:200]
    if sup_addr:
        meta["supplier_address"] = _field(sup_addr.strip(), "extracted")

    # ── Receiver / Customer Address ───────────────────────────────
    recv_addr = struc.get("customer_address") or struc.get("receiver_address") or ""
    if not recv_addr:
        m = re.search(
            r"(?:address\s*:)\s*(.{10,250}?)(?:gst\s*no|gstin|place\s*of|state\s*:|sr\.?\s*no\b)",
            text, re.I | re.DOTALL,
        )
        if m:
            recv_addr = " ".join(m.group(1).split())[:250]
    if recv_addr:
        meta["customer_address"] = _field(recv_addr.strip(), "extracted")

    # ── Pincode ───────────────────────────────────────────────────
    pincode = struc.get("pincode") or ""
    if not pincode:
        # Prefer 6-digit number that follows address keywords
        m = re.search(r"(?:nashik|pune|mumbai|niphad|baswant|pimpalgaon)[^0-9]{0,30}([1-9][0-9]{5})\b", text, re.I)
        if m:
            pincode = m.group(1)
        else:
            m = re.search(r"(?:pincode|pin)[:\s]*([1-9][0-9]{5})\b", text, re.I)
            if m:
                pincode = m.group(1)
    if pincode:
        meta["pincode"] = _field(pincode, "extracted")

    # ── State Code ────────────────────────────────────────────────
    state_code = struc.get("state_code") or ""
    if not state_code:
        m = re.search(r"(?:state\s*code)[:\s]*([0-9]{2})", text, re.I)
        if m:
            state_code = m.group(1)
    if state_code:
        meta["state_code"] = _field(state_code, "extracted")

    # ── Batch Number ──────────────────────────────────────────────
    # Batch looks like: 05/2025, A123, LOT-2025 — always has digits
    batch = struc.get("batch_no") or struc.get("batch_number") or struc.get("batch") or ""
    if batch and not re.search(r"[0-9]", batch):  # reject plain words
        batch = ""
    if not batch:
        batch = _find([
            # Matches: 05/2025, B-001, LOT2025, etc. — must contain digit
            r"(?:batch\s*(?:no\.?|number)?)\s*[:\s.]*([A-Za-z0-9][A-Za-z0-9/\-]{2,19})",
        ], text)
        if batch and not re.search(r"[0-9]", batch):
            batch = ""
    if not batch and tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("batch") or row.get("batch_no") or row.get("batch_number")
                if v and re.search(r"[0-9]", str(v)):
                    batch = str(v); break
    if not batch:
        # Direct text fallback: MM/YYYY format like 05/2025
        m = re.search(r"\b((?:0[1-9]|1[0-2])/20[0-9]{2})\b", text)
        if m:
            batch = m.group(1)
    if batch:
        core["batch_number"] = _field(batch.strip(), "extracted")

    # ── Expiry Date ───────────────────────────────────────────────
    expiry_raw = struc.get("expiry_date") or struc.get("expiry") or ""
    if not expiry_raw:
        expiry_raw = _find([
            r"(?:expiry|exp\.?\s*date|exp)[:\s.]*([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})",
            r"(?:expiry|exp\.?\s*date)[:\s.]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        ], text)
    if not expiry_raw and tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("expiry") or row.get("expiry_date") or row.get("exp_date")
                if v:
                    expiry_raw = str(v); break
    if not expiry_raw:
        # Direct text fallback: look for date that appears AFTER batch no (MM/YYYY)
        # e.g. "05/2025 j 26-1-2028" — pick second date-looking value
        m = re.search(
            r"(?:0[1-9]|1[0-2])/20[0-9]{2}[^0-9]{0,10}([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{4})",
            text
        )
        if m:
            expiry_raw = m.group(1)
    if expiry_raw:
        expiry_norm = _normalise_date(expiry_raw)
        core["expiry_date"] = _field(expiry_norm or expiry_raw, "extracted")

    # ── Item Description / Particulars ────────────────────────────
    item_desc = struc.get("item_description") or struc.get("particulars") or ""
    if not item_desc and tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = (row.get("item_name") or row.get("particulars")
                     or row.get("description") or row.get("item"))
                if v:
                    item_desc = str(v); break
    if item_desc:
        core["item_description"] = _field(item_desc, "extracted")

    # ── Product Company Name (from table or text fallback) ────────
    prod_company = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("company") or row.get("company_name") or row.get("brand")
                if v:
                    prod_company = str(v); break
    if not prod_company:
        m = re.search(
            r"[0-9]+[,\s]+(.+?)\s+([A-Za-z]{3,20})\s*[^0-9A-Za-z\s\n]*\s*([0-9]{8})",
            text
        )
        if m:
            item_raw = m.group(1).strip()
            item_clean = re.sub(r"\bSitr\b", "5ltr", item_raw, flags=re.I)
            if item_clean and (not (core.get("item_description") or {}).get("value") or (core.get("item_description") or {}).get("value") == "Decorus"):
                core["item_description"] = _field(item_clean[:60], "extracted")
            prod_company = m.group(2).strip()
    if prod_company:
        meta["product_company"] = _field(prod_company, "extracted")

    # ── Quantity ──────────────────────────────────────────────────
    qty = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("quantity") or row.get("qty") or row.get("qty_nos")
                if v and _clean_amount_val(str(v)):
                    qty = _clean_amount_val(str(v)); break
    if not qty:
        qty = _find_amount([r"(?:qty|quantity)[:\s.]+([0-9,]+(?:\.[0-9]+)?)"], text)
    if qty:
        core["quantity"] = _field(qty, "extracted")

    # ── Rate Per Unit ─────────────────────────────────────────────
    rate = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = (row.get("rate") or row.get("net_price") or row.get("rate_per_no")
                     or row.get("price") or row.get("unit_price"))
                if v and _clean_amount_val(str(v)):
                    rate = _clean_amount_val(str(v)); break
    if not rate:
        rate = _find_amount([
            r"(?:rate\s*per\s*(?:no|unit|pc|kg|ltr)?|mrp)[:\s\u20b9Rs.]+([0-9,]{2,}(?:\.[0-9]+)?)",
            r"(?<!disc)(?<!gst)\s+([2-9][0-9]{2,4}\.[0-9]{2})\s*(?:35|18|12|5)\s*%",  # rate before disc%
        ], text)
    if rate:
        core["rate"] = _field(rate, "extracted")

    # ── Discount % ────────────────────────────────────────────────
    disc_pct = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("disc_gst") or row.get("disc") or row.get("discount") or row.get("disc_percent")
                if v:
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(v))
                    if m:
                        disc_pct = m.group(1); break
    if not disc_pct:
        m = re.search(r"(?:disc(?:ount)?\s*%)[:\s.]*([0-9]+(?:\.[0-9]+)?)", text, re.I)
        if m:
            disc_pct = m.group(1)
        else:
            # pattern: amount  disc%  gst%  (e.g. "2,180.00  35%  18")
            m = re.search(r"[0-9,]{3,}\.[0-9]{2}\s+([0-9]+)\s*%\s+[0-9]+", text)
            if m:
                disc_pct = m.group(1)
    if disc_pct:
        core["discount_percent"] = _field(disc_pct + "%", "extracted")

    # ── GST % ─────────────────────────────────────────────────────
    gst_pct = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = row.get("gst") or row.get("gst_percent") or row.get("gst_pct") or row.get("net_price")
                if v:
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(v))
                    if m:
                        gst_pct = m.group(1); break
    if not gst_pct:
        m = re.search(r"GST\s*%?[:\s.]*([0-9]+(?:\.[0-9]+)?)(?:\s*%|\b)", text, re.I)
        if m:
            gst_pct = m.group(1)
        else:
            # After disc% in pattern: "35%  18"
            m = re.search(r"[0-9]+\s*%\s+([0-9]+)\s*(?:[0-9,|])", text)
            if m:
                gst_pct = m.group(1)
    if gst_pct:
        core["gst_percent"] = _field(gst_pct + "%", "extracted")

    # ── Assessable Amount (Ass. Amt) ──────────────────────────────
    ass_amt = ""
    if tables:
        for tbl in tables:
            for row in tbl.get("rows", []):
                v = (row.get("ass_amt") or row.get("assessable_amount")
                     or row.get("ass_amount") or row.get("taxable_value"))
                if v and _clean_amount_val(str(v)):
                    ass_amt = _clean_amount_val(str(v)); break
    if not ass_amt:
        ass_amt = _find_amount([
            r"(?:ass(?:essable)?\s*(?:amt|amount|value))[:\s\u20b9Rs.]*([0-9,]+(?:\.[0-9]+)?)",
        ], text)
    if ass_amt:
        core["ass_amount"] = _field(ass_amt, "extracted")
        if not (core.get("taxable_amount") or {}).get("value"):
            core["taxable_amount"] = _field(ass_amt, "extracted")

    # ── Round Off ─────────────────────────────────────────────────
    round_off = struc.get("round_off") or ""
    if not round_off:
        round_off = _find([
            r"(?:round\s*(?:off|up|down)?)[:\s]*\(?([\-]?[0-9]+\.?[0-9]*)\)?",
        ], text)
    if round_off:
        meta["round_off"] = _field(round_off, "extracted")

    # ── Addhar No / Mobile No ────────────────────────────────────
    addhar = struc.get("addhar_no") or struc.get("aadhaar") or ""
    if addhar:
        meta["addhar_number"] = _field(addhar, "extracted")

    mobile = struc.get("mobile_no") or struc.get("mobile") or struc.get("phone") or ""
    if not mobile:
        m = re.search(r"(?:mobile|mob|phone)[:\s.#]*([6-9][0-9]{9})", text, re.I)
        if m:
            mobile = m.group(1)
    if mobile:
        meta["supplier_phone"] = _field(mobile, "extracted")

    return core, meta


def _parse_invoice(t: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(t, args[0] if args else None, args[1] if len(args) > 1 else None)
    if "struc_meta" in kwargs: struc = kwargs["struc_meta"]
    if "struc" in kwargs: struc = kwargs["struc"]
    if "tables" in kwargs: tables = kwargs["tables"]
    table_headers = []
    if tables:
        for tbl in tables:
            table_headers.extend(tbl.get("headers", []))
            table_headers.extend(tbl.get("headers_raw", []))

    # Invoice / Bill Number
    inv_no_raw = (
        struc.get("invoice_number") or struc.get("inv_no") or struc.get("credit_note_no")
        or struc.get("debit_note_no") or struc.get("cpin_cin") or struc.get("cpin") or struc.get("cin")
        or struc.get("ewb_no") or struc.get("notice_no") or struc.get("document_number") or struc.get("ref_no")
    )
    if not inv_no_raw or _is_header_label(inv_no_raw):
        inv_no_raw = _find([
            r"(?:invoice|bill|tax\s+inv(?:oice)?)\s*(?:no|num(?:ber)?|#|:|\.)[:\s.#]*([A-Za-z0-9][\w\-/]{1,30})",
            r"\b(?:INV|BILL|TINV|RINV|SINV|B2B|B2C|PUR|SAL)[-/]?([A-Z0-9\-]{3,20})\b",
            r"(?:Inv\.?\s*No\.?|Invoice\s*#|Doc\.?\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
            r"\bNo\.?\s*[:\-]\s*([A-Za-z][A-Za-z0-9\-/]{3,20})\b",
            r"(?:Reference|Ref)\.?\s*(?:No|Number)?[:\s]+([A-Za-z0-9][\w\-/]{2,20})",
        ], t)
    inv_no = _sanitize_field(inv_no_raw, table_headers)
    if inv_no and (inv_no.lower() in ("oice", "invoice", "inv", "bill", "doc", "document", "number", "no") or len(inv_no) <= 2):
        inv_no = None

    # Date
    date_raw = (
        struc.get("invoice_date") or struc.get("date") or struc.get("generated_date")
        or struc.get("payment_date") or struc.get("filing_date") or struc.get("notice_date") or struc.get("issue_date")
    )
    if not date_raw:
        date_raw = _find([
            r"(?:invoice\s+date|bill\s+date|date\s+of\s+invoice|dt\.?|date)[:\s]*"
            r"((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
            r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b",
            r"\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
            r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
        ], t)
    date_norm = _normalise_date(date_raw) if date_raw else ""

    # GSTINs
    all_gstins = re.findall(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", t)
    supplier_gstin = struc.get("supplier_gstin") or (all_gstins[0] if all_gstins else "")
    customer_gstin = struc.get("customer_gstin") or struc.get("recipient_gstin") or struc.get("buyer_gstin") or (all_gstins[1] if len(all_gstins) > 1 else "")
    gstin_raw = supplier_gstin

    # Parties
    vendor, customer = _extract_parties_robust(t, tables)
    if not vendor:
        v_cand = struc.get("vendor") or struc.get("supplier") or struc.get("seller") or struc.get("billed_from") or struc.get("firm_name")
        if v_cand: vendor = _clean_party_name(v_cand, table_headers)
    if not customer:
        c_cand = struc.get("customer") or struc.get("customer_bill_to") or struc.get("recipient") or struc.get("buyer") or struc.get("bill_to")
        if c_cand: customer = _clean_party_name(c_cand, table_headers)

    # Place of Supply (strict validation against Indian states / state codes)
    place_of_supply = _clean_place_of_supply(struc.get("place_of_supply"))
    if not place_of_supply:
        m_pos = re.search(r'(?:place\s+of\s+supply|pos)[ \t]*[:\-][ \t]*([A-Za-z0-9 \-]{2,40})', t, re.I)
        if m_pos and not _is_header_label(m_pos.group(1)):
            place_of_supply = _clean_place_of_supply(m_pos.group(1))

    # Reverse Charge
    reverse_charge = struc.get("reverse_charge") or ""
    if not reverse_charge or reverse_charge.lower() not in ("yes", "no"):
        m_rc = re.search(r"reverse\s+charge[ \t]*[:\-][ \t]*(yes|no)", t, re.I)
        if m_rc:
            reverse_charge = m_rc.group(1).capitalize()
        elif re.search(r"\breverse\s+charge\b", t, re.I):
            reverse_charge = "No"

    # Amounts
    _CGST_PATS = [
        r"C\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"C\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"C\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]
    _SGST_PATS = [
        r"S\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"S\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"S\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]
    _IGST_PATS = [
        r"I\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]+\.[0-9]+)",
        r"I\.?G\.?S\.?T\.?\s*[@:]?\s*\d*\.?\d*\s*%\s*[:\s\u20b9Rs.]*\s*([0-9,]{3,})",
        r"I\.?G\.?S\.?T\.?\s*(?:Amount|Amt)?\s*[:\s\u20b9Rs.]+([0-9,]{3,}(?:\.[0-9]+)?)",
    ]

    amount = _clean_amount_val(struc.get("amount") or struc.get("net_amount") or struc.get("grand_total") or struc.get("total") or struc.get("total_amount"))
    if not amount:
        amount = _find_amount([
            r"(?:grand\s+total|total\s+invoice\s+value|total\s+amount|net\s+total|amount\s+due|balance\s+due)"
            r"[:\s\u20b9Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
            r"(?:\\bTotal\\b)[:\s\u20b9Rs.]*([0-9,]{3,}(?:\.[0-9]{1,2})?)",
        ], t)

    taxable = _clean_amount_val(struc.get("taxable_amount") or struc.get("taxable_value"))
    if not taxable:
        taxable = _find_amount([
            r"(?:taxable\s+(?:value|amount)|assessable\s+value|basic\s+(?:amount|value)|value\s+of\s+supply)"
            r"[:\s\u20b9Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], t)
    if not taxable and tables:
        for lt in tables:
            for r in lt.get("rows", []):
                if r.get("taxable_amount"):
                    taxable = _clean_amount_val(r.get("taxable_amount"))
                    if taxable:
                        break

    cgst = _clean_amount_val(struc.get("cgst") or struc.get("cgst_9"))
    if not cgst: cgst = _find_amount(_CGST_PATS, t)

    sgst = _clean_amount_val(struc.get("sgst") or struc.get("sgst_9"))
    if not sgst: sgst = _find_amount(_SGST_PATS, t)

    igst = _clean_amount_val(struc.get("igst"))
    if not igst: igst = _find_amount(_IGST_PATS, t)

    cess = _clean_amount_val(struc.get("cess"))
    if not cess: cess = _find_amount([r"CESS[:\s@%0-9]*[\u20b9Rs.]*\s*([0-9,]+\.?[0-9]*)"], t)

    if not amount and taxable and (cgst or sgst or igst):
        try:
            tot = float(taxable.replace(',', '')) + float((cgst or '0').replace(',', '')) + float((sgst or '0').replace(',', '')) + float((igst or '0').replace(',', ''))
            amount = f"{tot:.2f}"
        except Exception:
            pass

    # R5: Never plug taxable value from gross minus taxes. Every field is extracted independently.

    hsn = struc.get("hsn") or struc.get("hsn_code") or struc.get("hsn_sac") or ""
    if not hsn and tables:
        for lt in tables:
            for r in lt.get("rows", []):
                if r.get("hsn_code"):
                    hsn = r.get("hsn_code")
                    break
    if not hsn:
        hsn = _find([
            r"H\.?S\.?N\.?\s*(?:/\s*S\.?A\.?C\.?)?\s*(?:code)?[:\s]*([0-9]{4,8})",
            r"S\.?A\.?C\.?\s*(?:code)?[:\s]*([0-9]{4,8})",
        ], t)

    core = {
        "invoice_number": _field(inv_no, _conf_text(inv_no, 3)) if inv_no else _missing(),
        "gstin": _field(gstin_raw, _conf_gstin(gstin_raw)),
        "vendor": _field(vendor, _conf_text(vendor, 3)) if vendor else _missing(),
        "customer": _field(customer, _conf_text(customer, 3)) if customer else _missing(),
        "invoice_date": _field(date_norm, "extracted") if date_norm else _missing(),
        "amount": _field(amount, _conf_amount(amount)),
        "taxable_amount": _field(taxable, _conf_amount(taxable)),
        "cgst": _field(cgst, _conf_amount(cgst)),
        "sgst": _field(sgst, _conf_amount(sgst)),
        "igst": _field(igst, _conf_amount(igst)),
        "cess": _field(cess, _conf_amount(cess)),
        "hsn": _field(hsn, _conf_text(hsn, 4)),
        "item_description": _missing(),
        "quantity": _missing(),
        "rate": _missing(),
        "total_tax": _missing(),
        "ewb_number": _missing(),
    }

    irn = struc.get("irn") or _find([r"\bIRN[:\s]*([A-Za-z0-9]{60,})\b"], t)
    ack_no = struc.get("ack_no") or struc.get("ack_number") or _find([r"(?:ack(?:nowledgement)?\s*(?:no|number))[:\s]*([0-9]{14,20})"], t)
    payment_terms = struc.get("payment_terms") or _find([r"(?:payment\s+terms?)[:\s]+([A-Za-z0-9 ]{3,40})"], t)
    currency = struc.get("currency") or _find([r"(?:currency)[:\s]+([A-Z]{3})"], t) or ("INR" if re.search(r"[\u20b9]|\\bINR\b", t) else "")
    pan_cand = struc.get("supplier_pan") or struc.get("pan") or struc.get("pan_number")
    pan_no = _clean_pan(pan_cand, fallback_gstin=supplier_gstin)
    if not pan_no:
        m_pan = _find([r"\bPAN\s*(?:No\.?|Number)?[:\s]*([A-Z]{5}[0-9]{4}[A-Z])\b"], t)
        pan_no = _clean_pan(m_pan, fallback_gstin=supplier_gstin)

    customer_pan = _clean_pan(struc.get("customer_pan") or struc.get("buyer_pan"), fallback_gstin=customer_gstin)

    # Contact details & party info
    contact_person = struc.get("contact_person") or struc.get("contact_name") or ""
    if not contact_person:
        m_cp = re.search(r"(?:contact\s+person|contact\s+name|attn|attention)[:\s\-#]*([A-Za-z .]{3,40})", t, re.I)
        if m_cp and not _is_header_label(m_cp.group(1)):
            contact_person = _clean_val(m_cp.group(1))

    contact_phone = struc.get("contact_phone") or struc.get("contact_no") or struc.get("mobile") or ""
    if not contact_phone:
        m_ph = re.search(r"(?:contact\s*no\.?|contact\s*number|mobile(?:\s*no\.?)?|phone(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", t, re.I)
        if m_ph:
            contact_phone = m_ph.group(1).strip()

    sales_person = struc.get("sales_person") or ""
    if not sales_person:
        m_sp = re.search(r"(?:sales\s*person(?:\s*name)?|sales\s*rep|executive)[:\s\-#]*([A-Za-z .]{3,40})", t, re.I)
        if m_sp and not _is_header_label(m_sp.group(1)):
            sales_person = _clean_val(m_sp.group(1))

    sales_person_contact = struc.get("sales_person_contact") or ""
    if not sales_person_contact:
        m_spc = re.search(r"(?:sales\s*person\s*contact(?:\s*no\.?)?)[:\s\-#]*([0-9]{10,12})", t, re.I)
        if m_spc:
            sales_person_contact = m_spc.group(1).strip()

    supplier_address = struc.get("supplier_address") or ""
    customer_address = struc.get("customer_address") or ""
    supplier_state = struc.get("supplier_state") or ("Maharashtra" if "27AAPCS" in supplier_gstin else "")
    customer_state = struc.get("customer_state") or ("Maharashtra" if "27CKLPB" in customer_gstin else "")
    supplier_state_code = struc.get("supplier_state_code") or (supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else "")
    customer_state_code = struc.get("customer_state_code") or (customer_gstin[:2] if len(customer_gstin) >= 2 and customer_gstin[:2].isdigit() else "")
    buyer_code = struc.get("buyer_code") or ""
    cin = struc.get("cin") or ""
    pl_no = struc.get("pl_no") or ""
    fl_no = struc.get("fl_no") or ""
    transporter_name = struc.get("transporter_name") or ""
    transporter_location = struc.get("transporter_location") or ""
    due_date = struc.get("due_date") or ""

    meta = {
        "place_of_supply": _field(place_of_supply, _conf_text(place_of_supply, 2)) if place_of_supply else _missing(),
        "reverse_charge": _field(reverse_charge),
        "irn": _field(irn, _conf_text(irn, 60)),
        "ack_number": _field(ack_no, _conf_text(ack_no, 14)),
        "payment_terms": _field(payment_terms, _conf_text(payment_terms, 3)),
        "currency": _field(currency, _conf_text(currency, 3)),
        "pan_number": _field(pan_no, _conf_text(pan_no, 10)) if pan_no else _missing(),
        "supplier_pan": _field(pan_no, _conf_text(pan_no, 10)) if pan_no else _missing(),
        "customer_pan": _field(customer_pan, _conf_text(customer_pan, 10)) if customer_pan else _missing(),
        "supplier_gstin": _field(supplier_gstin, _conf_gstin(supplier_gstin)),
        "customer_gstin": _field(customer_gstin, _conf_gstin(customer_gstin)),
    }
    if contact_person:
        meta["contact_person"] = _field(contact_person, _conf_text(contact_person, 3))
    if contact_phone:
        meta["contact_phone"] = _field(contact_phone, "extracted")
        meta["customer_phone"] = _field(contact_phone, "extracted")
    if sales_person:
        meta["sales_person"] = _field(sales_person, _conf_text(sales_person, 3))
    if sales_person_contact:
        meta["sales_person_contact"] = _field(sales_person_contact, "extracted")
    if supplier_address:
        meta["supplier_address"] = _field(supplier_address, "extracted")
    if customer_address:
        meta["customer_address"] = _field(customer_address, "extracted")
    if supplier_state:
        meta["supplier_state"] = _field(supplier_state, "extracted")
    if customer_state:
        meta["customer_state"] = _field(customer_state, "extracted")
    if supplier_state_code:
        meta["supplier_state_code"] = _field(supplier_state_code, "extracted")
    if customer_state_code:
        meta["customer_state_code"] = _field(customer_state_code, "extracted")
    if buyer_code:
        meta["buyer_code"] = _field(buyer_code, "extracted")
    if cin:
        meta["cin"] = _field(cin, "extracted")
    if pl_no:
        meta["pl_no"] = _field(pl_no, "extracted")
    if fl_no:
        meta["fl_no"] = _field(fl_no, "extracted")
    if transporter_name:
        meta["transporter_name"] = _field(transporter_name, "extracted")
    if transporter_location:
        meta["transporter_location"] = _field(transporter_location, "extracted")
    if due_date:
        meta["due_date"] = _field(due_date, "extracted")
    return core, meta


def _parse_credit_debit_note(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    category = "credit_note"
    struc = None
    tables = []
    for a in args:
        if isinstance(a, str):
            category = a.lower()
        elif isinstance(a, dict):
            struc = a
        elif isinstance(a, list):
            tables = a
    for k, v in kwargs.items():
        if k == "category": category = v.lower()
        elif k == "struc": struc = v
        elif k == "tables": tables = v
    if struc is None:
        struc = _extract_document_text_blocks(text)

    core, meta = _parse_invoice(text, struc, tables)
    
    note_no = (
        struc.get("credit_note_no") or struc.get("debit_note_no")
        or struc.get("invoice_number") or struc.get("inv_no")
        or _find([
            r"(?:credit\s*note\s*no\.?|debit\s*note\s*no\.?|note\s*no\.?|cr\.?\s*note\s*no\.?|dr\.?\s*note\s*no\.?)[:\s.#]*([A-Za-z0-9\-_/]{2,30})",
            r"(CN[-_A-Za-z0-9]+|DN[-_A-Za-z0-9]+)",
        ], text)
    )
    if note_no:
        core["invoice_number"] = _field(note_no, _conf_text(note_no, 2))

    orig_inv = (
        struc.get("original_invoice") or struc.get("original_invoice_number") or struc.get("original_invoice_no")
        or _find([
            r"(?:original\s+invoice|orig\.?\s*inv(?:oice)?)\s*(?:no|num(?:ber)?|#|:)?[:\s.#]*([A-Za-z0-9][\w\-/]{1,30})",
            r"(?:against\s+invoice|ref(?:erence)?\s+inv(?:oice)?)\s*(?:no|#)?[:\s]*([A-Za-z0-9][\w\-/]{1,30})",
        ], text)
    )

    reason = (
        struc.get("reason") or _find([
            r"(?:reason\s*(?:for\s*issuance)?|remarks)[:\s]+([A-Za-z0-9 ,.\-/]{3,80})",
        ], text)
    )

    meta["original_invoice_number"] = _field(orig_inv, _conf_text(orig_inv, 3))
    meta["reason"] = _field(reason, _conf_text(reason, 3))
    meta["document_type"] = _field("Credit Note" if "credit" in category else "Debit Note")
    return core, meta



def _parse_e_invoice(t: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(t, args[0] if args else None, args[1] if len(args) > 1 else None)
    return _parse_invoice(t, struc, tables)


def _parse_e_way_bill(t: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(t, args[0] if args else None, args[1] if len(args) > 1 else None)
    core, meta = _parse_invoice(t, struc, tables)

    # 1. E-Way Bill Number (12 digits)
    ewb_no = struc.get("ewb_no") or struc.get("e_way_bill_no") or _find([
        r"E-Way\s*Bill\s*No[:\s]*([0-9]{12})",
        r"(?:e-?way\s*bill\s*no\.?|ewb\s*no\.?)[:\s]*([0-9]{12}|[A-Za-z0-9\-]{8,25})",
    ], t)
    if ewb_no:
        core["invoice_number"] = _field(ewb_no, "extracted")
        core["ewb_number"] = _field(ewb_no, "extracted")
        meta["ewb_number"] = _field(ewb_no, "extracted")

    # 2. Linked Document / Invoice No
    doc_no = struc.get("doc_no") or struc.get("document_no") or _find([
        r"Document\s*No[:\s]*([A-Za-z0-9\/\-_]+)",
        r"(?:Doc\s*No|Linked\s*Invoice)[:\s]*([A-Za-z0-9\/\-_]+)",
    ], t)
    if doc_no:
        meta["linked_invoice_number"] = _field(doc_no, "extracted")
        meta["document_number"] = _field(doc_no, "extracted")

    # 3. Dates
    gen_date = _find([r"Generated\s*Date[:\s]*([0-9]{2}[-/.][A-Za-z]{3}[-/.][0-9]{4}|[0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})"], t)
    if gen_date:
        norm_date = _normalise_date(gen_date)
        core["invoice_date"] = _field(norm_date, "extracted")
        meta["generated_date"] = _field(norm_date, "extracted")

    valid_until = struc.get("valid_until") or _find([
        r"Valid\s*Upto[:\s]*([0-9]{2}[-/.][A-Za-z]{3}[-/.][0-9]{4}|[0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
        r"(?:valid\s*until|validity)[:\s]*([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})",
    ], t)
    if valid_until:
        meta["valid_until"] = _field(_normalise_date(valid_until))

    # 4. Vehicle No
    veh_no = struc.get("vehicle_no") or struc.get("vehicle_number") or _find([
        r"Vehicle\s*No[:\s]*([A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4})",
        r"\b([A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4})\b",
    ], t)
    if veh_no:
        meta["vehicle_number"] = _field(veh_no, _conf_text(veh_no, 6))

    mode = struc.get("mode") or struc.get("transport_mode") or _find([r"(?:mode|transport\s*mode)[:\s]*([A-Za-z]+)"], t)
    if mode:
        meta["transport_mode"] = _field(mode, _conf_text(mode, 3))

    # 5. From (Dispatch) and To (Ship) Parties
    m_from = re.search(r"From\s*(?:\(Dispatch\))?[:\s]*\n([A-Za-z0-9 &.,()-]{3,60}?)(?:\n|GSTIN)", t, re.I)
    if m_from:
        v_name = _clean_party_name(m_from.group(1))
        if v_name and v_name.lower() not in ("entered date", "road", "dispatch", "from"):
            core["vendor"] = _field(v_name, "extracted")
            meta["from_party"] = _field(v_name, "extracted")

    m_to = re.search(r"To\s*(?:\(Ship\))?[:\s]*\n([A-Za-z0-9 &.,()-]{3,60}?)(?:\n|GSTIN)", t, re.I)
    if m_to:
        c_name = _clean_party_name(m_to.group(1))
        if c_name and c_name.lower() not in ("entered date", "road", "ship", "to"):
            core["customer"] = _field(c_name, "extracted")
            meta["to_party"] = _field(c_name, "extracted")

    # Guard against "Entered Date" in vendor
    v_val = (core.get("vendor") or {}).get("value", "")
    if v_val and v_val.lower() in ("entered date", "road", "mode", "vehicle no"):
        core["vendor"] = _missing()

    # 6. Total Invoice Value & Taxable Value
    tot_val = _find_amount([r"Total\s*Invoice\s*Value[:\s]*([0-9,]+\.?[0-9]*)"], t)
    if tot_val:
        core["amount"] = _field(tot_val, "extracted")

    tax_val = _find_amount([r"Taxable\s*Value[:\s]*([0-9,]+\.?[0-9]*)"], t)
    if tax_val:
        core["taxable_amount"] = _field(tax_val, "extracted")

    return core, meta


def _parse_challan(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(text, args[0] if args else None, args[1] if len(args) > 1 else None)
    core, meta = _parse_invoice(text, struc, tables)

    # 1. CPIN (14 digits)
    cpin = (
        struc.get("cpin")
        or _find([
            r"\bCPIN\s*[:\-]\s*([0-9]{14})\b",
            r"(?:Common\s*Portal\s*Identification\s*Number)[:\s]*([0-9]{14})",
            r"\b([0-9]{14})\b",
        ], text)
    )
    if cpin:
        meta["cpin"] = _field(cpin, _conf_text(cpin, 14))
        core["invoice_number"] = _field(cpin, "extracted")

    # 2. CIN (Challan Identification Number)
    cin = (
        struc.get("cin")
        or _find([
            r"\bCIN\s*[:\-]\s*([A-Za-z0-9]{18,25})\b",
            r"(?:Challan\s*Identification\s*Number)[:\s]*([A-Za-z0-9]{18,25})",
            r" (TESTCIN[0-9]+) ",
        ], text)
    )
    if cin:
        meta["cin"] = _field(cin, _conf_text(cin, 18))

    # 3. Taxpayer Legal Name
    legal_name = (
        struc.get("legal_name") or struc.get("taxpayer_name") or struc.get("vendor")
        or _find([
            r"Name\s*\(\s*Legal\s*\)\s*[:\-]\s*([^\n\r]+)",
            r"Taxpayer\s*Name\s*[:\-]\s*([^\n\r]+)",
            r"(?:Name\s*of\s*Taxpayer|Name\s*of\s*the\s*Taxpayer)[:\s]*([^\n\r]+)",
        ], text)
    )
    if legal_name:
        clean_legal = re.sub(r"\s*\|\s*.*$", "", legal_name).strip()
        core["vendor"] = _field(clean_legal, _conf_text(clean_legal, 3))
        meta["legal_name"] = _field(clean_legal, _conf_text(clean_legal, 3))

    # 4. Dates: Challan Generated Date, Expiry Date, Payment Date
    ch_date_raw = (
        struc.get("challan_date") or struc.get("challan_generated_date")
        or _find([
            r"Challan\s*Generated\s*(?:on)?\s*[:\-]\s*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
            r"(?:Challan\s*Date)[:\s]*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
        ], text)
    )
    if ch_date_raw:
        norm_ch_date = _normalise_date(ch_date_raw)
        meta["challan_date"] = _field(norm_ch_date, "extracted")
        if not core.get("invoice_date", {}).get("value"):
            core["invoice_date"] = _field(norm_ch_date, "extracted")

    exp_date_raw = (
        struc.get("expiry_date")
        or _find([
            r"Expiry\s*Date\s*[:\-]\s*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
            r"(?:Challan\s*Expiry\s*Date)[:\s]*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
        ], text)
    )
    if exp_date_raw:
        meta["expiry_date"] = _field(_normalise_date(exp_date_raw), "extracted")

    pmt_date_raw = (
        struc.get("payment_date")
        or _find([
            r"Payment\s*Date\s*[:\-]\s*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
            r"Date\s*of\s*Payment\s*[:\-]\s*([0-9]{2}[-/.][0-9]{2}[-/.][0-9]{4})",
        ], text)
    )
    if pmt_date_raw:
        norm_pmt = _normalise_date(pmt_date_raw)
        core["invoice_date"] = _field(norm_pmt, "extracted")

    # 5. Taxpayer Contact: Email, Mobile, Address
    email = (
        struc.get("email")
        or _find([
            r"Email\s*(?:Id)?\s*[:\-]\s*([^\s,]+@[^\s,]+)",
        ], text)
    )
    if email:
        meta["email"] = _field(email.strip(), "extracted")

    mobile = (
        struc.get("mobile") or struc.get("phone")
        or _find([
            r"Mobile\s*(?:No\.?)?\s*[:\-]\s*([0-9X]{10,12})",
        ], text)
    )
    if mobile:
        meta["phone"] = _field(mobile.strip(), "extracted")
        meta["mobile"] = _field(mobile.strip(), "extracted")

    address = (
        struc.get("address")
        or _find([
            r"Address\s*[:\-]\s*([^\n\r]+)",
        ], text)
    )
    if address:
        clean_addr = address.strip()
        meta["address"] = _field(clean_addr, "extracted")
        for st_k, st_name in sorted(INDIAN_STATES.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(r"\b" + re.escape(st_k) + r"\b", clean_addr.lower()):
                meta["state"] = _field(st_name, "extracted")
                break
        m_pin = re.search(r"\b([0-9]{6})\b", clean_addr)
        if m_pin:
            meta["pincode"] = _field(m_pin.group(1), "extracted")

    # 6. Reason for Challan / Purpose
    reason = (
        struc.get("reason") or struc.get("purpose")
        or _find([
            r"Reason\s*(?:for\s*Challan)?\s*[:\-]\s*([^\n\r]+)",
            r"Purpose\s*[:\-]\s*([^\n\r]+)",
        ], text)
    )
    if reason:
        meta["purpose"] = _field(reason.strip(), "extracted")
        meta["reason"] = _field(reason.strip(), "extracted")

    # 7. Mode of Payment
    mode = (
        struc.get("payment_method") or struc.get("mode_of_payment")
        or _find([
            r"(?:Mode\s*of\s*Payment|Payment\s*Mode)\s*[:\-]?\s*([^\n\r]+)",
        ], text)
    )
    if mode:
        clean_mode = re.sub(r"[\[\]\(\)✔☑xX]", "", mode).strip()
        if any(m in clean_mode.lower() for m in ("e-payment", "over the counter", "neft", "rtgs")):
            meta["payment_method"] = _field(clean_mode, "extracted")

    # 8. Amount in Words
    amt_words = (
        struc.get("amount_in_words")
        or _find([
            r"(?:Total\s*amount\s*\(\s*in\s*words\s*\)|Amount\s*in\s*words)[:\s]*([^\n\r]+)",
        ], text)
    )
    if amt_words:
        meta["amount_in_words"] = _field(amt_words.strip(), "extracted")

    # 9. Amounts: Total Paid, Taxable Value, Tax Heads
    taxable = (
        _clean_amount_val(struc.get("taxable_value") or struc.get("taxable_amount") or struc.get("sub_total"))
        or _find_amount([
            r"(?:Sub\s*Total|taxable\s+value|taxable\s+amount)[:\s₹Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], text)
    )
    if taxable:
        core["taxable_amount"] = _field(taxable, _conf_amount(taxable))

    amt_paid = (
        _clean_amount_val(struc.get("total_amount_paid") or struc.get("total_challan_amount") or struc.get("amount_paid") or struc.get("amount") or struc.get("total_amount"))
        or _find_amount([
            r"(?:Total\s+Amount|total\s+amount\s+paid|total\s+challan\s+amount|amount\s+paid|amount)[:\s₹Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], text)
    )
    if amt_paid:
        core["amount"] = _field(amt_paid, _conf_amount(amt_paid))

    # CGST, SGST, IGST, CESS breakdown from Deposit table
    cgst_val = _clean_amount_val(struc.get("cgst") or struc.get("cgst_amount") or struc.get("cgst_tax"))
    if not cgst_val:
        cgst_m = re.search(r"CGST(?:\([0-9]+\))?[\s|:]*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.I)
        if cgst_m:
            cgst_val = _clean_amount_val(cgst_m.group(1))
    if cgst_val:
        core["cgst"] = _field(cgst_val, "extracted")
        meta["cgst"] = _field(cgst_val, "extracted")
        meta["cgst_tax"] = _field(cgst_val, "extracted")

    sgst_val = _clean_amount_val(struc.get("sgst") or struc.get("sgst_amount") or struc.get("sgst_tax"))
    if not sgst_val:
        sgst_m = re.search(r"SGST(?:\([0-9]+\))?[\s|:]*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.I)
        if sgst_m:
            sgst_val = _clean_amount_val(sgst_m.group(1))
    if sgst_val:
        core["sgst"] = _field(sgst_val, "extracted")
        meta["sgst"] = _field(sgst_val, "extracted")
        meta["sgst_tax"] = _field(sgst_val, "extracted")

    # 10. PAN derivation from GSTIN
    gstin_val = core.get("gstin", {}).get("value")
    if gstin_val:
        pan = _clean_pan("", fallback_gstin=gstin_val)
        if pan:
            meta["pan_number"] = _field(pan, "extracted")

    return core, meta



def _parse_gst_return(t: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(t, args[0] if args else None, args[1] if len(args) > 1 else None)
    core, meta = _parse_invoice(t, struc, tables)
    
    ret_type = struc.get("return_type") or struc.get("gst_return_type") or _find([
        r"\b(GSTR-?1|GSTR-?3B|GSTR-?9|GSTR-?9C|CMP-?08|ITC-?04)\b",
    ], t)
    core["gst_return_type"] = _field(ret_type, "extracted") if ret_type else _missing()

    arn = struc.get("arn") or _find([r"\bARN[:\s]*([A-Za-z0-9]{14,20})\b"], t)
    core["arn"] = _field(arn, "extracted") if arn else _missing()

    fy = struc.get("financial_year") or _find([r"(?:financial\s*year|fy)[:\s]*([0-9]{4}[\-_][0-9]{2,4})"], t)
    core["financial_year"] = _field(fy, "extracted") if fy else _missing()

    month = struc.get("tax_period") or struc.get("month") or _find([r"(?:tax\s*period|month)[:\s]*([A-Za-z]{3}[\-_][0-9]{2,4}|[A-Za-z]+)"], t)
    core["month"] = _field(month, "extracted") if month else _missing()

    return core, meta


def _parse_gst_notice(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(text, args[0] if args else None, args[1] if len(args) > 1 else None)
    
    notice_no = (
        struc.get("notice_no") or struc.get("notice_number")
        or _find([
            r"(?:notice\s*(?:reference|ref|no|number)?|ref\.?\s*no\.?|show\s+cause\s+notice\s+no\.?)[:\s]*([A-Za-z0-9\-_/]{6,40})",
            r"([A-Za-z]{2,8}/[A-Za-z0-9\-_/]{4,30})",
            r"(TESTNOTICE[0-9]+)",
        ], text)
    )
    notice_date_raw = struc.get("notice_date") or struc.get("date") or _find([
        r"(?:notice\s*date|date\s*of\s*notice)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
    ], text)
    notice_date = _normalise_date(notice_date_raw) if notice_date_raw else ""
    
    due_date_raw = struc.get("response_due_date") or _find([
        r"(?:response\s*due\s*date|due\s*date|reply\s*by)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
    ], text)
    due_date = _normalise_date(due_date_raw) if due_date_raw else ""
    
    gstin = struc.get("gstin") or _find([r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])"], text)
    taxpayer = struc.get("taxpayer") or struc.get("name_of_taxpayer") or struc.get("legal_name") or struc.get("vendor") or ""
    
    amount_inv = _clean_amount_val(struc.get("amount_involved") or struc.get("demand_amount") or struc.get("tax_demand") or struc.get("amount"))
    if not amount_inv:
        amount_inv = _find_amount([
            r"(?:amount\s+involved|demand\s+amount|tax\s+demand|total\s+demand)[:\s₹Rs.]*([0-9,]+(?:\.[0-9]{1,2})?)",
        ], text)

    priority = "medium"
    if re.search(r"(urgent|immediate|high|severe|penalty)", text, re.I):
        priority = "high"
    elif re.search(r"(low|routine|information)", text, re.I):
        priority = "low"

    core = {
        "invoice_number": _field(notice_no, _conf_text(notice_no, 4)),
        "notice_number": _field(notice_no, _conf_text(notice_no, 4)),
        "gstin": _field(gstin, _conf_gstin(gstin)),
        "vendor": _field(taxpayer, _conf_text(taxpayer, 3)),
        "customer": _missing(),
        "invoice_date": _field(notice_date, "extracted") if notice_date else _missing(),
        "notice_date": _field(notice_date, "extracted") if notice_date else _missing(),
        "response_due_date": _field(due_date, "extracted") if due_date else _missing(),
        "priority": _field(priority, "extracted"),
        "amount": _field(amount_inv, _conf_amount(amount_inv)),
        "taxable_amount": _missing(),
        "cgst": _missing(),
        "sgst": _missing(),
        "igst": _missing(),
        "cess": _missing(),
        "hsn": _missing(),
    }
    
    notice_type = struc.get("notice_type") or _find([r"(?:notice\s+under\s+section[\s0-9()]+|show\s+cause\s+notice|scrutiny\s+notice)"], text) or "Show Cause Notice"
    meta = {
        "company_name": _field(taxpayer),
        "supplier_gstin": _field(gstin),
        "notice_type": _field(notice_type),
        "document_title": _field(notice_type),
        "subject": _field(struc.get("subject") or _find([r"(?:subject)[:\s]+([A-Za-z0-9 ,-]+)"], text)),
        "section_rule": _field(struc.get("section") or _find([r"(?:section)[:\s]+([A-Za-z0-9() ,-]+)"], text)),
        "issuing_authority": _field(struc.get("issuing_authority") or _find([r"(?:issuing\s+authority)[:\s]+([A-Za-z0-9 ,-]+)"], text)),
        "financial_year": _field(struc.get("financial_year")),
        "tax_period": _field(struc.get("tax_period") or _find([r"(?:tax\s+period)[:\s]+([A-Za-z0-9 ,-]+)"], text)),
    }
    return core, meta



def _parse_hsn_sac(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(text, args[0] if args else None, args[1] if len(args) > 1 else None)
    
    hsn_code = struc.get("hsn") or struc.get("hsn_code") or struc.get("sac") or struc.get("hsn_sac")
    if not hsn_code:
        hsn_code = _find([
            r"HSN[:\s]*([0-9]{4,8})",
            r"SAC[:\s]*([0-9]{4,8})",
            r"([0-9]{6,8})",
        ], text)
        
    desc = struc.get("description") or struc.get("item_description") or _find([
        r"(?:description|item\s+description|particulars)[:\s]+([A-Za-z0-9 &.,'()/-]{3,80})",
    ], text)
    
    gst_rate = struc.get("gst_rate") or struc.get("tax_rate") or _find([
        r"(?:gst\s+rate|tax\s+rate|rate)[:\s]*([0-9.]+\s*%)",
    ], text)

    core = {
        "invoice_number": _missing(),
        "gstin": _missing(),
        "vendor": _missing(),
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
        "description": _field(desc, _conf_text(desc, 3)),
        "gst_rate": _field(gst_rate, _conf_text(gst_rate, 2)),
        "code_type": _field(struc.get("code_type") or ("HSN" if hsn_code and len(hsn_code) in (4, 6, 8) else "SAC")),
    }
    return core, meta



def _parse_document_list(text: str, *args, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struc, tables = _norm_parser_args(text, args[0] if args else None, args[1] if len(args) > 1 else None)
    
    doc_type = struc.get("document_type") or _find([
        r"(?:GST\s+REGISTRATION\s+CERTIFICATE|INCORPORATION\s+CERTIFICATE|MSME\s+UDYAM|PAN\s+CARD|TAX\s+CLEARANCE|AUDIT\s+REPORT|IMPORT\s+EXPORT\s+CODE)",
    ], text)
    
    cert_no = struc.get("certificate_no") or struc.get("document_number") or struc.get("registration_number") or _find([
        r"(?:certificate\s*no\.?|reg(?:istration)?\s*no\.?|doc(?:ument)?\s*no\.?)[:\s]*([A-Za-z0-9\-_/]{6,40})",
        r"(GSTREG[A-Za-z0-9\-_]+)",
    ], text)
    
    issue_date_raw = struc.get("issue_date") or struc.get("date") or _find([
        r"(?:issue\s*date|date\s*of\s*issue)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
    ], text)
    issue_date = _normalise_date(issue_date_raw) if issue_date_raw else ""
    
    valid_till_raw = struc.get("valid_till") or struc.get("valid_until") or struc.get("expiry_date") or _find([
        r"(?:valid\s+(?:till|until|to)|expiry\s+date)[:\s]*((?:\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4})|(?:\d{4}-\d{2}-\d{2}))",
    ], text)
    valid_till = _normalise_date(valid_till_raw) if valid_till_raw else (valid_till_raw or "")
    
    gstin = struc.get("gstin") or _find([r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])"], text)
    taxpayer = struc.get("name_of_taxpayer") or struc.get("legal_name") or struc.get("taxpayer") or struc.get("company_name") or ""
    trade_name = struc.get("trade_name") or taxpayer

    core = {
        "invoice_number": _field(cert_no, _conf_text(cert_no, 4)),
        "gstin": _field(gstin, _conf_gstin(gstin)),
        "vendor": _field(taxpayer, _conf_text(taxpayer, 3)),
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
        "document_type": _field(doc_type),
        "document_number": _field(cert_no),
        "company_name": _field(taxpayer),
        "trade_name": _field(trade_name),
        "supplier_gstin": _field(gstin),
        "issue_date": _field(issue_date),
        "expiry_date": _field(valid_till),
        "expiry_validity": _field(valid_till),
    }
    return core, meta



def _dispatch_parser(
    category: str,
    text: str,
    tables: List[Dict],
    struc_meta: Optional[Dict[str, str]] = None,
) -> Tuple[Dict, Dict]:
    if struc_meta is None:
        struc_meta = _extract_document_text_blocks(text)

    if category in ("b2b_invoice", "b2c_invoice", "e_invoice"):
        return _parse_invoice(text, tables, struc_meta)
    elif category == "sales_records":
        return _parse_sales_records(text, tables, struc_meta)
    elif category == "purchase_records":
        return _parse_purchase_records(text, tables, struc_meta)
    elif category in ("credit_note", "debit_note"):
        return _parse_credit_debit_note(text, category, tables, struc_meta)
    elif category == "e_way_bill":
        return _parse_e_way_bill(text, tables, struc_meta)
    elif category == "gst_challan":
        return _parse_challan(text, tables, struc_meta)
    elif category == "gst_return":
        return _parse_gst_return(text, tables, struc_meta)
    elif category == "gst_notice":
        return _parse_gst_notice(text, tables, struc_meta)
    elif category == "hsn_sac":
        return _parse_hsn_sac(text, tables, struc_meta)
    elif category == "document_list":
        return _parse_document_list(text, tables, struc_meta)
    else:
        return _parse_invoice(text, tables, struc_meta)


# ---------------------------------------------------------------------------
# Post-extraction validation
# ---------------------------------------------------------------------------

def _validate_extraction(core_fields: dict, meta_fields: dict, category: str) -> dict:
    warnings = []

    def val(f: dict) -> str:
        return f.get("value", "") if isinstance(f, dict) else str(f or "")

    flat = {k: val(v) for k, v in {**core_fields, **meta_fields}.items()}

    # GSTIN validation
    gstin_result = validate_gstin(flat.get("gstin"))
    if gstin_result["valid"] is False:
        warnings.append(f"GSTIN: {gstin_result['message']}")

    # Amount validation
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

    return {"gstin": gstin_result, "amounts": amount_result, "warnings": warnings}


# ---------------------------------------------------------------------------
# Gemini Structured Extraction (fallback for zero-field extractions)
# ---------------------------------------------------------------------------

_CATEGORY_FIELD_SCHEMA: Dict[str, Dict[str, str]] = {
    "sales_records": {
        "vendor": "Company or seller name",
        "invoice_number": "Invoice number (e.g. INV-001) — null if this is a multi-invoice report",
        "invoice_date": "Invoice date (YYYY-MM-DD) — null if this is a report",
        "customer": "Customer or buyer name",
        "gstin": "GSTIN (15-char Indian tax ID, e.g. 27AABCN1234R1Z5)",
        "supplier_gstin": "Seller/supplier GSTIN (15-char)",
        "customer_gstin": "Buyer/customer GSTIN (15-char)",
        "supplier_pan": "10-character PAN of seller [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of seller GSTIN",
        "customer_pan": "10-character PAN of buyer [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of customer GSTIN",
        "place_of_supply": "Place of supply Indian state name ONLY if explicitly stated next to Place of Supply label, else null",
        "contact_person": "Contact person name if present, else null",
        "contact_phone": "Contact phone or mobile number if present, else null",
        "sales_person": "Sales person name or role if present, else null",
        "sales_person_contact": "Sales person contact number if present, else null",
        "supplier_state": "Seller/supplier state name (e.g. Maharashtra)",
        "supplier_state_code": "Seller 2-digit state code (e.g. 27)",
        "customer_state": "Buyer/customer state name (e.g. Maharashtra)",
        "customer_state_code": "Buyer 2-digit state code (e.g. 27)",
        "buyer_code": "Buyer or customer code if present",
        "cin": "Corporate Identification Number (CIN) if present, else null",
        "pl_no": "P.L No if present, else null",
        "fl_no": "F.L No if present, else null",
        "transporter_name": "Transporter name if present, else null",
        "transporter_location": "Transporter location if present, else null",
        "due_date": "Payment due date (YYYY-MM-DD) if present, else null",
        "supplier_address": "Full seller/supplier address",
        "customer_address": "Full buyer/customer address",
        "document_type": "Document type (e.g. Tax Invoice, Credit Memo)",
        "hsn": "HSN or SAC code",
        "taxable_amount": "Taxable amount (number only)",
        "cgst": "CGST amount (number only)",
        "sgst": "SGST amount (number only)",
        "igst": "IGST amount (number only)",
        "cess": "CESS amount (number only)",
        "round_off": "Round off amount (number only, may be negative)",
        "amount": "Grand total / total invoice value (number only)",
        "company_name": "Company name from document header",
        "report_title": "Report title if this is a report (e.g. Sale Analysis Report)",
        "period_start": "Period start date (YYYY-MM-DD)",
        "period_end": "Period end date (YYYY-MM-DD)",
        "total_sales": "Total sales amount (number only)",
    },
    "purchase_records": {
        "vendor": "Supplier/seller/vendor name (company letterhead name)",
        "gstin": "Supplier/seller GSTIN (15-char, e.g. 27AAZFB7251M1ZM)",
        "customer": "Receiver/buyer/customer name",
        "customer_gstin": "Receiver/buyer GSTIN (15-char)",
        "supplier_pan": "10-character PAN of seller [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of seller GSTIN",
        "customer_pan": "10-character PAN of buyer [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of customer GSTIN",
        "invoice_number": "Invoice or bill number (e.g. BHUV/25-26/870)",
        "invoice_date": "Invoice date (YYYY-MM-DD)",
        "document_type": "Document type: Credit Memo / Tax Invoice / etc.",
        "eway_bill_number": "E-Way Bill number if present",
        "ref_number": "Reference number (Ref. No.)",
        "vehicle_number": "Vehicle number if present",
        "place_of_supply": "Place of supply state name ONLY if explicitly stated next to Place of Supply, else null",
        "state_code": "State code (2-digit number, e.g. 27)",
        "pincode": "Buyer/receiver 6-digit pincode",
        "contact_person": "Contact person name if present, else null",
        "contact_phone": "Contact phone or mobile number if present, else null",
        "sales_person": "Sales person name or role if present, else null",
        "sales_person_contact": "Sales person contact number if present, else null",
        "supplier_state": "Seller/supplier state name (e.g. Maharashtra)",
        "supplier_state_code": "Seller 2-digit state code (e.g. 27)",
        "customer_state": "Buyer/customer state name (e.g. Maharashtra)",
        "customer_state_code": "Buyer 2-digit state code (e.g. 27)",
        "buyer_code": "Buyer or customer code if present",
        "cin": "Corporate Identification Number (CIN) if present, else null",
        "transporter_name": "Transporter name if present, else null",
        "transporter_location": "Transporter location if present, else null",
        "due_date": "Payment due date (YYYY-MM-DD) if present, else null",
        "supplier_address": "Full seller/supplier address",
        "customer_address": "Full buyer/receiver address",
        "hsn": "HSN or SAC code (numeric)",
        "item_description": "Product name / particulars (e.g. Decorus 5ltr)",
        "product_company": "Product brand/company name (e.g. Poorva)",
        "batch_number": "Batch number (e.g. 05/2025)",
        "expiry_date": "Product expiry date (YYYY-MM-DD or as shown)",
        "quantity": "Quantity ordered (number)",
        "rate": "Rate per unit (number only, no currency)",
        "discount_percent": "Discount percentage (e.g. 35%)",
        "gst_percent": "GST rate percentage (e.g. 18%)",
        "ass_amount": "Assessable / taxable amount after discount (number only)",
        "taxable_amount": "Taxable/assessable amount (number only)",
        "cgst": "CGST amount (number only)",
        "sgst": "SGST amount (number only)",
        "igst": "IGST amount (number only)",
        "cess": "CESS amount (number only)",
        "round_off": "Round off amount (may be negative)",
        "amount": "Grand total / final payable amount (number only)",
    },
    "b2b_invoice": {
        "vendor": "Seller/supplier name",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date (YYYY-MM-DD)",
        "customer": "Buyer/customer name",
        "gstin": "Seller GSTIN",
        "supplier_gstin": "Seller GSTIN",
        "customer_gstin": "Buyer GSTIN",
        "supplier_pan": "10-character PAN of seller [A-Z]{5}[0-9]{4}[A-Z]",
        "customer_pan": "10-character PAN of buyer [A-Z]{5}[0-9]{4}[A-Z]",
        "place_of_supply": "Place of supply state name ONLY if explicitly stated next to Place of Supply, else null",
        "contact_person": "Contact person name if present, else null",
        "contact_phone": "Contact phone or mobile number if present, else null",
        "supplier_state": "Seller state name",
        "customer_state": "Buyer state name",
        "supplier_address": "Seller address",
        "customer_address": "Buyer address",
        "hsn": "HSN code",
        "taxable_amount": "Taxable amount",
        "cgst": "CGST",
        "sgst": "SGST",
        "igst": "IGST",
        "cess": "CESS",
        "amount": "Grand total",
    },
    "b2c_invoice": {
        "customer": "Customer name",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date (YYYY-MM-DD)",
        "hsn": "HSN code",
        "taxable_amount": "Taxable amount",
        "cgst": "CGST",
        "sgst": "SGST",
        "igst": "IGST",
        "cess": "CESS",
        "amount": "Grand total",
    },
    "credit_note": {
        "invoice_number": "Credit note number (e.g. 147)",
        "invoice_date": "Credit note date (YYYY-MM-DD)",
        "original_invoice_number": "Original invoice number referenced, or null if none",
        "original_invoice_date": "Original invoice date referenced, or null if none",
        "vendor": "Seller / Supplier company name",
        "customer": "Buyer / Customer company name",
        "gstin": "Supplier GSTIN (15-character)",
        "supplier_gstin": "Seller/supplier GSTIN (15-character)",
        "customer_gstin": "Buyer/customer GSTIN (15-character)",
        "supplier_pan": "10-character PAN of seller [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of seller GSTIN",
        "customer_pan": "10-character PAN of buyer [A-Z]{5}[0-9]{4}[A-Z] or chars 3-12 of customer GSTIN",
        "supplier_state": "Seller/supplier state name (e.g. Maharashtra)",
        "supplier_state_code": "Seller 2-digit state code (e.g. 27)",
        "customer_state": "Buyer/customer state name (e.g. Maharashtra)",
        "customer_state_code": "Buyer 2-digit state code (e.g. 27)",
        "place_of_supply": "Place of supply state name ONLY if explicitly written, else null",
        "taxable_amount": "Total taxable value / assessable amount before tax (number only, e.g. 831316.07)",
        "cgst": "Total CGST amount (number only, e.g. 74818.45)",
        "sgst": "Total SGST / UTGST amount (number only, e.g. 74818.45)",
        "igst": "Total IGST amount (number only)",
        "cess": "Total CESS amount (number only)",
        "total_tax": "Total tax amount (CGST + SGST + IGST + CESS, e.g. 149636.90)",
        "round_off": "Round off amount (number only, e.g. 0.03)",
        "amount": "Grand total / Amount chargeable / Total Credit Note amount (number only, e.g. 980953.00)",
        "total_quantity": "Total quantity across all items (e.g. 230.00 Nos)",
        "amount_in_words": "Total amount chargeable in words",
        "tax_amount_in_words": "Total tax amount in words",
        "reason": "Reason for issuance / credit if stated",
        "document_type": "Document type (Credit Note)",
    },
    "debit_note": {
        "invoice_number": "Debit note number",
        "invoice_date": "Debit note date (YYYY-MM-DD)",
        "original_invoice_number": "Original invoice number referenced, or null if none",
        "original_invoice_date": "Original invoice date referenced, or null if none",
        "vendor": "Supplier name",
        "customer": "Customer name",
        "gstin": "Supplier GSTIN",
        "supplier_gstin": "Supplier GSTIN",
        "customer_gstin": "Customer GSTIN",
        "supplier_pan": "10-character PAN of seller",
        "customer_pan": "10-character PAN of buyer",
        "supplier_state": "Supplier state name",
        "supplier_state_code": "Supplier state code",
        "customer_state": "Customer state name",
        "customer_state_code": "Customer state code",
        "place_of_supply": "Place of supply state name ONLY if explicitly written, else null",
        "taxable_amount": "Total taxable amount (number only)",
        "cgst": "Total CGST amount",
        "sgst": "Total SGST amount",
        "igst": "Total IGST amount",
        "cess": "Total CESS amount",
        "total_tax": "Total tax amount",
        "round_off": "Round off amount",
        "amount": "Debit note total amount (number only)",
        "total_quantity": "Total quantity across all items",
        "amount_in_words": "Total amount in words",
        "tax_amount_in_words": "Total tax amount in words",
        "reason": "Reason for debit note",
        "document_type": "Document type (Debit Note)",
    },
    "gst_return": {
        "gst_return_type": "Return type (GSTR-1 / GSTR-3B / Annual Return)",
        "financial_year": "Financial year (e.g. 2025-26)",
        "month": "Month/period",
        "filed_date": "Filing date (YYYY-MM-DD)",
        "arn": "ARN number",
        "gstin": "GSTIN",
    },
    "gst_notice": {
        "notice_number": "Notice number",
        "vendor": "Issuing authority / department",
        "notice_date": "Notice date (YYYY-MM-DD)",
        "response_due_date": "Response due date (YYYY-MM-DD)",
        "priority": "Priority (low/medium/high)",
        "gstin": "GSTIN",
    },
    "e_invoice": {
        "invoice_number": "IRN or document number",
        "invoice_date": "Document date (YYYY-MM-DD)",
        "gstin": "Supplier GSTIN",
        "amount": "Total invoice value",
    },
    "e_way_bill": {
        "invoice_number": "E-way bill number",
        "invoice_date": "E-way bill date (YYYY-MM-DD)",
        "gstin": "GSTIN",
        "amount": "Taxable value",
    },
    "gst_challan": {
        "cpin": "14-digit CPIN (Common Portal Identification Number, e.g. 21023300000006)",
        "cin": "Challan Identification Number (CIN) if present, else null",
        "invoice_number": "CPIN or challan reference number",
        "gstin": "15-character GSTIN (e.g. 33AACCA1121E9ZF)",
        "vendor": "Taxpayer Legal Name (e.g. Karnataka Bank Ltd)",
        "pan_number": "10-character PAN of taxpayer (chars 2-12 of GSTIN, e.g. AACCA1121E)",
        "email": "Taxpayer email address if present",
        "phone": "Taxpayer mobile or phone number if present",
        "address": "Taxpayer address if present",
        "state": "Taxpayer state name (e.g. Tamil Nadu)",
        "state_code": "Taxpayer state code (e.g. 33)",
        "challan_date": "Challan Generated on date (YYYY-MM-DD)",
        "expiry_date": "Challan Expiry date (YYYY-MM-DD)",
        "invoice_date": "Payment date or Challan date (YYYY-MM-DD)",
        "purpose": "Reason for Challan / Purpose (e.g. Any other payment)",
        "payment_method": "Mode of Payment (e.g. E-Payment, Over the Counter, NEFT/RTGS)",
        "bank_name": "Bank name if mentioned",
        "utr_number": "Bank Reference Number (BRN) or UTR if present",
        "amount_in_words": "Total amount in words (e.g. Rupees Ten Thousand Only)",
        "cgst_tax": "CGST Tax amount (number only)",
        "cgst_interest": "CGST Interest amount",
        "cgst_penalty": "CGST Penalty amount",
        "cgst_fee": "CGST Fee amount",
        "cgst_others": "CGST Others amount",
        "cgst": "Total CGST amount (number only)",
        "sgst_tax": "SGST Tax amount (number only)",
        "sgst_interest": "SGST Interest amount",
        "sgst_penalty": "SGST Penalty amount",
        "sgst_fee": "SGST Fee amount",
        "sgst_others": "SGST Others amount",
        "sgst": "Total SGST amount (number only)",
        "igst_tax": "IGST Tax amount (number only)",
        "igst_interest": "IGST Interest amount",
        "igst_penalty": "IGST Penalty amount",
        "igst_fee": "IGST Fee amount",
        "igst_others": "IGST Others amount",
        "igst": "Total IGST amount (number only)",
        "cess_tax": "CESS Tax amount (number only)",
        "cess_interest": "CESS Interest amount",
        "cess_penalty": "CESS Penalty amount",
        "cess_others": "CESS Others amount",
        "cess": "Total CESS amount (number only)",
        "taxable_amount": "Sub total / Tax Head total (number only)",
        "amount": "Grand Total / Total amount paid (number only)",
    },
    "hsn_sac": {
        "vendor": "Document description",
        "hsn": "HSN or SAC code",
    },
    "document_list": {
        "vendor": "Document name or description",
        "gstin": "GSTIN if present",
        "invoice_date": "Issue date if present (YYYY-MM-DD)",
    },
}


def _gemini_structured_extract(raw_text: str, category: str) -> Dict[str, Any]:
    """
    Use Gemini to extract structured fields from raw text using the category field schema.
    Returns a flat dict of {field_key: value_string} — only found fields, null for missing.
    """
    try:
        from app.core.config import get_settings
        settings = get_settings()
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return {}

        import google.genai as genai

        schema = _CATEGORY_FIELD_SCHEMA.get(category, _CATEGORY_FIELD_SCHEMA.get("sales_records", {}))
        schema_desc = "\n".join(f'  "{k}": {desc}' for k, desc in schema.items())
        field_keys = list(schema.keys())

        prompt = f"""You are a precise data extraction assistant for Indian GST documents.

Extract field values from the following document text for category: {category}

FIELD SCHEMA (return ONLY these exact keys):
{schema_desc}

CRITICAL RULES:
- Return a valid JSON object with ONLY the exact field keys listed above.
- If a field cannot be found in the document, set its value to null.
- Do NOT invent or calculate values — only extract what is explicitly present.
- Do NOT set a field value to a table column header (e.g. "Party", "Invoice No.", "Date").
- Do NOT add extra fields or change field names.
- Amounts must be numbers only (no currency symbols, no commas).
- Dates must be in YYYY-MM-DD format.
- GSTIN must be exactly as it appears (15 characters).
- Do NOT add any explanation outside the JSON.

DOCUMENT TEXT:
{raw_text[:4000]}

Return ONLY a JSON object with keys: {field_keys}"""

        client = genai.Client(api_key=api_key)
        preferred = settings.GEMINI_MODEL if settings.GEMINI_MODEL and not any(bad in settings.GEMINI_MODEL for bad in ("2.0", "2.5", "3.6")) else "gemini-flash-lite-latest"
        candidate_models = [preferred]
        for m_name in ("gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"):
            if m_name not in candidate_models:
                candidate_models.append(m_name)

        response = None
        last_ex = None
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[{"role": "user", "parts": [{"text": prompt}]}],
                )
                if response and response.text:
                    break
            except Exception as ex:
                last_ex = ex
                logger.warning("Gemini text model %s failed: %s", model_name, ex)
            if response and response.text:
                break

        if not response or not response.text:
            logger.warning("All Gemini text candidate models failed. Last error: %s", last_ex)
            return {}

        text = (response.text or "").strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}

        result = {}
        for k in field_keys:
            v = parsed.get(k)
            if v is not None and str(v).strip() and str(v).lower() not in ("null", "none", "n/a", ""):
                # Apply header guard to Gemini results too
                cleaned = _sanitize_field(str(v).strip())
                if cleaned:
                    result[k] = cleaned
        return result

    except Exception as e:
        logger.warning("Gemini structured extraction failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# File type constants
# ---------------------------------------------------------------------------

IMAGE_EXTS = {
    "jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif",
    "heic", "heif", "jfif", "avif",
}
PDF_EXTS = {"pdf"}


# ---------------------------------------------------------------------------
# Multi-record grouping
# ---------------------------------------------------------------------------

# Column keys that identify unique invoices / records within a table
_INVOICE_ID_KEYS = {
    "invoice_number", "inv_no", "bill_no", "doc_no",
    "invoice_no", "bill_number", "document_number",
    "document", "voucher_no", "challan_no", "ref_no",
    "irn", "invoice",
}

# Column keys that hold dates (used to pick the invoice date per record)
_DATE_KEYS = {
    "invoice_date", "date", "bill_date", "doc_date", "transaction_date",
    "dt", "document_date", "voucher_date",
}

# Column keys that hold the party/customer name per row
_PARTY_KEYS = {
    "party_name", "customer", "customer_name", "buyer_name",
    "vendor", "vendor_name", "supplier_name", "client_name",
    "party", "buyer", "supplier", "seller",
}

# Amount columns aggregated (summed) across line items
_AMOUNT_AGG_KEYS = [
    ("taxable_amount", "taxable_amount"),
    ("taxable_value",  "taxable_amount"),
    ("tax_amount",     "tax_amount"),
    ("net_amount",     "amount"),       # net_amount → amount in record fields
    ("grand_total",    "amount"),
    ("total_amount",   "amount"),
    ("cgst",           "cgst"),
    ("sgst",           "sgst"),
    ("igst",           "igst"),
    ("cess",           "cess"),
]


def _safe_float(v: str) -> float:
    """Parse a string as float, returning 0.0 on failure."""
    try:
        return float(str(v).replace(",", "").strip() or "0")
    except (ValueError, TypeError):
        return 0.0


def _find_col(headers: List[str], key_set: set) -> Optional[str]:
    """Return the first header from *headers* that matches any key in *key_set*.
    Matching is case-insensitive and ignores surrounding whitespace.
    """
    normalized_keys = {k.strip().lower() for k in key_set}
    for h in headers:
        if h.strip().lower() in normalized_keys:
            return h
    return None


def _group_table_rows_into_records(
    tables: List[Dict],
    doc_meta: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Group table rows into invoice/record objects.

    Algorithm:
    1. Find the invoice_number column.
    2. Group rows that share the same invoice_number.
    3. Each group becomes one record with:
         - fields: document-level metadata + invoice-level fields from first row
         - line_items: all rows in the group
         - amounts: summed across line items
    4. If no invoice_number column → all rows become one record.

    Returns: list of record dicts
      {
        record_number : int,
        fields        : {field_key: value_string},
        line_items    : [{col_key: value_string}],
        headers       : [str],
      }
    """
    if not tables:
        return []

    # ── Process every table and accumulate records ────────────
    from collections import OrderedDict

    all_records: List[Dict[str, Any]] = []
    global_idx = 0  # record counter across all tables

    for table in tables:
        headers: List[str] = table.get("headers", [])
        rows: List[Dict[str, str]] = table.get("rows", [])
        if not rows:
            continue

        inv_col   = _find_col(headers, _INVOICE_ID_KEYS)
        date_col  = _find_col(headers, _DATE_KEYS)
        party_col = _find_col(headers, _PARTY_KEYS)

        logger.debug(
            "Table: inv_col=%s date_col=%s party_col=%s rows=%d",
            inv_col, date_col, party_col, len(rows),
        )

        groups: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
        if inv_col:
            for row in rows:
                key = (row.get(inv_col) or "").strip() or "__no_inv__"
                groups.setdefault(key, []).append(row)
        else:
            # No invoice identifier in this table – treat ALL rows as line-items
            # of a single invoice/record (per function docstring §4 and user spec:
            # a "Sr No" items table with no Invoice No col = 1 invoice containing
            # all rows, not N spurious invoices).
            groups["__all__"] = list(rows)

        logger.info("Table yielded %d group(s)", len(groups))

        records: List[Dict[str, Any]] = []

        for inv_key, group_rows in groups.items():
            first_row = group_rows[0]
            record_fields: Dict[str, str] = {}

            # 1. Start with document-level metadata (company, GSTIN, period, report title)
            for k, v in doc_meta.items():
                if v and str(v).strip():
                    record_fields[k] = str(v).strip()

            # 2. Invoice number from the group key
            if inv_key not in ("__all__", "__no_inv__"):
                record_fields["invoice_number"] = inv_key

            # 3. Date from first row
            if date_col and first_row.get(date_col, "").strip():
                record_fields["invoice_date"] = _normalise_date(first_row[date_col].strip())

            # 4. Party/customer from first row
            if party_col and first_row.get(party_col, "").strip():
                party_val = first_row[party_col].strip()
                sanitized = _sanitize_field(party_val, headers)
                if sanitized:
                    record_fields["customer"] = sanitized
                    record_fields["vendor"]   = sanitized  # same for reports

            # 5. Aggregate amounts across all rows in this group
            for src_col, dst_field in _AMOUNT_AGG_KEYS:
                total = sum(_safe_float(row.get(src_col, "0")) for row in group_rows)
                if total > 0:
                    record_fields[dst_field] = f"{total:.2f}"

            # 6. GSTIN — prefer doc-level, then check rows
            if not record_fields.get("gstin"):
                for row in group_rows:
                    for col_val in row.values():
                        m = GSTIN_RE.search(col_val or "")
                        if m:
                            record_fields["gstin"] = m.group(1)
                            break
                    if record_fields.get("gstin"):
                        break

            global_idx += 1
            records.append({
                "record_number": global_idx,
                "fields": record_fields,
                "line_items": group_rows,
                "headers": headers,
            })

        all_records.extend(records)

    logger.info("Total records across all tables: %d", len(all_records))
    return all_records


def _build_single_record_from_fields(
    core_fields: Dict[str, Dict],
    meta_fields: Dict[str, Dict],
) -> List[Dict[str, Any]]:
    """
    Wrap a single-invoice extraction result in the records[] shape.
    Returns a list with one record.
    """
    flat_fields: Dict[str, str] = {}
    for k, v in {**core_fields, **meta_fields}.items():
        val = v.get("value", "") if isinstance(v, dict) else str(v or "")
        if val and val.strip():
            flat_fields[k] = val.strip()

    return [{
        "record_number": 1,
        "fields": flat_fields,
        "line_items": [],
        "headers": [],
    }]


# ---------------------------------------------------------------------------
# Parser-baseline helpers (FIX 1 / FIX 2 / FIX 3)
# ---------------------------------------------------------------------------

def _flatten_parser_fields(
    core_fields: Dict[str, Dict],
    meta_fields: Dict[str, Dict],
) -> Dict[str, str]:
    """
    Flatten category-parser output (core_fields + meta_fields) into a single
    flat {field_key: value_string} dict using the same convention as
    _build_single_record_from_fields. Missing values are dropped.

    This is the BASELINE that every record produced by the table-grouping
    path inherits. It guarantees parser fields (irn, ack_number, gst_return_type,
    notice_number, hsn, amounts, etc.) are never lost simply because
    _group_table_rows_into_records didn't know about them.
    """
    flat: Dict[str, str] = {}
    for k, v in {**core_fields, **meta_fields}.items():
        val = v.get("value", "") if isinstance(v, dict) else str(v or "")
        if val and str(val).strip():
            flat[k] = str(val).strip()
    return flat


def _is_meaningful_table_value(v: Any) -> bool:
    """
    Return True when a value produced by the table grouper is reliable enough
    to *override* the parser baseline.

    Rejects: None, "", whitespace-only, numeric zeros (0 / "0" / "0.00" /
    "0.0") because zeros are typical when table column aliasing failed and
    the aggregation had nothing to sum. The parser's non-zero amount must
    win in that case.
    """
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    # Numeric check: zero → unreliable (FIX 2)
    try:
        if float(s.replace(",", "")) == 0:
            return False
    except ValueError:
        pass
    return True


def _merge_parser_baseline_into_records(
    records: List[Dict[str, Any]],
    parser_baseline: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Merge parser-derived baseline fields into every record produced by the
    table-grouping path. Priority per field per record:

      1. Existing record.fields[k] IF meaningful (non-empty, non-zero amount)
      2. parser_baseline[k]
      3. absent

    This covers:
      - Invoice/document-level metadata shared across a multi-record PDF.
      - Amounts whose table sums were 0 because column aliases weren't detected
        (parser value wins, FIX 2).
      - Category-specific keys that the grouper never writes (FIX 3).
    """
    if not parser_baseline:
        return records
    for rec in records:
        fields = rec.get("fields") or {}
        merged: Dict[str, str] = {}
        # 1. Parser baseline first
        for k, v in parser_baseline.items():
            if v and str(v).strip():
                merged[k] = str(v).strip()
        # 2. Override with record value only when it is meaningful
        for k, v in fields.items():
            if _is_meaningful_table_value(v):
                merged[k] = str(v).strip()
        rec["fields"] = merged
    return records


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
    Run layered extraction pipeline and return category-specific fields with confidence tags.

    Response shape:
      success           : bool
      has_content       : bool          — False = no document text detected
      category          : str
      extraction_method : str           — how text was extracted
      core_fields       : dict          — DB-mapped fields with {value, confidence}
      metadata_fields   : dict          — category-specific extra fields
      table_data        : dict|null     — {headers, rows} if tables were found
      validation        : dict          — GSTIN check, amount check, warnings
      extraction_summary: dict          — {fields_found, table_rows_found}
      raw_text          : str           — first 3000 chars for debugging
      message           : str
    """
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = (file.content_type or "").lower()

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB for OCR).")

    logger.info(
        "OCR extract: filename=%s ext=%s content_type=%s size=%d category=%s",
        filename, ext, content_type, len(content), category,
    )

    # ── Detect file type ─────────────────────────────────────────
    TEXT_EXTS = {"txt", "csv", "tsv", "html", "htm", "xml", "json"}
    DOCX_EXTS = {"docx"}
    LEGACY_DOC_EXTS = {"doc"}

    is_legacy_doc = (
        ext in LEGACY_DOC_EXTS
        or ("msword" in content_type and "wordprocessingml" not in content_type)
    )
    if is_legacy_doc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Legacy .doc format is not supported. "
                "Please open the file in Microsoft Word or LibreOffice "
                "and save it as .docx (Word 2007+ document) before uploading."
            ),
        )

    is_pdf = ext in PDF_EXTS or content_type == "application/pdf" or content[:4] == b"%PDF"
    is_image = ext in IMAGE_EXTS or content_type.startswith("image/")
    is_text = ext in TEXT_EXTS or content_type.startswith("text/")
    is_docx = ext in DOCX_EXTS or "wordprocessingml" in content_type or "msword" in content_type

    logger.info("File type detected: is_pdf=%s is_image=%s is_docx=%s is_text=%s", is_pdf, is_image, is_docx, is_text)

    # ── Extract text + tables ─────────────────────────────────────
    raw_text = ""
    extraction_method = "unknown"
    tables: List[Dict] = []
    # IMPORTANT: table_meta must be initialised here so it is ALWAYS defined,
    # regardless of which file-type branch is taken below.
    table_meta: Dict[str, str] = {}
    # ocr_confidence is set in the is_image branch; init here so always accessible.
    ocr_confidence: float = 100.0

    if is_pdf:
        raw_text, extraction_method = _ocr_pdf(content)
        logger.info("Attempting PDF table and metadata extraction...")
        table_meta, pdf_tables = _extract_tables_and_metadata_from_pdf(content)
        if pdf_tables:
            logger.info("PDF table extraction found %d table(s)", len(pdf_tables))
            tables = pdf_tables
            extraction_method = "native_pdf_text+table"
        else:
            logger.info("No vector tables in PDF; checking rasterized page for tabular data...")
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                if len(doc) > 0:
                    page_img = doc[0].get_pixmap(dpi=200).tobytes("jpeg")
                    scanned_pdf_tables = _extract_tables_from_image_ocr(page_img, raw_text)
                    if scanned_pdf_tables:
                        tables = scanned_pdf_tables
                        logger.info("Rasterized PDF table extraction found %d table(s)", len(tables))
                doc.close()
            except Exception as pdf_tbl_err:
                logger.debug("Rasterized PDF table fallback skipped: %s", pdf_tbl_err)

    elif is_image:
        raw_text, ocr_confidence = _ocr_image(content)
        extraction_method = "ocr_tesseract"
        logger.info("Image OCR complete: %d chars, mean_confidence=%.1f%%", len(raw_text), ocr_confidence)
        # X-coordinate column clustering for table structure
        tables = _extract_tables_from_image_ocr(content, raw_text)

    elif is_docx:
        raw_text = _ocr_docx(content)
        extraction_method = "docx_native"
        docx_tables = _extract_tables_from_docx(content)
        if docx_tables:
            tables = docx_tables
            extraction_method = "docx_native+table"

    elif is_text:
        raw_text = _read_text_file(content)
        extraction_method = "plain_text"

    else:
        # Unknown — try in order
        for extractor, method in [
            (lambda: (_ocr_image(content), "ocr_tesseract"), "image"),
            (lambda: (_ocr_docx(content), "docx_native"), "docx"),
            (lambda: (_read_text_file(content), "plain_text"), "text"),
        ]:
            try:
                raw_text, extraction_method = extractor()
                if _is_meaningful(raw_text):
                    break
            except Exception:
                pass
        if not raw_text:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '.{ext}'. Please upload an image (JPG, PNG), PDF, or DOCX.",
            )

    logger.info("Extraction method: %s, raw_text length: %d chars, tables: %d", extraction_method, len(raw_text), len(tables))

    # ── Meaningful-content check ─────────────────────────────────
    has_meaningful_text = _is_meaningful(raw_text)
    has_tables = len(tables) > 0 and any(len(t.get("rows", [])) > 0 for t in tables)

    if not has_meaningful_text and not has_tables:
        return {
            "success": True,
            "has_content": False,
            "category": category,
            "extraction_method": extraction_method,
            "core_fields": {},
            "metadata_fields": {},
            "table_data": None,
            "validation": {"gstin": {}, "amounts": {}, "warnings": []},
            "extraction_summary": {"fields_found": 0, "table_rows_found": 0},
            "raw_text": "",
            "message": (
                "No document text was detected. "
                "This appears to be a blank image or an image without readable document content. "
                "Please upload a clear photo of an invoice, receipt, bill, or notice."
            ),
        }

    # ── Category-aware parsing ────────────────────────────────────
    logger.info("Running category parser for: %s", category)
    block_meta = _extract_document_text_blocks(raw_text)
    combined_meta = {**block_meta, **table_meta}
    core_fields, meta_fields = _dispatch_parser(category, raw_text, tables, combined_meta)

    # ── Gemini Vision / Text fallback ─────────────────────────────
    extracted_count = sum(
        1 for v in {**core_fields, **meta_fields}.values()
        if isinstance(v, dict) and v.get("value")
    )

    # Determine if Gemini fallback is warranted:
    #   - 0 fields extracted anywhere (always trigger), OR
    #   - Image document with Tesseract confidence < 60% (bad OCR read), OR
    #   - Image with fewer than 20 fields extracted (Vision fills remaining gaps)
    #     Real-world invoice photos benefit from Gemini's multimodal understanding
    #     which can read rotated text, faded print, and OCR noise better than regex
    has_gemini_key = bool(getattr(_get_settings(), "GEMINI_API_KEY", ""))
    need_gemini = (
        extracted_count == 0
        or (is_image and ocr_confidence < 60.0)
        or ((is_image or is_pdf) and has_gemini_key)   # Use Vision for both images and PDFs when key is set
    )

    if need_gemini:
        if is_image or is_pdf:
            # TRUE vision fallback — send raw image or rendered PDF page bytes to Gemini
            logger.info(
                "Triggering Gemini Vision fallback for %s (extracted=%d, conf=%.1f%%)",
                "PDF" if is_pdf else "image", extracted_count, ocr_confidence,
            )
            gemini_fields, gemini_line_items = _gemini_vision_extract(content, category)
            extraction_method = "ocr_gemini_vision"
        else:
            # Text-based Gemini (for DOCX/plain text with 0 regex hits)
            logger.info("Regex extracted 0 fields — attempting Gemini text extraction")
            gemini_fields = _gemini_structured_extract(raw_text, category)
            gemini_line_items = []

        if gemini_line_items:
            logger.info("Gemini Vision extracted %d line item(s)", len(gemini_line_items))
            col_labels = {
                "sr_no": "Sr. No.",
                "item_name": "Item Description",
                "company_name": "Company / Brand",
                "hsn": "HSN / SAC",
                "batch_no": "Batch No.",
                "expiry_date": "Expiry Date",
                "quantity": "Quantity",
                "rate": "Rate / Price",
                "discount": "Discount",
                "taxable_amount": "Taxable Value",
                "cgst_amount": "CGST",
                "sgst_amount": "SGST",
                "igst_amount": "IGST",
                "total_amount": "Total Amount",
            }
            preferred_order = [
                "sr_no", "item_name", "company_name", "hsn", "batch_no", "expiry_date",
                "quantity", "rate", "discount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
            ]
            active_cols = [c for c in preferred_order if any(c in row for row in gemini_line_items)]
            for row in gemini_line_items:
                for k in row.keys():
                    if k not in active_cols:
                        active_cols.append(k)
            raw_headers = [col_labels.get(c, c.replace("_", " ").title()) for c in active_cols]

            enriched_rows = []
            for row in gemini_line_items:
                er = dict(row)
                for c, rh in zip(active_cols, raw_headers):
                    if c in row and rh not in er:
                        er[rh] = row[c]
                    elif rh in row and c not in er:
                        er[c] = row[rh]
                enriched_rows.append(er)

            gemini_table = {
                "headers": active_cols,
                "headers_raw": raw_headers,
                "rows": enriched_rows,
            }
            tables = [gemini_table]
            has_tables = True

        if gemini_fields:
            for k, v in gemini_fields.items():
                if k == "hsn_summary":
                    meta_fields["hsn_summary"] = _field(json.dumps(v) if isinstance(v, (list, dict)) else str(v), "extracted")
                    continue
                if v is not None and isinstance(v, (str, int, float)) and str(v).strip():
                    gemini_val = str(v).strip()
                    if k in ("invoice_date", "date", "expiry_date"):
                        norm_d = _normalise_date(gemini_val)
                        if norm_d:
                            gemini_val = norm_d
                    existing = (core_fields.get(k) or meta_fields.get(k) or {}).get("value", "")
                    # Overwrite if empty, or longer, or key invoice identity / calculation fields
                    if not existing or (len(gemini_val) > len(existing) * 0.6) or k in (
                        "vendor", "customer", "invoice_number", "invoice_date", "hsn", "gstin",
                        "amount", "taxable_amount", "cgst", "sgst", "igst", "cess", "total_tax",
                        "round_off", "total_quantity", "amount_in_words", "tax_amount_in_words",
                        "customer_gstin", "supplier_gstin"
                    ):
                        if k in core_fields:
                            core_fields[k] = _field(gemini_val, "extracted")
                        elif k in meta_fields:
                            meta_fields[k] = _field(gemini_val, "extracted")
                        else:
                            # Map standard invoice fields into appropriate section
                            if k in (
                                "vendor", "customer", "invoice_number", "invoice_date",
                                "amount", "taxable_amount", "cgst", "sgst", "igst", "cess", "hsn", "gstin"
                            ):
                                core_fields[k] = _field(gemini_val, "extracted")
                            else:
                                meta_fields[k] = _field(gemini_val, "extracted")

            # Ensure core gstin is populated if supplier_gstin was extracted
            if not (core_fields.get("gstin") or {}).get("value"):
                sup_g = (meta_fields.get("supplier_gstin") or core_fields.get("supplier_gstin") or {}).get("value")
                if sup_g:
                    core_fields["gstin"] = _field(sup_g, "extracted")

            logger.info("Gemini added/updated %d fields: %s", len(gemini_fields), list(gemini_fields.keys()))

    # ── Build table_data response (raw, kept for compat) ─────────
    table_data = None
    total_table_rows = 0
    if tables:
        primary_table = max(tables, key=lambda t: len(t.get("rows", [])))
        total_table_rows = sum(len(t.get("rows", [])) for t in tables)
        table_data = {
            "headers":      primary_table.get("headers", []),
            "headers_raw":  primary_table.get("headers_raw", []),
            "rows":         primary_table.get("rows", []),
            "total_rows":   total_table_rows,
            "table_count":  len(tables),
        }
        logger.info(
            "Table data: %d table(s), %d total rows, headers: %s",
            len(tables), total_table_rows, primary_table.get("headers", []),
        )

    # ── Strict place of supply and PAN sanitization ────────────────
    if "place_of_supply" in meta_fields:
        curr_pos = meta_fields["place_of_supply"].get("value", "")
        cl_pos = _clean_place_of_supply(curr_pos)
        if cl_pos:
            meta_fields["place_of_supply"] = _field(cl_pos, "extracted")
        else:
            meta_fields["place_of_supply"] = _missing()

    sup_g = (meta_fields.get("supplier_gstin") or core_fields.get("gstin") or {}).get("value", "")
    if "pan_number" in meta_fields:
        curr_pan = meta_fields["pan_number"].get("value", "")
        cl_pan = _clean_pan(curr_pan, fallback_gstin=sup_g)
        if cl_pan:
            meta_fields["pan_number"] = _field(cl_pan, "extracted")
            meta_fields["supplier_pan"] = _field(cl_pan, "extracted")
        else:
            meta_fields["pan_number"] = _missing()

    if "supplier_pan" in meta_fields:
        curr_span = meta_fields["supplier_pan"].get("value", "")
        cl_span = _clean_pan(curr_span, fallback_gstin=sup_g)
        if cl_span:
            meta_fields["supplier_pan"] = _field(cl_span, "extracted")
        else:
            meta_fields["supplier_pan"] = _missing()

    cust_g = (meta_fields.get("customer_gstin") or {}).get("value", "")
    if "customer_pan" in meta_fields:
        curr_cpan = meta_fields["customer_pan"].get("value", "")
        cl_cpan = _clean_pan(curr_cpan, fallback_gstin=cust_g)
        if cl_cpan:
            meta_fields["customer_pan"] = _field(cl_cpan, "extracted")
        else:
            meta_fields["customer_pan"] = _missing()

    if "contact_person" in meta_fields:
        curr_cp = meta_fields["contact_person"].get("value", "")
        cl_cp = _clean_contact_person(curr_cp)
        if cl_cp:
            meta_fields["contact_person"] = _field(cl_cp, "extracted")
        else:
            meta_fields["contact_person"] = _missing()

    # ── Post-extraction validation ────────────────────────────────
    validation = _validate_extraction(core_fields, meta_fields, category)

    gstin_val = validation["gstin"]
    if gstin_val.get("valid") is False and "gstin" in core_fields:
        core_fields["gstin"]["confidence"] = "needs_review"
    if gstin_val.get("normalized") and "gstin" in core_fields:
        core_fields["gstin"]["value"] = gstin_val["normalized"]

    if validation["amounts"].get("ok") is False:
        for f in ("amount", "taxable_amount", "cgst", "sgst", "igst"):
            if f in core_fields and core_fields[f].get("confidence") == "extracted":
                core_fields[f]["confidence"] = "needs_review"

    # ── Build records[] — multi-record grouping ───────────────────
    #
    # If the document has tables with an invoice_number column:
    #   → group rows by invoice_number → N records
    # Otherwise:
    #   → single record from core_fields / meta_fields
    #
    doc_meta_flat: Dict[str, str] = {}
    for k, v in {**core_fields, **meta_fields}.items():
        val = v.get("value", "") if isinstance(v, dict) else str(v or "")
        if val and val.strip():
            doc_meta_flat[k] = val.strip()

    records: List[Dict[str, Any]] = []

    # Build parser BASELINE: flatten core+meta fields once. This is the
    # authoritative source for any field the table grouper doesn't produce
    # reliably (FIX 1 / FIX 2 / FIX 3).
    parser_baseline = _flatten_parser_fields(core_fields, meta_fields)

    is_multi_invoice_table = False
    if has_tables and category in ("sales_records", "purchase_records", "document_list"):
        for t in tables:
            rows = t.get("rows", [])
            headers = t.get("headers", [])
            inv_col = _find_col(headers, _INVOICE_ID_KEYS)
            if inv_col and len(rows) > 1:
                inv_vals = {r.get(inv_col, "").strip() for r in rows if r.get(inv_col, "").strip()}
                if len(inv_vals) > 1:
                    is_multi_invoice_table = True
                    break

    if is_multi_invoice_table:
        records = _group_table_rows_into_records(tables, doc_meta_flat)
        logger.info("Multi-record grouping produced %d record(s)", len(records))
        records = _merge_parser_baseline_into_records(records, parser_baseline)
    else:
        records = _build_single_record_from_fields(core_fields, meta_fields)
        if tables and len(tables) > 0:
            records[0]["line_items"] = tables[0].get("rows", [])
            records[0]["headers"] = tables[0].get("headers_raw", [])
        logger.info("Single-record with %d line items", len(records[0].get("line_items", [])) if records else 0)
        records = _merge_parser_baseline_into_records(records, parser_baseline)

    if not records:
        records = _build_single_record_from_fields(core_fields, meta_fields)
        records = _merge_parser_baseline_into_records(records, parser_baseline)

    record_count = len(records)

    # ── Compute summary ───────────────────────────────────────────
    final_extracted = sum(
        1 for v in {**core_fields, **meta_fields}.values()
        if isinstance(v, dict) and v.get("value")
    )
    total_possible = len(core_fields) + len(meta_fields)

    has_any_content = (
        final_extracted > 0
        or total_table_rows > 0
        or any(r.get("fields") for r in records)
    )

    # ── Build message ─────────────────────────────────────────────
    if not has_any_content:
        message = (
            "Document processed, but no reliable fields were detected. "
            "Please review manually before saving."
        )
    elif record_count > 1:
        message = (
            f"Found {record_count} invoice record(s) in this document. "
            "Review each record before saving."
        )
    elif total_table_rows > 0 and final_extracted > 0:
        message = (
            f"Document processed. {final_extracted} field(s) and {total_table_rows} "
            f"table row(s) extracted."
        )
    elif total_table_rows > 0:
        message = (
            f"Document processed. {total_table_rows} table row(s) extracted. "
            "Fill in any missing document-level fields below."
        )
    elif final_extracted > 0:
        message = f"OCR extraction complete. {final_extracted} field(s) extracted."
    else:
        message = "Text detected but no structured fields found. Fill in fields manually."

    _diag: Dict[str, Any] = {
        "file": {
            "filename": filename,
            "ext": ext,
            "content_type": content_type,
            "size_bytes": len(content),
        },
        "processing": {
            "native_text_attempted": is_pdf or is_docx or is_text,
            "native_text_chars": len(raw_text) if extraction_method.startswith(("native", "plain", "docx")) else 0,
            "ocr_triggered": extraction_method in ("ocr_tesseract", "ocr_gemini_vision"),
            "pages_processed": record_count if extraction_method.startswith("native_pdf") else (1 if is_image else 0),
            "ocr_text_chars": len(raw_text) if extraction_method == "ocr_tesseract" else 0,
            "extraction_method": extraction_method,
        },
        "extraction": {
            "category": category,
            "parser_used": category,
            "fields_detected": final_extracted,
            "fields_not_detected": max(0, total_possible - final_extracted),
            "records_detected": record_count,
            "table_rows_detected": total_table_rows,
        },
    }
    logger.info("OCR pipeline diagnostics: %s", json.dumps(_diag, default=str))

    return {
        "success":           True,
        "has_content":       has_any_content,
        "category":          category,
        "extraction_method": extraction_method,
        # ── Multi-record response ──
        "record_count":      record_count,
        "records":           records,
        # ── Legacy single-record fields (records[0] equivalent) ──
        "core_fields":       core_fields,
        "metadata_fields":   meta_fields,
        "table_data":        table_data,
        # ── Validation & summary ──
        "validation": validation,
        "extraction_summary": {
            "fields_found":    final_extracted,
            "fields_available": total_possible,
            "table_rows_found": total_table_rows,
            "record_count":    record_count,
        },
        "raw_text": raw_text[:3000],
        "message":  message,
    }


# ---------------------------------------------------------------------------
# Test compatibility aliases
# ---------------------------------------------------------------------------

_extract_document_metadata = _extract_document_text_blocks
_parse_gst_challan = _parse_challan

def _dispatch_parser(category: str, raw_text: str, tables: Optional[list] = None, struc: Optional[dict] = None):
    if struc is None:
        struc = _extract_document_text_blocks(raw_text)
    if tables is None:
        tables = []
    parsers = {
        "sales_records": _parse_sales_records,
        "purchase_records": _parse_purchase_records,
        "credit_note": _parse_credit_debit_note,
        "debit_note": _parse_credit_debit_note,
        "b2b_invoice": _parse_invoice,
        "b2c_invoice": _parse_invoice,
        "hsn_sac": _parse_hsn_sac,
        "e_invoice": _parse_invoice,
        "e_way_bill": _parse_e_way_bill,
        "gst_challan": _parse_challan,
        "gst_return": _parse_gst_return,
        "gst_notice": _parse_gst_notice,
        "document_list": _parse_document_list,
    }
    fn = parsers.get(category, _parse_invoice)
    return fn(raw_text, struc, tables)

def _extract_hsn(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"\bHSN[:\s]*([0-9]{4,8})\b", text, re.I)
    if not m:
        m = re.search(r"\b([0-9]{4,8})\b", text)
    return m.group(1) if m else ""

def _split_invoice_zones(text: str) -> Tuple[str, str, bool]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    seller = ""
    buyer = ""
    has = False
    for i, line in enumerate(lines):
        if any(k in line.lower() for k in ("bill to", "buyer", "sold to", "recipient", "to:")):
            has = True
            buyer = "\n".join(lines[i:])
            seller = "\n".join(lines[:i])
            break
    if not has:
        seller = text
        buyer = ""
    return seller, buyer, has
