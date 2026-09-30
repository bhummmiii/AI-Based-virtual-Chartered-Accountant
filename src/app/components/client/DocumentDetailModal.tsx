/**
 * DocumentDetailModal — opens when user clicks "View" on a document row.
 *
 * LEFT COLUMN:  Category label + dynamically-rendered category-specific
 *               standard fields (non-empty only) + optional Line Items table
 *               + Additional Details section for extra metadata fields.
 * RIGHT COLUMN: Document preview (PDF iframe, image img, or fallback card)
 *               reusing the same fetch/blob pattern as FilePreviewModal.
 *
 * IMPORTANT: the CATEGORY_FIELD_SCHEMA below surfaces every field that the
 * upcoming Accounting, GST and Reports modules will need (posting dates,
 * place of supply, PO, bank, IRN, ACK, transporter, vehicle, GSTIN pair,
 * tax head breakdowns for challans, line-item totals, etc.).
 *
 * Data flow:
 *   GET /invoices/document/{docId}
 *     → doc.document_category → choose field schema
 *     → doc.* (DB columns) + doc.metadata_ (JSON blob fields)
 *       → render only fields with values
 *   GET /invoices/document/{docId}/download  → blob  → preview
 */
import { useEffect, useMemo, useState } from "react";
import {
  Download, X, FileText, Loader2, AlertCircle, Eye, FileDown, FileType, Sparkles,
  Pencil, Plus, Trash2, Save, Info, FileQuestion, CheckCircle2, BookOpen, RefreshCw,
  Compass, Link as LinkIcon, ExternalLink, ArrowUpRight, Clock, FileSpreadsheet,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Card, CardContent } from "../ui/card";
import { Separator } from "../ui/separator";
import { Badge } from "../ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../ui/select";
import { toast } from "sonner";
import { cn } from "../ui/utils";
import { DOCUMENT_CATEGORIES, type DocumentCategory } from "./DocumentCategoryModal";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  docId: string;
  onUpdate?: () => void;
  onNavigateTab?: (tab: string) => void;
  onViewVoucher?: (voucherId?: string) => void;
  allDocs?: any[];
}

type AnyDoc = Record<string, any>;

interface ParsedMeta {
  fields?: Record<string, unknown>;
  line_items?: Array<Record<string, unknown>>;
  line_item_headers?: string[];
  field_verification?: Record<string, string>;
  extraction_method?: string;
  ocr_confidence?: number | string;
  table_data?: {
    headers?: string[];
    headers_raw?: string[];
    rows?: Array<Record<string, unknown>>;
  };
}

/* ── Category-to-Module Routing Rules (ICAI & GST Compliance Guidelines) ── */

export interface CategoryRoutingInfo {
  category: string;
  routeTitle: string;
  targetModule: string;
  accountingDraft: "yes" | "adjustment" | "payment" | "conditional" | "link" | "no";
  draftStatusText: string;
  explanation: string;
  badgeClass: string;
  badgeText: string;
  verifyButtonText: string;
  createDraftButtonText: string;
  postButtonText: string;
  primaryAction: "draft" | "link_invoice" | "gst_workspace" | "track_notice" | "reference_data";
}

export const CATEGORY_ROUTING_CONFIG: Record<string, CategoryRoutingInfo> = {
  sales_records: {
    category: "sales_records",
    routeTitle: "Accounting & GST Workflow",
    targetModule: "Outward supplies / sales reporting",
    accountingDraft: "yes",
    draftStatusText: "Yes — Outward Sales Turnover Draft",
    explanation: "Eligible document. Prepares a sales revenue voucher for CA review and ledger posting, feeding GSTR-1 outward reporting.",
    badgeClass: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    badgeText: "Accounting Draft: Yes",
    verifyButtonText: "Verify & Create Accounting Draft",
    createDraftButtonText: "Create Accounting Draft",
    postButtonText: "Post to Ledger",
    primaryAction: "draft",
  },
  purchase_records: {
    category: "purchase_records",
    routeTitle: "Accounting & GST Workflow",
    targetModule: "Purchase records / ITC reconciliation",
    accountingDraft: "yes",
    draftStatusText: "Yes — Purchase Expense Draft",
    explanation: "Eligible document. Prepares a purchase expense voucher for CA review and ledger posting, feeding GSTR-2B ITC reconciliation.",
    badgeClass: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    badgeText: "Accounting Draft: Yes",
    verifyButtonText: "Verify & Create Accounting Draft",
    createDraftButtonText: "Create Accounting Draft",
    postButtonText: "Post to Ledger",
    primaryAction: "draft",
  },
  credit_note: {
    category: "credit_note",
    routeTitle: "Adjustment & GST Workflow",
    targetModule: "Adjust relevant sales and GST records",
    accountingDraft: "adjustment",
    draftStatusText: "Yes, adjustment draft",
    explanation: "Adjustment document. Prepares a sales return adjustment draft to credit the debtor and reduce output GST liability.",
    badgeClass: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30",
    badgeText: "Accounting Draft: Yes, Adjustment",
    verifyButtonText: "Verify & Create Adjustment Draft",
    createDraftButtonText: "Create Adjustment Draft",
    postButtonText: "Post Adjustment to Ledger",
    primaryAction: "draft",
  },
  debit_note: {
    category: "debit_note",
    routeTitle: "Adjustment & GST Workflow",
    targetModule: "Adjust relevant purchase and GST records",
    accountingDraft: "adjustment",
    draftStatusText: "Yes, adjustment draft",
    explanation: "Adjustment document. Prepares a purchase return adjustment draft to debit the supplier and adjust claimable ITC.",
    badgeClass: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30",
    badgeText: "Accounting Draft: Yes, Adjustment",
    verifyButtonText: "Verify & Create Adjustment Draft",
    createDraftButtonText: "Create Adjustment Draft",
    postButtonText: "Post Adjustment to Ledger",
    primaryAction: "draft",
  },
  b2b_invoice: {
    category: "b2b_invoice",
    routeTitle: "Commercial & GST Workflow",
    targetModule: "GST invoice data & outward/inward supplies",
    accountingDraft: "conditional",
    draftStatusText: "Conditional — Distinct Transaction Only",
    explanation: "GST registered business invoice. Creates an accounting draft only if it represents a distinct, not-yet-recorded commercial transaction.",
    badgeClass: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30",
    badgeText: "Accounting Draft: Conditional",
    verifyButtonText: "Verify & Create Accounting Draft",
    createDraftButtonText: "Create Accounting Draft",
    postButtonText: "Post to Ledger",
    primaryAction: "draft",
  },
  b2c_invoice: {
    category: "b2c_invoice",
    routeTitle: "Commercial & GST Workflow",
    targetModule: "GST invoice data & consumer supplies",
    accountingDraft: "conditional",
    draftStatusText: "Conditional — Distinct Transaction Only",
    explanation: "Consumer invoice. Creates an accounting draft only if it represents a distinct, not-yet-recorded commercial transaction.",
    badgeClass: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30",
    badgeText: "Accounting Draft: Conditional",
    verifyButtonText: "Verify & Create Accounting Draft",
    createDraftButtonText: "Create Accounting Draft",
    postButtonText: "Post to Ledger",
    primaryAction: "draft",
  },
  e_invoice: {
    category: "e_invoice",
    routeTitle: "Compliance & IRN Validation",
    targetModule: "IRN / invoice validation and GST information",
    accountingDraft: "link",
    draftStatusText: "Usually link, not duplicate",
    explanation: "Compliance document with Invoice Reference Number (IRN). Link to the parent commercial invoice rather than creating duplicate ledger entries.",
    badgeClass: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30",
    badgeText: "Accounting: Link, Not Duplicate",
    verifyButtonText: "Verify Document",
    createDraftButtonText: "Link to Invoice",
    postButtonText: "Link to Invoice",
    primaryAction: "link_invoice",
  },
  e_way_bill: {
    category: "e_way_bill",
    routeTitle: "Transport & Logistics Tracking",
    targetModule: "Transport and compliance tracking",
    accountingDraft: "no",
    draftStatusText: "Usually no — Transport Compliance",
    explanation: "Goods transport document. Retains transport metadata and vehicle tracking, linked to parent invoice without generating ledger postings.",
    badgeClass: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30",
    badgeText: "Accounting Draft: Usually No",
    verifyButtonText: "Verify Document",
    createDraftButtonText: "Link to Invoice",
    postButtonText: "Link to Invoice",
    primaryAction: "link_invoice",
  },
  gst_challan: {
    category: "gst_challan",
    routeTitle: "Tax Payment & Treasury Workflow",
    targetModule: "GST tax-payment tracking",
    accountingDraft: "payment",
    draftStatusText: "Yes, when it records a payment",
    explanation: "Statutory tax payment record. Generates a payment draft settling GST tax liabilities from bank treasury once amount is verified.",
    badgeClass: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    badgeText: "Accounting Draft: Payment Draft",
    verifyButtonText: "Verify & Create Payment Draft",
    createDraftButtonText: "Create Payment Draft",
    postButtonText: "Post Payment to Ledger",
    primaryAction: "draft",
  },
  gst_return: {
    category: "gst_return",
    routeTitle: "GST Filing & Return Workspace",
    targetModule: "GST filing, reconciliation and return data",
    accountingDraft: "no",
    draftStatusText: "Not automatically — GST Filing Only",
    explanation: "Filed return (GSTR-1, GSTR-3B). Feeds the GST workspace for filing review and reconciliation without forcing double-entry postings.",
    badgeClass: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
    badgeText: "Accounting Draft: Not Automatically",
    verifyButtonText: "Verify Return",
    createDraftButtonText: "Open in GST Workspace",
    postButtonText: "Open in GST Workspace",
    primaryAction: "gst_workspace",
  },
  gst_notice: {
    category: "gst_notice",
    routeTitle: "Statutory Notice & Compliance",
    targetModule: "Notice tracking, response and due dates",
    accountingDraft: "no",
    draftStatusText: "No, normally — Notice Tracking",
    explanation: "Statutory department communication. Tracks response deadlines, sections, and legal status without creating financial transactions.",
    badgeClass: "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/30",
    badgeText: "Accounting Draft: No, Normally",
    verifyButtonText: "Verify Notice",
    createDraftButtonText: "Track Notice",
    postButtonText: "Track Notice",
    primaryAction: "track_notice",
  },
  hsn_sac: {
    category: "hsn_sac",
    routeTitle: "Reference Master Data",
    targetModule: "HSN/SAC reference data and rate mapping",
    accountingDraft: "no",
    draftStatusText: "No — Reference Master Data",
    explanation: "Classification tariff master data. Feeds HSN tax rate schedules and product classification rules across all financial modules.",
    badgeClass: "bg-slate-500/10 text-slate-700 dark:text-slate-400 border-slate-500/30",
    badgeText: "Accounting Draft: No",
    verifyButtonText: "Verify Reference Data",
    createDraftButtonText: "View / Manage Reference Data",
    postButtonText: "View / Manage Reference Data",
    primaryAction: "reference_data",
  },
  document_list: {
    category: "document_list",
    routeTitle: "Identity & General Compliance",
    targetModule: "Identity and KYC verification",
    accountingDraft: "no",
    draftStatusText: "No — Identity & Compliance",
    explanation: "Identity, registration, and KYC documents (PAN, Aadhaar, electricity bills) retained for CA compliance audits.",
    badgeClass: "bg-slate-500/10 text-slate-700 dark:text-slate-400 border-slate-500/30",
    badgeText: "Accounting Draft: No",
    verifyButtonText: "Verify Document",
    createDraftButtonText: "Verify Document",
    postButtonText: "Verify Document",
    primaryAction: "reference_data",
  },
};

export function getCategoryRouting(category: string): CategoryRoutingInfo {
  return CATEGORY_ROUTING_CONFIG[category] ?? {
    category,
    routeTitle: "General Document",
    targetModule: "Compliance and document archiving",
    accountingDraft: "no",
    draftStatusText: "No",
    explanation: "General document retained for client audit record.",
    badgeClass: "bg-muted text-muted-foreground border-border",
    badgeText: "Accounting Draft: No",
    verifyButtonText: "Verify Document",
    createDraftButtonText: "Create Accounting Draft",
    postButtonText: "Post to Ledger",
    primaryAction: "reference_data",
  };
}

/* ── Constants ─────────────────────────────────────────────────── */

const IMAGE_EXTS = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp", "svg", "tiff", "tif"]);
const PDF_EXTS   = new Set(["pdf"]);

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

const INFORMATIONAL_CATEGORIES = new Set([
  "document_list",
  "gst_notice",
  "hsn_sac",
  "gst_return",
  "e_way_bill",
  "e_invoice",
]);

/** Primary DB-backed keys. Expanded so metadata aliases (e.g. cpin, cin,
 *  bank_account) CAN surface as Additional Details if they do not match
 *  a schema key first, but we always prioritise the column values. */
const CORE_KEYS = new Set([
  "invoice_number", "gstin", "invoice_date", "vendor", "customer",
  "amount", "taxable_amount", "cgst", "sgst", "igst", "cess", "hsn", "arn",
  "notice_number", "notice_date", "response_due_date", "priority",
  "gst_return_type", "financial_year", "month", "filed_date", "invoice_type",
  "status", "ocr_confidence", "metadata",
]);

/* ── FIELD ALIAS MAP ──────────────────────────────────────────────
 *  Backend parsers store extracted values under MANY key names that are
 *  synonyms of each other (e.g. "total" == "amount", "supplier" == "vendor",
 *  "irn" == "irn_hash", "from_gstin" == "supplier_gstin"). The frontend
 *  schema uses canonical keys. This map lets resolve() chase every known
 *  alias across core_fields + meta_fields and return the first non-empty hit.
 *
 *  NOTE: The canonical key itself is ALWAYS tried first (see resolve()).
 *  Aliases are fallbacks ordered from strongest to weakest.
 *
 *  Sources consulted for this list:
 *    • _parse_invoice       (core + meta: place_of_supply, irn, ack_number, reverse_charge)
 *    • _parse_e_invoice     (meta: irn, ack_number, ack_date, recipient_gstin, supplier_gstin)
 *    • _parse_e_way_bill    (meta: valid_until, from_gstin, to_gstin, vehicle_number, distance, supply_type)
 *    • _parse_gst_challan  (meta: cpin, cin, transaction_reference, interest, penalty)
 *    • _parse_gst_return   (meta: status, itc_claimed, late_fee)
 *    • _parse_gst_notice   (meta: notice_type, issuing_authority, act/section)
 *    • _parse_credit_debit_note (meta: original_invoice_number, reason, document_type)
 *    • _CATEGORY_FIELD_SCHEMA Gemini fallback (company_name, total_sales, net_amount, ewb_number)
 *    • _AMOUNT_AGG_KEYS table grouper (tax_amount, net_amount → amount)
 *    • _INVOICE_ID_KEYS / _DATE_KEYS / _PARTY_KEYS (invoice_no, bill_no, party_name, …)
 *    • UploadedDocumentResponse Pydantic (190 canonical field names)
 */
type AliasMap = Record<string, readonly string[]>;

const FIELD_ALIASES: AliasMap = {
  /* —— Identifiers —— */
  invoice_number: [
    "invoice_no", "inv_no", "bill_no", "bill_number",
    "doc_no", "document_no", "document_number",
    "doc_number", "document", "reference_no", "reference_number",
    "supplier_invoice_number", "tax_invoice_no", "tax_invoice_number",
    "challan_no", "challan_number", "receipt_number", "ewb_number",
  ],
  irn_hash: ["irn", "irn_number", "invoice_ref_no", "invoice_reference_number", "qr_irn"],
  acknowledgement_number: ["ack_number", "acknowledgement_no", "ack_no", "acknowledgment_number"],
  acknowledgement_date: ["ack_date", "acknowledgement_no_date", "acknowledgment_date"],

  /* —— Dates —— */
  invoice_date: [
    "date", "bill_date", "doc_date", "document_date",
    "transaction_date", "inv_date", "dt", "tax_invoice_date",
    "supplier_invoice_date", "posting_date",
  ],
  due_date: ["payment_due_date", "due", "net_due_date"],
  challan_date: ["challan_generated_date", "generated_on", "payment_date", "date_of_payment", "date_of_receipt"],
  filed_date: ["filing_date", "date_of_filing"],
  notice_date: ["date_of_notice", "issued_on", "issued_date"],
  response_due_date: ["due_date", "reply_by", "respond_by", "last_date"],
  valid_upto: ["valid_until", "eway_expiry", "valid_till", "valid_through", "expiry_date"],
  period_start: ["from_date", "start_date"],
  period_end: ["to_date", "end_date"],
  posting_date: ["posting_dt"],

  /* —— Party / Names —— */
  vendor: [
    "supplier", "supplier_name", "seller", "seller_name",
    "vendor_name", "from", "from_name", "consignor", "billed_from",
    "sold_by", "supplier_company", "company_name", "legal_name",
    "trade_name", "firm_name", "taxpayer_name", "name_of_taxpayer",
    "issuing_authority", "authority", "department", "biller",
    "company", "organisation", "organization", "from_party", "dispatched_from",
  ],
  customer: [
    "buyer", "buyer_name", "customer_name", "recipient", "recipient_name",
    "to", "to_name", "consignee", "bill_to", "ship_to", "billed_to",
    "sold_to", "party_name", "party", "client", "client_name",
    "deliver_to", "to_party",
  ],
  supplier_pan: ["pan", "pan_number", "taxpayer_pan"],
  customer_pan: ["buyer_pan", "recipient_pan", "client_pan"],
  contact_person: ["contact_name", "contact", "contact_person_name", "attn", "attention"],
  contact_phone: ["contact_no", "contact_number", "customer_phone", "mobile", "phone_no", "phone"],
  sales_person: ["salesperson", "sales_rep", "sales_person_name", "executive"],
  sales_person_contact: ["sales_person_phone", "salesperson_phone", "sales_rep_contact"],
  buyer_code: ["consignee_code", "customer_code"],
  pl_no: ["p_l_no", "pl_number"],
  fl_no: ["f_l_no", "fl_number"],

  /* —— GSTINs —— */
  gstin: [
    "supplier_gstin", "seller_gstin", "vendor_gstin", "from_gstin",
    "gst_no", "gst_num", "gst_number", "taxpayer_gstin",
  ],
  supplier_gstin: [
    "from_gstin", "seller_gstin", "vendor_gstin", "gstin", "gst_no",
  ],
  customer_gstin: [
    "to_gstin", "recipient_gstin", "buyer_gstin", "client_gstin",
  ],
  recipient_gstin: ["to_gstin", "buyer_gstin", "customer_gstin"],

  /* —— Addresses —— */
  supplier_address: ["from_address", "seller_address", "billing_address"],
  customer_address: ["to_address", "buyer_address", "shipping_address"],
  billing_address: ["bill_address", "bill_to_address"],
  shipping_address: ["ship_address", "ship_to_address", "delivery_address"],
  supplier_state: ["from_state", "source_state", "state_of_supply"],
  customer_state: ["to_state", "destination_state", "recipient_state"],
  supplier_state_code: ["from_state_code", "src_state_code"],
  customer_state_code: ["to_state_code", "dest_state_code"],
  place_of_supply: ["place_of_supply_state_code", "pos", "supply_place", "place"],
  state_code: ["pos_state_code", "supply_state_code", "taxpayer_state_code", "supplier_state_code", "customer_state_code"],

  /* —— Amounts / Financial —— */
  amount: [
    "total", "grand_total", "total_amount", "net_amount",
    "amount_due", "balance_due", "net_total", "total_invoice_value",
    "total_value", "note_value", "amount_paid", "total_payable",
    "total_sales", "total_purchase", "total_amount_involved",
    "demand_amount", "tax_demand", "amount_involved",
    "tax_payable", "total_tax", "net_tax",
  ],
  taxable_amount: [
    "taxable_value", "assessable_value", "basic_amount", "basic_value",
    "value_of_supply", "assessable", "taxable_turnover",
  ],
  tax_amount: ["total_tax_amount", "gross_tax"],
  cgst: ["central_gst", "central_tax", "cgst_amount"],
  sgst: ["state_gst", "state_tax", "sgst_amount"],
  igst: ["integrated_gst", "integrated_tax", "igst_amount"],
  cess: ["compensation_cess", "cess_amount"],
  total_tax: ["gross_tax", "tax_total"],
  discount: ["discount_amount", "discount_total"],
  freight: ["transport_charges", "shipping_charges"],
  packing_charges: ["packing_cost", "packing_fee"],
  round_off: ["rounding", "rounding_off", "round_off_diff"],
  other_charges: ["misc_charges", "extra_charges", "handling_charges"],
  amount_in_words: ["total_amount_in_words", "in_words", "total_in_words", "rupees_in_words", "amt_in_words"],

  /* —— Rates —— */
  gst_rate: ["tax_rate", "rate"],
  cgst_rate: ["cgst_pct", "cgst_percent"],
  sgst_rate: ["sgst_pct", "sgst_percent"],
  igst_rate: ["igst_pct", "igst_percent"],
  cess_rate: ["cess_pct", "cess_percent"],

  /* —— Reverse Charge / RCM —— */
  reverse_charge: ["rcm", "rcm_applicable", "reverse_charge_applicable"],
  rcm_applicable: ["reverse_charge", "rcm"],

  /* —— PO / Delivery / Transport —— */
  po_number: ["po_no", "purchase_order_no", "purchase_order_number", "order_no"],
  po_date: ["purchase_order_date", "order_date"],
  delivery_note: ["delivery_note_no", "delivery_note_number"],
  delivery_challan: ["delivery_challan_no", "challan_delivery_number"],
  grn_number: ["grn", "grn_no", "goods_receipt_no"],
  eway_bill_number: ["ewaybill", "eway_bill_no", "ewb_no", "ewb_number", "e_way_bill_no", "eway_number"],
  vehicle_number: ["vehicle_no", "vehicle_reg", "reg_no", "vrn"],
  transport_mode: ["mode_of_transport", "transport"],
  distance_km: ["distance", "transport_distance", "distance_in_km"],
  supply_type: ["transaction_type", "nature_of_supply"],

  /* —— Payment —— */
  payment_terms: ["terms", "payment_conditions", "credit_terms"],
  payment_method: ["mode_of_payment", "paid_via", "payment_mode"],
  payment_reference: ["ref", "payment_ref", "payment_ref_no"],
  utr_number: ["transaction_reference", "utr", "brn", "transaction_id", "txn_ref", "txn_id"],
  remarks: ["notes", "comments", "narration", "remark", "note"],

  /* —— Bank —— */
  bank_name: ["bank", "banker", "beneficiary_bank", "paid_via_bank"],
  bank_account: ["account_no", "account_number", "a/c_no", "bank_account_no"],
  ifsc_code: ["ifsc", "ifs_code", "branch_ifsc"],
  bank_branch: ["branch", "branch_name", "bank_branch_name"],
  bsr_code: ["bsr", "bank_bsr_code"],

  /* —— Credit / Debit Notes —— */
  credit_note_number: ["cn_number", "cn_no", "crn", "crn_no", "note_number"],
  credit_note_date: ["cn_date", "note_date"],
  debit_note_number: ["dn_number", "dn_no", "dbn", "dbn_no"],
  debit_note_date: ["dn_date", "dbn_date"],
  original_invoice_number: ["against_invoice", "original_invoice_no", "ref_invoice", "reference_invoice", "orig_inv_no"],
  reason: ["purpose", "reason_for_note", "credit_reason", "debit_reason"],
  document_type: ["type", "doc_type", "note_type"],

  /* —— GST Returns —— */
  gst_return_type: ["return_type", "form_type", "gst_return_form"],
  financial_year: ["fy", "financial_yr", "fin_year", "assessment_year", "ay", "year"],
  month: ["tax_period", "period", "quarter", "return_period"],
  quarter: ["qtr"],
  arn: ["acknowledgement_number_arn", "return_ack_no"],
  status: ["filing_status", "return_status"],
  filing_mode: ["mode_of_filing", "online_offline"],
  turnover_previous: ["previous_year_turnover", "last_year_turnover", "annual_turnover"],
  exempted_turnover: ["exempt_turnover", "exempt_sales"],
  export_turnover: ["exports", "export_value", "zero_rated_supply"],
  deemed_export_turnover: ["deemed_exports", "deemed_export_value"],
  outward_supplies: ["outward_supply", "outward", "sales", "sales_total", "total_outward"],
  rcm_supplies: ["rcm_supply", "supplies_subject_to_rcm", "inward_rcm"],
  input_credit: ["input_tax_credit", "itc", "itc_claimed", "itc_available"],
  itc_reversed: ["input_credit_reversed", "reversed_itc", "itc_reversal"],
  net_itc: ["net_input_credit", "net_credit"],
  cgst_payable: ["cgst_tax_payable"],
  sgst_payable: ["sgst_tax_payable"],
  igst_payable: ["igst_tax_payable"],
  cess_payable: ["cess_tax_payable"],
  cgst_cash: ["cgst_paid_by_cash", "cgst_cash_payment"],
  sgst_cash: ["sgst_paid_by_cash", "sgst_cash_payment"],
  igst_cash: ["igst_paid_by_cash", "igst_cash_payment"],
  cess_cash: ["cess_paid_by_cash", "cess_cash_payment"],
  cgst_itc: ["cgst_paid_by_itc", "cgst_adjusted"],
  sgst_itc: ["sgst_paid_by_itc", "sgst_adjusted"],
  igst_itc: ["igst_paid_by_itc", "igst_adjusted"],
  interest: ["interest_amount", "int", "total_interest"],
  late_fee: ["latefee", "fee", "penalty_fee"],
  linked_challans: ["challan_linked", "challan_references"],

  /* —— Notices / Orders —— */
  notice_number: [
    "notice_no", "notice_ref", "reference_number", "ref_number",
    "ref_no", "order_no", "order_number", "notice_reference",
  ],
  notice_type: ["type_of_notice"],
  reference_number: ["case_no", "case_number", "docket_no", "file_no"],
  adjudication_date: ["adjudication_dt", "order_date", "judgment_date"],
  period: ["tax_period", "notice_period", "return_period", "involved_period"],
  assessment_year: ["ay", "assess_year"],
  pan_number: ["pan", "permanent_account_number"],
  trade_name: ["doing_business_as", "dba", "business_name"],
  principal_address: ["registered_office", "address_of_taxpayer", "assesse_address"],
  range_division: ["range", "division", "jurisdiction_range", "jurisdiction_division"],
  commissionerate: ["commissionerate_jurisdiction", "jurisdiction_commissionerate"],
  officer_name: ["issued_by", "officer", "authorised_signatory", "signatory"],
  officer_designation: ["rank", "post", "designation"],
  act_section: ["section", "under_section", "rule", "act", "act_and_rule", "section_rule"],
  subject: ["subject_line", "notice_subject"],
  demand_tax: ["demand_principal", "tax_demand", "principle_demand"],
  demand_interest: ["interest_on_demand", "demand_int"],
  demand_penalty: ["penalty_demand", "total_penalty", "fine"],
  demand_other: ["other_demand", "misc_demand", "other_charges_demand"],
  next_action: ["recommended_action", "action_needed", "steps_required"],

  /* —— Challan —— */
  cpin: ["cpin_no", "cpi_no", "challan_payment_identification_number", "challan_number", "cpin_number"],
  cin: ["cin_no", "challan_identification_number", "bank_ack_no", "company_cin", "corporate_id"],
  challan_serial: ["challan_sr_no", "serial_no", "sr_no"],
  purpose: ["reason", "reason_for_challan", "tax_purpose", "nature_of_payment"],
  expiry_date: ["challan_expiry_date", "valid_upto", "valid_until"],
  email: ["taxpayer_email", "email_id", "supplier_email", "customer_email"],
  phone: ["mobile", "mobile_no", "taxpayer_phone", "contact_phone", "contact_no"],
  address: ["taxpayer_address", "supplier_address", "customer_address"],
  state: ["taxpayer_state", "supplier_state", "customer_state"],
  cgst_tax: ["cgst_principal", "cgst_basic"],
  cgst_interest: ["cgst_int"],
  cgst_penalty: ["cgst_pen"],
  cgst_fee: ["cgst_latefee", "cgst_fees"],
  cgst_others: ["cgst_misc"],
  sgst_tax: ["sgst_principal", "sgst_basic"],
  sgst_interest: ["sgst_int"],
  sgst_penalty: ["sgst_pen"],
  sgst_fee: ["sgst_latefee", "sgst_fees"],
  sgst_others: ["sgst_misc"],
  igst_tax: ["igst_principal", "igst_basic"],
  igst_interest: ["igst_int"],
  igst_penalty: ["igst_pen"],
  igst_fee: ["igst_latefee", "igst_fees"],
  igst_others: ["igst_misc"],
  cess_tax: ["cess_principal", "cess_basic"],
  cess_interest: ["cess_int"],
  cess_penalty: ["cess_pen"],
  cess_others: ["cess_misc"],

  /* —— E-Invoice / QR —— */
  qr_code: ["qr", "qr_payload", "qr_image"],
  signed_qr: ["signed_qr_code", "qr_signed"],
  valid_from: ["generated_on", "invoice_generated_date"],
  supplier_invoice_number: ["supplier_doc_no", "supplier_inv_no", "original_inv_no"],
  dispatch_from: ["dispatch_address", "from_pickup"],
  ship_to: ["delivery_address", "delivery_spot", "destination"],

  /* —— E-Way Bill transporter —— */
  transporter_id: ["transporter_gstin", "tansporter_gstin" /* sic */, "tpt_id"],
  transporter_name: ["transporter", "carrier", "logistics_provider"],
  transporter_doc_no: ["lr_no", "lr_number", "consignment_note_no", "doc_reference", "transport_doc_no"],
  supplier_pincode: ["from_pincode", "dispatch_pincode", "pickup_pincode"],
  recipient_pincode: ["to_pincode", "delivery_pincode", "destination_pincode"],
  from_state: ["origin_state", "supplier_state"],
  to_state: ["destination_state", "recipient_state"],
  vehicle_type: ["transporter_type", "type_of_vehicle", "transport_vehicle"],
  cancelled_date: ["eway_cancelled_date", "cancellation_date"],
  cancelled: ["is_cancelled", "eway_cancelled"],

  /* —— HSN / SAC / Items —— */
  hsn: ["hsn_code", "hsn_sac", "sac", "sac_code", "hsn_sac_code"],
  hsn_description: ["product", "product_description", "item", "item_name", "item_description", "description_of_goods"],
  item_description: ["hsn_description", "description", "product_name", "goods_description"],
  quantity: ["qty", "pack_size", "no_of_packs", "units"],
  unit_price: ["rate", "price", "per_unit_price", "unit_rate"],
  rate: ["unit_rate", "price_per_unit"],
  ewb_number: ["eway_bill_number", "eway_bill_no"],

  /* —— B2C / POS extras —— */
  cashier: ["cashier_name", "billed_by", "salesperson"],
  counter_no: ["counter", "till_no", "pos_no"],

  /* —— Company/Report level —— */
  company_name: ["report_issuer", "report_company", "organisation_name"],
  report_title: ["report_name", "report_heading", "title"],
  total_sales: ["sales_total", "outward_supplies", "sales_amount"],
  total_purchases: ["purchase_total", "inward_supplies", "purchase_amount"],
} as const;

/* ── Helpers ───────────────────────────────────────────────────── */

const token = () => localStorage.getItem("ca_token");

const authHeaders = (extra: Record<string, string> = {}) => {
  const t = token();
  return { ...extra, ...(t ? { Authorization: `Bearer ${t}` } : {}) };
};

function parseMeta(raw?: string | null): ParsedMeta {
  if (!raw) return {};
  try {
    const p = JSON.parse(raw);
    return typeof p === "object" && p !== null ? (p as ParsedMeta) : {};
  } catch {
    return {};
  }
}

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  if (typeof v === "number") return false;
  if (typeof v === "boolean") return false;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v).length === 0;
  return false;
}

function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  try {
    return Number(n).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  } catch {
    return String(n);
  }
}

const NON_CURRENCY_KEY_REGEX = /(hsn|sac|batch|serial|sr_no|s_no|lot|pin|phone|mobile|account|gstin|pan|arn|cin|cpin|irn|ack|vehicle|number|no$|id$|date|year|month|qty|quantity)/i;

function formatValue(v: unknown, key?: string): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "Yes" : "No";

  // If this key is an identifier, code, date, quantity, or phone, never format as currency
  if (key && NON_CURRENCY_KEY_REGEX.test(key)) {
    if (typeof v === "number") return String(v);
    return String(v).trim();
  }

  if (typeof v === "number") return fmtNum(v);

  if (typeof v === "string") {
    const trimmed = v.trim();
    if (trimmed === "") return "";
    /* -- Fast-path: already a plain number string -- */
    if (/^-?[0-9]+(\.[0-9]+)?$/.test(trimmed)) {
      // If it looks like an integer with 5+ digits (like HSN code or PIN code) without currency hint, keep clean
      if (!trimmed.includes(".") && trimmed.length >= 5 && (!key || !/(amount|total|tax|price|rate|value|fee|charge)/i.test(key))) {
        return trimmed;
      }
      return fmtNum(Number(trimmed));
    }
    /* -- Slow-path: numeric-looking strings with ₹ / Rs. / commas / spaces -- */
    if (/[₹$]|Rs\.?|^-?[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?$/.test(trimmed)) {
      const cleaned = trimmed
        .replace(/[₹$]/g, "")
        .replace(/Rs\.?/gi, "")
        .replace(/,/g, "")
        .trim();
      /* Only keep the LAST dot (e.g. "1,234.56" → "1234.56"). Strip all other non-numeric chars. */
      const lastDot = cleaned.lastIndexOf(".");
      const withoutDotsExceptLast = lastDot >= 0
        ? cleaned.slice(0, lastDot).replace(/\./g, "") + cleaned.slice(lastDot)
        : cleaned;
      const digits = withoutDotsExceptLast.replace(/[^0-9.\-]/g, "");
      if (digits !== "" && !Number.isNaN(Number(digits))) {
        return fmtNum(Number(digits));
      }
    }
    return trimmed;
  }
  if (Array.isArray(v)) return v.map((x) => formatValue(x, key)).join(", ");
  if (typeof v === "object") {
    try { return JSON.stringify(v); } catch { return String(v); }
  }
  return String(v);
}

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

export interface TableColumn {
  key: string;
  label: string;
}

export interface TableModel {
  columns: TableColumn[];
  rows: Array<Record<string, unknown>>;
}

const CANONICAL_COL_LABELS: Record<string, string> = {
  sr_no: "Sr. No.",
  item_name: "Item Description",
  company_name: "Company / Brand",
  hsn: "HSN / SAC",
  batch_no: "Batch No.",
  expiry_date: "Expiry Date",
  quantity: "Quantity",
  rate: "Rate / Price",
  discount: "Discount",
  taxable_amount: "Taxable Value",
  cgst_amount: "CGST",
  sgst_amount: "SGST",
  igst_amount: "IGST",
  total_amount: "Total Amount",
};

function getTableCellValue(row: Record<string, unknown>, colKey: string, colLabel: string): unknown {
  if (!row || typeof row !== "object") return null;

  // 1. Direct hit by colKey or colLabel
  if (!isEmpty(row[colKey])) return row[colKey];
  if (!isEmpty(row[colLabel])) return row[colLabel];

  // 2. Normalized matching
  const normKey = colKey.toLowerCase().replace(/[^a-z0-9]/g, "");
  const normLabel = colLabel.toLowerCase().replace(/[^a-z0-9]/g, "");

  for (const [rk, rv] of Object.entries(row)) {
    if (isEmpty(rv)) continue;
    const normRk = rk.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (normRk === normKey || normRk === normLabel) return rv;
  }

  // 3. Known synonym fallbacks
  const synonymGroups: Record<string, string[]> = {
    sr_no: ["sr_no", "sr", "s_no", "serial_no", "srno", "sno", "sr_num"],
    item_name: ["item_name", "item", "description", "particulars", "product", "product_name", "item_description", "particular", "desc"],
    company_name: ["company_name", "company", "brand", "manufacturer", "make", "mfr"],
    hsn: ["hsn", "hsn_sac", "hsn_code", "sac", "hsncode"],
    batch_no: ["batch_no", "batch", "batchnumber", "lot_no", "lot"],
    expiry_date: ["expiry_date", "expiry", "exp_date", "expdate", "exp"],
    quantity: ["quantity", "qty", "nos", "units", "qnty"],
    rate: ["rate", "price", "unit_price", "rate_per_no", "unitrate", "mrp"],
    discount: ["discount", "disc", "disc_percent", "disc_amt", "discount_amount"],
    taxable_amount: ["taxable_amount", "taxable_value", "ass_amt", "assessable_value", "taxable", "assamt"],
    cgst_amount: ["cgst_amount", "cgst", "cgst_amt", "cgstamt"],
    sgst_amount: ["sgst_amount", "sgst", "sgst_amt", "sgstamt"],
    igst_amount: ["igst_amount", "igst", "igst_amt", "igstamt"],
    total_amount: ["total_amount", "total", "amount", "net_amount", "total_value", "item_total"],
  };

  for (const [canon, synList] of Object.entries(synonymGroups)) {
    const isTarget = normKey === canon.replace(/[^a-z0-9]/g, "") ||
                     normLabel === canon.replace(/[^a-z0-9]/g, "") ||
                     synList.includes(colKey) ||
                     synList.some(s => s.replace(/[^a-z0-9]/g, "") === normLabel);
    if (isTarget) {
      for (const s of synList) {
        if (!isEmpty(row[s])) return row[s];
        for (const [rk, rv] of Object.entries(row)) {
          if (!isEmpty(rv) && rk.toLowerCase().replace(/[^a-z0-9]/g, "") === s.replace(/[^a-z0-9]/g, "")) {
            return rv;
          }
        }
      }
    }
  }

  return null;
}

function formatTableCellValue(val: unknown, colKey: string): string {
  if (isEmpty(val)) return "";
  const key = colKey.toLowerCase();

  // Non-currency strings (identifiers/codes)
  if (/(hsn|batch|sr_no|expiry|serial)/i.test(key)) {
    return String(val).trim();
  }

  // Discount
  if (/discount/i.test(key)) {
    const s = String(val).trim();
    if (s.endsWith("%")) return s;
    if (!Number.isNaN(Number(s))) return `${s}%`;
    return s;
  }

  // Quantity
  if (/quantity|qty/i.test(key)) {
    const n = Number(val);
    if (!Number.isNaN(n)) return String(n);
    return String(val).trim();
  }

  // Currency amounts
  if (/(amount|rate|price|cgst|sgst|igst|taxable|total)/i.test(key)) {
    return formatValue(val);
  }

  return formatValue(val, colKey);
}

/* ── Field schema per category ──────────────────────────────────── */

interface FieldDef { label: string; key: string; }

/**
 * Expanded field schemas for every category. We intentionally include
 * fields that the OCR may have saved as synonyms (e.g. for GST Challan
 * both `cpin` and `cin` are listed) — the resolver will keep the first
 * non-empty value, while the remaining synonym falls through to
 * Additional Details ONLY if the label/key pair was already rendered.
 * This guarantees downstream modules (Accounting, GST, Reports) can
 * always read their required fields from the View output.
 */
const CATEGORY_FIELD_SCHEMA: Record<string, FieldDef[]> = {
  /* —— Sales / B2B / B2C —— */
  sales_records: [
    { label: "Invoice Number",       key: "invoice_number" },
    { label: "Invoice Date",         key: "invoice_date" },
    { label: "Due Date",             key: "due_date" },
    { label: "Posting Date",         key: "posting_date" },
    { label: "Document Type",        key: "invoice_type" },
    { label: "Place of Supply",      key: "place_of_supply" },
    { label: "Reverse Charge (Y/N)", key: "reverse_charge" },

    { label: "Vendor / Company (Seller)", key: "vendor" },
    { label: "Vendor GSTIN",              key: "supplier_gstin" },
    { label: "PAN of Seller",             key: "supplier_pan" },
    { label: "Vendor Address",            key: "supplier_address" },
    { label: "Vendor State",              key: "supplier_state" },
    { label: "Vendor State Code",         key: "supplier_state_code" },
    { label: "Vendor Phone",              key: "supplier_phone" },
    { label: "Vendor Email",              key: "supplier_email" },
    { label: "Vendor Bank Name",          key: "bank_name" },
    { label: "Vendor Bank A/c No.",       key: "bank_account" },
    { label: "Vendor IFSC",               key: "ifsc_code" },
    { label: "Vendor Branch",             key: "bank_branch" },

    { label: "Customer / Buyer",     key: "customer" },
    { label: "Customer GSTIN",       key: "customer_gstin" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Customer PAN",         key: "customer_pan" },
    { label: "Customer Address",     key: "customer_address" },
    { label: "Customer State",       key: "customer_state" },
    { label: "Customer State Code",  key: "customer_state_code" },
    { label: "Customer Phone",       key: "customer_phone" },
    { label: "Customer Email",       key: "customer_email" },
    { label: "Ship To Address",      key: "shipping_address" },
    { label: "Bill To Address",      key: "billing_address" },
    { label: "Contact Person",       key: "contact_person" },
    { label: "Contact Phone",        key: "contact_phone" },
    { label: "Sales Person / Work",  key: "sales_person" },
    { label: "Sales Person Contact", key: "sales_person_contact" },
    { label: "Buyer / Customer Code", key: "buyer_code" },
    { label: "Corporate ID (CIN)",   key: "cin" },
    { label: "P.L. No.",             key: "pl_no" },
    { label: "F.L. No.",             key: "fl_no" },
    { label: "Transporter Name",     key: "transporter_name" },
    { label: "Transporter Location", key: "transporter_location" },

    { label: "Purchase Order No.",   key: "po_number" },
    { label: "PO Date",              key: "po_date" },
    { label: "Delivery Note No.",    key: "delivery_note" },
    { label: "Vehicle / LR No.",     key: "vehicle_number" },
    { label: "Transport Mode",       key: "transport_mode" },
    { label: "Payment Terms",        key: "payment_terms" },
    { label: "Payment Due Date",     key: "payment_due_date" },
    { label: "Payment Method",       key: "payment_method" },
    { label: "Payment Reference",    key: "payment_reference" },
    { label: "Bank UTR / Transfer ID", key: "utr_number" },
    { label: "Remark / Notes",       key: "remarks" },

    { label: "HSN / SAC (Summary)",  key: "hsn" },
    { label: "Total Taxable Value",  key: "taxable_amount" },
    { label: "CGST Amount",          key: "cgst" },
    { label: "SGST Amount",          key: "sgst" },
    { label: "IGST Amount",          key: "igst" },
    { label: "CESS Amount",          key: "cess" },
    { label: "CGST % (Avg)",         key: "cgst_rate" },
    { label: "SGST % (Avg)",         key: "sgst_rate" },
    { label: "IGST % (Avg)",         key: "igst_rate" },
    { label: "CESS % (Avg)",         key: "cess_rate" },
    { label: "Discount Amount",      key: "discount" },
    { label: "Freight / Shipping",   key: "freight" },
    { label: "Round Off",            key: "round_off" },
    { label: "Grand Total Amount",   key: "amount" },
    { label: "Total in Words",       key: "amount_in_words" },
  ],

  b2b_invoice: [
    { label: "Invoice Number",       key: "invoice_number" },
    { label: "Invoice Date",         key: "invoice_date" },
    { label: "Due Date",             key: "due_date" },
    { label: "Posting Date",         key: "posting_date" },
    { label: "Document Type",        key: "invoice_type" },
    { label: "Place of Supply",      key: "place_of_supply" },
    { label: "Reverse Charge (Y/N)", key: "reverse_charge" },

    { label: "Supplier / Vendor",    key: "vendor" },
    { label: "Supplier GSTIN",       key: "supplier_gstin" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Supplier State",       key: "supplier_state" },
    { label: "Supplier Address",     key: "supplier_address" },
    { label: "Supplier Bank Name",   key: "bank_name" },
    { label: "Supplier Bank A/c",    key: "bank_account" },
    { label: "Supplier IFSC",        key: "ifsc_code" },

    { label: "Customer / Buyer",     key: "customer" },
    { label: "Customer GSTIN",       key: "customer_gstin" },
    { label: "Customer Address",     key: "customer_address" },
    { label: "Customer State",       key: "customer_state" },

    { label: "Purchase Order No.",   key: "po_number" },
    { label: "PO Date",              key: "po_date" },
    { label: "Delivery Note No.",    key: "delivery_note" },
    { label: "Vehicle No.",          key: "vehicle_number" },
    { label: "Payment Terms",        key: "payment_terms" },
    { label: "Payment Reference",    key: "payment_reference" },
    { label: "UTR / Transfer ID",    key: "utr_number" },
    { label: "Remarks",              key: "remarks" },

    { label: "HSN / SAC (Summary)",  key: "hsn" },
    { label: "Total Taxable Value",  key: "taxable_amount" },
    { label: "CGST",                 key: "cgst" },
    { label: "SGST",                 key: "sgst" },
    { label: "IGST",                 key: "igst" },
    { label: "CESS",                 key: "cess" },
    { label: "Discount",             key: "discount" },
    { label: "Freight",              key: "freight" },
    { label: "Round Off",            key: "round_off" },
    { label: "Grand Total",          key: "amount" },
    { label: "Total in Words",       key: "amount_in_words" },
  ],

  b2c_invoice: [
    { label: "Invoice Number",       key: "invoice_number" },
    { label: "Invoice Date",         key: "invoice_date" },
    { label: "Due Date",             key: "due_date" },
    { label: "Document Type",        key: "invoice_type" },
    { label: "Place of Supply",      key: "place_of_supply" },
    { label: "POS State Code",       key: "state_code" },

    { label: "Seller / Company",     key: "vendor" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Supplier Address",     key: "supplier_address" },
    { label: "Supplier State",       key: "supplier_state" },
    { label: "Bank Name",            key: "bank_name" },
    { label: "Bank A/c No.",         key: "bank_account" },
    { label: "IFSC Code",            key: "ifsc_code" },

    { label: "Customer (B2C)",       key: "customer" },
    { label: "Customer Phone",       key: "customer_phone" },
    { label: "Customer Email",       key: "customer_email" },
    { label: "Billing Address",      key: "billing_address" },
    { label: "Shipping Address",     key: "shipping_address" },

    { label: "POS Cashier",          key: "cashier" },
    { label: "Counter / Till No.",   key: "counter_no" },
    { label: "Receipt No.",          key: "receipt_number" },
    { label: "Payment Method",       key: "payment_method" },
    { label: "Payment Reference",    key: "payment_reference" },
    { label: "Remarks",              key: "remarks" },

    { label: "HSN / SAC (Summary)",  key: "hsn" },
    { label: "Total Taxable Value",  key: "taxable_amount" },
    { label: "CGST",                 key: "cgst" },
    { label: "SGST",                 key: "sgst" },
    { label: "IGST",                 key: "igst" },
    { label: "CESS",                 key: "cess" },
    { label: "Discount",             key: "discount" },
    { label: "Freight",              key: "freight" },
    { label: "Round Off",            key: "round_off" },
    { label: "Grand Total",          key: "amount" },
    { label: "Total in Words",       key: "amount_in_words" },
  ],

  purchase_records: [
    { label: "Invoice / Bill No.",    key: "invoice_number" },
    { label: "Bill / Invoice Date",   key: "invoice_date" },
    { label: "Document Type",         key: "document_type" },
    { label: "Entry / Posting Date",  key: "posting_date" },
    { label: "Due Date",              key: "due_date" },
    { label: "Place of Supply",       key: "place_of_supply" },
    { label: "State Code",            key: "state_code" },
    { label: "Reverse Charge (Y/N)",  key: "reverse_charge" },
    { label: "RCM Applicable",        key: "rcm_applicable" },
    { label: "E-Way Bill No.",        key: "eway_bill_number" },
    { label: "Ref. No.",              key: "ref_number" },
    { label: "Vehicle / LR No.",      key: "vehicle_number" },

    { label: "Supplier / Vendor",     key: "vendor" },
    { label: "GSTIN (Seller)",        key: "gstin" },
    { label: "Supplier GSTIN",        key: "supplier_gstin" },
    { label: "Supplier PAN",          key: "supplier_pan" },
    { label: "Supplier Address",      key: "supplier_address" },
    { label: "Supplier State",        key: "supplier_state" },
    { label: "Supplier State Code",   key: "supplier_state_code" },
    { label: "Supplier Phone",        key: "supplier_phone" },
    { label: "Supplier Email",        key: "supplier_email" },
    { label: "Supplier Bank Name",    key: "bank_name" },
    { label: "Supplier Bank A/c",     key: "bank_account" },
    { label: "Supplier IFSC",         key: "ifsc_code" },

    { label: "Recipient / Buyer",     key: "customer" },
    { label: "Recipient GSTIN",       key: "customer_gstin" },
    { label: "Recipient Address",     key: "customer_address" },
    { label: "Pincode",               key: "pincode" },
    { label: "Addhar No.",            key: "addhar_number" },
    { label: "Mobile No.",            key: "mobile_number" },

    { label: "Purchase Order No.",    key: "po_number" },
    { label: "PO Date",               key: "po_date" },
    { label: "Goods Receipt No.",     key: "grn_number" },
    { label: "Delivery Challan No.",  key: "delivery_challan" },
    { label: "Payment Terms",         key: "payment_terms" },
    { label: "Payment Method",        key: "payment_method" },
    { label: "Payment Reference",     key: "payment_reference" },
    { label: "UTR / Transfer ID",     key: "utr_number" },
    { label: "Remarks / Narration",   key: "remarks" },

    { label: "Product / Particulars", key: "item_description" },
    { label: "Product Company",       key: "product_company" },
    { label: "HSN / SAC Code",        key: "hsn" },
    { label: "Batch No.",             key: "batch_number" },
    { label: "Expiry Date",           key: "expiry_date" },
    { label: "Quantity",              key: "quantity" },
    { label: "Rate Per Unit",         key: "rate" },
    { label: "Discount %",            key: "discount_percent" },
    { label: "GST %",                 key: "gst_percent" },
    { label: "Assessable Amount",     key: "ass_amount" },

    { label: "Total Taxable Value",   key: "taxable_amount" },
    { label: "CGST",                  key: "cgst" },
    { label: "SGST",                  key: "sgst" },
    { label: "IGST",                  key: "igst" },
    { label: "CESS",                  key: "cess" },
    { label: "CGST Rate",             key: "cgst_rate" },
    { label: "SGST Rate",             key: "sgst_rate" },
    { label: "IGST Rate",             key: "igst_rate" },
    { label: "CESS Rate",             key: "cess_rate" },
    { label: "Discount Amount",       key: "discount" },
    { label: "Freight / Cartage",     key: "freight" },
    { label: "Packing / Forwarding",  key: "packing_charges" },
    { label: "Round Off",             key: "round_off" },
    { label: "Grand Total (Payable)", key: "amount" },
    { label: "Total in Words",        key: "amount_in_words" },
  ],


  /* —— Credit / Debit Note —— */
  credit_note: [
    { label: "Credit Note No.",      key: "credit_note_number" },
    { label: "Credit Note Number",   key: "notice_number" },
    { label: "Credit Note Date",     key: "credit_note_date" },
    { label: "Document Date",        key: "invoice_date" },
    { label: "Posting Date",         key: "posting_date" },

    { label: "Original Invoice No.", key: "invoice_number" },
    { label: "Original Invoice Date", key: "original_invoice_date" },
    { label: "Document Type",        key: "invoice_type" },

    { label: "Supplier / Vendor",    key: "vendor" },
    { label: "Customer / Buyer",     key: "customer" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Customer GSTIN",       key: "customer_gstin" },
    { label: "Supplier GSTIN",       key: "supplier_gstin" },

    { label: "Reason for Credit",    key: "reason" },
    { label: "Nature / Remarks",     key: "remarks" },

    { label: "HSN / SAC (Summary)",  key: "hsn" },
    { label: "Taxable Value (Cr.)",  key: "taxable_amount" },
    { label: "CGST (Cr.)",           key: "cgst" },
    { label: "SGST (Cr.)",           key: "sgst" },
    { label: "IGST (Cr.)",           key: "igst" },
    { label: "CESS (Cr.)",           key: "cess" },
    { label: "Total Credit Amount",  key: "amount" },
  ],

  debit_note: [
    { label: "Debit Note No.",       key: "debit_note_number" },
    { label: "Debit Note Number",    key: "notice_number" },
    { label: "Debit Note Date",      key: "debit_note_date" },
    { label: "Document Date",        key: "invoice_date" },
    { label: "Posting Date",         key: "posting_date" },

    { label: "Original Invoice No.", key: "invoice_number" },
    { label: "Original Invoice Date", key: "original_invoice_date" },
    { label: "Document Type",        key: "invoice_type" },

    { label: "Supplier / Vendor",    key: "vendor" },
    { label: "Customer / Buyer",     key: "customer" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Supplier GSTIN",       key: "supplier_gstin" },
    { label: "Customer GSTIN",       key: "customer_gstin" },

    { label: "Reason for Debit",     key: "reason" },
    { label: "Nature / Remarks",     key: "remarks" },

    { label: "HSN / SAC (Summary)",  key: "hsn" },
    { label: "Taxable Value (Dr.)",  key: "taxable_amount" },
    { label: "CGST (Dr.)",           key: "cgst" },
    { label: "SGST (Dr.)",           key: "sgst" },
    { label: "IGST (Dr.)",           key: "igst" },
    { label: "CESS (Dr.)",           key: "cess" },
    { label: "Total Debit Amount",   key: "amount" },
  ],

  /* —— GST Returns —— */
  gst_return: [
    { label: "GST Return",           key: "gst_return_type" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Legal Name",           key: "vendor" },
    { label: "PAN",                  key: "pan_number" },
    { label: "Financial Year",       key: "financial_year" },
    { label: "Return Period / Month", key: "month" },
    { label: "Quarter",              key: "quarter" },
    { label: "Date of Filing",       key: "filed_date" },
    { label: "Due Date of Filing",   key: "due_date" },
    { label: "ARN (Acknowledgement)", key: "arn" },
    { label: "Status",               key: "status" },
    { label: "Mode of Filing",       key: "filing_mode" },

    { label: "Aggregate Turnover (PY)", key: "turnover_previous" },
    { label: "Taxable Turnover",     key: "taxable_amount" },
    { label: "Exempted / Nil Rated", key: "exempted_turnover" },
    { label: "Export Turnover",      key: "export_turnover" },
    { label: "Deemed Export",        key: "deemed_export_turnover" },

    { label: "Outward Taxable Supplies", key: "outward_supplies" },
    { label: "RCM Supplies",         key: "rcm_supplies" },
    { label: "Total ITC Claimed",    key: "input_credit" },
    { label: "ITC Reversed",         key: "itc_reversed" },
    { label: "Net ITC Available",    key: "net_itc" },

    { label: "CGST Payable",         key: "cgst_payable" },
    { label: "SGST Payable",         key: "sgst_payable" },
    { label: "IGST Payable",         key: "igst_payable" },
    { label: "CESS Payable",         key: "cess_payable" },
    { label: "CGST Paid via Cash",   key: "cgst_cash" },
    { label: "SGST Paid via Cash",   key: "sgst_cash" },
    { label: "IGST Paid via Cash",   key: "igst_cash" },
    { label: "CESS Paid via Cash",   key: "cess_cash" },
    { label: "CGST Paid via ITC",    key: "cgst_itc" },
    { label: "SGST Paid via ITC",    key: "sgst_itc" },
    { label: "IGST Paid via ITC",    key: "igst_itc" },
    { label: "Interest Paid",        key: "interest" },
    { label: "Late Fee / Penalty",   key: "late_fee" },
    { label: "Total Tax Paid",       key: "amount" },
    { label: "Challan CINs Linked",  key: "linked_challans" },
    { label: "Remarks",              key: "remarks" },
  ],

  /* —— GST Notice —— */
  gst_notice: [
    { label: "Notice / Order No.",   key: "notice_number" },
    { label: "Reference No.",        key: "reference_number" },
    { label: "Notice Date",          key: "notice_date" },
    { label: "Issue Date",           key: "invoice_date" },
    { label: "Response Due Date",    key: "response_due_date" },
    { label: "Adjudication Date",    key: "adjudication_date" },
    { label: "Period of Dispute",    key: "period" },
    { label: "Financial Year",       key: "financial_year" },
    { label: "Assessment Year",      key: "assessment_year" },
    { label: "Priority",             key: "priority" },
    { label: "Status",               key: "status" },

    { label: "GSTIN",                key: "gstin" },
    { label: "PAN",                  key: "pan_number" },
    { label: "Legal Name (Taxpayer)", key: "vendor" },
    { label: "Trade Name",           key: "trade_name" },
    { label: "Principal Address",    key: "principal_address" },

    { label: "Issuing Authority",    key: "customer" },
    { label: "Range / Division",     key: "range_division" },
    { label: "Commissionerate",      key: "commissionerate" },
    { label: "Officer Name",         key: "officer_name" },
    { label: "Officer Designation",  key: "officer_designation" },

    { label: "Notice Act / Section", key: "act_section" },
    { label: "Subject / Short Code", key: "subject" },
    { label: "Type of Notice",       key: "notice_type" },
    { label: "Demand Amount (Tax)",  key: "demand_tax" },
    { label: "Demand Interest",      key: "demand_interest" },
    { label: "Demand Penalty",       key: "demand_penalty" },
    { label: "Other Dues",           key: "demand_other" },
    { label: "Total Demand Amount",  key: "amount" },
    { label: "Remarks / Summary",    key: "remarks" },
    { label: "Suggested Next Action", key: "next_action" },
  ],

  /* —— E-Invoice —— */
  e_invoice: [
    { label: "Invoice Number",         key: "invoice_number" },
    { label: "Invoice Date",           key: "invoice_date" },
    { label: "Posting Date",           key: "posting_date" },

    { label: "IRN Hash (64-char)",     key: "irn_hash" },
    { label: "Acknowledgement No.",    key: "acknowledgement_number" },
    { label: "Acknowledgement Date",   key: "acknowledgement_date" },
    { label: "Valid Upto",             key: "valid_upto" },

    { label: "Original Doc No.",       key: "doc_number" },
    { label: "Document Type",          key: "invoice_type" },
    { label: "Place of Supply",        key: "place_of_supply" },
    { label: "Reverse Charge (RCM)",   key: "reverse_charge" },

    { label: "Supplier Name",          key: "vendor" },
    { label: "Supplier GSTIN",         key: "supplier_gstin" },
    { label: "Supplier PAN",           key: "supplier_pan" },
    { label: "Supplier Address",       key: "supplier_address" },
    { label: "Supplier State Code",    key: "supplier_state_code" },
    { label: "Supplier State",         key: "supplier_state" },

    { label: "Recipient Name",         key: "customer" },
    { label: "Recipient GSTIN",        key: "customer_gstin" },
    { label: "Recipient PAN",          key: "customer_pan" },
    { label: "Recipient Address",      key: "customer_address" },
    { label: "Recipient State Code",   key: "customer_state_code" },
    { label: "Recipient State",        key: "customer_state" },

    { label: "Dispatch From",          key: "dispatch_from" },
    { label: "Ship To",                key: "ship_to" },
    { label: "Billing Address",        key: "billing_address" },
    { label: "Shipping Address",       key: "shipping_address" },

    { label: "Supplier Invoice No.",   key: "supplier_invoice_number" },
    { label: "PO Number",              key: "po_number" },
    { label: "PO Date",                key: "po_date" },
    { label: "E-Way Bill No.",         key: "eway_bill_number" },
    { label: "Vehicle No.",            key: "vehicle_number" },
    { label: "Mode of Transport",      key: "transport_mode" },

    { label: "Bank Name",              key: "bank_name" },
    { label: "Bank A/C No.",           key: "bank_account" },
    { label: "IFSC Code",              key: "ifsc_code" },
    { label: "Payment Terms",          key: "payment_terms" },
    { label: "Due Date",               key: "due_date" },
    { label: "Payment Method",         key: "payment_method" },
    { label: "UTR / Payment Ref",      key: "utr_number" },

    { label: "HSN / SAC (Summary)",    key: "hsn" },
    { label: "GST Rate",               key: "gst_rate" },
    { label: "CGST Rate",              key: "cgst_rate" },
    { label: "SGST Rate",              key: "sgst_rate" },
    { label: "IGST Rate",              key: "igst_rate" },

    { label: "Total Taxable Value",    key: "taxable_amount" },
    { label: "CGST",                   key: "cgst" },
    { label: "SGST",                   key: "sgst" },
    { label: "IGST",                   key: "igst" },
    { label: "CESS",                   key: "cess" },
    { label: "Total Tax",              key: "total_tax" },
    { label: "Discount",               key: "discount" },
    { label: "Freight / Shipping",     key: "freight" },
    { label: "Packing Charges",        key: "packing_charges" },
    { label: "Round Off",              key: "round_off" },
    { label: "Other Charges",          key: "other_charges" },
    { label: "Grand Total",            key: "amount" },
    { label: "Amount in Words",        key: "amount_in_words" },

    { label: "QR Code (Base64)",       key: "qr_code" },
    { label: "Signed QR (if any)",     key: "signed_qr" },

    { label: "Remarks",                key: "remarks" },
  ],

  /* —— E-Way Bill —— */
  e_way_bill: [
    { label: "E-Way Bill No.",       key: "invoice_number" },
    { label: "EWB Number",           key: "eway_bill_number" },
    { label: "Generated Date & Time", key: "invoice_date" },
    { label: "Valid Upto",           key: "valid_upto" },
    { label: "Expiry Date",          key: "eway_expiry" },
    { label: "Mode of Transport",    key: "transport_mode" },
    { label: "Transporter Document No.", key: "transporter_doc_no" },
    { label: "Document Type",        key: "invoice_type" },
    { label: "Original Invoice No.", key: "supplier_invoice_number" },
    { label: "Original Invoice Date", key: "original_invoice_date" },

    { label: "GSTIN",                key: "gstin" },
    { label: "Supplier Name",        key: "vendor" },
    { label: "Supplier GSTIN",       key: "supplier_gstin" },
    { label: "Supplier Address",     key: "supplier_address" },
    { label: "Supplier State",       key: "supplier_state" },
    { label: "Supplier Pincode",     key: "supplier_pincode" },

    { label: "Recipient Name",       key: "customer" },
    { label: "Recipient GSTIN",      key: "customer_gstin" },
    { label: "Recipient Address",    key: "customer_address" },
    { label: "Recipient State",      key: "customer_state" },
    { label: "Recipient Pincode",    key: "recipient_pincode" },

    { label: "Dispatch From",        key: "dispatch_from" },
    { label: "Ship To Address",      key: "shipping_address" },
    { label: "From State",           key: "from_state" },
    { label: "To State",             key: "to_state" },

    { label: "Distance (Km)",        key: "distance_km" },
    { label: "Vehicle No.",          key: "vehicle_number" },
    { label: "Vehicle Type",         key: "vehicle_type" },
    { label: "Transporter ID (GSTIN)", key: "transporter_id" },
    { label: "Transporter Name",     key: "transporter_name" },

    { label: "HSN (Summary)",        key: "hsn" },
    { label: "Taxable Value",        key: "taxable_amount" },
    { label: "CGST",                 key: "cgst" },
    { label: "SGST",                 key: "sgst" },
    { label: "IGST",                 key: "igst" },
    { label: "CESS",                 key: "cess" },
    { label: "Total Consignment Value", key: "amount" },
    { label: "Status",               key: "status" },
    { label: "Cancellation Date",    key: "cancelled_date" },
    { label: "Remarks",              key: "remarks" },
  ],

  /* —— GST Payment Challan —— */
  gst_challan: [
    { label: "CPIN",                 key: "cpin" },
    { label: "CIN",                  key: "cin" },
    { label: "Challan / Reference No.", key: "invoice_number" },
    { label: "Challan Serial No.",   key: "challan_serial" },
    { label: "Status",               key: "status" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Legal Name",           key: "vendor" },
    { label: "PAN",                  key: "pan_number" },
    { label: "Trade Name",           key: "trade_name" },
    { label: "Taxpayer Email",       key: "email" },
    { label: "Taxpayer Mobile",      key: "phone" },
    { label: "Taxpayer Address",     key: "address" },
    { label: "State",                key: "state" },
    { label: "State Code",           key: "state_code" },

    { label: "Payment Mode",         key: "payment_method" },
    { label: "Bank Name",            key: "bank_name" },
    { label: "Bank Code / BSR",      key: "bsr_code" },
    { label: "Challan Date",         key: "challan_date" },
    { label: "Challan Expiry Date",  key: "expiry_date" },
    { label: "Date of Payment",      key: "invoice_date" },
    { label: "Date of Receipt by Bank", key: "date_of_receipt" },
    { label: "Posting Date",         key: "posting_date" },

    { label: "Tax Period / Month",   key: "month" },
    { label: "Quarter",              key: "quarter" },
    { label: "Financial Year",       key: "financial_year" },
    { label: "Return / Major Head",  key: "gst_return_type" },
    { label: "Reason for Challan",   key: "purpose" },

    { label: "CGST - Tax",           key: "cgst_tax" },
    { label: "CGST - Interest",      key: "cgst_interest" },
    { label: "CGST - Penalty",       key: "cgst_penalty" },
    { label: "CGST - Fees",          key: "cgst_fee" },
    { label: "CGST - Others",        key: "cgst_others" },
    { label: "Total CGST",           key: "cgst" },

    { label: "SGST - Tax",           key: "sgst_tax" },
    { label: "SGST - Interest",      key: "sgst_interest" },
    { label: "SGST - Penalty",       key: "sgst_penalty" },
    { label: "SGST - Fees",          key: "sgst_fee" },
    { label: "SGST - Others",        key: "sgst_others" },
    { label: "Total SGST",           key: "sgst" },

    { label: "IGST - Tax",           key: "igst_tax" },
    { label: "IGST - Interest",      key: "igst_interest" },
    { label: "IGST - Penalty",       key: "igst_penalty" },
    { label: "IGST - Fees",          key: "igst_fee" },
    { label: "IGST - Others",        key: "igst_others" },
    { label: "Total IGST",           key: "igst" },

    { label: "CESS - Tax",           key: "cess_tax" },
    { label: "CESS - Interest",      key: "cess_interest" },
    { label: "CESS - Penalty",       key: "cess_penalty" },
    { label: "CESS - Others",        key: "cess_others" },
    { label: "Total CESS",           key: "cess" },

    { label: "Total Tax Head",       key: "taxable_amount" },
    { label: "Grand Total Paid",     key: "amount" },
    { label: "Amount in Words",      key: "amount_in_words" },
    { label: "UTR / Bank Reference", key: "utr_number" },
    { label: "Remarks",              key: "remarks" },
  ],

  /* —— HSN / SAC / Document List (fallbacks) —— */
  hsn_sac: [
    { label: "Document Title",       key: "vendor" },
    { label: "Primary HSN / SAC",    key: "hsn" },
    { label: "HSN Description",      key: "hsn_description" },
    { label: "Taxable Value",        key: "taxable_amount" },
    { label: "GST Rate (Avg)",       key: "gst_rate" },
    { label: "Total Amount",         key: "amount" },
    { label: "Financial Year",       key: "financial_year" },
    { label: "Period",               key: "month" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Remarks",              key: "remarks" },
  ],

  document_list: [
    { label: "Document Title",       key: "vendor" },
    { label: "Reference No.",        key: "invoice_number" },
    { label: "Person / Entity Name", key: "customer" },
    { label: "Uploaded By",          key: "uploaded_by" },
    { label: "Date",                 key: "invoice_date" },
    { label: "GSTIN",                key: "gstin" },
    { label: "Subject / Details",    key: "subject" },
    { label: "Total Amount",         key: "amount" },
    { label: "Status",               key: "status" },
    { label: "Remarks",              key: "remarks" },
  ],
};

function schemaFor(category: string): FieldDef[] {
  if (CATEGORY_FIELD_SCHEMA[category]) return CATEGORY_FIELD_SCHEMA[category];
  const base: FieldDef[] = [];
  for (const k of CORE_KEYS) base.push({ label: humanize(k), key: k });
  return base;
}

/* ── Field Row ─────────────────────────────────────────────────── */

const FieldRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="space-y-1.5">
    <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
    <div className="text-sm break-words font-medium leading-snug">
      {isEmpty(value) ? (
        <span className="font-normal text-muted-foreground/70 italic">—</span>
      ) : (
        value
      )}
    </div>
  </div>
);

/* ── Main Component ────────────────────────────────────────────── */

export function DocumentDetailModal({
  open,
  onOpenChange,
  docId,
  onUpdate,
  onNavigateTab,
  onViewVoucher,
  allDocs,
}: Props) {
  const [doc, setDoc]           = useState<AnyDoc | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError]     = useState<string | null>(null);

  const [blobUrl, setBlobUrl]   = useState<string | null>(null);
  const [prevLoading, setPrevLoading] = useState(false);
  const [prevError, setPrevError]     = useState<string | null>(null);

  // ── Accounting Draft State ──
  const [draftRecord, setDraftRecord] = useState<AnyDoc | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [verifying, setVerifying]     = useState(false);
  const [posting, setPosting]         = useState(false);

  // ── Category Routing & Contextual Action States ──
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [selectedInvoiceToLink, setSelectedInvoiceToLink] = useState<string>("");
  const [linkingInvoice, setLinkingInvoice] = useState(false);

  const [noticeModalOpen, setNoticeModalOpen] = useState(false);
  const [noticeStatus, setNoticeStatus] = useState<string>("Under Review");
  const [updatingNotice, setUpdatingNotice] = useState(false);

  const fetchDraft = async () => {
    if (!docId) return;
    try {
      setDraftLoading(true);
      const res = await fetch(`${BASE_URL}/accounting/drafts?document_id=${docId}&status=`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const body = await res.json();
        if (body?.data && Array.isArray(body.data) && body.data.length > 0) {
          setDraftRecord(body.data[0]);
        } else {
          setDraftRecord(null);
        }
      }
    } catch (e) {
      console.error("Failed to load draft:", e);
    } finally {
      setDraftLoading(false);
    }
  };

  /* — Fetch document details & draft — */
  useEffect(() => {
    if (!open || !docId) {
      setDraftRecord(null);
      return;
    }
    fetchDraft();
  }, [open, docId]);

  /* — Fetch document details — */
  useEffect(() => {
    if (!open || !docId) return;
    setDoc(null);
    setDocError(null);
    setDocLoading(true);

    let cancelled = false;
    fetch(`${BASE_URL}/invoices/document/${docId}`, { headers: authHeaders() })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const body = await res.json();
        if (!cancelled) setDoc(body?.data ?? body ?? null);
      })
      .catch((e) => { if (!cancelled) setDocError(e.message ?? "Failed to load document"); })
      .finally(() => { if (!cancelled) setDocLoading(false); });

    return () => { cancelled = true; };
  }, [open, docId]);

  /* — Fetch file blob for preview — */
  useEffect(() => {
    if (!open || !docId) return;
    if (blobUrl) { try { URL.revokeObjectURL(blobUrl); } catch { /* ignore */ } }
    setBlobUrl(null);
    setPrevError(null);

    const hasFile = Boolean(doc?.file_path || doc?.file_name);
    if (!hasFile) return;

    const ext = String(doc?.file_type ?? (doc?.file_name ?? "").split(".").pop() ?? "").toLowerCase();
    const canPreview = IMAGE_EXTS.has(ext) || PDF_EXTS.has(ext);
    if (!canPreview) return;

    setPrevLoading(true);
    let cancelled = false;
    let localUrl: string | null = null;

    fetch(`${BASE_URL}/invoices/document/${docId}/download`, { headers: authHeaders() })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const blob = await res.blob();
        localUrl = URL.createObjectURL(blob);
        if (!cancelled) setBlobUrl(localUrl);
      })
      .catch((e) => { if (!cancelled) setPrevError(e.message ?? "Preview unavailable"); })
      .finally(() => { if (!cancelled) setPrevLoading(false); });

    return () => {
      cancelled = true;
      if (localUrl) { try { URL.revokeObjectURL(localUrl); } catch { /* ignore */ } setBlobUrl(null); }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, docId, doc?.file_type, doc?.file_name, doc?.file_path]);

  /* — Revoke blob on unmount / new blobUrl — */
  useEffect(() => {
    return () => { if (blobUrl) { try { URL.revokeObjectURL(blobUrl); } catch { /* ignore */ } } };
  }, [blobUrl]);

  /* — Derived — */

  const category: DocumentCategory | undefined = useMemo(
    () => DOCUMENT_CATEGORIES.find((c) => c.id === doc?.document_category),
    [doc?.document_category]
  );

  const routing = useMemo(
    () => getCategoryRouting(String(doc?.document_category ?? "")),
    [doc?.document_category]
  );

  const commercialInvoices = useMemo(() => {
    return (allDocs || []).filter(
      (d) =>
        d.id !== docId &&
        ["sales_records", "purchase_records", "b2b_invoice", "b2c_invoice"].includes(
          d.document_category
        )
    );
  }, [allDocs, docId]);

  const linkedInvoiceNumber = useMemo(() => {
    return (
      doc?.metadata_?.linked_invoice_number ??
      doc?.metadata?.linked_invoice_number ??
      null
    );
  }, [doc]);

  const meta = useMemo(() => parseMeta(doc?.metadata_ ?? doc?.metadata ?? null), [doc]);

  const schema = useMemo(
    () => schemaFor(String(doc?.document_category ?? "")),
    [doc?.document_category]
  );

  /**
   * Resolve a canonical (schema) field by probing:
   *   1. `doc.<canonicalKey>`                      (top-level DB column, highest priority)
   *   2. `doc.<alias>`                              (DB column for any alias)
   *   3. `meta.fields.<canonicalKey>`               (OCR parser output in metadata JSON)
   *   4. `meta.fields.<alias>` ... each alias in order
   *
   * Returns the FIRST non-empty hit. This is critical because different
   * backend parsers / Gemini fallbacks store data under DIFFERENT keys
   * (e.g. "irn" vs "irn_hash", "total" vs "amount", "supplier" vs "vendor",
   * "ack_number" vs "acknowledgement_number", "from_gstin" vs "supplier_gstin").
   *
   * See FIELD_ALIASES near the top of this file for the full catalogue of
   * ~350 synonyms gathered from every backend parser & the Gemini schema.
   */
  const resolve = (key: string): unknown => {
    if (!doc) return null;
    const aliases = (FIELD_ALIASES[key] ?? []) as readonly string[];

    /* 1 & 2 — Top-level DB columns: canonical first, then each alias */
    const direct = (doc as Record<string, unknown>)[key];
    if (!isEmpty(direct)) return direct;
    for (const alias of aliases) {
      const v = (doc as Record<string, unknown>)[alias];
      if (!isEmpty(v)) return v;
    }

    /* 3 & 4 — metadata.fields JSON blob (OCR output): canonical then aliases */
    const fields = (meta.fields ?? {}) as Record<string, unknown>;
    const fromFields = fields[key];
    if (!isEmpty(fromFields)) return fromFields;
    for (const alias of aliases) {
      const v = fields[alias];
      if (!isEmpty(v)) return v;
    }
    return null;
  };

  /** Standard fields rendered via schema.
   *  Two fields with the SAME key are de-duplicated naturally because
   *  only the first non-empty value is rendered; we also avoid rendering
   *  a key twice on the SAME label to prevent the "CPIN/CIN & CIN dup".
   */
  const standardFields = useMemo(() => {
    const seenKeys   = new Set<string>();
    const seenLabels = new Set<string>();
    const out: Array<{ label: string; key: string; value: string }> = [];

    for (const f of schema) {
      const key = String(f.key);
      if (seenKeys.has(key)) continue;
      const raw = resolve(key);
      if (isEmpty(raw)) continue;

      const label = f.label;
      const normLabel = label.toLowerCase().replace(/[^a-z0-9]/g, "");
      if (seenLabels.has(normLabel)) continue;

      seenKeys.add(key);
      seenLabels.add(normLabel);
      out.push({ label, key, value: formatValue(raw, key) });
    }
    return out;
  }, [schema, doc, meta]);

  /** Additional fields: keys in meta.fields NOT already rendered via schema */
  const additionalFields = useMemo(() => {
    const fields = (meta.fields ?? {}) as Record<string, unknown>;
    const schemaKeys = new Set(schema.map((s) => String(s.key)));
    const out: Array<{ label: string; key: string; value: string }> = [];
    for (const [k, v] of Object.entries(fields)) {
      if (schemaKeys.has(k)) continue;
      if (CORE_KEYS.has(k)) continue;
      if (k === "line_items" || k === "line_item_headers" || k === "table_data") continue;
      if (k === "ocr_confidence" || k === "field_verification" || k === "extraction_method") continue;
      if (isEmpty(v)) continue;
      out.push({ label: humanize(k), key: k, value: formatValue(v, k) });
    }
    return out;
  }, [meta, schema]);

  /* — Editing State — */
  const [isEditing, setIsEditing] = useState(false);
  const [editFields, setEditFields] = useState<Array<{ key: string; label: string; value: string; isCustom?: boolean }>>([]);
  const [saving, setSaving] = useState(false);
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customFieldLabel, setCustomFieldLabel] = useState("");
  const [customFieldValue, setCustomFieldValue] = useState("");

  // Reset edit state when modal closes
  useEffect(() => {
    if (!open) {
      setIsEditing(false);
      setShowCustomInput(false);
      setCustomFieldLabel("");
      setCustomFieldValue("");
    }
  }, [open]);

  const handleStartEditing = () => {
    const initial: Array<{ key: string; label: string; value: string; isCustom?: boolean }> = [];
    const seen = new Set<string>();

    for (const sf of standardFields) {
      const raw = resolve(sf.key);
      initial.push({
        key: sf.key,
        label: sf.label,
        value: raw !== null && raw !== undefined ? String(raw) : sf.value,
        isCustom: false,
      });
      seen.add(sf.key.toLowerCase());
    }

    for (const af of additionalFields) {
      if (!seen.has(af.key.toLowerCase())) {
        const raw = (meta.fields ?? {})[af.key];
        initial.push({
          key: af.key,
          label: af.label,
          value: raw !== null && raw !== undefined ? String(raw) : af.value,
          isCustom: true,
        });
        seen.add(af.key.toLowerCase());
      }
    }

    setEditFields(initial);
    setShowCustomInput(false);
    setCustomFieldLabel("");
    setCustomFieldValue("");
    setIsEditing(true);
  };

  const handleCancelEditing = () => {
    setIsEditing(false);
    setShowCustomInput(false);
    setCustomFieldLabel("");
    setCustomFieldValue("");
  };

  const handleFieldChange = (index: number, val: string) => {
    setEditFields((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], value: val };
      return copy;
    });
  };

  const handleRemoveField = (index: number) => {
    setEditFields((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddField = (key: string, label: string) => {
    setEditFields((prev) => {
      if (prev.some((f) => f.key.toLowerCase() === key.toLowerCase())) return prev;
      return [...prev, { key, label, value: "", isCustom: false }];
    });
  };

  const handleAddCustomField = () => {
    const trimmedLabel = customFieldLabel.trim();
    if (!trimmedLabel) return;
    const generatedKey = trimmedLabel.toLowerCase().replace(/[^a-z0-9]/g, "_");
    setEditFields((prev) => [
      ...prev,
      {
        key: generatedKey,
        label: trimmedLabel,
        value: customFieldValue.trim(),
        isCustom: true,
      },
    ]);
    setCustomFieldLabel("");
    setCustomFieldValue("");
    setShowCustomInput(false);
  };

  const handleSaveEditing = async () => {
    if (!docId) return;
    setSaving(true);
    try {
      const payload: Record<string, string> = {};
      // Mark all previously present keys as cleared
      for (const sf of standardFields) {
        payload[sf.key] = "";
      }
      for (const af of additionalFields) {
        payload[af.key] = "";
      }
      // Populate new/updated field values
      for (const ef of editFields) {
        payload[ef.key] = ef.value.trim();
      }

      const res = await fetch(`${BASE_URL}/invoices/document/${docId}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ fields: payload }),
      });

      const body = await res.json();
      if (!res.ok) {
        throw new Error(body?.detail || body?.message || `Server returned ${res.status}`);
      }

      if (body?.data) {
        setDoc(body.data);
      }
      setIsEditing(false);
      toast.success("Document fields updated successfully", {
        description: "All changes have been saved and applied to calculations.",
      });

      // If document is verified, re-sync accounting draft to reflect updated fields
      if (doc?.status === "verified" && !INFORMATIONAL_CATEGORIES.has(doc?.document_category)) {
        try {
          const draftRes = await fetch(`${BASE_URL}/accounting/drafts/generate/${docId}`, {
            method: "POST",
            headers: authHeaders(),
          });
          const draftBody = await draftRes.json();
          if (draftBody?.data?.record) {
            setDraftRecord(draftBody.data.record);
          }
        } catch {
          // non-blocking
        }
      }

      onUpdate?.();
    } catch (e: any) {
      toast.error("Failed to save changes", {
        description: e.message || "An unexpected error occurred while saving.",
      });
    } finally {
      setSaving(false);
    }
  };

  /* — Verify Document & Prepare Accounting Draft — */
  const handleVerify = async () => {
    if (!docId || !doc) return;
    setVerifying(true);
    try {
      // 1. Mark document as verified
      const patchRes = await fetch(`${BASE_URL}/invoices/document/${docId}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ status: "verified" }),
      });
      const patchBody = await patchRes.json();
      if (!patchRes.ok) {
        throw new Error(patchBody?.detail || patchBody?.message || "Failed to verify document");
      }

      if (patchBody?.data) {
        setDoc(patchBody.data);
      } else {
        setDoc((prev: any) => prev ? { ...prev, status: "verified" } : null);
      }

      const isInfo = INFORMATIONAL_CATEGORIES.has(doc.document_category);

      if (!isInfo) {
        // 2. Generate or update accounting draft
        const draftRes = await fetch(`${BASE_URL}/accounting/drafts/generate/${docId}`, {
          method: "POST",
          headers: authHeaders(),
        });
        const draftBody = await draftRes.json();
        if (!draftRes.ok) {
          throw new Error(draftBody?.detail || draftBody?.message || "Failed to generate accounting draft");
        }

        if (draftBody?.data?.record) {
          setDraftRecord(draftBody.data.record);
        } else {
          await fetchDraft();
        }

        toast.success("Document Verified & Draft Created", {
          description: "Accounting draft generated and ready for review in the ledger.",
        });
      } else {
        toast.success("Document Verified", {
          description: "Informational document marked as verified.",
        });
      }

      onUpdate?.();
    } catch (e: any) {
      toast.error("Verification failed", {
        description: e.message || "An unexpected error occurred during verification.",
      });
    } finally {
      setVerifying(false);
    }
  };

  /* — Explicitly Post Draft to Ledger — */
  const handlePostToLedger = async () => {
    if (!draftRecord?.id) return;
    setPosting(true);
    try {
      const postRes = await fetch(`${BASE_URL}/accounting/drafts/${draftRecord.id}/post`, {
        method: "POST",
        headers: authHeaders(),
      });
      const postBody = await postRes.json();
      if (!postRes.ok) {
        throw new Error(postBody?.detail || postBody?.message || "Failed to post draft to ledger");
      }

      if (postBody?.data?.record) {
        setDraftRecord(postBody.data.record);
      } else {
        await fetchDraft();
      }

      toast.success("Posted to Ledger", {
        description: "Accounting transaction has been permanently committed to ledger.",
      });
      onUpdate?.();
    } catch (e: any) {
      toast.error("Failed to post to ledger", {
        description: e.message || "An unexpected error occurred.",
      });
    } finally {
      setPosting(false);
    }
  };

  /* — Explicitly Create Draft (if verified but draft not yet generated) — */
  const handleCreateDraft = async () => {
    if (!docId) return;
    setDraftLoading(true);
    try {
      const draftRes = await fetch(`${BASE_URL}/accounting/drafts/generate/${docId}`, {
        method: "POST",
        headers: authHeaders(),
      });
      const draftBody = await draftRes.json();
      if (!draftRes.ok) {
        throw new Error(draftBody?.detail || draftBody?.message || "Failed to generate accounting draft");
      }

      if (draftBody?.data?.record) {
        setDraftRecord(draftBody.data.record);
      } else {
        await fetchDraft();
      }

      const draftTypeLabel =
        routing.accountingDraft === "adjustment"
          ? "Adjustment Draft"
          : routing.accountingDraft === "payment"
          ? "Payment Draft"
          : "Accounting Draft";

      toast.success(`${draftTypeLabel} Created`, {
        description: `${draftTypeLabel} ready for review in the ledger.`,
      });
      onUpdate?.();
    } catch (e: any) {
      toast.error("Failed to generate draft", {
        description: e.message || "An unexpected error occurred.",
      });
    } finally {
      setDraftLoading(false);
    }
  };

  /* — Contextual Navigation & Linking Handlers — */
  const handleViewLinkedTransaction = () => {
    onOpenChange(false);
    if (draftRecord?.id) {
      onViewVoucher?.(draftRecord.id);
    } else {
      onNavigateTab?.("accounting");
    }
  };

  const handleOpenGstWorkspace = () => {
    onOpenChange(false);
    onNavigateTab?.("gsttax");
    toast.success("Navigated to GST Returns & Filing workspace");
  };

  const handleManageReferenceData = () => {
    onOpenChange(false);
    onNavigateTab?.("gsttax");
    toast.success("Navigated to HSN / SAC Reference Data");
  };

  const handleLinkInvoice = async () => {
    if (!docId || !selectedInvoiceToLink) return;
    setLinkingInvoice(true);
    try {
      const parentInv = (allDocs || []).find((d) => d.id === selectedInvoiceToLink);
      const invNumber = parentInv?.invoice_number || `DOC-${selectedInvoiceToLink.slice(0, 8)}`;
      
      const currentMeta = parseMeta(doc?.metadata_ ?? doc?.metadata ?? null);
      const updatedMeta = {
        ...currentMeta,
        linked_invoice_id: selectedInvoiceToLink,
        linked_invoice_number: invNumber,
        linked_at: new Date().toISOString(),
      };

      const res = await fetch(`${BASE_URL}/invoices/document/${docId}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ metadata: updatedMeta }),
      });
      if (!res.ok) throw new Error("Failed to link document to invoice");

      setDoc((prev: any) =>
        prev
          ? {
              ...prev,
              metadata_: updatedMeta,
              metadata: updatedMeta,
            }
          : null
      );
      toast.success("Document Linked Successfully", {
        description: `Linked ${category?.label ?? "document"} to Invoice #${invNumber}. Duplicate ledger entry prevented.`,
      });
      setLinkModalOpen(false);
      onUpdate?.();
    } catch (e: any) {
      toast.error("Failed to link invoice", { description: e.message });
    } finally {
      setLinkingInvoice(false);
    }
  };

  const handleSaveNoticeStatus = async () => {
    if (!docId) return;
    setUpdatingNotice(true);
    try {
      const currentMeta = parseMeta(doc?.metadata_ ?? doc?.metadata ?? null);
      const updatedMeta = {
        ...currentMeta,
        notice_status: noticeStatus,
        notice_updated_at: new Date().toISOString(),
      };
      const res = await fetch(`${BASE_URL}/invoices/document/${docId}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ metadata: updatedMeta }),
      });
      if (!res.ok) throw new Error("Failed to update notice status");
      setDoc((prev: any) =>
        prev
          ? {
              ...prev,
              metadata_: updatedMeta,
              metadata: updatedMeta,
            }
          : null
      );
      toast.success("Notice Tracking Updated", {
        description: `Statutory notice marked as '${noticeStatus}'.`,
      });
      setNoticeModalOpen(false);
      onUpdate?.();
    } catch (e: any) {
      toast.error("Failed to update notice", { description: e.message });
    } finally {
      setUpdatingNotice(false);
    }
  };

  const availableMissingFields = useMemo(() => {
    const currentKeys = new Set(editFields.map((f) => f.key.toLowerCase()));
    return schema.filter((f) => !currentKeys.has(String(f.key).toLowerCase()));
  }, [schema, editFields]);

  const COMMON_QUICK_FIELDS = useMemo(
    () => new Set([
      "amount", "total_amount", "taxable_amount", "taxable_value",
      "cgst", "sgst", "igst", "cess", "place_of_supply", "state_code",
      "due_date", "po_number", "vehicle_number", "eway_bill_number",
    ]),
    []
  );

  const quickAddFields = useMemo(
    () => availableMissingFields.filter((f) => COMMON_QUICK_FIELDS.has(String(f.key).toLowerCase())),
    [availableMissingFields, COMMON_QUICK_FIELDS]
  );

  const otherMissingFields = useMemo(
    () => availableMissingFields.filter((f) => !COMMON_QUICK_FIELDS.has(String(f.key).toLowerCase())),
    [availableMissingFields, COMMON_QUICK_FIELDS]
  );

  const [extractingItems, setExtractingItems] = useState(false);

  const handleExtractLineItems = async () => {
    if (!docId) return;
    setExtractingItems(true);
    try {
      const res = await fetch(`${BASE_URL}/invoices/document/${docId}/extract-items`, {
        method: "POST",
        headers: authHeaders(),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail ?? "Failed to extract line items");
      if (body?.data) {
        setDoc(body.data);
      }
    } catch (e: any) {
      console.error("Line items extraction failed:", e);
    } finally {
      setExtractingItems(false);
    }
  };

  /** Line items table (from table_data or line_items, root or nested) */
  const lineItems = useMemo<TableModel | null>(() => {
    const metaFields = (meta.fields ?? {}) as Record<string, unknown>;
    const td = meta.table_data ?? (metaFields.table_data as { headers?: string[]; headers_raw?: string[]; rows?: Array<Record<string, unknown>> } | undefined);

    let rawRows: Array<Record<string, unknown>> = [];
    let headerKeys: string[] = [];
    let headerLabels: string[] = [];

    if (td && Array.isArray(td.rows) && td.rows.length > 0) {
      rawRows = td.rows as Array<Record<string, unknown>>;
      headerKeys = Array.isArray(td.headers) ? td.headers : [];
      headerLabels = Array.isArray(td.headers_raw) ? td.headers_raw : [];
    } else {
      const li = (Array.isArray(meta.line_items) && meta.line_items.length > 0 ? meta.line_items : null) ??
                 (Array.isArray(metaFields.line_items) && metaFields.line_items.length > 0 ? (metaFields.line_items as Array<Record<string, unknown>>) : null);
      if (Array.isArray(li) && li.length > 0) {
        rawRows = li as Array<Record<string, unknown>>;
        const lh = meta.line_item_headers ?? (metaFields.line_item_headers as string[] | undefined);
        headerLabels = Array.isArray(lh) ? lh : [];
      }
    }

    if (rawRows.length === 0) return null;

    // Build columns cleanly
    const columns: TableColumn[] = [];
    const seen = new Set<string>();

    if (headerKeys.length > 0) {
      headerKeys.forEach((k, idx) => {
        const label = headerLabels[idx] || CANONICAL_COL_LABELS[k] || humanize(k);
        if (!seen.has(k)) {
          seen.add(k);
          columns.push({ key: k, label });
        }
      });
    } else if (headerLabels.length > 0) {
      headerLabels.forEach((label) => {
        const k = Object.keys(CANONICAL_COL_LABELS).find(ck => CANONICAL_COL_LABELS[ck].toLowerCase() === label.toLowerCase()) 
               || label.toLowerCase().replace(/[^a-z0-9]/g, "_");
        if (!seen.has(label)) {
          seen.add(label);
          columns.push({ key: k, label });
        }
      });
    } else {
      const preferred = [
        "sr_no", "item_name", "company_name", "hsn", "batch_no", "expiry_date",
        "quantity", "rate", "discount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
      ];
      preferred.forEach((k) => {
        if (rawRows.some(r => !isEmpty(r[k]))) {
          seen.add(k);
          columns.push({ key: k, label: CANONICAL_COL_LABELS[k] || humanize(k) });
        }
      });
      const sample = rawRows[0] || {};
      Object.keys(sample).forEach((k) => {
        if (!seen.has(k) && !seen.has(k.toLowerCase())) {
          seen.add(k);
          columns.push({ key: k, label: CANONICAL_COL_LABELS[k] || humanize(k) });
        }
      });
    }

    return { columns, rows: rawRows };
  }, [meta]);

  const hasFile = Boolean(doc?.file_path || doc?.file_name);
  const ext = useMemo(
    () => String(doc?.file_type ?? (doc?.file_name ?? "").split(".").pop() ?? "").toLowerCase(),
    [doc?.file_type, doc?.file_name]
  );
  const isImage = IMAGE_EXTS.has(ext);
  const isPdf   = PDF_EXTS.has(ext);
  const canPreview = hasFile && (isImage || isPdf);

  /* — Actions — */

  const handleDownload = async () => {
    if (!hasFile) {
      toast.info("No file attached", {
        description: "This document record contains extracted field data only.",
      });
      return;
    }
    const fileName = doc?.file_name ?? `document-${docId}`;
    if (blobUrl) {
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      toast.success("Download started", { description: fileName });
      return;
    }
    const token = localStorage.getItem("ca_token");
    const url = `${BASE_URL}/invoices/document/${docId}/download${token ? `?token=${token}` : ""}`;
    try {
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const bUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = bUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(bUrl), 1000);
      toast.success("Download started", { description: fileName });
    } catch (e: any) {
      toast.error("Download failed", {
        description: e?.message?.includes("404")
          ? "The document file was not found on the server."
          : (e?.message || "Could not download document file"),
      });
    }
  };

  const fileName = doc?.file_name ?? "document";
  const fileSize = doc?.file_size;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="!max-w-none !p-0 flex max-h-[94vh] w-[min(1400px,96vw)] flex-col overflow-hidden gap-0 sm:!max-w-none"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => { e.preventDefault(); onOpenChange(false); }}
      >
        {/* ── Header ───────────────────────────────────────── */}
        <DialogHeader className="flex-row items-center justify-between gap-3 border-b border-border bg-card/40 px-6 py-3">
          <DialogTitle className="flex flex-wrap items-center gap-2 text-lg">
            <Eye className="size-4 shrink-0 text-primary" />
            <span className="font-semibold">Document Details</span>
            {category && (
              <Badge variant="outline" className="gap-1 border-primary/30 bg-primary/5 text-xs font-medium text-primary">
                <span>{category.icon}</span>
                <span>{category.label}</span>
              </Badge>
            )}
            {isEditing && (
              <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/30 text-xs font-medium">
                Editing Mode
              </Badge>
            )}
          </DialogTitle>
          <div className="flex shrink-0 items-center gap-2">
            {!isEditing ? (
              <>
                {/* 1. Unverified State: Context-aware verification button */}
                {doc && doc.status !== "verified" && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleVerify}
                    disabled={verifying}
                    className="bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
                  >
                    {verifying ? (
                      <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="mr-1.5 size-3.5" />
                    )}
                    {verifying ? "Verifying…" : routing.verifyButtonText}
                  </Button>
                )}

                {/* 2. Verified Badge */}
                {doc && doc.status === "verified" && (
                  <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30 gap-1 py-1 px-2.5">
                    <CheckCircle2 className="size-3.5" />
                    Verified
                  </Badge>
                )}

                {/* 3. Contextual Action Buttons by Document Type (per Evaluator Spec) */}
                {doc && doc.status === "verified" && (
                  <>
                    {/* (a) Draft-Eligible: Sales, Purchase, Credit/Debit Notes, Challans, B2B/B2C */}
                    {routing.primaryAction === "draft" && (
                      <>
                        {!draftRecord && (
                          <Button
                            variant="default"
                            size="sm"
                            onClick={handleCreateDraft}
                            disabled={draftLoading}
                            className={cn(
                              "text-white shadow-sm",
                              routing.accountingDraft === "adjustment"
                                ? "bg-purple-600 hover:bg-purple-700"
                                : "bg-emerald-600 hover:bg-emerald-700"
                            )}
                          >
                            {draftLoading ? (
                              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                            ) : (
                              <Sparkles className="mr-1.5 size-3.5" />
                            )}
                            {draftLoading ? "Creating…" : routing.createDraftButtonText}
                          </Button>
                        )}
                        {draftRecord?.status === "draft" && (
                          <Button
                            variant="default"
                            size="sm"
                            onClick={handlePostToLedger}
                            disabled={posting}
                            className="bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
                          >
                            {posting ? (
                              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                            ) : (
                              <BookOpen className="mr-1.5 size-3.5" />
                            )}
                            {posting ? "Posting…" : routing.postButtonText}
                          </Button>
                        )}
                        {draftRecord?.status === "posted" && (
                          <>
                            <Badge className="bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30 gap-1 py-1 px-2.5">
                              <BookOpen className="size-3.5" />
                              Posted to Ledger
                            </Badge>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleViewLinkedTransaction}
                              className="border-blue-500/30 text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 gap-1.5"
                            >
                              <ExternalLink className="size-3.5" />
                              View Linked Transaction
                            </Button>
                          </>
                        )}
                      </>
                    )}

                    {/* (b) E-Invoice / E-Way Bill: Link to Commercial Invoice */}
                    {routing.primaryAction === "link_invoice" && (
                      <>
                        {linkedInvoiceNumber ? (
                          <>
                            <Badge className="bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30 gap-1 py-1 px-2.5">
                              <LinkIcon className="size-3.5" />
                              Linked: #{linkedInvoiceNumber}
                            </Badge>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setLinkModalOpen(true)}
                              className="border-blue-500/30 text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 gap-1.5"
                            >
                              <LinkIcon className="size-3.5" />
                              Change Link
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setLinkModalOpen(true)}
                            className="border-blue-500/40 text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 shadow-sm gap-1.5"
                          >
                            <LinkIcon className="size-3.5" />
                            Link to Invoice
                          </Button>
                        )}
                      </>
                    )}

                    {/* (c) GST Return: Open in GST Workspace */}
                    {routing.primaryAction === "gst_workspace" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleOpenGstWorkspace}
                        className="border-cyan-500/40 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/10 shadow-sm gap-1.5"
                      >
                        <ExternalLink className="size-3.5" />
                        Open in GST Workspace
                      </Button>
                    )}

                    {/* (d) GST Notice: Track Notice */}
                    {routing.primaryAction === "track_notice" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setNoticeModalOpen(true)}
                        className="border-rose-500/40 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 shadow-sm gap-1.5"
                      >
                        <AlertCircle className="size-3.5" />
                        Track Notice
                      </Button>
                    )}

                    {/* (e) HSN/SAC List / Reference Master Data: View / Manage Reference Data */}
                    {routing.primaryAction === "reference_data" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleManageReferenceData}
                        className="border-slate-500/40 text-slate-700 dark:text-slate-300 hover:bg-slate-500/10 shadow-sm gap-1.5"
                      >
                        <ExternalLink className="size-3.5" />
                        View / Manage Reference Data
                      </Button>
                    )}
                  </>
                )}

                {doc && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleStartEditing}
                    className="text-primary border-primary/30 hover:bg-primary/10"
                  >
                    <Pencil className="mr-1.5 size-3.5" />
                    Edit Fields
                  </Button>
                )}
                {doc && (
                  <Button variant="outline" size="sm" onClick={handleDownload}>
                    <FileDown className="mr-1.5 size-4" />
                    Download
                  </Button>
                )}
              </>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={handleCancelEditing} disabled={saving}>
                  <X className="mr-1.5 size-3.5" />
                  Cancel
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleSaveEditing}
                  disabled={saving}
                  className="bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
                >
                  {saving ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Save className="mr-1.5 size-3.5" />}
                  {saving ? "Saving…" : "Save Changes"}
                </Button>
              </>
            )}
            <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>

        {/* ── Loading ──────────────────────────────────────── */}
        {docLoading && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 py-20 text-muted-foreground">
            <Loader2 className="size-8 animate-spin text-primary" />
            <p className="text-sm">Loading document details…</p>
          </div>
        )}

        {/* ── Error ────────────────────────────────────────── */}
        {!docLoading && docError && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center text-destructive">
            <AlertCircle className="size-9" />
            <p className="max-w-md text-sm">{docError}</p>
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
          </div>
        )}

        {/* ── Body: 2-column layout ────────────────────────── */}
        {!docLoading && !docError && doc && (
          <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[1.1fr_0.9fr]">
            {/* ──────────── LEFT: fields ──────────────────── */}
            <div className="flex min-h-0 flex-col overflow-y-auto border-border bg-card/10 p-6 md:border-r">
              {/* File metadata strip */}
              <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {fileSize && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1">
                    <FileText className="size-3" />{fileSize}
                  </span>
                )}
                {ext && (
                  <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 font-mono uppercase">
                    <FileType className="size-3" />{ext}
                  </span>
                )}
                <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1">
                  Uploaded: {
                    doc.uploaded_at
                      ? new Date(doc.uploaded_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
                      : "—"
                  }
                </span>
                {doc.uploaded_by && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1">
                    Uploaded by: {doc.uploaded_by}
                  </span>
                )}
                {doc.ocr_confidence !== undefined && doc.ocr_confidence !== null && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1">
                    Confidence: {Number(doc.ocr_confidence).toLocaleString("en-IN", { maximumFractionDigits: 2 }) + "%"}
                  </span>
                )}
                {meta.ocr_confidence !== undefined && doc.ocr_confidence === undefined && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1">
                    Confidence: {Number(meta.ocr_confidence).toLocaleString("en-IN", { maximumFractionDigits: 2 }) + "%"}
                  </span>
                )}
                {doc.status && (
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[11px] capitalize",
                      doc.status === "verified"
                        ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                        : "bg-secondary text-muted-foreground"
                    )}
                  >
                    Status · {String(doc.status)}
                  </Badge>
                )}
              </div>

              {/* ── ACCOUNTING DRAFT BANNER / CARD ──────────── */}
              {draftRecord && (
                <Card className="mb-5 border-emerald-500/30 bg-emerald-500/5 shadow-none">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <BookOpen className="size-4 text-emerald-600 dark:text-emerald-400" />
                        <span className="text-xs font-semibold uppercase tracking-wider text-emerald-800 dark:text-emerald-300">
                          Accounting {draftRecord.status === "posted" ? "Ledger Entry" : "Draft Prepared"}
                        </span>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[11px] capitalize",
                          draftRecord.status === "posted"
                            ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30"
                            : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                        )}
                      >
                        {draftRecord.status === "posted" ? "Posted to Ledger" : "Draft (Ready for Review)"}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-medium">Voucher</span>
                        <span className="font-semibold uppercase">{draftRecord.voucher_type}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-medium">Category</span>
                        <span className="font-semibold capitalize">{draftRecord.category ?? "General"}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-medium">Debit</span>
                        <span className="font-mono font-medium">₹{Number(draftRecord.debit ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-medium">Credit</span>
                        <span className="font-mono font-medium">₹{Number(draftRecord.credit ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                      </div>
                    </div>
                    {draftRecord.description && (
                      <p className="mt-2 text-[11px] text-muted-foreground truncate border-t border-border/40 pt-1.5" title={draftRecord.description}>
                        {draftRecord.description}
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* ── 1) DOCUMENT INFORMATION CARD ──────────── */}
              <Card className="border-border/70 shadow-none">
                <CardContent className="p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="size-1.5 rounded-full bg-primary" />
                      <h3 className="text-sm font-semibold tracking-wide text-foreground/90">
                        {isEditing ? "Edit Document Fields" : "Document Information"}
                      </h3>
                    </div>
                    {!isEditing && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleStartEditing}
                        className="h-7 text-xs gap-1.5 text-primary hover:text-primary hover:bg-primary/10"
                      >
                        <Pencil className="size-3" />
                        Edit Fields
                      </Button>
                    )}
                  </div>

                  {/* Editing Guidance Banner */}
                  {isEditing && (
                    <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-primary/30 bg-primary/5 p-3 text-xs text-foreground/90">
                      <Info className="size-4 shrink-0 text-primary mt-0.5" />
                      <div className="space-y-0.5">
                        <span className="font-semibold text-primary">Field Editing Mode Active:</span>
                        <p className="text-muted-foreground">
                          Correct wrongly scanned values or add missing fields (e.g. Total Amount, Taxable Amount, Taxes) for calculation modules. You can reference the scanned invoice on the right side.
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="mb-4 rounded-lg border border-dashed border-border bg-card/60 px-4 py-3">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      Document Category
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-base font-semibold text-foreground">
                        {category?.icon && <span className="text-lg leading-none">{category.icon}</span>}
                        <span>{category?.label ?? doc.document_category ?? "—"}</span>
                      </div>
                      <Badge variant="outline" className={cn("text-[11px] font-medium px-2 py-0.5 border", routing.badgeClass)}>
                        {routing.badgeText}
                      </Badge>
                    </div>
                  </div>

                  {/* ── Category-to-Module Routing Guidance (Screenshot 1 & 2 Spec) ── */}
                  <div className="mb-5 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.04] p-4 text-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-border/50 pb-2">
                      <div className="flex items-center gap-1.5 font-semibold text-foreground">
                        <Compass className="size-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span>Recommended category-to-module routing</span>
                      </div>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {routing.routeTitle}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                      <div className="rounded-lg bg-card/80 p-2 border border-border/60">
                        <span className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">
                          GST / Other Module:
                        </span>
                        <span className="font-medium text-foreground">{routing.targetModule}</span>
                      </div>
                      <div className="rounded-lg bg-card/80 p-2 border border-border/60">
                        <span className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">
                          Accounting Draft?
                        </span>
                        <span className="font-medium text-foreground">{routing.draftStatusText}</span>
                      </div>
                    </div>

                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      {routing.explanation}
                    </p>

                    {linkedInvoiceNumber && (
                      <div className="flex items-center gap-2 rounded-lg bg-blue-500/10 border border-blue-500/20 p-2 text-[11px] text-blue-600 dark:text-blue-400">
                        <LinkIcon className="size-3.5 shrink-0" />
                        <span>
                          Linked to commercial invoice: <strong className="font-mono">#{linkedInvoiceNumber}</strong> (duplicate ledger entry prevented).
                        </span>
                      </div>
                    )}
                  </div>

                  <Separator className="my-4" />

                  {/* Fields Rendering: View Mode vs Edit Mode */}
                  {!isEditing ? (
                    standardFields.length > 0 ? (
                      <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
                        {standardFields.map((f) => (
                          <FieldRow key={f.key + f.label} label={f.label} value={f.value} />
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm italic text-muted-foreground">
                        No standard fields populated for this document.
                      </p>
                    )
                  ) : (
                    <div className="space-y-4">
                      {editFields.length > 0 ? (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          {editFields.map((f, idx) => (
                            <div
                              key={`${f.key}-${idx}`}
                              className="rounded-lg border border-border/80 bg-card/60 p-2.5 space-y-1.5 focus-within:border-primary/60 transition-colors"
                            >
                              <div className="flex items-center justify-between gap-1">
                                <label
                                  className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground truncate"
                                  title={f.label}
                                >
                                  {f.label}
                                </label>
                                <button
                                  type="button"
                                  onClick={() => handleRemoveField(idx)}
                                  className="text-muted-foreground/50 hover:text-destructive transition-colors p-0.5 rounded"
                                  title={`Remove ${f.label}`}
                                >
                                  <Trash2 className="size-3.5" />
                                </button>
                              </div>
                              <Input
                                value={f.value}
                                onChange={(e) => handleFieldChange(idx, e.target.value)}
                                placeholder={`Enter ${f.label}...`}
                                className="h-8 text-xs font-medium bg-background"
                              />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm italic text-muted-foreground">
                          No fields currently added. Use the section below to add fields.
                        </p>
                      )}

                      {/* ── Add Missing Fields Section ── */}
                      <div className="mt-5 rounded-lg border border-dashed border-primary/40 bg-primary/[0.03] p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                            <Plus className="size-3.5 text-primary" />
                            <span>Add Missing Field</span>
                          </div>
                          <span className="text-[11px] text-muted-foreground">
                            {availableMissingFields.length} available for this category
                          </span>
                        </div>

                        {/* Quick Add Chips */}
                        {quickAddFields.length > 0 && (
                          <div className="space-y-1.5">
                            <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
                              Quick Add Common Missing Fields:
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {quickAddFields.map((qf) => (
                                <Button
                                  key={qf.key}
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleAddField(qf.key, qf.label)}
                                  className="h-7 text-xs border-primary/30 hover:bg-primary/10 hover:border-primary text-primary"
                                >
                                  <Plus className="mr-1 size-3" />
                                  {qf.label}
                                </Button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Dropdown for All Other Schema Fields */}
                        {otherMissingFields.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            <select
                              aria-label="Select missing category field"
                              value=""
                              onChange={(e) => {
                                const chosen = availableMissingFields.find((f) => f.key === e.target.value);
                                if (chosen) {
                                  handleAddField(chosen.key, chosen.label);
                                }
                              }}
                              className="h-8 text-xs rounded-md border border-input bg-background px-2.5 py-1 text-foreground shadow-sm outline-none focus:border-ring focus:ring-1 focus:ring-ring flex-1 min-w-[200px]"
                            >
                              <option value="" disabled>Select from {otherMissingFields.length} more category fields...</option>
                              {otherMissingFields.map((mf) => (
                                <option key={mf.key} value={mf.key}>{mf.label}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {/* Custom Field Input */}
                        <div className="pt-2 border-t border-border/50">
                          {!showCustomInput ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => setShowCustomInput(true)}
                              className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1 -ml-2"
                            >
                              <Plus className="size-3" />
                              Add Custom Field (not in schema)
                            </Button>
                          ) : (
                            <div className="flex flex-wrap items-center gap-2 pt-1">
                              <Input
                                placeholder="Field Label (e.g. Delivery Batch)"
                                value={customFieldLabel}
                                onChange={(e) => setCustomFieldLabel(e.target.value)}
                                className="h-8 text-xs flex-1 min-w-[140px] bg-background"
                              />
                              <Input
                                placeholder="Field Value"
                                value={customFieldValue}
                                onChange={(e) => setCustomFieldValue(e.target.value)}
                                className="h-8 text-xs flex-1 min-w-[140px] bg-background"
                              />
                              <Button
                                type="button"
                                size="sm"
                                onClick={handleAddCustomField}
                                disabled={!customFieldLabel.trim()}
                                className="h-8 text-xs"
                              >
                                Add
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setShowCustomInput(false);
                                  setCustomFieldLabel("");
                                  setCustomFieldValue("");
                                }}
                                className="h-8 text-xs"
                              >
                                Cancel
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Edit Mode Bottom Actions */}
                      <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/70">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleCancelEditing}
                          disabled={saving}
                        >
                          Cancel
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={handleSaveEditing}
                          disabled={saving}
                          className="bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
                        >
                          {saving ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Save className="mr-1.5 size-3.5" />}
                          {saving ? "Saving…" : "Save Changes"}
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* ── ON-DEMAND LINE ITEMS EXTRACTION ──────── */}
              {canPreview && (!lineItems || lineItems.rows.length === 0) && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-primary/40 bg-primary/5 p-3.5">
                  <div className="text-xs text-muted-foreground">
                    <span className="font-semibold text-foreground">Extract Product Line Items:</span> Fetch individual product names, quantities, rates, and tax amounts with AI Vision.
                  </div>
                  <Button
                    size="sm"
                    variant="default"
                    className="gap-1.5 text-xs shadow-sm"
                    disabled={extractingItems}
                    onClick={handleExtractLineItems}
                  >
                    {extractingItems ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                    {extractingItems ? "Extracting Products…" : "Extract Products"}
                  </Button>
                </div>
              )}

              {/* ── 2) LINE ITEMS CARD ────────────────────── */}
              {lineItems && lineItems.rows.length > 0 && (
                <Card className="mt-5 border-border/70 shadow-none">
                  <CardContent className="p-5">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <div className="size-1.5 rounded-full bg-primary" />
                        <h3 className="text-sm font-semibold tracking-wide text-foreground/90">
                          Line Items
                        </h3>
                      </div>
                      <Badge variant="outline" className="text-[11px]">
                        {lineItems.rows.length} row{lineItems.rows.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>

                    <div className="overflow-x-auto rounded-lg border border-border bg-background">
                      <table className="w-full border-collapse text-xs">
                        <thead>
                          <tr className="bg-muted/50">
                            <th className="border-b border-border px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                              #
                            </th>
                            {lineItems.columns.map((col, i) => (
                              <th
                                key={col.key || i}
                                className="whitespace-nowrap border-b border-border px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
                              >
                                {col.label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {lineItems.rows.map((row, ri) => (
                            <tr
                              key={ri}
                              className={ri % 2 === 0 ? "bg-background" : "bg-muted/20"}
                            >
                              <td className="whitespace-nowrap border-b border-border/50 px-3 py-1.5 align-top text-muted-foreground">
                                {ri + 1}
                              </td>
                              {lineItems.columns.map((col, ci) => {
                                const val = getTableCellValue(row, col.key, col.label);
                                const formatted = formatTableCellValue(val, col.key);
                                return (
                                  <td
                                    key={ci}
                                    className="whitespace-nowrap border-b border-border/50 px-3 py-1.5 align-top font-medium text-foreground/90"
                                  >
                                    {formatted || <span className="text-muted-foreground/60">—</span>}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* ── 3) ADDITIONAL DETAILS CARD ────────────── */}
              {!isEditing && additionalFields.length > 0 && (
                <Card className="mt-5 border-border/70 shadow-none">
                  <CardContent className="p-5">
                    <div className="mb-4 flex items-center gap-2">
                      <div className="size-1.5 rounded-full bg-primary" />
                      <h3 className="text-sm font-semibold tracking-wide text-foreground/90">
                        Additional Details
                      </h3>
                      <Badge variant="outline" className="text-[11px] ml-1">
                        {additionalFields.length} field{additionalFields.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
                      {additionalFields.map((f) => (
                        <FieldRow key={`extra-${f.key}`} label={f.label} value={f.value} />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* ──────────── RIGHT: preview ───────────────────── */}
            <div className="flex min-h-[60vh] min-w-0 flex-col border-border bg-muted/20 p-5 md:border-l">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="size-1.5 rounded-full bg-primary" />
                  <h3 className="text-sm font-semibold tracking-wide text-foreground/90">
                    Document Preview
                  </h3>
                </div>
                <Badge variant="outline" className="text-[11px] truncate max-w-[55%]">
                  {fileName}
                </Badge>
              </div>

              <div className="relative flex min-h-[55vh] flex-1 items-center justify-center overflow-hidden rounded-xl border border-border bg-card shadow-inner">
                {prevLoading && (
                  <div className="flex flex-col items-center gap-3 p-10 text-muted-foreground">
                    <Loader2 className="size-7 animate-spin text-primary" />
                    <p className="text-xs">Loading document preview…</p>
                  </div>
                )}

                {!hasFile && !docLoading && (
                  <div className="flex flex-col items-center gap-4 p-10 text-center">
                    <FileQuestion className="size-12 text-muted-foreground/50" />
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-foreground/80">No File Stored on Server</p>
                      <p className="max-w-xs text-xs text-muted-foreground">
                        This document record contains extracted field values only. No physical document file is saved on the server for this entry.
                      </p>
                    </div>
                  </div>
                )}

                {hasFile && !prevLoading && prevError && (
                  <div className="flex flex-col items-center gap-3 p-10 text-center">
                    <AlertCircle className="size-8 text-destructive" />
                    <p className="max-w-xs text-sm text-destructive">{prevError}</p>
                    <Button variant="outline" size="sm" onClick={handleDownload}>
                      <Download className="mr-1.5 size-4" />
                      Try Download
                    </Button>
                  </div>
                )}

                {hasFile && !prevLoading && !prevError && canPreview && blobUrl && isImage && (
                  <img
                    src={blobUrl}
                    alt={fileName}
                    className="max-h-full max-w-full object-contain p-3"
                  />
                )}

                {hasFile && !prevLoading && !prevError && canPreview && blobUrl && isPdf && (
                  <iframe
                    src={blobUrl}
                    title={fileName}
                    className="h-full min-h-[60vh] w-full border-0 bg-white rounded-md"
                  />
                )}

                {hasFile && !prevLoading && !prevError && !canPreview && (
                  <div className="flex flex-col items-center gap-4 p-10 text-center">
                    <FileText className="size-12 text-muted-foreground" />
                    <div className="space-y-1">
                      <p className="text-sm font-medium">{fileName}</p>
                      <p className="max-w-xs text-xs text-muted-foreground">
                        Browser preview is not available for .{ext || "unknown"} files.
                        Download the document to view its contents.
                      </p>
                    </div>
                    <Button variant="default" size="sm" onClick={handleDownload}>
                      <Download className="mr-1.5 size-4" />
                      Download / Open
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Footer ───────────────────────────────────────── */}
        <DialogFooter className="border-t border-border bg-card/40 px-6 py-3">
          <div className="flex w-full items-center justify-between gap-3">
            <div className="truncate text-xs text-muted-foreground">
              {doc?.id ? `ID: ${String(doc.id).slice(0, 13)}…` : ""}
            </div>
            <div className="flex items-center gap-2">
              {isEditing ? (
                <>
                  <Button variant="outline" onClick={handleCancelEditing} disabled={saving}>
                    Cancel
                  </Button>
                  <Button
                    variant="default"
                    onClick={handleSaveEditing}
                    disabled={saving}
                    className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
                  >
                    {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                    {saving ? "Saving…" : "Save Changes"}
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    onClick={handleStartEditing}
                    className="gap-1.5 text-primary border-primary/30 hover:bg-primary/10"
                  >
                    <Pencil className="size-3.5" />
                    Edit Fields
                  </Button>
                  <Button variant="outline" onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                </>
              )}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    {/* ── Link to Commercial Invoice Dialog (for E-Invoice / E-Way Bill) ── */}
    <Dialog open={linkModalOpen} onOpenChange={setLinkModalOpen}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <LinkIcon className="size-4 text-blue-500" />
            Link to Commercial Invoice
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Link this {category?.label ?? "document"} to an existing sales or purchase transaction. This keeps transport and IRN compliance records connected without creating duplicate ledger entries.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Select Parent Commercial Invoice:
            </label>
            {commercialInvoices.length > 0 ? (
              <Select
                value={selectedInvoiceToLink}
                onValueChange={setSelectedInvoiceToLink}
              >
                <SelectTrigger className="w-full text-xs">
                  <SelectValue placeholder="Choose an invoice from this client..." />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {commercialInvoices.map((inv) => (
                    <SelectItem key={inv.id} value={inv.id} className="text-xs">
                      <span className="font-semibold font-mono">
                        {inv.invoice_number || inv.file_name || `Doc #${inv.id.slice(0, 8)}`}
                      </span>
                      {" · "}
                      <span className="capitalize">{inv.document_category?.replace(/_/g, " ")}</span>
                      {inv.total_amount ? ` · ₹${Number(inv.total_amount).toLocaleString("en-IN")}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground bg-card/40">
                No commercial invoices found for this client. Upload or verify a sales/purchase record first.
              </div>
            )}
          </div>

          {linkedInvoiceNumber && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-500/10 border border-blue-500/20 p-2.5 text-xs text-blue-600 dark:text-blue-400">
              <LinkIcon className="size-3.5 shrink-0" />
              <span>
                Currently linked to invoice: <strong className="font-mono">#{linkedInvoiceNumber}</strong>
              </span>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" onClick={() => setLinkModalOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleLinkInvoice}
            disabled={!selectedInvoiceToLink || linkingInvoice}
            className="bg-blue-600 text-white hover:bg-blue-700"
          >
            {linkingInvoice ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <LinkIcon className="mr-1.5 size-3.5" />}
            {linkingInvoice ? "Linking…" : "Link Document"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    {/* ── Track Statutory GST Notice Dialog ── */}
    <Dialog open={noticeModalOpen} onOpenChange={setNoticeModalOpen}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <AlertCircle className="size-4 text-rose-500" />
            Track Statutory GST Notice
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Monitor response deadlines, department proceedings, and update compliance tracking status for this notice.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Notice Compliance Status:
            </label>
            <Select value={noticeStatus} onValueChange={setNoticeStatus}>
              <SelectTrigger className="w-full text-xs">
                <SelectValue placeholder="Select tracking status..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Under Review">Under Review (Scrutiny by CA)</SelectItem>
                <SelectItem value="Response Drafted">Response Drafted (Awaiting Client Approval)</SelectItem>
                <SelectItem value="Pending CA Sign-off">Pending CA Sign-off</SelectItem>
                <SelectItem value="Replied to Department">Replied to Department (Submitted)</SelectItem>
                <SelectItem value="Closed / Dropped">Closed / Dropped by Authority</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-lg border border-border/80 bg-card/40 p-3 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Notice Number:</span>
              <span className="font-mono font-medium">{resolve("notice_number") ? String(resolve("notice_number")) : (doc?.invoice_number || "—")}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Issuing Section:</span>
              <span className="font-medium">{resolve("section_code") ? String(resolve("section_code")) : "Section 61 / 73"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Response Due Date:</span>
              <span className="font-medium text-rose-600 dark:text-rose-400">
                {resolve("due_date") ? String(resolve("due_date")) : "Within 30 Days of receipt"}
              </span>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" onClick={() => setNoticeModalOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleSaveNoticeStatus}
            disabled={updatingNotice}
            className="bg-rose-600 text-white hover:bg-rose-700"
          >
            {updatingNotice ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Save className="mr-1.5 size-3.5" />}
            {updatingNotice ? "Saving…" : "Save Notice Status"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
