"""
Trial Balance and Period Control Schemas — Models for Trial Balance generation,
financial health checks, duplicate reference checks, and period closures.
"""

import uuid
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class TrialBalanceAccountRow(BaseModel):
    """Account line item in the Trial Balance."""
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    account_subgroup: Optional[str] = None
    debit_balance: Decimal = Field(default=Decimal("0.00"))
    credit_balance: Decimal = Field(default=Decimal("0.00"))

    class Config:
        from_attributes = True


class TrialBalanceGroup(BaseModel):
    """Sub-group of accounts in Trial Balance (e.g. Assets, Liabilities, Revenue, Expense)."""
    account_type: str
    total_debit: Decimal = Field(default=Decimal("0.00"))
    total_credit: Decimal = Field(default=Decimal("0.00"))
    net_balance: Decimal = Field(default=Decimal("0.00"))
    accounts: List[TrialBalanceAccountRow] = []

    class Config:
        from_attributes = True


class TrialBalanceHealthCheck(BaseModel):
    """Financial integrity and audit control checks."""
    is_balanced: bool
    total_debit: Decimal
    total_credit: Decimal
    difference: Decimal
    unbalanced_entries_count: int
    duplicate_references: List[str] = []
    unposted_drafts_count: int
    closed_period_warnings: List[str] = []
    status: str  # "PASS" | "WARNING" | "FAIL"

    class Config:
        from_attributes = True


class TrialBalanceResponse(BaseModel):
    """Complete Trial Balance report with double-entry balance validation."""
    client_id: uuid.UUID
    as_of_date: date
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    total_debit: Decimal = Field(default=Decimal("0.00"))
    total_credit: Decimal = Field(default=Decimal("0.00"))
    is_balanced: bool = True
    groups: List[TrialBalanceGroup] = []
    health_check: TrialBalanceHealthCheck

    class Config:
        from_attributes = True


class AccountingPeriodCreate(BaseModel):
    """Payload to define an accounting period."""
    period_name: str
    start_date: date
    end_date: date
    closing_notes: Optional[str] = None


class AccountingPeriodResponse(BaseModel):
    """Details of an accounting period."""
    id: uuid.UUID
    client_id: uuid.UUID
    period_name: str
    start_date: date
    end_date: date
    status: str
    is_closed: bool
    closed_at: Optional[datetime] = None
    closed_by_user_id: Optional[uuid.UUID] = None
    closing_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
