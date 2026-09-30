"""
Pydantic schemas for the UploadedDocument model.
Covers create (form metadata), response, and list item.
"""

import uuid
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, Dict
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
    applies_to: Optional[str] = None

    # ── Core Identifiers ────────────────────────────────────
    invoice_number: Optional[str] = None
    gstin: Optional[str] = None
    vendor: Optional[str] = None
    customer: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    posting_date: Optional[str] = None

    # ── Supplier / Vendor Details ───────────────────────────
    supplier_gstin: Optional[str] = None
    supplier_pan: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_state: Optional[str] = None
    supplier_state_code: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_email: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_branch: Optional[str] = None

    # ── Customer / Buyer Details ────────────────────────────
    customer_gstin: Optional[str] = None
    customer_pan: Optional[str] = None
    customer_address: Optional[str] = None
    customer_state: Optional[str] = None
    customer_state_code: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None

    # ── Location / Supply ───────────────────────────────────
    place_of_supply: Optional[str] = None
    state_code: Optional[str] = None
    reverse_charge: Optional[str] = None
    rcm_applicable: Optional[str] = None

    # ── PO / Delivery / Transport ───────────────────────────
    po_number: Optional[str] = None
    po_date: Optional[str] = None
    delivery_note: Optional[str] = None
    delivery_challan: Optional[str] = None
    grn_number: Optional[str] = None
    vehicle_number: Optional[str] = None
    transport_mode: Optional[str] = None
    eway_bill_number: Optional[str] = None

    # ── Payment ─────────────────────────────────────────────
    payment_terms: Optional[str] = None
    payment_due_date: Optional[str] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    utr_number: Optional[str] = None
    remarks: Optional[str] = None

    # ── Financial Breakdown ─────────────────────────────────
    amount: Optional[Decimal] = None
    taxable_amount: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    cess: Optional[Decimal] = None
    hsn: Optional[str] = None
    cgst_rate: Optional[Decimal] = None
    sgst_rate: Optional[Decimal] = None
    igst_rate: Optional[Decimal] = None
    cess_rate: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    freight: Optional[Decimal] = None
    packing_charges: Optional[Decimal] = None
    round_off: Optional[Decimal] = None
    amount_in_words: Optional[str] = None
    other_charges: Optional[Decimal] = None

    # ── Credit / Debit Note ─────────────────────────────────
    credit_note_number: Optional[str] = None
    credit_note_date: Optional[str] = None
    debit_note_number: Optional[str] = None
    debit_note_date: Optional[str] = None
    original_invoice_date: Optional[str] = None
    reason: Optional[str] = None

    # ── GST Return ──────────────────────────────────────────
    gst_return_type: Optional[str] = None
    financial_year: Optional[str] = None
    month: Optional[str] = None
    quarter: Optional[str] = None
    filed_date: Optional[str] = None
    arn: Optional[str] = None
    status: Optional[str] = None
    filing_mode: Optional[str] = None
    turnover_previous: Optional[Decimal] = None
    exempted_turnover: Optional[Decimal] = None
    export_turnover: Optional[Decimal] = None
    deemed_export_turnover: Optional[Decimal] = None
    outward_supplies: Optional[Decimal] = None
    rcm_supplies: Optional[Decimal] = None
    input_credit: Optional[Decimal] = None
    itc_reversed: Optional[Decimal] = None
    net_itc: Optional[Decimal] = None
    cgst_payable: Optional[Decimal] = None
    sgst_payable: Optional[Decimal] = None
    igst_payable: Optional[Decimal] = None
    cess_payable: Optional[Decimal] = None
    cgst_cash: Optional[Decimal] = None
    sgst_cash: Optional[Decimal] = None
    igst_cash: Optional[Decimal] = None
    cess_cash: Optional[Decimal] = None
    cgst_itc: Optional[Decimal] = None
    sgst_itc: Optional[Decimal] = None
    igst_itc: Optional[Decimal] = None
    interest: Optional[Decimal] = None
    late_fee: Optional[Decimal] = None
    linked_challans: Optional[str] = None

    # ── GST Notice / Order ──────────────────────────────────
    notice_number: Optional[str] = None
    notice_date: Optional[str] = None
    response_due_date: Optional[str] = None
    priority: Optional[str] = None
    reference_number: Optional[str] = None
    adjudication_date: Optional[str] = None
    period: Optional[str] = None
    assessment_year: Optional[str] = None
    pan_number: Optional[str] = None
    trade_name: Optional[str] = None
    principal_address: Optional[str] = None
    range_division: Optional[str] = None
    commissionerate: Optional[str] = None
    officer_name: Optional[str] = None
    officer_designation: Optional[str] = None
    act_section: Optional[str] = None
    subject: Optional[str] = None
    notice_type: Optional[str] = None
    demand_tax: Optional[Decimal] = None
    demand_interest: Optional[Decimal] = None
    demand_penalty: Optional[Decimal] = None
    demand_other: Optional[Decimal] = None
    next_action: Optional[str] = None

    # ── E-Invoice (IRN) ─────────────────────────────────────
    irn_hash: Optional[str] = None
    acknowledgement_number: Optional[str] = None
    acknowledgement_date: Optional[str] = None
    valid_upto: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    doc_number: Optional[str] = None
    dispatch_from: Optional[str] = None
    ship_to: Optional[str] = None
    qr_code: Optional[str] = None
    signed_qr: Optional[str] = None

    # ── E-Way Bill ──────────────────────────────────────────
    eway_expiry: Optional[str] = None
    transporter_doc_no: Optional[str] = None
    supplier_pincode: Optional[str] = None
    recipient_pincode: Optional[str] = None
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    distance_km: Optional[str] = None
    vehicle_type: Optional[str] = None
    transporter_id: Optional[str] = None
    transporter_name: Optional[str] = None
    cancelled_date: Optional[str] = None

    # ── GST Challan / Payment ───────────────────────────────
    cpin: Optional[str] = None
    cin: Optional[str] = None
    challan_serial: Optional[str] = None
    bsr_code: Optional[str] = None
    challan_date: Optional[str] = None
    date_of_receipt: Optional[str] = None
    purpose: Optional[str] = None
    cgst_tax: Optional[Decimal] = None
    cgst_interest: Optional[Decimal] = None
    cgst_penalty: Optional[Decimal] = None
    cgst_fee: Optional[Decimal] = None
    cgst_others: Optional[Decimal] = None
    sgst_tax: Optional[Decimal] = None
    sgst_interest: Optional[Decimal] = None
    sgst_penalty: Optional[Decimal] = None
    sgst_fee: Optional[Decimal] = None
    sgst_others: Optional[Decimal] = None
    igst_tax: Optional[Decimal] = None
    igst_interest: Optional[Decimal] = None
    igst_penalty: Optional[Decimal] = None
    igst_fee: Optional[Decimal] = None
    igst_others: Optional[Decimal] = None
    cess_tax: Optional[Decimal] = None
    cess_interest: Optional[Decimal] = None
    cess_penalty: Optional[Decimal] = None
    cess_others: Optional[Decimal] = None

    # ── B2C / POS extras ────────────────────────────────────
    cashier: Optional[str] = None
    counter_no: Optional[str] = None
    receipt_number: Optional[str] = None

    # ── HSN / SAC extras ────────────────────────────────────
    hsn_description: Optional[str] = None
    gst_rate: Optional[str] = None

    # ── File / OCR ──────────────────────────────────────────
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[str] = None
    file_type: Optional[str] = None
    ocr_status: Optional[str] = None
    ocr_confidence: Optional[Decimal] = None
    uploaded_by: Optional[str] = None
    metadata_: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime

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
    uploaded_by: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class DocumentUpdateRequest(BaseModel):
    """Payload for updating/editing fields or status of an existing uploaded document."""

    fields: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    document_category: Optional[str] = None
    applies_to: Optional[str] = None

