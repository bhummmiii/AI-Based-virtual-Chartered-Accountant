"""
PDF text extraction adapter for statutory gazettes and circulars.
Strictly respects R4/J4:
- Uses pypdf (already in project dependencies)
- text_status = 'no_text' for scanned images without selectable text
- No OCR
- text_status = 'too_large' if extracted text > 1,000,000 characters
"""

import io
import re
from typing import Tuple
import pypdf


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 50) -> Tuple[str, str]:
    """
    Extracts text from PDF bytes.
    Returns (content_text, text_status) where text_status in ('ok', 'no_text', 'too_large').
    """
    if not pdf_bytes:
        return "", "no_text"

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        if num_pages == 0:
            return "", "no_text"

        extracted_pages = []
        total_len = 0
        pages_to_read = min(num_pages, max_pages)

        for i in range(pages_to_read):
            page_text = reader.pages[i].extract_text() or ""
            total_len += len(page_text)
            if total_len > 1_000_000:
                return "\n\n".join(extracted_pages)[:1_000_000], "too_large"
            extracted_pages.append(page_text)

        full_text = "\n\n".join(extracted_pages).strip()

        # Check if the extracted text contains meaningful characters (not scanned image)
        alphanumeric_count = len(re.findall(r"[A-Za-z0-9]", full_text))
        if alphanumeric_count < 50:
            return "", "no_text"

        return full_text, "ok"

    except Exception:
        return "", "no_text"
