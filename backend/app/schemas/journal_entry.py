"""
Journal Entry Schemas — Pydantic v2 schemas for Double-Entry Journal Engine.
Enforces validation of lines, balance equation, and financial amounts.
"""

import uuid
from decimal import Decimal
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class JournalEntryLineBase(BaseModel):
    account_id: uuid.UUID
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    description: Optional[str] = None
    party_name: Optional[str] = None
    party_gstin: Optional[str] = None
    tax_head: Optional[str] = None
    tax_rate: Optional[Decimal] = None


class JournalEntryLineCreate(JournalEntryLineBase):
    @field_validator("debit_amount", "credit_amount")
    @classmethod
    def validate_non_negative(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Amount cannot be negative")
        return v.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def validate_single_sided(self) -> "JournalEntryLineCreate":
        dr = self.debit_amount
        cr = self.credit_amount
        if dr > Decimal("0") and cr > Decimal("0"):
            raise ValueError("A single journal line cannot have both debit and credit amounts greater than zero")
        if dr == Decimal("0") and cr == Decimal("0"):
            raise ValueError("A journal line must specify either a debit or a credit amount greater than zero")
        return self


class JournalEntryLineResponse(JournalEntryLineBase):
    id: uuid.UUID
    journal_entry_id: uuid.UUID
    line_number: int
    created_at: datetime
    account_code: Optional[str] = None
    account_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JournalEntryBase(BaseModel):
    client_id: uuid.UUID
    entry_date: date
    entry_type: str  # sales | purchase | payment | receipt | journal | contra
    narration: Optional[str] = None
    reference_number: Optional[str] = None
    accounting_record_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None


class JournalEntryCreate(JournalEntryBase):
    lines: List[JournalEntryLineCreate]

    @model_validator(mode="after")
    def validate_double_entry_balance(self) -> "JournalEntryCreate":
        if not self.lines or len(self.lines) < 2:
            raise ValueError("A journal entry must contain at least 2 lines (one debit and one credit)")

        total_dr = sum(line.debit_amount for line in self.lines)
        total_cr = sum(line.credit_amount for line in self.lines)

        diff = abs(total_dr - total_cr)
        if diff >= Decimal("0.001"):
            raise ValueError(
                f"Double-entry mathematical imbalance detected: Total Debit (₹{total_dr}) != Total Credit (₹{total_cr}). "
                f"Difference: ₹{diff}."
            )
        return self


class JournalEntryResponse(JournalEntryBase):
    id: uuid.UUID
    entry_number: str
    status: str
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool
    posted_at: Optional[datetime] = None
    posted_by_user_id: Optional[uuid.UUID] = None
    is_reversed: bool
    reversal_entry_id: Optional[uuid.UUID] = None
    reversal_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JournalEntryDetailResponse(JournalEntryResponse):
    lines: List[JournalEntryLineResponse] = []


class JournalReversalRequest(BaseModel):
    reversal_reason: str
