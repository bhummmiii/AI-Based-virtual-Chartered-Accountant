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
  force_save?: "true" | "false";
  file?: File;
}

// -- OCR Extract Response --------------------------------------
export interface OcrExtractResponse {
  category: string;
  raw_text: string;
  core_fields: Record<string, OcrField>;
  metadata_fields: Record<string, OcrField>;
  validation: {
    gstin?: {
      valid: boolean | null;
      normalized?: string;
      message: string;
      government_verified: boolean;
    };
    amounts?: {
      consistent: boolean;
      expected_total?: number;
      actual_total?: number;
      difference?: number;
      message: string;
    };
    warnings: string[];
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
