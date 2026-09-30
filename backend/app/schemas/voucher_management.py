"""
Voucher Management Schemas — Models for Customer Receipts, Supplier Payments,
Contra entries, and Outstanding Balances (AR/AP Aging).
"""

import uuid
from typing import Optional, List
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field

from app.schemas.journal_entry import JournalEntryDetailResponse


class CustomerReceiptCreate(BaseModel):
    """Payload to record customer receipt (Bank/Cash Dr, Debtor Cr)."""
    client_id: uuid.UUID
    receipt_date: date
    amount: Decimal = Field(gt=Decimal("0.00"), description="Receipt amount in INR")
    customer_name: str
    customer_gstin: Optional[str] = None
    bank_or_cash_account_code: str = Field(default="1020", description="1020 for Bank, 1010 for Cash")
    reference_number: Optional[str] = Field(None, description="Cheque/UTR/Transaction Reference")
    allocated_document_id: Optional[uuid.UUID] = Field(None, description="Linked sales invoice ID")
    narration: Optional[str] = None


class SupplierPaymentCreate(BaseModel):
    """Payload to record supplier payment (Creditor Dr, Bank/Cash Cr)."""
    client_id: uuid.UUID
    payment_date: date
    amount: Decimal = Field(gt=Decimal("0.00"), description="Payment amount in INR")
    vendor_name: str
    vendor_gstin: Optional[str] = None
    bank_or_cash_account_code: str = Field(default="1020", description="1020 for Bank, 1010 for Cash")
    reference_number: Optional[str] = Field(None, description="Cheque/NEFT/UTR Reference")
    allocated_document_id: Optional[uuid.UUID] = Field(None, description="Linked purchase bill ID")
    narration: Optional[str] = None


class ContraVoucherCreate(BaseModel):
    """Payload to record contra transaction (Bank-to-Cash, Cash-to-Bank, or Bank-to-Bank)."""
    client_id: uuid.UUID
    voucher_date: date
    amount: Decimal = Field(gt=Decimal("0.00"), description="Transferred amount")
    from_account_code: str = Field(..., description="Source liquid account code (e.g. 1020)")
    to_account_code: str = Field(..., description="Destination liquid account code (e.g. 1010)")
    reference_number: Optional[str] = None
    narration: Optional[str] = None


class OutstandingInvoiceDoc(BaseModel):
    """Invoice or Bill metadata linked to an outstanding party balance."""
    document_id: Optional[uuid.UUID] = None
    voucher_id: Optional[uuid.UUID] = None
    invoice_number: str
    invoice_date: date
    gross_amount: Decimal
    settled_amount: Decimal
    outstanding_amount: Decimal
    days_overdue: int

    class Config:
        from_attributes = True


class OutstandingPartyItem(BaseModel):
    """Party-wise aging and outstanding balance."""
    party_name: str
    party_gstin: Optional[str] = None
    total_invoiced: Decimal
    total_settled: Decimal
    net_outstanding: Decimal
    aging_0_30: Decimal = Field(default=Decimal("0.00"))
    aging_31_60: Decimal = Field(default=Decimal("0.00"))
    aging_61_90: Decimal = Field(default=Decimal("0.00"))
    aging_90_plus: Decimal = Field(default=Decimal("0.00"))
    invoices: List[OutstandingInvoiceDoc] = []

    class Config:
        from_attributes = True


class OutstandingReportResponse(BaseModel):
    """Aging report for Receivables (Customers) or Payables (Suppliers)."""
    client_id: uuid.UUID
    as_of_date: date
    report_type: str  # "receivables" | "payables"
    total_invoiced: Decimal
    total_settled: Decimal
    total_outstanding: Decimal
    aging_0_30_total: Decimal = Field(default=Decimal("0.00"))
    aging_31_60_total: Decimal = Field(default=Decimal("0.00"))
    aging_61_90_total: Decimal = Field(default=Decimal("0.00"))
    aging_90_plus_total: Decimal = Field(default=Decimal("0.00"))
    parties: List[OutstandingPartyItem] = []

    class Config:
        from_attributes = True
