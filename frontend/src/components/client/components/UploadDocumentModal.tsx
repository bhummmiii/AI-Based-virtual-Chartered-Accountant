// ============================================================
// UploadDocumentModal — category-specific form for all 13 categories
// ============================================================
import React, { useState } from "react";
import type { DocumentCategory, DocumentUploadPayload } from "../../../types/document.types";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import { uploadDocument } from "../../../services/api/documents";
import type { DuplicateResponse } from "../../../types/document.types";

interface Props {
  clientId: string;
  category: DocumentCategory;
  onClose: () => void;
  onSuccess: () => void;
}

// -- Category-specific field definitions ----------------------
interface FieldDef {
  key: keyof DocumentUploadPayload;
  label: string;
  type?: "text" | "date" | "number" | "select";
  options?: string[];
  placeholder?: string;
  required?: boolean;
}

export const COMMON_INVOICE_FIELDS: FieldDef[] = [
  { key: "invoice_number", label: "Invoice Number", placeholder: "INV-2024-001", required: true },
  { key: "gstin",          label: "GSTIN",          placeholder: "22AAAAA0000A1Z5" },
  { key: "invoice_date",   label: "Invoice Date",   type: "date" },
  { key: "vendor",         label: "Vendor / Supplier" },
  { key: "customer",       label: "Customer" },
  { key: "item_description", label: "Item Description" },
  { key: "quantity",       label: "Quantity",       type: "number" },
  { key: "rate",           label: "Rate",           type: "number" },
  { key: "total_tax",      label: "Total Tax (?)",  type: "number" },
];

export const AMOUNT_FIELDS: FieldDef[] = [
  { key: "taxable_amount", label: "Taxable Amount (?)", type: "number", placeholder: "0.00" },
  { key: "cgst",           label: "CGST (?)",           type: "number", placeholder: "0.00" },
  { key: "sgst",           label: "SGST (?)",           type: "number", placeholder: "0.00" },
  { key: "igst",           label: "IGST (?)",           type: "number", placeholder: "0.00" },
  { key: "cess",           label: "Cess (?)",           type: "number", placeholder: "0.00" },
  { key: "amount",         label: "Total Amount (?)",   type: "number", placeholder: "0.00" },
  { key: "hsn",            label: "HSN / SAC Code",     placeholder: "e.g. 9954" },
];

export const CATEGORY_FIELDS: Partial<Record<DocumentCategory, FieldDef[]>> = {
  sales_records:    [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "invoice_type", label: "Invoice Type", type: "select", options: ["sales", "b2b", "b2c", "other"] },
    { key: "supplier_gstin",    label: "Supplier GSTIN" },
    { key: "customer_gstin",    label: "Customer GSTIN" },
    { key: "place_of_supply",   label: "Place of Supply" },
    { key: "reverse_charge",    label: "Reverse Charge" },
    { key: "payment_terms",     label: "Payment Terms" },
    { key: "currency",          label: "Currency" },
    { key: "pan_number",        label: "PAN Number" },
    { key: "company_name",      label: "Company Name" },
    { key: "report_title",      label: "Report Title" },
    { key: "period_start",      label: "Period Start" },
    { key: "period_end",        label: "Period End" },
  ],
  purchase_records: [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "invoice_type", label: "Invoice Type", type: "select", options: ["purchase", "b2b", "other"] },
    { key: "supplier_gstin",    label: "Supplier GSTIN" },
    { key: "customer_gstin",    label: "Recipient GSTIN" },
    { key: "place_of_supply",   label: "Place of Supply" },
    { key: "reverse_charge",    label: "Reverse Charge" },
    { key: "payment_terms",     label: "Payment Terms" },
    { key: "currency",          label: "Currency" },
    { key: "pan_number",        label: "PAN Number" },
    { key: "company_name",      label: "Company Name" },
    { key: "report_title",      label: "Report Title" },
    { key: "period_start",      label: "Period Start" },
    { key: "period_end",        label: "Period End" },
  ],
  credit_note: [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "supplier_gstin",         label: "Supplier GSTIN" },
    { key: "customer_gstin",         label: "Customer GSTIN" },
    { key: "original_invoice_number", label: "Original Invoice Number" },
    { key: "reason",                 label: "Reason" },
    { key: "document_type",          label: "Document Type" },
    { key: "place_of_supply",        label: "Place of Supply" },
    { key: "reverse_charge",         label: "Reverse Charge" },
  ],
  debit_note: [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "supplier_gstin",         label: "Supplier GSTIN" },
    { key: "customer_gstin",         label: "Customer GSTIN" },
    { key: "original_invoice_number", label: "Original Invoice Number" },
    { key: "reason",                 label: "Reason" },
    { key: "document_type",          label: "Document Type" },
    { key: "place_of_supply",        label: "Place of Supply" },
    { key: "reverse_charge",         label: "Reverse Charge" },
  ],
  b2b_invoice: [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "supplier_gstin",    label: "Supplier GSTIN" },
    { key: "customer_gstin",    label: "Buyer GSTIN" },
    { key: "place_of_supply",   label: "Place of Supply" },
    { key: "reverse_charge",    label: "Reverse Charge" },
    { key: "payment_terms",     label: "Payment Terms" },
    { key: "currency",          label: "Currency" },
    { key: "pan_number",        label: "PAN Number" },
    { key: "irn",               label: "IRN" },
    { key: "ack_number",        label: "Acknowledgement Number" },
  ],
  b2c_invoice: [
    { key: "invoice_number",    label: "Invoice Number", required: true },
    { key: "invoice_date",      label: "Invoice Date",   type: "date" },
    { key: "customer",          label: "Customer Name" },
    { key: "vendor",            label: "Vendor / Supplier" },
    { key: "gstin",             label: "GSTIN" },
    ...AMOUNT_FIELDS,
    { key: "place_of_supply",   label: "Place of Supply" },
    { key: "payment_terms",     label: "Payment Terms" },
    { key: "currency",          label: "Currency" },
    { key: "pan_number",        label: "PAN Number" },
  ],
  hsn_sac: [
    { key: "hsn",            label: "HSN / SAC Code",  placeholder: "e.g. 9954", required: true },
    { key: "invoice_number", label: "Reference Number" },
    { key: "taxable_amount", label: "Taxable Value (₹)", type: "number" },
    { key: "cgst",           label: "CGST Rate %",      type: "number" },
    { key: "sgst",           label: "SGST Rate %",      type: "number" },
    { key: "igst",           label: "IGST Rate %",      type: "number" },
  ],
  e_invoice: [
    ...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS,
    { key: "irn",               label: "IRN" },
    { key: "ack_number",        label: "Acknowledgement Number" },
    { key: "supplier_gstin",    label: "Supplier GSTIN" },
    { key: "customer_gstin",    label: "Buyer GSTIN" },
    { key: "place_of_supply",   label: "Place of Supply" },
    { key: "reverse_charge",    label: "Reverse Charge" },
    { key: "currency",          label: "Currency" },
  ],
  e_way_bill: [
    { key: "invoice_number",  label: "E-Way Bill Number", required: true },
    { key: "invoice_date",    label: "Generated Date",   type: "date" },
    { key: "gstin",           label: "Supplier GSTIN" },
    { key: "vendor",          label: "Supplier Name" },
    { key: "customer",        label: "Recipient Name" },
    { key: "amount",          label: "Total Value (₹)",  type: "number" },
    { key: "hsn",             label: "HSN Code" },
    { key: "vehicle_number",  label: "Vehicle Number" },
    { key: "transport_mode",  label: "Transport Mode" },
    { key: "valid_until",     label: "Validity Date",    type: "date" },
    { key: "place_of_supply", label: "Place of Supply" },
  ],
  gst_challan: [
    { key: "invoice_number",  label: "CPIN / CIN",       required: true, placeholder: "CPIN / CIN number" },
    { key: "invoice_date",    label: "Payment Date",     type: "date" },
    { key: "gstin",           label: "GSTIN" },
    { key: "amount",          label: "Amount Paid (₹)",  type: "number" },
    { key: "taxable_amount",  label: "Taxable Amount (₹)", type: "number" },
    { key: "cgst",            label: "CGST (₹)",         type: "number" },
    { key: "sgst",            label: "SGST (₹)",         type: "number" },
    { key: "igst",            label: "IGST (₹)",         type: "number" },
    { key: "financial_year",  label: "Financial Year",   placeholder: "2024-25" },
    { key: "month",           label: "Tax Period",       placeholder: "March 2025" },
  ],
  gst_return: [
    { key: "gst_return_type", label: "Return Type", type: "select",
      options: ["GSTR-1", "GSTR-2A", "GSTR-2B", "GSTR-3B", "GSTR-9", "GSTR-9C"] },
    { key: "financial_year",  label: "Financial Year", placeholder: "2024-25", required: true },
    { key: "month",           label: "Period / Month",  placeholder: "March 2025" },
    { key: "filed_date",      label: "Date of Filing",  type: "date" },
    { key: "arn",             label: "ARN",              placeholder: "Acknowledgement Reference Number" },
    { key: "gstin",           label: "GSTIN" },
    { key: "taxable_amount",  label: "Taxable Turnover (₹)", type: "number" },
    { key: "amount",          label: "Total Tax Paid (₹)",   type: "number" },
    { key: "cgst",            label: "CGST (₹)",         type: "number" },
    { key: "sgst",            label: "SGST (₹)",         type: "number" },
    { key: "igst",            label: "IGST (₹)",         type: "number" },
  ],
  gst_notice: [
    { key: "notice_number",    label: "Notice / Reference Number", required: true },
    { key: "notice_date",      label: "Notice Date",               type: "date" },
    { key: "response_due_date", label: "Response Due Date",        type: "date" },
    { key: "gstin",            label: "GSTIN" },
    { key: "priority",         label: "Priority", type: "select", options: ["low", "medium", "high"] },
    { key: "financial_year",   label: "Financial Year",            placeholder: "2024-25" },
    { key: "vendor",           label: "Taxpayer / Company" },
    { key: "amount",           label: "Demand Amount (₹)",         type: "number" },
  ],
  document_list: [
    { key: "invoice_number", label: "Reference Number" },
    { key: "invoice_date",   label: "Document Date",   type: "date" },
    { key: "vendor",         label: "Source / Issuer" },
  ],
};


// -- Component -------------------------------------------------
export const UploadDocumentModal: React.FC<Props> = ({ clientId, category, onClose, onSuccess }) => {
  const catMeta = DOCUMENT_CATEGORIES.find((c) => c.id === category);
  const fields = CATEGORY_FIELDS[category] ?? COMMON_INVOICE_FIELDS;

  const [form, setForm] = useState<Partial<DocumentUploadPayload>>({ document_category: category, document_type: "upload" });
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateResponse | null>(null);

  const set = (key: keyof DocumentUploadPayload, val: string) =>
    setForm((prev) => ({ ...prev, [key]: val }));

  const handleSubmit = async (forceSave = false) => {
    setLoading(true);
    setError(null);
    try {
      const baseKeys = [
        "document_category", "document_type", "invoice_type", "invoice_number", 
        "gstin", "vendor", "customer", "invoice_date", "amount", "taxable_amount", 
        "cgst", "sgst", "igst", "cess", "hsn", "arn", "notice_number", "notice_date", 
        "response_due_date", "priority", "gst_return_type", "financial_year", "month", "filed_date"
      ];
      
      const rootPayload: any = {};
      const metaPayload: any = {};
      
      Object.entries(form).forEach(([k, v]) => {
        if (baseKeys.includes(k)) {
          rootPayload[k] = v;
        } else {
          metaPayload[k] = v;
        }
      });

      const payload: DocumentUploadPayload = {
        ...rootPayload,
        document_type: "upload",
        metadata_json: Object.keys(metaPayload).length > 0 ? JSON.stringify(metaPayload) : undefined,
        force_save: forceSave ? "true" : "false",
        file: file ?? undefined,
      };
      const result = await uploadDocument(clientId, payload);
      if (result.type === "duplicate") {
        setDuplicate(result.info);
      } else {
        onSuccess();
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string; message?: string } }; message?: string };
      setError(e?.response?.data?.message ?? e?.message ?? "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card upload-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-cat-icon">{catMeta?.icon}</span>
            <h2 className="modal-title">Upload {catMeta?.label}</h2>
          </div>
          <button className="modal-close" onClick={onClose}>?</button>
        </div>

        {/* Duplicate Warning */}
        {duplicate && (
          <div className="dup-banner">
            <div className="dup-banner-icon">??</div>
            <div className="dup-banner-body">
              <p className="dup-banner-title">Duplicate Detected</p>
              <p className="dup-banner-msg">{duplicate.message}</p>
              <div className="dup-banner-actions">
                <button className="btn btn-ghost" onClick={() => setDuplicate(null)}>Cancel</button>
                <button className="btn btn-warning" onClick={() => handleSubmit(true)} disabled={loading}>
                  Save Anyway
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && <div className="error-banner">? {error}</div>}

        {/* Form */}
        <form className="upload-form" onSubmit={(e) => { e.preventDefault(); handleSubmit(false); }}>
          <div className="form-grid">
            {fields.map((f) => (
              <div key={f.key} className="form-group">
                <label className="form-label">
                  {f.label}{f.required && <span className="required-star">*</span>}
                </label>
                {f.type === "select" ? (
                  <select
                    className="form-input"
                    value={(form[f.key] as string) ?? ""}
                    onChange={(e) => set(f.key, e.target.value)}
                  >
                    <option value="">Select…</option>
                    {f.options?.map((o) => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="form-input"
                    type={f.type ?? "text"}
                    placeholder={f.placeholder}
                    value={(form[f.key] as string) ?? ""}
                    onChange={(e) => set(f.key, e.target.value)}
                    required={f.required}
                  />
                )}
              </div>
            ))}
          </div>

          {/* File Upload */}
          <div className="file-upload-area">
            <label className="file-upload-label" htmlFor="upload-file-input">
              {file ? (
                <span className="file-selected">?? {file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
              ) : (
                <>
                  <span className="file-upload-icon">??</span>
                  <span>Drag and drop or <u>browse</u> to attach a file</span>
                  <span className="file-upload-hint">PDF, JPG, PNG, XLSX — max 10 MB</span>
                </>
              )}
            </label>
            <input
              id="upload-file-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls,.json,.xml"
              style={{ display: "none" }}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? <span className="spinner" /> : null}
              {loading ? "Uploading…" : "Upload Document"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
