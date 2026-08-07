"""
OCR API Router
POST /api/v1/ocr/extract  — upload any image/PDF, return extracted key-value fields
"""

import io
import re
import os
import logging
from typing import Optional

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
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_from_text(raw: str, category: str) -> dict:
    """
    Parse key accounting fields from raw OCR text using regex heuristics.
    Returns a flat dict of field_name -> value_string (may be empty strings).
    """
    t = raw  # keep original case for some patterns

    def find(patterns, flags=re.IGNORECASE):
        for p in patterns:
            m = re.search(p, t, flags)
            if m:
                return _clean(m.group(1))
        return ""

    # ── Invoice / document fields ──────────────────────────────
    invoice_number = find([
        r"invoice\s*(?:no|number|num|#)[:\s.]*([A-Z0-9\-/]+)",
        r"bill\s*(?:no|number|#)[:\s.]*([A-Z0-9\-/]+)",
        r"(?:INV|BILL|GST)\s*[-/]?\s*([A-Z0-9]{4,})",
    ])

    gstin = find([
        r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
    ])

    vendor = find([
        r"(?:from|sold\s+by|vendor|supplier|billed\s+from)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"^([A-Z][A-Za-z0-9 &.,()-]{3,60}(?:Pvt\.?\s*Ltd|Ltd|LLP|Inc|Corp|Co)\.?)",
    ], re.MULTILINE)

    customer = find([
        r"(?:to|bill\s+to|ship\s+to|customer|buyer)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
        r"(?:consignee)[:\s]+([A-Za-z0-9 &.,()-]{3,60})",
    ])

    invoice_date = find([
        r"(?:date|invoice\s+date|bill\s+date)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
    ])
    # Normalise to YYYY-MM-DD if possible
    if invoice_date:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m-%d-%Y", "%m/%d/%Y"):
            try:
                from datetime import datetime
                invoice_date = datetime.strptime(invoice_date, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

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
        r"(?:grand\s+total|total\s+amount|total)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:net\s+payable|payable\s+amount)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
    ])
    taxable_amount = find_amount([
        r"(?:taxable\s+(?:value|amount)|assessable\s+value)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
        r"(?:sub\s*total|subtotal)[:\s₹Rs.]*([0-9,]+\.?[0-9]*)",
    ])
    cgst = find_amount([
        r"CGST[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    sgst = find_amount([
        r"SGST[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    igst = find_amount([
        r"IGST[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])
    cess = find_amount([
        r"CESS[:\s@%0-9]*₹?\s*([0-9,]+\.?[0-9]*)",
    ])

    hsn = find([
        r"HSN[/\s]*(?:SAC)?[:\s]*([0-9]{4,8})",
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
        r"(?:notice\s*(?:no|number|ref)|ref(?:erence)?\s*no)[:\s.]*([A-Z0-9/\-]+)",
    ])
    notice_date = find([
        r"(?:notice\s+date|issued\s+on)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ])
    response_due_date = find([
        r"(?:due\s+date|respond\s+by|last\s+date)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ])

    # ── Assemble by category ───────────────────────────────────
    if category in ("gst_notice",):
        return {
            "notice_number": notice_number or invoice_number,
            "notice_date": notice_date or invoice_date,
            "response_due_date": response_due_date,
        }

    if category in ("gst_return",):
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


def _ocr_image(content: bytes) -> str:
    """Run Tesseract OCR on image bytes."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(content)).convert("RGB")
        return pytesseract.image_to_string(img, lang="eng")
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OCR engine not installed on server. Please install pytesseract and Tesseract-OCR.",
        )
    except Exception as e:
        logger.error("OCR image error: %s", e)
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")


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
        # If neither pypdf nor PyMuPDF, just warn
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF processing library not installed. Install pypdf or PyMuPDF.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF OCR failed: {e}")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

ALLOWED_MIME_PREFIXES = ("image/", "application/pdf", "text/")
IMAGE_EXTS = {
    "jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif", "heic", "heif",
    "jfif", "avif",
}
PDF_EXTS = {"pdf"}


@router.post("/extract", summary="Extract fields from a scanned document via OCR")
async def extract_ocr(
    file: UploadFile = File(...),
    category: str = Form(default="sales_records"),
):
    """
    Accept any image or PDF file.
    Run OCR / text extraction and return parsed accounting fields.
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
    elif (
        ext in IMAGE_EXTS
        or (file.content_type or "").lower().startswith("image/")
    ):
        raw_text = _ocr_image(content)
    else:
        # Unknown type — try image OCR as a best-effort
        try:
            raw_text = _ocr_image(content)
        except Exception:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '.{ext}'. Please upload an image or PDF.",
            )

    if not raw_text or not raw_text.strip():
        return {
            "success": True,
            "raw_text": "",
            "fields": {},
            "message": (
                "No readable text found in the image. "
                "Please upload a clear photo of a document (invoice, receipt, notice, etc.)."
            ),
        }

    fields = _extract_from_text(raw_text, category)

    return {
        "success": True,
        "raw_text": raw_text[:3000],  # truncated for payload size
        "fields": fields,
        "message": "OCR extraction complete",
    }
