"""
General Ledger Schemas — Strongly typed models for account ledgers, running balances, and GL summaries.
"""

import uuid
from typing import Optional, List
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class LedgerTransactionItem(BaseModel):
    """Individual line item in an account's ledger view."""
    journal_entry_id: uuid.UUID
    line_id: uuid.UUID
    entry_number: str
    entry_date: date
    entry_type: str
    accounting_record_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None
    narration: Optional[str] = None
    line_description: Optional[str] = None
    party_name: Optional[str] = None
    party_gstin: Optional[str] = None
    tax_head: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    debit: Decimal = Field(default=Decimal("0.00"))
    credit: Decimal = Field(default=Decimal("0.00"))
    running_balance: Decimal = Field(default=Decimal("0.00"))
    balance_side: str = Field(default="Dr")  # "Dr" or "Cr"

    class Config:
        from_attributes = True


class AccountLedgerResponse(BaseModel):
    """Detailed ledger view for a single account showing opening, transactions, and closing balance."""
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    client_id: uuid.UUID
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    opening_balance: Decimal = Field(default=Decimal("0.00"))
    opening_balance_side: str = Field(default="Dr")
    total_debit: Decimal = Field(default=Decimal("0.00"))
    total_credit: Decimal = Field(default=Decimal("0.00"))
    closing_balance: Decimal = Field(default=Decimal("0.00"))
    closing_balance_side: str = Field(default="Dr")
    transaction_count: int = 0
    transactions: List[LedgerTransactionItem] = []

    class Config:
        from_attributes = True


class GeneralLedgerAccountSummary(BaseModel):
    """Account-level summary in the General Ledger overview."""
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    account_subgroup: Optional[str] = None
    is_active: bool = True
    opening_balance: Decimal = Field(default=Decimal("0.00"))
    opening_balance_side: str = Field(default="Dr")
    total_debit: Decimal = Field(default=Decimal("0.00"))
    total_credit: Decimal = Field(default=Decimal("0.00"))
    closing_balance: Decimal = Field(default=Decimal("0.00"))
    closing_balance_side: str = Field(default="Dr")
    transaction_count: int = 0

    class Config:
        from_attributes = True


class GeneralLedgerSummaryResponse(BaseModel):
    """Overview of all accounts in the General Ledger for a client."""
    client_id: uuid.UUID
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    total_debit: Decimal = Field(default=Decimal("0.00"))
    total_credit: Decimal = Field(default=Decimal("0.00"))
    net_difference: Decimal = Field(default=Decimal("0.00"))
    accounts: List[GeneralLedgerAccountSummary] = []

    class Config:
        from_attributes = True
