"""
Pydantic schemas for the UploadedDocument model.
Covers create (form metadata), response, and list item.
"""

import uuid
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

VALID_CATEGORIES = {
    "sales_records",
    "purchase_records",
    "credit_note",
    "debit_note",
    "b2b_invoice",
    "b2c_invoice",
    "hsn_sac",
    "e_invoice",
    "e_way_bill",
    "gst_challan",
    "gst_return",
    "gst_notice",
    "document_list",
}
VALID_DOC_TYPES = {"upload", "scan"}


class DocumentMetaCreate(BaseModel):
    """
    Metadata submitted alongside the file upload.
    All fields except document_category and document_type are optional —
    they depend on the selected category.
    """

    document_category: str = Field(
        ..., description="One of the 13 GST document categories"
    )
    document_type: str = Field(default="upload", description="upload | scan")
    invoice_type: Optional[str] = None

    # Core
    invoice_number: Optional[str] = None
    gstin: Optional[str] = None
    vendor: Optional[str] = None
    customer: Optional[str] = None
    invoice_date: Optional[str] = None

    # Financial
    amount: Optional[Decimal] = None
    taxable_amount: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    cess: Optional[Decimal] = None
    hsn: Optional[str] = None

    # GST Return
    gst_return_type: Optional[str] = None
    financial_year: Optional[str] = None
    month: Optional[str] = None
    filed_date: Optional[str] = None
    arn: Optional[str] = None

    # Notice
    notice_number: Optional[str] = None
    notice_date: Optional[str] = None
    response_due_date: Optional[str] = None
    priority: Optional[str] = None

    @field_validator("document_category")
    @classmethod
    def v_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )
        return v

    @field_validator("document_type")
    @classmethod
    def v_doc_type(cls, v: str) -> str:
        if v not in VALID_DOC_TYPES:
            raise ValueError("document_type must be 'upload' or 'scan'")
        return v

    @field_validator("gstin")
    @classmethod
    def v_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip().upper()
        if not GSTIN_RE.match(v):
            raise ValueError("Invalid GSTIN format. Expected: 27AABCN1234R1Z5")
        return v


class UploadedDocumentResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    document_category: str
    document_type: str
    invoice_type: Optional[str] = None
    invoice_number: Optional[str] = None
    gstin: Optional[str] = None
    vendor: Optional[str] = None
    customer: Optional[str] = None
    invoice_date: Optional[str] = None
    amount: Optional[Decimal] = None
    taxable_amount: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    cess: Optional[Decimal] = None
    hsn: Optional[str] = None
    gst_return_type: Optional[str] = None
    financial_year: Optional[str] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[str] = None
    file_type: Optional[str] = None
    ocr_status: Optional[str] = None
    ocr_confidence: Optional[Decimal] = None
    status: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class UploadedDocumentListItem(BaseModel):
    """Minimal item for list/table views."""

    id: uuid.UUID
    document_category: str
    document_type: str
    invoice_number: Optional[str] = None
    vendor: Optional[str] = None
    customer: Optional[str] = None
    amount: Optional[Decimal] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    status: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
