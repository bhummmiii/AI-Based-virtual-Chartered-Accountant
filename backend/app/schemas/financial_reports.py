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


class CashFlowActivitySection(BaseModel):
    """Categorized activity flow in Cash Flow Statement."""
    title: str
    total: Decimal = Field(default=Decimal("0.00"))
    items: List[ReportLineItem] = []

    class Config:
        from_attributes = True


class CashFlowResponse(BaseModel):
    """Direct/Indirect Cash Flow Statement compliant with ICAI AS-3."""
    client_id: uuid.UUID
    from_date: date
    to_date: date
    operating_activities: CashFlowActivitySection
    investing_activities: CashFlowActivitySection
    financing_activities: CashFlowActivitySection
    net_cash_flow: Decimal
    opening_cash_balance: Decimal
    closing_cash_balance: Decimal
    is_reconciled: bool

    class Config:
        from_attributes = True


class GstSummarySectionItem(BaseModel):
    """Summary row for GST tax category."""
    category: str
    taxable_amount: Decimal = Field(default=Decimal("0.00"))
    cgst: Decimal = Field(default=Decimal("0.00"))
    sgst: Decimal = Field(default=Decimal("0.00"))
    igst: Decimal = Field(default=Decimal("0.00"))
    cess: Decimal = Field(default=Decimal("0.00"))
    total_tax: Decimal = Field(default=Decimal("0.00"))
    invoice_count: int = 0

    class Config:
        from_attributes = True


class GstFilingRecordItem(BaseModel):
    """GST return filing tracking record."""
    period: str
    gst_type: str
    taxable_amount: Decimal = Field(default=Decimal("0.00"))
    total_tax: Decimal = Field(default=Decimal("0.00"))
    filing_status: str
    due_date: Optional[date] = None

    class Config:
        from_attributes = True


class GstSummaryReportResponse(BaseModel):
    """Consolidated GST Summary Report combining GSTR-1, GSTR-2B, and GSTR-3B tax figures."""
    client_id: uuid.UUID
    from_date: date
    to_date: date
    outward_supplies: List[GstSummarySectionItem] = []
    total_outward_taxable: Decimal = Field(default=Decimal("0.00"))
    total_output_tax: Decimal = Field(default=Decimal("0.00"))
    inward_supplies: List[GstSummarySectionItem] = []
    total_inward_taxable: Decimal = Field(default=Decimal("0.00"))
    total_input_tax_credit: Decimal = Field(default=Decimal("0.00"))
    net_tax_payable: Decimal = Field(default=Decimal("0.00"))
    itc_balance_carried_forward: Decimal = Field(default=Decimal("0.00"))
    filing_records: List[GstFilingRecordItem] = []

    class Config:
        from_attributes = True


class IntegrityCheckResult(BaseModel):
    """Individual assertion in data integrity and anti-fraud audit."""
    check_id: str
    check_name: str
    status: str  # "PASSED" | "FLAGGED" | "WARNING"
    severity: str  # "CLEAN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    description: str
    metric: Optional[str] = None
    details: Optional[List[str]] = None

    class Config:
        from_attributes = True


class IntegrityAnomalyItem(BaseModel):
    """Detected anomaly, duplicate, or fraud alert."""
    anomaly_id: str
    rule_code: str
    severity: str
    title: str
    description: str
    source_module: str  # "invoices" | "accounting" | "gst"
    document_id: Optional[uuid.UUID] = None
    voucher_id: Optional[uuid.UUID] = None
    affected_amount: Optional[Decimal] = None
    recommended_action: str

    class Config:
        from_attributes = True


class IntegrityAuditReportResponse(BaseModel):
    """Statutory Data Integrity, Anti-Fraud, and Cross-Module Parity Audit Report."""
    client_id: uuid.UUID
    as_of_date: date
    integrity_score: int  # 0 to 100
    status: str  # "EXCELLENT" | "GOOD" | "ATTENTION_REQUIRED" | "CRITICAL"
    total_invoices_audited: int
    total_vouchers_audited: int
    duplicate_invoices_count: int
    unposted_vouchers_count: int
    unbalanced_entries_count: int
    math_mismatches_count: int
    tax_head_mismatches_count: int
    checks: List[IntegrityCheckResult] = []
    anomalies: List[IntegrityAnomalyItem] = []

    class Config:
        from_attributes = True


class ClientReportsSummaryResponse(BaseModel):
    """Lightweight dashboard headline metrics for all 4 financial reports + integrity score."""
    client_id: uuid.UUID
    client_code: str
    company_name: str
    from_date: date
    to_date: date
    # Balance sheet highlights
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    is_balance_sheet_balanced: bool
    # Profit & loss highlights
    revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    net_profit: Decimal
    net_profit_margin_pct: Decimal
    # GST highlights
    total_output_tax: Decimal
    total_itc: Decimal
    net_gst_payable: Decimal
    gst_compliance_rate_pct: Decimal
    # Cash flow highlights
    net_cash_flow: Decimal
    closing_cash_balance: Decimal
    # Integrity highlights
    integrity_score: int
    integrity_status: str
    active_anomalies_count: int

    class Config:
        from_attributes = True

