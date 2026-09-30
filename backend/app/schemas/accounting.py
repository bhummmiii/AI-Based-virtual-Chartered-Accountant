"""Accounting Record schema — matches AccountingRecord model (UUID, Numeric fields)."""

import uuid
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class AccountingRecordResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    transaction_date: date
    voucher_type: str
    description: Optional[str] = None
    debit: Decimal
    credit: Decimal
    category: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    status: str = "draft"
    reference_number: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, v):
        return v if v is not None else "draft"


class AccountingValidationResult(BaseModel):
    """Result of validating a document for accounting draft creation."""
    eligible: bool
    status: str  # "valid" | "unverified" | "informational_skipped" | "validation_error" | "already_posted"
    reason: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    document_category: Optional[str] = None
    warnings: list[str] = []


class AccountingDraftDetail(BaseModel):
    """Rich draft transaction representation for review."""
    id: uuid.UUID
    client_id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    transaction_date: date
    voucher_type: str  # sales | purchase | journal | payment | receipt | contra
    category: Optional[str] = None
    status: Optional[str] = "draft"  # draft | posted
    reference_number: Optional[str] = None
    debit: Decimal
    credit: Decimal
    party_name: Optional[str] = None
    amount: Decimal
    taxable_amount: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    cess: Optional[Decimal] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DraftGenerateResponse(BaseModel):
    """Response when generating an accounting draft from a verified document."""
    status: str  # "created" | "updated" | "skipped" | "error"
    message: str
    record: Optional[AccountingRecordResponse] = None
    validation: Optional[AccountingValidationResult] = None


from app.schemas.journal_entry import JournalEntryResponse


class DraftPostResponse(BaseModel):
    """Response when explicitly posting a draft to the accounting ledger."""
    success: bool
    message: str
    record: Optional[AccountingRecordResponse] = None
    journal_entry: Optional[JournalEntryResponse] = None



class DraftBulkPostRequest(BaseModel):
    """Request payload for posting multiple approved drafts at once."""
    draft_ids: list[uuid.UUID]


class DraftBulkPostResponse(BaseModel):
    """Summary response for bulk posting drafts."""
    total_requested: int
    posted_count: int
    failed_count: int
    posted_ids: list[uuid.UUID] = []
    errors: list[str] = []

