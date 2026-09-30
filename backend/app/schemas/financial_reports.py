"""
Financial Statement Schemas — Strongly typed models for Profit & Loss (Income Statement),
Balance Sheet, and audit drill-down to vouchers and source documents.
"""

import uuid
from typing import Optional, List
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class ReportLineItem(BaseModel):
    """Line item in a financial statement with drill-down metadata."""
    account_id: Optional[uuid.UUID] = None
    account_code: Optional[str] = None
    name: str
    amount: Decimal = Field(default=Decimal("0.00"))
    percentage_of_revenue: Optional[Decimal] = None
    drill_down_account_id: Optional[uuid.UUID] = None

    class Config:
        from_attributes = True


class ReportSection(BaseModel):
    """Categorized section of a financial statement."""
    title: str
    total: Decimal = Field(default=Decimal("0.00"))
    items: List[ReportLineItem] = []

    class Config:
        from_attributes = True


class ProfitAndLossResponse(BaseModel):
    """Profit & Loss Statement (Income Statement) adhering to ICAI Schedule III principles."""
    client_id: uuid.UUID
    from_date: date
    to_date: date
    revenue_section: ReportSection
    cost_of_sales_section: ReportSection
    gross_profit: Decimal
    gross_profit_margin_pct: Decimal
    operating_expenses_section: ReportSection
    total_operating_expenses: Decimal
    net_profit_before_tax: Decimal
    net_profit_margin_pct: Decimal

    class Config:
        from_attributes = True


class BalanceSheetResponse(BaseModel):
    """Balance Sheet (Statement of Financial Position) with double-entry balance check."""
    client_id: uuid.UUID
    as_of_date: date
    current_assets_section: ReportSection
    non_current_assets_section: ReportSection
    total_assets: Decimal
    current_liabilities_section: ReportSection
    non_current_liabilities_section: ReportSection
    equity_section: ReportSection
    current_period_net_profit: Decimal
    total_equity: Decimal
    total_liabilities: Decimal
    total_equity_and_liabilities: Decimal
    is_balanced: bool
    difference: Decimal

    class Config:
        from_attributes = True


class DrillDownTransactionItem(BaseModel):
    """Underlying transaction detail for a financial statement drill-down."""
    journal_entry_id: uuid.UUID
    line_id: uuid.UUID
    entry_number: str
    entry_date: date
    entry_type: str
    voucher_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None
    narration: Optional[str] = None
    party_name: Optional[str] = None
    party_gstin: Optional[str] = None
    tax_head: Optional[str] = None
    debit: Decimal
    credit: Decimal
    net_effect: Decimal

    class Config:
        from_attributes = True


class DrillDownResponse(BaseModel):
    """Drill-down response connecting report line item to underlying vouchers and source documents."""
    client_id: uuid.UUID
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    total_debit: Decimal
    total_credit: Decimal
    net_balance: Decimal
    transaction_count: int
    transactions: List[DrillDownTransactionItem] = []

    class Config:
        from_attributes = True
