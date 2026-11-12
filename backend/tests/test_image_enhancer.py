"""
Tests for Document Image Enhancement and Accuracy Verification.
"""
import pytest
import numpy as np
import cv2
from app.services.image_enhancer import DocumentImageEnhancer, DocumentImageQuality


def _create_synthetic_invoice_image(blur: bool = False, low_contrast: bool = False) -> bytes:
    w, h = 600, 400
    img = np.ones((h, w, 3), dtype=np.uint8) * 245
    # Add text
    cv2.putText(img, "TAX INVOICE", (180, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2)
    cv2.putText(img, "GSTIN: 27ACGPH4660M1ZB", (60, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)
    cv2.putText(img, "HSN Code: 998898", (60, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)
    cv2.putText(img, "Taxable: Rs 7638.00  CGST: Rs 687.42", (60, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 2)
    cv2.putText(img, "Grand Total: Rs 9013.00", (60, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)

    if low_contrast:
        # Reduce dynamic range
        img = (img * 0.2 + 180).astype(np.uint8)

    if blur:
        # Strong Gaussian blur simulating out-of-focus phone camera
        img = cv2.GaussianBlur(img, (15, 15), 5.0)

    success, enc = cv2.imencode(".jpg", img)
    return enc.tobytes()


def test_clear_document_enhancement():
    raw_bytes = _create_synthetic_invoice_image(blur=False)
    cleaned_bytes, quality, data_url = DocumentImageEnhancer.analyze_and_enhance(raw_bytes)

    assert isinstance(quality, DocumentImageQuality)
    assert quality.accuracy_score >= 85.0
    assert quality.was_preprocessed is True
    assert len(quality.enhancements_applied) > 0
    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(cleaned_bytes) > 0


def test_blurry_document_restoration():
    blurry_bytes = _create_synthetic_invoice_image(blur=True)
    cleaned_bytes, quality, data_url = DocumentImageEnhancer.analyze_and_enhance(blurry_bytes)

    assert quality.is_blurry is True
    assert "Unsharp Mask" in " ".join(quality.enhancements_applied)
    assert quality.accuracy_score >= 80.0
    assert data_url.startswith("data:image/jpeg;base64,")


def test_low_contrast_enhancement():
    low_con_bytes = _create_synthetic_invoice_image(low_contrast=True)
    cleaned_bytes, quality, data_url = DocumentImageEnhancer.analyze_and_enhance(low_con_bytes)

    assert quality.is_low_contrast is True
    assert "CLAHE" in " ".join(quality.enhancements_applied)
    assert quality.accuracy_score >= 80.0
