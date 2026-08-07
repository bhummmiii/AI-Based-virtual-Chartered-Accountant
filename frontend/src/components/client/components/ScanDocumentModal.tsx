// ============================================================
// ScanDocumentModal — OCR scan with confidence badges + duplicate warning
// ============================================================
import React, { useState, useRef } from "react";
import type {
  DocumentCategory,
  OcrExtractResponse,
  OcrField,
  DocumentUploadPayload,
  DuplicateResponse,
} from "../../../types/document.types";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import { ocrExtract, uploadDocument } from "../../../services/api/documents";

interface Props {
  clientId: string;
  category: DocumentCategory;
  onClose: () => void;
  onSuccess: () => void;
}

type ScanStep = "capture" | "review" | "saving";

// -- Confidence Badge ------------------------------------------
const ConfidenceBadge: React.FC<{ confidence: OcrField["confidence"] }> = ({ confidence }) => {
  const map = {
    extracted:    { label: "Extracted",    cls: "badge-extracted" },
    needs_review: { label: "Needs Review", cls: "badge-review" },
    missing:      { label: "Missing",      cls: "badge-missing" },
  } as const;
  const { label, cls } = map[confidence];
  return <span className={`ocr-badge ${cls}`}>{label}</span>;
};

// -- Editable OCR Field ----------------------------------------
interface OcrFieldRowProps {
  label: string;
  field: OcrField;
  onChange: (val: string) => void;
}
const OcrFieldRow: React.FC<OcrFieldRowProps> = ({ label, field, onChange }) => (
  <div className="ocr-field-row">
    <div className="ocr-field-meta">
      <span className="ocr-field-label">{label}</span>
      <ConfidenceBadge confidence={field.confidence} />
    </div>
    <input
      className={`form-input ocr-input ${field.confidence === "needs_review" ? "input-warn" : ""}`}
      value={field.value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={field.confidence === "missing" ? "(not detected)" : undefined}
    />
  </div>
);

// -- Friendly field labels -------------------------------------
const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice Number",
  gstin:          "GSTIN",
  invoice_date:   "Invoice Date",
  vendor:         "Vendor / Supplier",
  customer:       "Customer",
  amount:         "Total Amount",
  taxable_amount: "Taxable Amount",
  cgst:           "CGST",
  sgst:           "SGST",
  igst:           "IGST",
  cess:           "Cess",
  hsn:            "HSN / SAC",
  arn:            "ARN",
  notice_number:  "Notice Number",
  notice_date:    "Notice Date",
  response_due_date: "Response Due Date",
  priority:       "Priority",
  gst_return_type:"Return Type",
  financial_year: "Financial Year",
  month:          "Tax Period",
  filed_date:     "Filed Date",
  ewb_number:     "EWB Number",
  validity_date:  "Validity Date",
  transport_mode: "Transport Mode",
  vehicle_number: "Vehicle Number",
  cpin:           "CPIN",
  cin:            "CIN",
  irn:            "IRN",
  ack_number:     "Ack Number",
  ack_date:       "Ack Date",
};

// -- Component -------------------------------------------------
export const ScanDocumentModal: React.FC<Props> = ({ clientId, category, onClose, onSuccess }) => {
  const catMeta = DOCUMENT_CATEGORIES.find((c) => c.id === category);
  const fileRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<ScanStep>("capture");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [ocrResult, setOcrResult] = useState<OcrExtractResponse | null>(null);
  const [editedFields, setEditedFields] = useState<Record<string, OcrField>>({});
  const [duplicate, setDuplicate] = useState<DuplicateResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // File picked
  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setSelectedFile(f);
    setPreviewUrl(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
    setScanError(null);
  };

  // Run OCR
  const handleScan = async () => {
    if (!selectedFile) return;
    setScanning(true);
    setScanError(null);
    try {
      const result = await ocrExtract(selectedFile, category);
      setOcrResult(result);
      setEditedFields({ ...result.core_fields, ...result.metadata_fields });
      setStep("review");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const msg = e?.response?.data?.detail ?? e?.message ?? "Scan failed";
      if (msg === "no_content") {
        setScanError("?? This image appears to be blank or unreadable. Please upload a clear document image.");
      } else {
        setScanError(msg);
      }
    } finally {
      setScanning(false);
    }
  };

  // Edit a field value
  const handleFieldEdit = (key: string, val: string) => {
    setEditedFields((prev) => ({
      ...prev,
      [key]: { value: val, confidence: "extracted" },
    }));
  };

  // Save document
  const handleSave = async (forceSave = false) => {
    setSaving(true);
    setSaveError(null);
    try {
      // Build payload from editedFields
      const f = editedFields;
      const payload: DocumentUploadPayload = {
        document_category: category,
        document_type: "scan",
        invoice_number: f.invoice_number?.value,
        gstin:          f.gstin?.value,
        invoice_date:   f.invoice_date?.value,
        vendor:         f.vendor?.value,
        customer:       f.customer?.value,
        amount:         f.amount?.value,
        taxable_amount: f.taxable_amount?.value,
        cgst:           f.cgst?.value,
        sgst:           f.sgst?.value,
        igst:           f.igst?.value,
        cess:           f.cess?.value,
        hsn:            f.hsn?.value,
        arn:            f.arn?.value,
        notice_number:  f.notice_number?.value,
        notice_date:    f.notice_date?.value,
        response_due_date: f.response_due_date?.value,
        priority:       f.priority?.value,
        gst_return_type: f.gst_return_type?.value,
        financial_year: f.financial_year?.value,
        month:          f.month?.value,
        filed_date:     f.filed_date?.value,
        // metadata overflow fields
        metadata_json: JSON.stringify(
          Object.fromEntries(
            Object.entries(editedFields)
              .filter(([k]) => !Object.keys({
                invoice_number:1, gstin:1, invoice_date:1, vendor:1, customer:1,
                amount:1, taxable_amount:1, cgst:1, sgst:1, igst:1, cess:1, hsn:1,
                arn:1, notice_number:1, notice_date:1, response_due_date:1, priority:1,
                gst_return_type:1, financial_year:1, month:1, filed_date:1
              }).includes(k))
              .map(([k, v]) => [k, v.value])
          )
        ),
        field_verification: JSON.stringify(
          Object.fromEntries(
            Object.entries(editedFields).map(([k, v]) => [k, v.confidence])
          )
        ),
        force_save: forceSave ? "true" : "false",
        file: selectedFile ?? undefined,
      };

      const result = await uploadDocument(clientId, payload);
      if (result.type === "duplicate") {
        setDuplicate(result.info);
      } else {
        onSuccess();
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string } }; message?: string };
      setSaveError(e?.response?.data?.message ?? e?.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  };

  // Count fields needing review
  const reviewCount = Object.values(editedFields).filter((f) => f.confidence === "needs_review").length;
  const missingCount = Object.values(editedFields).filter((f) => f.confidence === "missing").length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal-card scan-modal ${step === "review" ? "scan-modal--wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-cat-icon">{catMeta?.icon}</span>
            <h2 className="modal-title">
              {step === "capture" ? `Scan ${catMeta?.label}` : `Review — ${catMeta?.label}`}
            </h2>
          </div>
          <button className="modal-close" onClick={onClose}>?</button>
        </div>

        {/* -- STEP: CAPTURE ---------------------------------- */}
        {step === "capture" && (
          <div className="scan-capture-body">
            {/* Drop zone */}
            <div
              className="scan-dropzone"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files[0];
                if (f) {
                  setSelectedFile(f);
                  setPreviewUrl(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
                }
              }}
            >
              {previewUrl ? (
                <img src={previewUrl} alt="Document preview" className="scan-preview-img" />
              ) : selectedFile ? (
                <div className="scan-file-picked">
                  <span className="scan-file-icon">??</span>
                  <span className="scan-file-name">{selectedFile.name}</span>
                  <span className="scan-file-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                </div>
              ) : (
                <div className="scan-dropzone-empty">
                  <span className="scan-drop-icon">??</span>
                  <p>Drop your document here or <u>browse</u></p>
                  <p className="scan-drop-hint">Supports PDF, JPG, PNG — max 10 MB</p>
                </div>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              style={{ display: "none" }}
              onChange={handleFilePick}
            />

            {scanError && <div className="error-banner">{scanError}</div>}

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button
                className="btn btn-primary"
                disabled={!selectedFile || scanning}
                onClick={handleScan}
              >
                {scanning ? <><span className="spinner" /> Scanning…</> : "?? Scan Document"}
              </button>
            </div>
          </div>
        )}

        {/* -- STEP: REVIEW ----------------------------------- */}
        {step === "review" && ocrResult && (
          <div className="scan-review-body">
            {/* Validation warnings */}
            {ocrResult.validation.warnings.length > 0 && (
              <div className="validation-warnings">
                <p className="validation-warnings-title">?? Validation Warnings</p>
                <ul>
                  {ocrResult.validation.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

            {/* Confidence summary */}
            <div className="confidence-summary">
              <span className="cs-item cs-extracted">
                ? {Object.values(editedFields).filter((f) => f.confidence === "extracted").length} Extracted
              </span>
              {reviewCount > 0 && (
                <span className="cs-item cs-review">? {reviewCount} Needs Review</span>
              )}
              {missingCount > 0 && (
                <span className="cs-item cs-missing">? {missingCount} Missing</span>
              )}
            </div>

            {/* GSTIN validation */}
            {ocrResult.validation.gstin && (
              <div className={`gstin-validation ${ocrResult.validation.gstin.valid ? "gstin-valid" : "gstin-invalid"}`}>
                <strong>GSTIN:</strong> {ocrResult.validation.gstin.message}
                {ocrResult.validation.gstin.normalized && (
                  <span className="gstin-normalized"> ? {ocrResult.validation.gstin.normalized}</span>
                )}
              </div>
            )}

            {/* Amount validation */}
            {ocrResult.validation.amounts && (
              <div className={`amount-validation ${ocrResult.validation.amounts.consistent ? "amount-ok" : "amount-warn"}`}>
                <strong>Amount Check:</strong> {ocrResult.validation.amounts.message}
              </div>
            )}

            {/* Duplicate warning */}
            {duplicate && (
              <div className="dup-banner">
                <div className="dup-banner-icon">??</div>
                <div className="dup-banner-body">
                  <p className="dup-banner-title">Duplicate Detected</p>
                  <p className="dup-banner-msg">{duplicate.message}</p>
                  <div className="dup-banner-actions">
                    <button className="btn btn-ghost" onClick={() => setDuplicate(null)}>Cancel</button>
                    <button className="btn btn-warning" onClick={() => handleSave(true)} disabled={saving}>
                      Save Anyway
                    </button>
                  </div>
                </div>
              </div>
            )}

            {saveError && <div className="error-banner">? {saveError}</div>}

            {/* Field editing grid */}
            <div className="ocr-fields-grid">
              {Object.entries(editedFields).map(([key, field]) => (
                <OcrFieldRow
                  key={key}
                  label={FIELD_LABELS[key] ?? key}
                  field={field}
                  onChange={(val) => handleFieldEdit(key, val)}
                />
              ))}
            </div>

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => { setStep("capture"); setOcrResult(null); }}>
                ? Re-scan
              </button>
              <button
                className="btn btn-primary"
                disabled={saving}
                onClick={() => handleSave(false)}
              >
                {saving ? <><span className="spinner" /> Saving…</> : "? Confirm & Save"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
