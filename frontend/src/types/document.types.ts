// ============================================================
// Document Management Type Definitions
// ============================================================

// -- Field Confidence (OCR) ------------------------------------
export type FieldConfidence = "extracted" | "needs_review" | "missing";

export interface OcrField {
  value: string;
  confidence: FieldConfidence;
}

// -- Document Categories ---------------------------------------
export const DOCUMENT_CATEGORIES = [
  { id: "sales_records",    label: "Sales Records",      icon: "??" },
  { id: "purchase_records", label: "Purchase Records",   icon: "??" },
  { id: "credit_note",      label: "Credit Note",        icon: "??" },
  { id: "debit_note",       label: "Debit Note",         icon: "??" },
  { id: "b2b_invoice",      label: "B2B Invoice",        icon: "??" },
  { id: "b2c_invoice",      label: "B2C Invoice",        icon: "??" },
  { id: "hsn_sac",          label: "HSN / SAC",          icon: "??" },
  { id: "e_invoice",        label: "E-Invoice",          icon: "?" },
  { id: "e_way_bill",       label: "E-Way Bill",         icon: "??" },
  { id: "gst_challan",      label: "GST Challan",        icon: "??" },
  { id: "gst_return",       label: "GST Return",         icon: "??" },
  { id: "gst_notice",       label: "GST Notice",         icon: "??" },
  { id: "document_list",    label: "Document List",      icon: "??" },
] as const;

export type DocumentCategory = typeof DOCUMENT_CATEGORIES[number]["id"];

// -- Document record (from backend) ---------------------------
export interface UploadedDocument {
  id: string;
  client_id: string;
  document_category: DocumentCategory;
  document_type: "upload" | "scan";
  invoice_type?: string;
  invoice_number?: string;
  gstin?: string;
  vendor?: string;
  customer?: string;
  invoice_date?: string;
  amount?: number;
  taxable_amount?: number;
  cgst?: number;
  sgst?: number;
  igst?: number;
  cess?: number;
  hsn?: string;
  gst_return_type?: string;
  financial_year?: string;
  month?: string;
  filed_date?: string;
  arn?: string;
  notice_number?: string;
  notice_date?: string;
  response_due_date?: string;
  priority?: string;
  file_name?: string;
  file_path?: string;
  file_size?: string;
  file_type?: string;
  ocr_status?: "pending" | "processing" | "done" | "failed";
  ocr_confidence?: number;
  status: "pending" | "processed" | "verified" | "rejected";
  uploaded_by?: string;
  metadata_?: string;
  uploaded_at: string;
  created_at: string;
  updated_at: string;
}

// -- Upload form state -----------------------------------------
export interface DocumentUploadPayload {
  document_category: string;
  document_type: "upload" | "scan";
  invoice_type?: string;
  invoice_number?: string;
  gstin?: string;
  vendor?: string;
  customer?: string;
  invoice_date?: string;
  amount?: string;
  taxable_amount?: string;
  cgst?: string;
  sgst?: string;
  igst?: string;
  cess?: string;
  hsn?: string;
  gst_return_type?: string;
  financial_year?: string;
  month?: string;
  filed_date?: string;
  arn?: string;
  notice_number?: string;
  notice_date?: string;
  response_due_date?: string;
  priority?: string;
  metadata_json?: string;
  field_verification?: string;
  extraction_method?: string;
  force_save?: "true" | "false";
  file?: File;

  // Additional OCR & category-specific fields
  supplier_gstin?: string;
  customer_gstin?: string;
  place_of_supply?: string;
  reverse_charge?: string;
  payment_terms?: string;
  currency?: string;
  pan_number?: string;
  irn?: string;
  ack_number?: string;
  original_invoice_number?: string;
  reason?: string;
  vehicle_number?: string;
  transport_mode?: string;
  valid_until?: string;
  cpin?: string;
  cin?: string;
  bank?: string;
  tax_period?: string;
  company_name?: string;
  report_title?: string;
  period_start?: string;
  period_end?: string;
  total_sales?: string;
  [key: string]: any;
}


// -- OCR Multi-record types ------------------------------------
export interface OcrLineItem {
  [key: string]: string;
}

export interface OcrRecord {
  record_number: number;
  /** Flat string values keyed by field name */
  fields: Record<string, string>;
  line_items: OcrLineItem[];
  /** Column headers for the line items table */
  headers?: string[];
}

// -- OCR Extract Response --------------------------------------
export interface OcrTableData {
  headers: string[];
  headers_raw?: string[];
  rows: Record<string, string>[];
  total_rows?: number;
  table_count?: number;
}

export interface OcrExtractResponse {
  success: boolean;
  has_content: boolean;
  message: string;
  category: string;
  extraction_method?: string;
  raw_text: string;
  // -- Multi-record fields (primary) ---
  record_count: number;
  records: OcrRecord[];
  // -- Legacy single-record fields (= records[0] equivalent) ---
  core_fields: Record<string, OcrField>;
  metadata_fields: Record<string, OcrField>;
  table_data?: OcrTableData | null;
  validation: {
    gstin?: {
      valid: boolean | null;
      normalized?: string;
      message: string;
      government_verified: boolean;
    };
    amounts?: {
      ok: boolean | null;
      supply_type?: string;
      discrepancy?: number;
      calculated?: number;
      declared?: number;
      message: string;
      needs_review?: boolean;
    };
    warnings: string[];
  };
  extraction_summary?: {
    fields_found: number;
    fields_available?: number;
    table_rows_found: number;
    record_count?: number;
  };
}


// -- Duplicate detection response (409) -----------------------
export interface DuplicateInfo {
  id: string;
  invoice_number?: string;
  uploaded_at: string;
  document_category: string;
}

export interface DuplicateResponse {
  detail: "duplicate_detected";
  duplicate: DuplicateInfo;
  message: string;
}
