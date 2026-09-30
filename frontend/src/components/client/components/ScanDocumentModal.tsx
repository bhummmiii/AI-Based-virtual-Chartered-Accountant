// ============================================================
// ScanDocumentModal — OCR with single & multi-record support
// ============================================================
import React, { useState, useRef, useCallback } from "react";
import type {
  DocumentCategory,
  OcrExtractResponse,
  OcrField,
  OcrRecord,
  OcrLineItem,
  DocumentUploadPayload,
  DuplicateResponse,
} from "../../../types/document.types";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import { ocrExtract, uploadDocument } from "../../../services/api/documents";
import { CATEGORY_FIELDS, COMMON_INVOICE_FIELDS, AMOUNT_FIELDS } from "./UploadDocumentModal";

interface Props {
  clientId: string;
  category: DocumentCategory;
  onClose: () => void;
  onSuccess: () => void;
}

type ScanStep = "capture" | "review";

// ── Confidence badge ─────────────────────────────────────────────
const ConfidenceBadge: React.FC<{ confidence: OcrField["confidence"] }> = ({ confidence }) => {
  const labels = { extracted: "Extracted", needs_review: "Needs Review", missing: "Missing" } as const;
  const classes = { extracted: "badge-extracted", needs_review: "badge-review", missing: "badge-missing" } as const;
  return <span className={`ocr-badge ${classes[confidence]}`}>{labels[confidence]}</span>;
};

// ── Editable field row ───────────────────────────────────────────
interface OcrFieldRowProps {
  label: string; fieldKey: string; value: string;
  confidence?: OcrField["confidence"]; onChange: (v: string) => void;
}
const OcrFieldRow: React.FC<OcrFieldRowProps> = ({ label, fieldKey, value, confidence = "extracted", onChange }) => (
  <div className="ocr-field-row">
    <div className="ocr-field-meta">
      <span className="ocr-field-label">{label}</span>
      <ConfidenceBadge confidence={confidence} />
    </div>
    <input
      id={`ocr-field-${fieldKey}`}
      className={`form-input ocr-input${confidence === "needs_review" ? " input-warn" : ""}`}
      value={value} onChange={(e) => onChange(e.target.value)}
      placeholder={confidence === "missing" ? "(not detected)" : undefined}
    />
  </div>
);

// ── Line items mini-table ────────────────────────────────────────
const LineItemsTable: React.FC<{ headers: string[]; items: OcrLineItem[] }> = ({ headers, items }) => {
  if (!items.length) return null;
  return (
    <div className="ocr-table-preview" style={{ marginTop: "0.75rem" }}>
      <div className="ocr-table-header">
        <span className="ocr-table-title">Line Items</span>
        <span className="ocr-table-count">{items.length} item{items.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="ocr-table-scroll">
        <table className="ocr-table">
          <thead>
            <tr>{headers.map((h, i) => <th key={i} className="ocr-th">{h.replace(/_/g, " ")}</th>)}</tr>
          </thead>
          <tbody>
            {items.slice(0, 8).map((row, ri) => (
              <tr key={ri} className={ri % 2 === 0 ? "ocr-tr-even" : "ocr-tr-odd"}>
                {headers.map((h, ci) => <td key={ci} className="ocr-td">{row[h] ?? ""}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {items.length > 8 && <p className="ocr-table-more">Showing 8 of {items.length} items. All will be saved.</p>}
    </div>
  );
};

// ── Record card (collapsible) ────────────────────────────────────
interface RecordCardProps {
  record: OcrRecord; index: number; category: DocumentCategory;
  saveStatus: "idle" | "saving" | "saved" | "error"; saveError?: string;
  onFieldChange: (i: number, k: string, v: string) => void;
  isOpen: boolean; onToggle: () => void;
  ocrResult: OcrExtractResponse | null;
}
const RecordCard: React.FC<RecordCardProps> = ({
  record, index, category, saveStatus, saveError, onFieldChange, isOpen, onToggle,
  ocrResult,
}) => {
  const schemaFields = CATEGORY_FIELDS[category] ?? [...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS];
  const invNum = record.fields.invoice_number || `Record ${record.record_number}`;
  const party = record.fields.customer || record.fields.vendor || "";
  const amt = record.fields.amount || "";

  // FIX 5: value/confidence fallback chain.
  // Priority: record.fields[k] -> ocrResult.core_fields[k].value ->
  // ocrResult.metadata_fields[k].value -> "".
  const resolveField = (k: string): { value: string; confidence: OcrField["confidence"] } => {
    const recVal = (record.fields as Record<string, string | undefined>)[k];
    if (recVal !== undefined && recVal !== null && String(recVal).trim() !== "") {
      return { value: String(recVal), confidence: "extracted" };
    }
    const core = (ocrResult?.core_fields as Record<string, OcrField | undefined> | null)?.[k];
    if (core && core.value && core.value.trim() !== "") {
      return { value: core.value, confidence: core.confidence ?? "extracted" };
    }
    const meta = (ocrResult?.metadata_fields as Record<string, OcrField | undefined> | null)?.[k];
    if (meta && meta.value && meta.value.trim() !== "") {
      return { value: meta.value, confidence: meta.confidence ?? "extracted" };
    }
    return { value: "", confidence: "missing" };
  };

  return (
    <div className={`record-card${isOpen ? " record-card--open" : ""}${saveStatus === "saved" ? " record-card--saved" : ""}${saveStatus === "error" ? " record-card--error" : ""}`}>
      <button className="record-card-header" onClick={onToggle} type="button">
        <div className="rc-header-left">
          <span className="rc-num">#{index + 1}</span>
          <div className="rc-title-group">
            <span className="rc-inv-num">{invNum}</span>
            {party && <span className="rc-party">{party}</span>}
          </div>
        </div>
        <div className="rc-header-right">
          {amt && <span className="rc-amount">Rs. {amt}</span>}
          {record.line_items.length > 0 && (
            <span className="rc-items-badge">{record.line_items.length} item{record.line_items.length !== 1 ? "s" : ""}</span>
          )}
          {saveStatus === "saving" && <span className="spinner" style={{ marginLeft: "0.5rem" }} />}
          {saveStatus === "saved" && <span className="rc-status-saved">Saved</span>}
          {saveStatus === "error" && <span className="rc-status-error">Failed</span>}
          <span className="rc-chevron">{isOpen ? "▲" : "▼"}</span>
        </div>
      </button>

      {isOpen && (
        <div className="record-card-body">
          {saveStatus === "error" && saveError && (
            <div className="error-banner" style={{ marginBottom: "0.75rem" }}>{saveError}</div>
          )}
          <div className="ocr-fields-grid">
            {schemaFields.map((fd) => {
              const { value, confidence } = resolveField(fd.key as string);
              return (
                <OcrFieldRow key={fd.key as string} label={fd.label} fieldKey={fd.key as string}
                  value={value} confidence={confidence}
                  onChange={(v) => onFieldChange(index, fd.key as string, v)} />
              );
            })}
          </div>
          {record.line_items.length > 0 && record.headers && record.headers.length > 0 && (
            <LineItemsTable headers={record.headers} items={record.line_items} />
          )}
        </div>
      )}
    </div>
  );
};

// ── Main component ───────────────────────────────────────────────
export const ScanDocumentModal: React.FC<Props> = ({ clientId, category, onClose, onSuccess }) => {
  const catMeta = DOCUMENT_CATEGORIES.find((c) => c.id === category);
  const fileRef = useRef<HTMLInputElement>(null);

  const [step, setStep]                   = useState<ScanStep>("capture");
  const [selectedFile, setSelectedFile]   = useState<File | null>(null);
  const [previewUrl, setPreviewUrl]       = useState<string | null>(null);
  const [scanning, setScanning]           = useState(false);
  const [scanError, setScanError]         = useState<string | null>(null);
  const [ocrResult, setOcrResult]         = useState<OcrExtractResponse | null>(null);

  // multi-record state
  const [records, setRecords]             = useState<OcrRecord[]>([]);
  const [openCards, setOpenCards]         = useState<boolean[]>([]);
  const [saveStatuses, setSaveStatuses]   = useState<Array<"idle" | "saving" | "saved" | "error">>([]);
  const [saveErrors, setSaveErrors]       = useState<string[]>([]);
  const [saveProgress, setSaveProgress]   = useState<{ done: number; total: number } | null>(null);

  // single-record state
  const [editedFields, setEditedFields]   = useState<Record<string, OcrField>>({});
  const [duplicate, setDuplicate]         = useState<DuplicateResponse | null>(null);
  const [saveError, setSaveError]         = useState<string | null>(null);
  const [saving, setSaving]               = useState(false);

  // ── Handlers ────────────────────────────────────────────────
  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setSelectedFile(f); setScanError(null);
    setPreviewUrl(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
  };

  const handleScan = async () => {
    if (!selectedFile) return;
    setScanning(true); setScanError(null);
    try {
      const result = await ocrExtract(selectedFile, category);
      if (!result.has_content) {
        setScanError(result.message || "No document text detected. Please upload a clearer image or digital PDF.");
        return;
      }
      setOcrResult(result);
      const recs = result.records ?? [];
      setRecords(recs);
      setOpenCards(recs.map((_, i) => i === 0));
      setSaveStatuses(recs.map(() => "idle"));
      setSaveErrors(recs.map(() => ""));
      setEditedFields({ ...result.core_fields, ...result.metadata_fields });
      setStep("review");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string; message?: string } }; message?: string };
      setScanError(e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.message ?? "Scan failed.");
    } finally { setScanning(false); }
  };

  const toggleCard = useCallback(
    (idx: number) => setOpenCards((p) => p.map((v, i) => (i === idx ? !v : v))),
    []
  );

  const handleRecordFieldChange = useCallback((ri: number, k: string, v: string) =>
    setRecords((p) => p.map((r, i) => i === ri ? { ...r, fields: { ...r.fields, [k]: v } } : r)),
    []
  );

  const handleSingleFieldEdit = (k: string, v: string) =>
    setEditedFields((p) => ({ ...p, [k]: { value: v, confidence: "extracted" } }));

  // ── Payload builders ─────────────────────────────────────────
  const CORE_DB_KEYS = new Set([
    "invoice_number", "gstin", "invoice_date", "vendor", "customer",
    "amount", "taxable_amount", "cgst", "sgst", "igst", "cess", "hsn", "arn",
    "notice_number", "notice_date", "response_due_date", "priority",
    "gst_return_type", "financial_year", "month", "filed_date",
  ]);

  const buildFromRecord = (rec: OcrRecord, file: File | null): DocumentUploadPayload => {
    const f = rec.fields as Record<string, string | undefined>;
    // FIX 6: Resolve a value with fallback priority:
    // 1. record.fields[k]   (user-edited value is already written back here by handleRecordFieldChange)
    // 2. ocrResult.core_fields[k].value
    // 3. ocrResult.metadata_fields[k].value
    // 4. empty -> undefined
    const resolve = (k: string): string | undefined => {
      const recVal = f[k];
      if (recVal !== undefined && recVal !== null && String(recVal).trim() !== "") {
        return String(recVal);
      }
      const core = (ocrResult?.core_fields as Record<string, OcrField | undefined> | null)?.[k];
      if (core?.value && core.value.trim() !== "") return core.value;
      const meta = (ocrResult?.metadata_fields as Record<string, OcrField | undefined> | null)?.[k];
      if (meta?.value && meta.value.trim() !== "") return meta.value;
      return undefined;
    };

    const meta: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) { if (!CORE_DB_KEYS.has(k) && v) meta[k] = v; }
    if (rec.line_items.length > 0) {
      meta["line_items"] = rec.line_items;
      if (rec.headers) meta["line_item_headers"] = rec.headers;
    }
    return {
      document_category: category, document_type: "scan",
      invoice_number: resolve("invoice_number"), gstin: resolve("gstin"),
      invoice_date: resolve("invoice_date"), vendor: resolve("vendor"),
      customer: resolve("customer"), amount: resolve("amount"),
      taxable_amount: resolve("taxable_amount"), cgst: resolve("cgst"),
      sgst: resolve("sgst"), igst: resolve("igst"), cess: resolve("cess"),
      hsn: resolve("hsn"), arn: resolve("arn"),
      notice_number: resolve("notice_number"), notice_date: resolve("notice_date"),
      response_due_date: resolve("response_due_date"), priority: resolve("priority"),
      gst_return_type: resolve("gst_return_type"), financial_year: resolve("financial_year"),
      month: resolve("month"), filed_date: resolve("filed_date"),
      metadata_json: Object.keys(meta).length > 0 ? JSON.stringify(meta) : undefined,
      extraction_method: ocrResult?.extraction_method || undefined,
      force_save: "false", file: file ?? undefined,
    };
  };

  const buildFromFields = (f: Record<string, OcrField>, force: boolean): DocumentUploadPayload => {
    const overflow: Record<string, string> = {};
    for (const [k, v] of Object.entries(f)) { if (!CORE_DB_KEYS.has(k) && v.value) overflow[k] = v.value; }
    const meta: Record<string, unknown> = { ...overflow };
    if (ocrResult?.table_data && (ocrResult.table_data.rows?.length ?? 0) > 0)
      meta["table_data"] = ocrResult.table_data;
    return {
      document_category: category, document_type: "scan",
      invoice_number: f.invoice_number?.value || undefined, gstin: f.gstin?.value || undefined,
      invoice_date: f.invoice_date?.value || undefined, vendor: f.vendor?.value || undefined,
      customer: f.customer?.value || undefined, amount: f.amount?.value || undefined,
      taxable_amount: f.taxable_amount?.value || undefined, cgst: f.cgst?.value || undefined,
      sgst: f.sgst?.value || undefined, igst: f.igst?.value || undefined, cess: f.cess?.value || undefined,
      hsn: f.hsn?.value || undefined, arn: f.arn?.value || undefined,
      notice_number: f.notice_number?.value || undefined, notice_date: f.notice_date?.value || undefined,
      response_due_date: f.response_due_date?.value || undefined, priority: f.priority?.value || undefined,
      gst_return_type: f.gst_return_type?.value || undefined, financial_year: f.financial_year?.value || undefined,
      month: f.month?.value || undefined, filed_date: f.filed_date?.value || undefined,
      metadata_json: Object.keys(meta).length > 0 ? JSON.stringify(meta) : undefined,
      field_verification: JSON.stringify(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.confidence]))),
      extraction_method: ocrResult?.extraction_method || undefined,
      force_save: force ? "true" : "false", file: selectedFile ?? undefined,
    };
  };

  // ── Save handlers ─────────────────────────────────────────────
  const handleSaveAll = async () => {
    setSaveProgress({ done: 0, total: records.length });
    let anyOk = false;
    for (let i = 0; i < records.length; i++) {
      if (saveStatuses[i] === "saved") {
        setSaveProgress((p) => p && { ...p, done: p.done + 1 });
        continue;
      }
      setSaveStatuses((p) => p.map((s, idx) => idx === i ? "saving" : s));
      try {
        await uploadDocument(clientId, buildFromRecord(records[i], selectedFile));
        setSaveStatuses((p) => p.map((s, idx) => idx === i ? "saved" : s));
        anyOk = true;
      } catch (err: unknown) {
        const e = err as { response?: { data?: { detail?: string; message?: string } }; message?: string };
        const msg = e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.message ?? "Save failed";
        setSaveStatuses((p) => p.map((s, idx) => idx === i ? "error" : s));
        setSaveErrors((p) => p.map((v, idx) => idx === i ? msg : v));
      }
      setSaveProgress((p) => p && { ...p, done: p.done + 1 });
    }
    if (anyOk) onSuccess();
  };

  const handleSingleSave = async (force = false) => {
    setSaving(true); setSaveError(null);
    try {
      const res = await uploadDocument(clientId, buildFromFields(editedFields, force));
      if (res.type === "duplicate") setDuplicate(res.info); else onSuccess();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string; detail?: string } }; message?: string };
      setSaveError(e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.message ?? "Save failed");
    } finally { setSaving(false); }
  };

  // ── Derived values ────────────────────────────────────────────
  const isMulti       = (ocrResult?.record_count ?? 0) > 1;
  const isSavingAny   = saveStatuses.some((s) => s === "saving");
  const allDone       = records.length > 0 && saveStatuses.every((s) => s === "saved" || s === "error");
  const savedCount    = saveStatuses.filter((s) => s === "saved").length;
  const failedCount   = saveStatuses.filter((s) => s === "error").length;
  const extractedCnt  = Object.values(editedFields).filter((f) => f.confidence === "extracted").length;
  const reviewCnt     = Object.values(editedFields).filter((f) => f.confidence === "needs_review").length;
  const schemaFields  = CATEGORY_FIELDS[category] ?? [...COMMON_INVOICE_FIELDS, ...AMOUNT_FIELDS];
  const singleFields  = Object.entries(editedFields).filter(([, f]) => f.confidence !== "missing");

  // ── Render ───────────────────────────────────────────────────
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className={`modal-card scan-modal${step === "review" ? (isMulti ? " scan-modal--multi" : " scan-modal--wide") : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ────────────────────────────────────────── */}
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-cat-icon">{catMeta?.icon}</span>
            <div>
              <h2 className="modal-title">
                {step === "capture" ? `Scan ${catMeta?.label}` : `Review — ${catMeta?.label}`}
              </h2>
              {step === "review" && isMulti && (
                <p className="modal-subtitle">{ocrResult?.record_count} invoice records detected</p>
              )}
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {/* ── CAPTURE step ──────────────────────────────────── */}
        {step === "capture" && (
          <div className="scan-capture-body">
            <div
              className="scan-dropzone"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files[0];
                if (f) { setSelectedFile(f); setPreviewUrl(f.type.startsWith("image/") ? URL.createObjectURL(f) : null); }
              }}
            >
              {previewUrl ? (
                <img src={previewUrl} alt="Document preview" className="scan-preview-img" />
              ) : selectedFile ? (
                <div className="scan-file-picked">
                  <span className="scan-file-icon">📄</span>
                  <span className="scan-file-name">{selectedFile.name}</span>
                  <span className="scan-file-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                </div>
              ) : (
                <div className="scan-dropzone-empty">
                  <span className="scan-drop-icon">📂</span>
                  <p>Drop your document here or <u>browse</u></p>
                  <p className="scan-drop-hint">PDF, JPG, PNG, DOCX — max 50 MB</p>
                  <p className="scan-drop-hint" style={{ color: "#a78bfa", marginTop: "0.25rem" }}>
                    Multi-invoice PDFs are fully supported
                  </p>
                </div>
              )}
            </div>
            <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.docx,.txt"
              style={{ display: "none" }} onChange={handleFilePick} />
            {scanError && <div className="error-banner">{scanError}</div>}
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={!selectedFile || scanning} onClick={handleScan}>
                {scanning ? <><span className="spinner" /> Scanning…</> : "🔍 Scan Document"}
              </button>
            </div>
          </div>
        )}

        {/* ── REVIEW — MULTI-RECORD ─────────────────────────── */}
        {step === "review" && ocrResult && isMulti && (
          <div className="scan-review-body scan-review-body--multi">
            {ocrResult.extraction_method && (
              <div className="extraction-method-banner">
                <span className="em-label">Extraction:</span>
                <span className="em-value">{ocrResult.extraction_method.replace(/_/g, " ")}</span>
                <span className="em-sep">·</span>
                <span className="em-value em-table">{ocrResult.record_count} records</span>
                {(ocrResult.extraction_summary?.table_rows_found ?? 0) > 0 && (
                  <><span className="em-sep">·</span>
                  <span className="em-value">{ocrResult.extraction_summary!.table_rows_found} table rows</span></>
                )}
              </div>
            )}
            {ocrResult.validation.warnings.length > 0 && (
              <div className="validation-warnings">
                <p className="validation-warnings-title">⚠️ Warnings</p>
                <ul>{ocrResult.validation.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </div>
            )}
            {saveProgress && (
              <div className="multi-save-progress">
                <div className="msp-bar">
                  <div className="msp-fill" style={{ width: `${(saveProgress.done / saveProgress.total) * 100}%` }} />
                </div>
                <span className="msp-label">
                  {saveProgress.done}/{saveProgress.total}
                  {savedCount > 0 && ` · ${savedCount} saved`}
                  {failedCount > 0 && ` · ${failedCount} failed`}
                </span>
              </div>
            )}
            <div className="record-cards-list">
              {records.map((rec, i) => (
                <RecordCard key={i} record={rec} index={i} category={category}
                  saveStatus={saveStatuses[i] ?? "idle"} saveError={saveErrors[i]}
                  onFieldChange={handleRecordFieldChange}
                  isOpen={openCards[i] ?? false} onToggle={() => toggleCard(i)}
                  ocrResult={ocrResult} />
              ))}
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => { setStep("capture"); setOcrResult(null); }}>
                ↩ Re-scan
              </button>
              {allDone && savedCount > 0 ? (
                <button className="btn btn-primary" onClick={onSuccess}>✓ Done ({savedCount} saved)</button>
              ) : (
                <button className="btn btn-primary" disabled={isSavingAny} onClick={handleSaveAll}>
                  {isSavingAny ? <><span className="spinner" /> Saving…</> : `✓ Save All ${records.length} Records`}
                </button>
              )}
            </div>
          </div>
        )}

        {/* ── REVIEW — SINGLE RECORD ────────────────────────── */}
        {step === "review" && ocrResult && !isMulti && (
          <div className="scan-review-body">
            {ocrResult.extraction_method && (
              <div className="extraction-method-banner">
                <span className="em-label">Extraction:</span>
                <span className="em-value">{ocrResult.extraction_method.replace(/_/g, " ")}</span>
                {(ocrResult.extraction_summary?.fields_found ?? 0) > 0 && (
                  <><span className="em-sep">·</span>
                  <span className="em-value">{ocrResult.extraction_summary!.fields_found} fields</span></>
                )}
                {(ocrResult.extraction_summary?.table_rows_found ?? 0) > 0 && (
                  <><span className="em-sep">·</span>
                  <span className="em-value em-table">{ocrResult.extraction_summary!.table_rows_found} table rows</span></>
                )}
              </div>
            )}
            {ocrResult.validation.warnings.length > 0 && (
              <div className="validation-warnings">
                <p className="validation-warnings-title">⚠️ Validation Warnings</p>
                <ul>{ocrResult.validation.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </div>
            )}
            <div className="confidence-summary">
              {extractedCnt > 0 && <span className="cs-item cs-extracted">✓ {extractedCnt} Extracted</span>}
              {reviewCnt > 0    && <span className="cs-item cs-review">⚠ {reviewCnt} Needs Review</span>}
              {(ocrResult.table_data?.rows?.length ?? 0) > 0 && (
                <span className="cs-item cs-table">📋 {ocrResult.table_data!.rows.length} Table Rows</span>
              )}
            </div>
            {ocrResult.validation.gstin && (
              <div className={`gstin-validation ${ocrResult.validation.gstin.valid ? "gstin-valid" : "gstin-invalid"}`}>
                <strong>GSTIN:</strong> {ocrResult.validation.gstin.message}
                {ocrResult.validation.gstin.normalized && (
                  <span className="gstin-normalized"> → {ocrResult.validation.gstin.normalized}</span>
                )}
              </div>
            )}
            {ocrResult.validation.amounts && ocrResult.validation.amounts.ok !== null && (
              <div className={`amount-validation ${ocrResult.validation.amounts.ok !== false ? "amount-ok" : "amount-warn"}`}>
                <strong>Amount Check:</strong> {ocrResult.validation.amounts.message}
              </div>
            )}
            {duplicate && (
              <div className="dup-banner">
                <div className="dup-banner-icon">⚠️</div>
                <div className="dup-banner-body">
                  <p className="dup-banner-title">Duplicate Detected</p>
                  <p className="dup-banner-msg">{duplicate.message}</p>
                  <div className="dup-banner-actions">
                    <button className="btn btn-ghost" onClick={() => setDuplicate(null)}>Cancel</button>
                    <button className="btn btn-warning" onClick={() => handleSingleSave(true)} disabled={saving}>
                      Save Anyway
                    </button>
                  </div>
                </div>
              </div>
            )}
            {saveError && <div className="error-banner">⚠ {saveError}</div>}

            {/* Table preview */}
            {ocrResult.table_data && (ocrResult.table_data.rows?.length ?? 0) > 0 && (
              <div className="ocr-table-preview">
                <div className="ocr-table-header">
                  <span className="ocr-table-title">📋 Extracted Table</span>
                  <span className="ocr-table-count">{ocrResult.table_data.rows.length} rows</span>
                </div>
                <div className="ocr-table-scroll">
                  <table className="ocr-table">
                    <thead>
                      <tr>
                        {(ocrResult.table_data.headers_raw ?? ocrResult.table_data.headers).map((h, i) => (
                          <th key={i} className="ocr-th">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {ocrResult.table_data.rows.slice(0, 10).map((row, ri) => (
                        <tr key={ri} className={ri % 2 === 0 ? "ocr-tr-even" : "ocr-tr-odd"}>
                          {ocrResult.table_data!.headers.map((k, ci) => (
                            <td key={ci} className="ocr-td">{row[k] ?? ""}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {ocrResult.table_data.rows.length > 10 && (
                  <p className="ocr-table-more">
                    Showing 10 of {ocrResult.table_data.rows.length} rows. All will be saved.
                  </p>
                )}
              </div>
            )}

            {/* Fields */}
            {singleFields.length > 0 && (
              <div className="ocr-fields-section">
                <p className="ocr-fields-section-title">📝 Document Fields</p>
                <div className="ocr-fields-grid">
                  {singleFields.map(([key, field]) => {
                    const match = schemaFields.find((f) => f.key === key);
                    const label = match?.label ?? key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
                    return (
                      <OcrFieldRow key={key} label={label} fieldKey={key}
                        value={field.value} confidence={field.confidence}
                        onChange={(v) => handleSingleFieldEdit(key, v)} />
                    );
                  })}
                </div>
              </div>
            )}
            {singleFields.length === 0 && (ocrResult.table_data?.rows?.length ?? 0) === 0 && (
              <div className="ocr-no-content">
                <p>⚠️ No fields or table rows detected. You can still save this document.</p>
              </div>
            )}

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => { setStep("capture"); setOcrResult(null); }}>
                ↩ Re-scan
              </button>
              <button className="btn btn-primary" disabled={saving} onClick={() => handleSingleSave(false)}>
                {saving ? <><span className="spinner" /> Saving…</> : "✓ Confirm & Save"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
