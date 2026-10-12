/**
 * report.service.ts — Frontend service for client-specific financial reports:
 * - Balance Sheet (Statement of Financial Position)
 * - Profit & Loss Statement (Income Statement)
 * - Cash Flow Statement (Operating, Investing, Financing activities)
 * - GST Summary Report (GSTR-1, GSTR-2B, GSTR-3B)
 * - Statutory Data Integrity & Anti-Fraud Audit
 * - Master Client Reports Headline Summary
 * - Audit Drill-down to source vouchers and documents
 */

import api from "./api";

export interface ReportLineItem {
  account_id?: string | null;
  account_code?: string | null;
  name: string;
  amount: number | string;
  percentage_of_revenue?: number | string | null;
  drill_down_account_id?: string | null;
}

export interface ReportSection {
  title: string;
  total: number | string;
  items: ReportLineItem[];
}

export interface ProfitAndLossReport {
  client_id: string;
  from_date: string;
  to_date: string;
  revenue_section: ReportSection;
  cost_of_sales_section: ReportSection;
  gross_profit: number | string;
  gross_profit_margin_pct: number | string;
  operating_expenses_section: ReportSection;
  total_operating_expenses: number | string;
  net_profit_before_tax: number | string;
  net_profit_margin_pct: number | string;
}

export interface BalanceSheetReport {
  client_id: string;
  as_of_date: string;
  current_assets_section: ReportSection;
  non_current_assets_section: ReportSection;
  total_assets: number | string;
  current_liabilities_section: ReportSection;
  non_current_liabilities_section: ReportSection;
  equity_section: ReportSection;
  current_period_net_profit: number | string;
  total_equity: number | string;
  total_liabilities: number | string;
  total_equity_and_liabilities: number | string;
  is_balanced: boolean;
  difference: number | string;
}

export interface CashFlowActivitySection {
  title: string;
  total: number | string;
  items: ReportLineItem[];
}

export interface CashFlowReport {
  client_id: string;
  from_date: string;
  to_date: string;
  operating_activities: CashFlowActivitySection;
  investing_activities: CashFlowActivitySection;
  financing_activities: CashFlowActivitySection;
  net_cash_flow: number | string;
  opening_cash_balance: number | string;
  closing_cash_balance: number | string;
  is_reconciled: boolean;
}

export interface GstSummarySectionItem {
  category: string;
  taxable_amount: number | string;
  cgst: number | string;
  sgst: number | string;
  igst: number | string;
  cess: number | string;
  total_tax: number | string;
  invoice_count: number;
}

export interface GstFilingRecordItem {
  period: string;
  gst_type: string;
  taxable_amount: number | string;
  total_tax: number | string;
  filing_status: string;
  due_date?: string | null;
}

export interface GstSummaryReport {
  client_id: string;
  from_date: string;
  to_date: string;
  outward_supplies: GstSummarySectionItem[];
  total_outward_taxable: number | string;
  total_output_tax: number | string;
  inward_supplies: GstSummarySectionItem[];
  total_inward_taxable: number | string;
  total_input_tax_credit: number | string;
  net_tax_payable: number | string;
  itc_balance_carried_forward: number | string;
  filing_records: GstFilingRecordItem[];
}

export interface IntegrityCheckResult {
  check_id: string;
  check_name: string;
  status: "PASSED" | "FLAGGED" | "WARNING";
  severity: "CLEAN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  description: string;
  metric?: string | null;
  details?: string[] | null;
}

export interface IntegrityAnomalyItem {
  anomaly_id: string;
  rule_code: string;
  severity: string;
  title: string;
  description: string;
  source_module: string;
  document_id?: string | null;
  voucher_id?: string | null;
  affected_amount?: number | string | null;
  recommended_action: string;
}

export interface IntegrityAuditReport {
  client_id: string;
  as_of_date: string;
  integrity_score: number;
  status: "EXCELLENT" | "GOOD" | "ATTENTION_REQUIRED" | "CRITICAL";
  total_invoices_audited: number;
  total_vouchers_audited: number;
  duplicate_invoices_count: number;
  unposted_vouchers_count: number;
  unbalanced_entries_count: number;
  math_mismatches_count: number;
  tax_head_mismatches_count: number;
  checks: IntegrityCheckResult[];
  anomalies: IntegrityAnomalyItem[];
}

export interface ClientReportsSummary {
  client_id: string;
  client_code: string;
  company_name: string;
  from_date: string;
  to_date: string;
  total_assets: number | string;
  total_liabilities: number | string;
  total_equity: number | string;
  is_balance_sheet_balanced: boolean;
  revenue: number | string;
  cogs: number | string;
  gross_profit: number | string;
  net_profit: number | string;
  net_profit_margin_pct: number | string;
  total_output_tax: number | string;
  total_itc: number | string;
  net_gst_payable: number | string;
  gst_compliance_rate_pct: number | string;
  net_cash_flow: number | string;
  closing_cash_balance: number | string;
  integrity_score: number;
  integrity_status: string;
  active_anomalies_count: number;
}

export interface DrillDownTransactionItem {
  journal_entry_id: string;
  line_id: string;
  entry_number: string;
  entry_date: string;
  entry_type: string;
  voucher_id?: string | null;
  document_id?: string | null;
  reference_number?: string | null;
  narration?: string | null;
  party_name?: string | null;
  party_gstin?: string | null;
  tax_head?: string | null;
  debit: number | string;
  credit: number | string;
  net_effect: number | string;
}

export interface DrillDownResponse {
  client_id: string;
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  from_date?: string | null;
  to_date?: string | null;
  total_debit: number | string;
  total_credit: number | string;
  net_balance: number | string;
  transaction_count: number;
  transactions: DrillDownTransactionItem[];
}

export const reportService = {
  /** Fetch live master reports headline summary for client workspace cards */
  async getClientSummary(
    clientId: string,
    fromDate?: string,
    toDate?: string
  ): Promise<ClientReportsSummary> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);
    return api.get<ClientReportsSummary>(`/reports/client-summary?${qs.toString()}`);
  },

  /** Fetch live Balance Sheet */
  async getBalanceSheet(clientId: string, asOfDate?: string): Promise<BalanceSheetReport> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (asOfDate) qs.set("as_of_date", asOfDate);
    return api.get<BalanceSheetReport>(`/reports/balance-sheet?${qs.toString()}`);
  },

  /** Fetch live Profit & Loss Statement */
  async getProfitAndLoss(
    clientId: string,
    fromDate?: string,
    toDate?: string
  ): Promise<ProfitAndLossReport> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);
    return api.get<ProfitAndLossReport>(`/reports/profit-and-loss?${qs.toString()}`);
  },

  /** Fetch live Cash Flow Statement */
  async getCashFlow(
    clientId: string,
    fromDate?: string,
    toDate?: string
  ): Promise<CashFlowReport> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);
    return api.get<CashFlowReport>(`/reports/cash-flow?${qs.toString()}`);
  },

  /** Fetch live GST Summary Report */
  async getGstSummary(
    clientId: string,
    fromDate?: string,
    toDate?: string
  ): Promise<GstSummaryReport> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);
    return api.get<GstSummaryReport>(`/reports/gst-summary?${qs.toString()}`);
  },

  /** Fetch live Statutory Data Integrity & Anti-Fraud Audit */
  async getIntegrityAudit(clientId: string, asOfDate?: string): Promise<IntegrityAuditReport> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (asOfDate) qs.set("as_of_date", asOfDate);
    return api.get<IntegrityAuditReport>(`/reports/integrity-audit?${qs.toString()}`);
  },

  /** Drill down into underlying transactions for a line item account */
  async getDrilldown(
    accountId: string,
    clientId: string,
    fromDate?: string,
    toDate?: string
  ): Promise<DrillDownResponse> {
    const qs = new URLSearchParams({ client_id: clientId });
    if (fromDate) qs.set("from_date", fromDate);
    if (toDate) qs.set("to_date", toDate);
    return api.get<DrillDownResponse>(`/reports/drilldown/${accountId}?${qs.toString()}`);
  },
};

export default reportService;
