"""
OCR API Router
POST /api/v1/ocr/extract  — upload any image/PDF, return extracted key-value fields

Supports:
  • Printed documents (invoices, receipts, GST notices, returns)
  • Handwritten documents — uses Tesseract LSTM (OEM 1) with multiple PSM strategies
  • PDFs — text layer first, image OCR fallback per-page
Returns has_content=False when no document text is found so the frontend can block saving.
"""

import io
import re
import os
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Configure Tesseract path (Windows default install location)
# pytesseract will use this if tesseract.exe is not already in the system PATH
# ---------------------------------------------------------------------------
_TESSERACT_WINDOWS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    import pytesseract

    # Only set the path if it hasn't been found on PATH already
    if os.name == "nt" and os.path.isfile(_TESSERACT_WINDOWS_PATH):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WINDOWS_PATH
except ImportError:
    pass  # handled lazily inside _ocr_image


# ---------------------------------------------------------------------------
# Image pre-processing for better OCR accuracy (printed + handwritten)
# ---------------------------------------------------------------------------

def _preprocess(img):
    """
    Apply contrast/sharpness enhancement and convert to grayscale.
    This improves OCR on low-quality photos and handwritten documents.
    """
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps

        # Convert to grayscale
        img = img.convert("L")
        # Increase contrast
        img = ImageEnhance.Contrast(img).enhance(2.0)
        # Increase sharpness
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        # Auto-level (stretch histogram) for uneven lighting
        img = ImageOps.autocontrast(img, cutoff=1)
        # Sharpen edges — helps with blurry handwriting
        img = img.filter(ImageFilter.SHARPEN)
        return img
    except Exception:
        return img  # return unchanged if PIL ops fail


# ---------------------------------------------------------------------------
# OCR strategies
# ---------------------------------------------------------------------------

# PSM modes to try (in order):
#   6  = Assume a uniform block of text (good for printed invoices)
#   11 = Sparse text — find as much text as possible (good for receipts)
#   3  = Fully automatic page segmentation (default)
#   13 = Raw line, treat image as a single text line (handwriting)
_PSM_MODES = [6, 11, 3, 13]


def _ocr_image(content: bytes) -> str:
    """
    Run Tesseract OCR on image bytes.
    Tries multiple PSM modes and returns the longest / best result.
    Uses OEM 1 (LSTM neural net) which handles handwriting significantly better
    than the legacy engine.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OCR engine not installed on server. Please install pytesseract and Tesseract-OCR.",
        )

    try:
        raw_img = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    # Always try on both original and pre-processed versions
    images_to_try = [raw_img, _preprocess(raw_img)]

    best_text = ""
    for img in images_to_try:
        for psm in _PSM_MODES:
            try:
                config = f"--oem 1 --psm {psm}"
                text = pytesseract.image_to_string(img, lang="eng", config=config)
                text = text.strip()
                # Keep the longest meaningful result
                if len(text) > len(best_text):
                    best_text = text
                # If we already have good data (>100 chars) stop trying more modes
                if len(best_text) > 100:
                    break
            except Exception as e:
                logger.debug("OCR psm=%d failed: %s", psm, e)
                continue
        if len(best_text) > 100:
            break

    return best_text


def _ocr_pdf(content: bytes) -> str:
    """Extract text from PDF (text-layer first, then image OCR per page)."""
    text_parts = []
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        for page in reader.pages:
            extracted = page.extract_text() or ""
            text_parts.append(extracted)
        combined = "\n".join(text_parts).strip()
        if combined:
            return combined
    except ImportError:
        pass  # fall through to image-based OCR
    except Exception as e:
        logger.warning("pypdf error: %s", e)

    # Fallback: render PDF pages as images then OCR
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            text_parts.append(_ocr_image(img_bytes))
        return "\n".join(text_parts)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF processing library not installed. Install pypdf or PyMuPDF.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF OCR failed: {e}")


# ---------------------------------------------------------------------------
# Field extraction from raw text
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_from_text(raw: str, category: str) -> dict:
    """
    Parse key accounting fields from raw OCR text using regex heuristics.
    Handles both printed and handwritten text (OCR outputs may have imperfect spacing).
    Returns a flat dict of field_name -> value_string.
    """
    t = raw

    def find(patterns, flags=re.IGNORECASE):
        for p in patterns:
            m = re.search(p, t, flags)
            if m:
                return _clean(m.group(1))
        return ""

    # ── Invoice / document fields ──────────────────────────────
    invoice_number = find([
        r"invoice\s*(?:no|number|num|#|:)[:\s.#]*([A-Z0-9][\w\-/]{2,})",
        r"bill\s*(?:no|number|#|:)[:\s.#]*([A-Z0-9][\w\-/]{2,})",
        r"(?:INV|BILL|GST|TAX\s*INV)\s*[-/]?\s*([A-Z0-9]{4,})",
        # Handwriting patterns: numbers written on a line after a label
        r"(?:Inv\.?\s*No\.?|Invoice\s*#)\s*[:\-]?\s*([A-Z0-9][\w\-/]{2,})",
    ])

    gstin = find([
        r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
    ])

    vendor = find([
        r"(?:from|sold\s+by|vendor|supplier|billed\s+from|party\s+name|firm\s+name)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"^([A-Z][A-Za-z0-9 &.,()-]{3,60}(?:Pvt\.?\s*Ltd|Ltd|LLP|Inc|Corp|Co|Enterprises|Trading)\.?)",
        # Handwriting: first non-empty line that looks like a business name
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s*$",
    ], re.MULTILINE)

    customer = find([
        r"(?:to|bill\s+to|ship\s+to|customer|buyer|consignee|delivered\s+to)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"(?:M/s\.?\s*)([A-Za-z0-9 &.,()-]{3,60})",
    ])

    invoice_date = find([
        r"(?:date|invoice\s+date|bill\s+date|dt\.?)[:\s]*((?:\d{1,2}[-/\s.]\d{1,2}[-/\s.]\d{2,4})|\d{4}[-/]\d{2}[-/]\d{2})",
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        # Written dates like "07 Aug 2026", "7th August 2026"
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    ])
    # Normalise to YYYY-MM-DD if possible
    if invoice_date:
        from datetime import datetime
        normalised = ""
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m-%d-%Y", "%m/%d/%Y",
                    "%d %B %Y", "%d %b %Y", "%dth %B %Y", "%dst %B %Y",
                    "%dnd %B %Y", "%drd %B %Y"):
            try:
                # Remove ordinal suffixes for parsing
                clean_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", invoice_date)
                normalised = datetime.strptime(clean_date.strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        if normalised:
            invoice_date = normalised

    # ── Monetary amounts ───────────────────────────────────────
    def find_amount(patterns):
        for p in patterns:
            m = re.search(p, t, re.IGNORECASE)
            if m:
                raw_val = m.group(1).replace(",", "").strip()
                try:
                    return f"{float(raw_val):.2f}"
                except ValueError:
                    pass
        return ""

    amount = find_amount([
        r"(?:grand\s+total|total\s+amount|total\s+due|net\s+total|amount\s+due|total)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:net\s+payable|payable\s+amount|pay\s+this\s+amount)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        # Handwriting: line starting with ₹ or Rs
        r"(?:₹|Rs\.?)\s*([0-9,]+\.?[0-9]{0,2})\s*(?:/-|only|$)",
    ])
    taxable_amount = find_amount([
        r"(?:taxable\s+(?:value|amount)|assessable\s+value|basic\s+amount)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:sub\s*total|subtotal)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
    ])
    cgst = find_amount([
        r"C\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    sgst = find_amount([
        r"S\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    igst = find_amount([
        r"I\.?G\.?S\.?T\.?[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    cess = find_amount([
        r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])

    hsn = find([
        r"H\.?S\.?N\.?[/\s]*(?:SAC)?[:\s]*([0-9]{4,8})",
        r"SAC[:\s]*([0-9]{4,8})",
    ])

    # ── GST Return specific ────────────────────────────────────
    gst_return_type = find([
        r"\b(GSTR-[0-9A-Z]+(?:\s*Annual\s*Return)?)\b",
    ])
    arn = find([
        r"\bARN[:\s]*([A-Z0-9]{14,20})\b",
    ])
    financial_year = find([
        r"(?:financial\s+year|FY|F\.Y\.?)[:\s]*([0-9]{4}[-–][0-9]{2,4})",
    ])

    # ── Notice specific ────────────────────────────────────────
    notice_number = find([
        r"(?:notice\s*(?:no|number|ref)|ref(?:erence)?\s*no)[:\s.]*([A-Z0-9/\-]{4,})",
    ])
    notice_date = find([
        r"(?:notice\s+date|issued\s+on|date\s+of\s+issue)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ])
    response_due_date = find([
        r"(?:due\s+date|respond\s+by|last\s+date|reply\s+by)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ])

    # ── Assemble by category ───────────────────────────────────
    if category == "gst_notice":
        return {
            "notice_number": notice_number or invoice_number,
            "notice_date": notice_date or invoice_date,
            "response_due_date": response_due_date,
        }

    if category == "gst_return":
        return {
            "gst_return_type": gst_return_type,
            "financial_year": financial_year,
            "arn": arn,
        }

    return {
        "invoice_number": invoice_number,
        "vendor": vendor,
        "customer": customer,
        "gstin": gstin,
        "invoice_date": invoice_date,
        "amount": amount,
        "taxable_amount": taxable_amount,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "hsn": hsn,
    }


def _is_meaningful_text(raw: str) -> bool:
    """
    Return True only if the OCR output looks like it came from a document
    (not a blank page, face photo, or random noise).
    A meaningful document text should contain:
      - At least 20 characters total, AND
      - At least 3 real word-like tokens (letters 3+ chars long)
    """
    if not raw or len(raw.strip()) < 20:
        return False
    # Count word-like tokens (3+ alphabetic chars)
    words = re.findall(r"[A-Za-z]{3,}", raw)
    return len(words) >= 3


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
    Accept any image or PDF file.
    Run OCR / text extraction and return parsed accounting fields.

    Response includes:
      has_content (bool) — False means no document text was detected; frontend should NOT allow saving.
    """
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB for OCR).")

    # ── Choose extraction strategy ─────────────────────────────
    if ext in PDF_EXTS or (file.content_type or "").lower() == "application/pdf":
        raw_text = _ocr_pdf(content)
    elif ext in IMAGE_EXTS or (file.content_type or "").lower().startswith("image/"):
        raw_text = _ocr_image(content)
    else:
        # Unknown type — try image OCR as a best-effort
        try:
            raw_text = _ocr_image(content)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '.{ext}'. Please upload an image or PDF.",
            )

    # ── Check if the OCR output actually looks like a document ─
    if not _is_meaningful_text(raw_text):
        return {
            "success": True,
            "has_content": False,
            "raw_text": "",
            "fields": {},
            "message": (
                "No document text was detected in this file. "
                "This appears to be a photo or image without readable document content. "
                "Please upload a clear photo of an invoice, receipt, bill, or notice."
            ),
        }

    fields = _extract_from_text(raw_text, category)

    # Check if at least some fields were extracted
    has_any_field = any(v and v.strip() for v in fields.values())

    return {
        "success": True,
        "has_content": True,
        "raw_text": raw_text[:3000],  # truncated for payload size
        "fields": fields,
        "message": (
            "OCR extraction complete."
            if has_any_field
            else (
                "Text was detected but no structured fields could be extracted. "
                "You can fill in the fields manually below."
            )
        ),
    }
