"""
GST Reconciliation & Financial Insights Schemas
Phase 7 — GSTR-1, GSTR-2B, GSTR-3B, discrepancy detection, and explainable CA review insights.
"""

import uuid
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


# ── Invoice Line Items in Reconciliation ──────────────────────────────
class GstReconciliationInvoiceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: Optional[uuid.UUID] = None
    voucher_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    party_name: Optional[str] = None
    party_gstin: Optional[str] = None
    document_category: str
    taxable_amount: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    igst: Decimal = Decimal("0.00")
    cess: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")
    invoice_total: Decimal = Decimal("0.00")
    supply_type: str = "B2B"  # B2B | B2CL | B2CS | CDNR | CDNUR | EXP
    is_posted: bool = False
    reconciliation_status: str = "matched"  # matched | discrepancy | unposted | unlinked


# ── GSTR-1 Outward Supplies Reconciliation ─────────────────────────────
class Gstr1SectionSummary(BaseModel):
    category_name: str
    invoice_count: int = 0
    taxable_amount: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    igst: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")


class Gstr1ReconciliationResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    # Document / Voucher aggregations
    b2b_summary: Gstr1SectionSummary
    b2cl_summary: Gstr1SectionSummary
    b2cs_summary: Gstr1SectionSummary
    credit_notes_summary: Gstr1SectionSummary
    debit_notes_summary: Optional[Gstr1SectionSummary] = None
    total_outward_taxable: Decimal = Decimal("0.00")
    total_outward_cgst: Decimal = Decimal("0.00")
    total_outward_sgst: Decimal = Decimal("0.00")
    total_outward_igst: Decimal = Decimal("0.00")
    total_outward_tax: Decimal = Decimal("0.00")

    # General Ledger comparison
    ledger_sales_turnover: Decimal = Decimal("0.00")
    ledger_output_cgst: Decimal = Decimal("0.00")
    ledger_output_sgst: Decimal = Decimal("0.00")
    ledger_output_igst: Decimal = Decimal("0.00")
    ledger_total_output_tax: Decimal = Decimal("0.00")

    # Variances
    turnover_variance: Decimal = Decimal("0.00")
    tax_variance: Decimal = Decimal("0.00")
    is_reconciled: bool = True
    invoices: List[GstReconciliationInvoiceItem] = []


# ── GSTR-2B / ITC Reconciliation ──────────────────────────────────────
class Gstr2bReconciliationResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    # Inward document aggregations
    total_inward_taxable: Decimal = Decimal("0.00")
    eligible_itc_cgst: Decimal = Decimal("0.00")
    eligible_itc_sgst: Decimal = Decimal("0.00")
    eligible_itc_igst: Decimal = Decimal("0.00")
    total_eligible_itc: Decimal = Decimal("0.00")

    ineligible_itc: Decimal = Decimal("0.00")

    # General Ledger comparison
    ledger_input_cgst: Decimal = Decimal("0.00")
    ledger_input_sgst: Decimal = Decimal("0.00")
    ledger_input_igst: Decimal = Decimal("0.00")
    ledger_total_input_tax: Decimal = Decimal("0.00")

    # Variances
    itc_variance: Decimal = Decimal("0.00")
    is_reconciled: bool = True
    invoices: List[GstReconciliationInvoiceItem] = []


# ── GSTR-3B Monthly Return Summary ────────────────────────────────────
class Gstr3bSectionSummary(BaseModel):
    taxable_value: Decimal = Decimal("0.00")
    igst: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    cess: Decimal = Decimal("0.00")


class Gstr3bResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    # 3.1 Details of Outward Supplies
    table_3_1_outward: Gstr3bSectionSummary
    # 4. Eligible ITC
    table_4_itc_available: Gstr3bSectionSummary
    table_4_itc_reversed: Gstr3bSectionSummary
    table_4_net_itc: Gstr3bSectionSummary
    # 6. Tax Payable & Paid
    tax_payable_in_cash: Decimal = Decimal("0.00")
    excess_credit_carried_forward: Decimal = Decimal("0.00")

    # Table 6 Head-wise Statutory Set-off Splits (C10)
    cash_payable_cgst: Decimal = Decimal("0.00")
    cash_payable_sgst: Decimal = Decimal("0.00")
    cash_payable_igst: Decimal = Decimal("0.00")
    itc_carried_forward_cgst: Decimal = Decimal("0.00")
    itc_carried_forward_sgst: Decimal = Decimal("0.00")
    itc_carried_forward_igst: Decimal = Decimal("0.00")
    needs_ca_review: bool = False
    review_notes: List[str] = Field(default_factory=list)


# ── Discrepancy Items ─────────────────────────────────────────────────
class GstDiscrepancyItem(BaseModel):
    discrepancy_id: str
    rule_code: str  # MISSING_GSTIN | TAX_MATH_MISMATCH | UNPOSTED_INVOICE | DUPLICATE_INVOICE | UNLINKED_LEDGER_ENTRY | TIMING_MISMATCH
    severity: str   # HIGH | MEDIUM | LOW
    title: str
    description: str
    document_id: Optional[uuid.UUID] = None
    voucher_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = None
    party_name: Optional[str] = None
    variance_amount: Decimal = Decimal("0.00")
    statutory_reference: Optional[str] = None  # e.g., "Sec 16(2)(aa) CGST Act", "Sec 17(5)"
    recommended_action: str


class GstDiscrepancyReportResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    total_discrepancies: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_tax_at_risk: Decimal = Decimal("0.00")
    discrepancies: List[GstDiscrepancyItem] = []


# ── Financial Insights & CA Review ────────────────────────────────────
class FilingChecklistItem(BaseModel):
    check_name: str
    status: str  # PASSED | WARNING | ACTION_REQUIRED
    message: str
    statutory_section: Optional[str] = None


class GstFinancialInsightsResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    compliance_score: int = 100  # 0 to 100
    risk_level: str = "LOW"     # LOW | MEDIUM | HIGH
    summary_metrics: dict
    ca_observations: List[str] = []
    action_checklist: List[FilingChecklistItem] = []


# ── Table 12 HSN/SAC Outward Supplies Summary (D8) ────────────────────
class Gstr1HsnItem(BaseModel):
    hsn_sac: str
    description: str = ""
    uqc: str = "OTH"  # Unit Quantity Code (NOS, KGS, LOT, OTH, etc.)
    total_quantity: Decimal = Decimal("0.00")
    total_value: Decimal = Decimal("0.00")
    taxable_amount: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    igst: Decimal = Decimal("0.00")
    cess: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")
    gst_rate: Optional[Decimal] = None
    invoice_count: int = 1


class Gstr1HsnSummaryResponse(BaseModel):
    client_id: uuid.UUID
    period: Optional[str] = None
    total_records: int = 0
    total_taxable_value: Decimal = Decimal("0.00")
    total_tax_amount: Decimal = Decimal("0.00")
    hsn_items: List[Gstr1HsnItem] = []
