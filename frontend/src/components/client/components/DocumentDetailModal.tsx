import React, { useEffect, useState, useMemo } from "react";
import type { UploadedDocument, DocumentCategory } from "../../../types/document.types";
import { DOCUMENT_CATEGORIES } from "../../../types/document.types";
import { getDocument } from "../../../services/api/documents";
import apiClient from "../../../services/api/client";
import { CATEGORY_FIELDS, COMMON_INVOICE_FIELDS, AMOUNT_FIELDS } from "./UploadDocumentModal";

interface Props {
  docId: string;
  onClose: () => void;
}

type PreviewType = "pdf" | "image" | "none";

interface ParsedMetadata {
  fields?: Record<string, unknown>;
  line_items?: Array<Record<string, unknown>>;
  line_item_headers?: string[];
  field_verification?: Record<string, string>;
  extraction_method?: string;
  table_data?: { headers?: string[]; headers_raw?: string[]; rows?: Array<Record<string, unknown>> };
}

const CORE_KEYS = new Set([
  "invoice_number", "gstin", "invoice_date", "vendor", "customer",
  "amount", "taxable_amount", "cgst", "sgst", "igst", "cess", "hsn", "arn",
  "notice_number", "notice_date", "response_due_date", "priority",
  "gst_return_type", "financial_year", "month", "filed_date", "invoice_type",
  // Extended extracted fields
  "supplier_gstin", "customer_gstin", "place_of_supply", "reverse_charge",
  "payment_terms", "currency", "pan_number", "irn", "ack_number",
  "original_invoice_number", "reason", "document_type",
  "company_name", "report_title", "period_start", "period_end", "total_sales",
  "address", "mobile", "email",
  "vehicle_number", "transport_mode", "valid_until",
]);

const FIELD_ALIASES: Record<string, string[]> = {
  amount: ["amount", "total_amount", "grand_total", "net_amount", "total", "total_sales", "total_tax_paid", "note_value"],
  taxable_amount: ["taxable_amount", "taxable_value", "assessable_value", "basic_amount", "taxable_turnover"],
  invoice_number: ["invoice_number", "inv_no", "bill_no", "bill_number", "doc_no", "document_number", "notice_number", "cpin", "cin", "ref_no"],
  invoice_date: ["invoice_date", "bill_date", "doc_date", "date", "date_of_invoice", "notice_date", "payment_date", "filed_date", "generated_date"],
  vendor: ["vendor", "supplier", "seller", "party_name", "firm_name", "company_name", "supplier_name"],
  customer: ["customer", "buyer", "client_name", "recipient", "buyer_name", "consignee"],
  gstin: ["gstin", "supplier_gstin", "tin", "gst_no"],
  cgst: ["cgst", "cgst_amount", "cgst_tax"],
  sgst: ["sgst", "sgst_amount", "sgst_tax"],
  igst: ["igst", "igst_amount", "igst_tax"],
  cess: ["cess", "cess_amount"],
  hsn: ["hsn", "hsn_code", "sac", "hsn_sac"],
  supplier_gstin: ["supplier_gstin", "gstin"],
  customer_gstin: ["customer_gstin", "buyer_gstin", "recipient_gstin"],
  supplier_pan: ["pan", "pan_number", "taxpayer_pan"],
  customer_pan: ["buyer_pan", "recipient_pan", "client_pan"],
  contact_person: ["contact_name", "contact", "contact_person_name", "attn", "attention"],
  contact_phone: ["contact_no", "contact_number", "customer_phone", "mobile", "phone_no", "phone"],
  sales_person: ["salesperson", "sales_rep", "sales_person_name", "executive"],
  sales_person_contact: ["sales_person_phone", "salesperson_phone", "sales_rep_contact"],
  buyer_code: ["consignee_code", "customer_code"],
  cin: ["company_cin", "corporate_id", "cin_no"],
  pl_no: ["p_l_no", "pl_number"],
  fl_no: ["f_l_no", "fl_number"],
  transporter_name: ["transporter", "carrier", "logistics_provider"],
  transporter_location: ["transporter_place"],
};

const PREVIEW_IMAGE_EXT = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp"]);

const parseMetadata = (raw?: string | null): ParsedMetadata => {
  if (!raw) return {};
  try {
    const p = JSON.parse(raw);
    return typeof p === "object" && p !== null ? (p as ParsedMetadata) : {};
  } catch {
    return {};
  }
};

const formatValue = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return String(v);
    return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "object") {
    try { return JSON.stringify(v); } catch { return String(v); }
  }
  return String(v);
};

const isEmpty = (v: unknown): boolean => {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  if (typeof v === "number") return false;
  if (Array.isArray(v)) return v.length === 0;
  return false;
};

const humanizeKey = (k: string): string =>
  k.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());

const CANONICAL_LABELS: Record<string, string> = {
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
  if (!isEmpty(row[colKey])) return row[colKey];
  if (!isEmpty(row[colLabel])) return row[colLabel];

  const normKey = colKey.toLowerCase().replace(/[^a-z0-9]/g, "");
  const normLabel = colLabel.toLowerCase().replace(/[^a-z0-9]/g, "");

  for (const [rk, rv] of Object.entries(row)) {
    if (isEmpty(rv)) continue;
    const normRk = rk.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (normRk === normKey || normRk === normLabel) return rv;
  }

  const synonymGroups: Record<string, string[]> = {
    sr_no: ["sr_no", "sr", "s_no", "serial_no", "srno", "sno"],
    item_name: ["item_name", "item", "description", "particulars", "product", "product_name", "item_description"],
    company_name: ["company_name", "company", "brand", "manufacturer", "make"],
    hsn: ["hsn", "hsn_sac", "hsn_code", "sac"],
    batch_no: ["batch_no", "batch", "batchnumber", "lot_no", "lot"],
    expiry_date: ["expiry_date", "expiry", "exp_date", "expdate"],
    quantity: ["quantity", "qty", "nos", "units"],
    rate: ["rate", "price", "unit_price", "rate_per_no"],
    discount: ["discount", "disc", "disc_percent"],
    taxable_amount: ["taxable_amount", "taxable_value", "ass_amt", "assessable_value", "taxable"],
    cgst_amount: ["cgst_amount", "cgst", "cgst_amt"],
    sgst_amount: ["sgst_amount", "sgst", "sgst_amt"],
    igst_amount: ["igst_amount", "igst", "igst_amt"],
    total_amount: ["total_amount", "total", "amount", "net_amount"],
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

export const DocumentDetailModal: React.FC<Props> = ({ docId, onClose }) => {
  const [doc, setDoc] = useState<UploadedDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);

  const handleExtractItems = async () => {
    if (!docId) return;
    setExtracting(true);
    try {
      const res = await apiClient.post(`/invoices/document/${docId}/extract-items`);
      if (res.data?.data) {
        setDoc(res.data.data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setExtracting(false);
    }
  };

  const meta = useMemo(() => parseMetadata(doc?.metadata_ ?? null), [doc?.metadata_]);

  const previewType: PreviewType = useMemo(() => {
    const ext = (doc?.file_type ?? "").toLowerCase();
    if (ext === "pdf") return "pdf";
    if (PREVIEW_IMAGE_EXT.has(ext)) return "image";
    return "none";
  }, [doc?.file_type]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const d = await getDocument(docId);
        if (!cancelled) setDoc(d);
      } catch (err: unknown) {
        const e = err as { response?: { data?: { message?: string } }; message?: string };
        if (!cancelled) setError(e?.response?.data?.message ?? e?.message ?? "Failed to load document");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [docId]);

  useEffect(() => {
    if (!doc || !doc.file_path) return;
    let cancelled = false;
    let objUrl: string | null = null;
    (async () => {
      setPreviewLoading(true);
      setPreviewError(null);
      try {
        const res = await apiClient.get(`/invoices/document/${docId}/download`, {
          responseType: "blob",
        });
        if (cancelled) return;
        const blob = res.data as Blob;
        objUrl = URL.createObjectURL(blob);
        setPreviewUrl(objUrl);
      } catch {
        if (!cancelled) setPreviewError("Preview unavailable");
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [docId, doc?.file_path]);

  const catMeta = useMemo(
    () => DOCUMENT_CATEGORIES.find((c) => c.id === doc?.document_category) ?? null,
    [doc?.document_category]
  );

  const schemaFields = useMemo(() => {
    if (!doc) return [];
    return (
      CATEGORY_FIELDS[doc.document_category as DocumentCategory] ?? [
        ...COMMON_INVOICE_FIELDS,
        ...AMOUNT_FIELDS,
      ]
    );
  }, [doc]);

  const resolveFieldValue = (key: string): unknown => {
    if (!doc) return null;
    const metaFields = (meta.fields ?? {}) as Record<string, unknown>;
    const keysToCheck = [key, ...(FIELD_ALIASES[key] ?? [])];

    for (const k of keysToCheck) {
      // 1. Direct document model property
      const direct = (doc as unknown as Record<string, unknown>)[k];
      if (!isEmpty(direct)) return direct;

      // 2. Parsed meta.fields
      const rawMeta = metaFields[k];
      if (rawMeta && typeof rawMeta === "object" && !Array.isArray(rawMeta)) {
        const asField = rawMeta as Record<string, unknown>;
        if ("value" in asField && !isEmpty(asField.value)) return asField.value;
      }
      if (!isEmpty(rawMeta)) return rawMeta;

      // 3. Top-level meta
      const topMeta = (meta as Record<string, unknown>)[k];
      if (!isEmpty(topMeta) && typeof topMeta !== "object") return topMeta;
    }
    return null;
  };

  const standardRenderedFields = useMemo(() => {
    const rendered: Array<{ label: string; key: string; value: string }> = [];
    for (const fd of schemaFields) {
      const key = String(fd.key);
      const raw = resolveFieldValue(key);
      if (!isEmpty(raw)) {
        rendered.push({ label: fd.label, key, value: formatValue(raw) });
      }
    }
    return rendered;
  }, [schemaFields, doc, meta]);

  const additionalFields = useMemo(() => {
    const metaFields = (meta.fields ?? {}) as Record<string, unknown>;
    const schemaKeys = new Set(schemaFields.map((f) => String(f.key)));
    const skipKeys = new Set([
      "line_items", "line_item_headers", "table_data",
      "field_verification", "extraction_method",
    ]);
    const out: Array<{ label: string; key: string; value: string }> = [];
    for (const [k, v] of Object.entries(metaFields)) {
      if (schemaKeys.has(k)) continue;
      if (CORE_KEYS.has(k)) continue;
      if (skipKeys.has(k)) continue;
      // Unwrap OcrField-shaped objects: { value: string, confidence: string }
      let displayVal: unknown = v;
      if (v && typeof v === "object" && !Array.isArray(v)) {
        const asField = v as Record<string, unknown>;
        if ("value" in asField) displayVal = asField.value;
      }
      if (isEmpty(displayVal)) continue;
      out.push({ label: humanizeKey(k), key: k, value: formatValue(displayVal) });
    }
    return out;
  }, [meta, schemaFields]);

  const tableRows = useMemo(() => {
    // 1. Direct meta.table_data.rows
    if (Array.isArray(meta.table_data?.rows) && meta.table_data!.rows.length > 0) {
      return meta.table_data!.rows;
    }
    // 2. Nested meta.fields.table_data.rows
    const metaFields = (meta.fields ?? {}) as Record<string, unknown>;
    const nestedTd = metaFields.table_data as { headers?: string[]; rows?: Array<Record<string, unknown>> } | undefined;
    if (nestedTd && Array.isArray(nestedTd.rows) && nestedTd.rows.length > 0) {
      return nestedTd.rows;
    }
    // 3. Nested meta.fields.line_items
    if (Array.isArray(metaFields.line_items) && metaFields.line_items.length > 0) {
      return metaFields.line_items as Array<Record<string, unknown>>;
    }
    // 4. Direct meta.line_items
    if (Array.isArray(meta.line_items) && meta.line_items.length > 0) {
      return meta.line_items;
    }
    return [];
  }, [meta]);

  const hasTablePreview = useMemo(() => tableRows.length > 0, [tableRows]);

  const tableColumns = useMemo(() => {
    const td = meta.table_data;
    const metaFields = (meta.fields ?? {}) as Record<string, unknown>;
    const nestedTd = metaFields.table_data as { headers?: string[]; headers_raw?: string[] } | undefined;
    const activeTd = td || nestedTd;

    const headerKeys = (activeTd?.headers && activeTd.headers.length > 0) ? activeTd.headers : [];
    const headerLabels = (activeTd?.headers_raw && activeTd.headers_raw.length > 0) ? activeTd.headers_raw : [];

    const cols: Array<{ key: string; label: string }> = [];
    const seen = new Set<string>();

    if (headerKeys.length > 0) {
      headerKeys.forEach((k, idx) => {
        const label = headerLabels[idx] || CANONICAL_LABELS[k] || humanizeKey(k);
        if (!seen.has(k)) {
          seen.add(k);
          cols.push({ key: k, label });
        }
      });
    } else if (headerLabels.length > 0) {
      headerLabels.forEach((label) => {
        const k = Object.keys(CANONICAL_LABELS).find(ck => CANONICAL_LABELS[ck].toLowerCase() === label.toLowerCase()) 
               || label.toLowerCase().replace(/[^a-z0-9]/g, "_");
        if (!seen.has(label)) {
          seen.add(label);
          cols.push({ key: k, label });
        }
      });
    } else {
      const preferred = [
        "sr_no", "item_name", "company_name", "hsn", "batch_no", "expiry_date",
        "quantity", "rate", "discount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
      ];
      preferred.forEach((k) => {
        if (tableRows.some(r => !isEmpty((r as Record<string, unknown>)[k]))) {
          seen.add(k);
          cols.push({ key: k, label: CANONICAL_LABELS[k] || humanizeKey(k) });
        }
      });
      if (tableRows.length > 0 && typeof tableRows[0] === "object" && tableRows[0] !== null) {
        Object.keys(tableRows[0]).forEach((k) => {
          if (!seen.has(k) && !seen.has(k.toLowerCase())) {
            seen.add(k);
            cols.push({ key: k, label: CANONICAL_LABELS[k] || humanizeKey(k) });
          }
        });
      }
    }
    return cols;
  }, [meta, tableRows]);

  const openDownload = async () => {
    if (!doc) return;
    const token = localStorage.getItem("ca_token") || localStorage.getItem("token");
    const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
    const url = `${base}/invoices/document/${docId}/download${token ? `?token=${token}` : ""}`;
    const fileName = doc.file_name || `document-${docId}`;
    try {
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error("Failed");
      const blob = await res.blob();
      const bUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = bUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(bUrl), 1000);
    } catch {
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card"
        style={{ width: "min(1100px, 95vw)", maxHeight: "92vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-cat-icon">{catMeta?.icon ?? "📄"}</span>
            <div>
              <h2 className="modal-title">
                Document Details
                {catMeta && <span style={{ fontWeight: 400, fontSize: "0.85em", marginLeft: "0.5rem", opacity: 0.75 }}>— {catMeta.label}</span>}
              </h2>
              {doc?.file_name && (
                <p className="modal-subtitle" style={{ margin: 0 }}>
                  {doc.file_name} {doc.file_size && <span style={{ opacity: 0.65 }}>({doc.file_size})</span>}
                </p>
              )}
            </div>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {loading && (
          <div className="loading-state" style={{ padding: "3rem 0" }}>
            <div className="loading-spinner" />
            <p>Loading document details…</p>
          </div>
        )}

        {!loading && error && (
          <div className="error-banner" style={{ margin: "1rem" }}>⚠ {error}</div>
        )}

        {!loading && !error && doc && (
          <div className="doc-detail-body" style={{ display: "grid", gridTemplateColumns: "minmax(320px, 1fr) minmax(340px, 1.1fr)", gap: "1.25rem", padding: "0.75rem 1.25rem 0.5rem", overflow: "hidden" }}>
            <div className="doc-detail-left" style={{ overflowY: "auto", maxHeight: "68vh", paddingRight: "0.25rem" }}>
              <div className="detail-section" style={{ marginBottom: "1.25rem" }}>
                <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#6366f1", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.35rem" }}>
                  Document Information
                </h3>
                <div className="detail-field-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem 1rem" }}>
                  <div className="detail-field" style={{ gridColumn: "1 / -1" }}>
                    <span className="detail-label" style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "#6b7280", marginBottom: "0.1rem" }}>Document Category</span>
                    <span className="detail-value" style={{ fontSize: "0.95rem", fontWeight: 500 }}>
                      {catMeta?.label ?? doc.document_category}
                    </span>
                  </div>
                  {standardRenderedFields.map((f) => (
                    <div key={f.key} className="detail-field">
                      <span className="detail-label" style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "#6b7280", marginBottom: "0.1rem" }}>{f.label}</span>
                      <span className="detail-value" style={{ fontSize: "0.9rem" }}>{f.value || <span style={{ color: "#9ca3af", fontStyle: "italic" }}>Not available</span>}</span>
                    </div>
                  ))}
                  {standardRenderedFields.length === 0 && (
                    <div style={{ gridColumn: "1 / -1", color: "#6b7280", fontStyle: "italic", fontSize: "0.85rem" }}>
                      No standard fields populated.
                    </div>
                  )}
                </div>
              </div>

              {!hasTablePreview && previewType !== "none" && (
                <div style={{ margin: "0 0 1.25rem", padding: "0.75rem", borderRadius: "6px", border: "1px dashed #6366f1", background: "#f5f3ff", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                  <span style={{ fontSize: "0.75rem", color: "#4b5563" }}>
                    <strong style={{ color: "#1f2937" }}>Extract Line Items:</strong> Fetch individual product rows, rates, quantities & taxes using AI.
                  </span>
                  <button
                    onClick={handleExtractItems}
                    disabled={extracting}
                    style={{ padding: "0.35rem 0.75rem", background: "#6366f1", color: "#fff", border: "none", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 500, cursor: extracting ? "not-allowed" : "pointer", whiteSpace: "nowrap" }}
                  >
                    {extracting ? "Extracting…" : "✨ Extract Products"}
                  </button>
                </div>
              )}

              {hasTablePreview && (
                <div className="detail-section" style={{ marginBottom: "1.25rem" }}>
                  <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#6366f1", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.35rem" }}>
                    Line Items
                  </h3>
                  <div style={{ overflowX: "auto", borderRadius: "6px", border: "1px solid #e5e7eb" }}>
                    <table className="detail-line-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                      <thead style={{ background: "#f3f4f6" }}>
                        <tr>
                          {tableColumns.map((col, i) => (
                            <th key={col.key || i} style={{ padding: "0.45rem 0.6rem", textAlign: "left", borderBottom: "1px solid #e5e7eb", fontWeight: 600, whiteSpace: "nowrap" }}>
                              {col.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tableRows.slice(0, 12).map((row, ri) => (
                          <tr key={ri} style={{ background: ri % 2 === 0 ? "#ffffff" : "#fafafa" }}>
                            {tableColumns.map((col, ci) => {
                              const val = getTableCellValue(row as Record<string, unknown>, col.key, col.label);
                              return (
                                <td key={ci} style={{ padding: "0.35rem 0.6rem", borderBottom: "1px solid #f3f4f6", whiteSpace: "nowrap" }}>
                                  {formatValue(val) || <span style={{ color: "#9ca3af" }}>—</span>}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(tableRows.length > 12) && (
                    <p style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.4rem" }}>
                      Showing 12 of {tableRows.length} rows.
                    </p>
                  )}
                </div>
              )}

              {additionalFields.length > 0 && (
                <div className="detail-section">
                  <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#6366f1", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.35rem" }}>
                    Additional Details
                  </h3>
                  <div className="detail-field-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem 1rem" }}>
                    {additionalFields.map((f) => (
                      <div key={f.key} className="detail-field">
                        <span className="detail-label" style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "#6b7280", marginBottom: "0.1rem" }}>{f.label}</span>
                        <span className="detail-value" style={{ fontSize: "0.85rem", wordBreak: "break-word" }}>{f.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="doc-detail-right" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <h3 style={{ margin: 0, fontSize: "0.95rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#6366f1", borderBottom: "1px solid #e5e7eb", paddingBottom: "0.35rem", flex: 1 }}>
                  Document Preview
                </h3>
              </div>
              <div
                className="doc-preview-container"
                style={{
                  flex: 1,
                  minHeight: "50vh",
                  maxHeight: "68vh",
                  background: "#f9fafb",
                  borderRadius: "8px",
                  border: "1px solid #e5e7eb",
                  overflow: "hidden",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {previewLoading && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", color: "#6b7280" }}>
                    <div className="loading-spinner" />
                    <span style={{ fontSize: "0.85rem" }}>Loading preview…</span>
                  </div>
                )}
                {!previewLoading && previewError && (
                  <div style={{ textAlign: "center", padding: "1.5rem", color: "#6b7280" }}>
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🗂️</div>
                    <p style={{ margin: "0 0 0.5rem", fontSize: "0.9rem" }}>{previewError}</p>
                    <button className="btn btn-secondary" onClick={openDownload}>Download Document</button>
                  </div>
                )}
                {!previewLoading && !previewError && previewType === "pdf" && previewUrl && (
                  <iframe
                    src={previewUrl}
                    title="PDF Preview"
                    style={{ width: "100%", height: "100%", border: "none" }}
                  />
                )}
                {!previewLoading && !previewError && previewType === "image" && previewUrl && (
                  <img
                    src={previewUrl}
                    alt="Document preview"
                    style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                  />
                )}
                {!previewLoading && !previewError && previewType === "none" && (
                  <div style={{ textAlign: "center", padding: "1.5rem", color: "#6b7280" }}>
                    <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>📎</div>
                    <p style={{ margin: "0 0 0.5rem", fontSize: "0.95rem", fontWeight: 500 }}>
                      Browser preview not available for this file type
                    </p>
                    <p style={{ margin: "0 0 1rem", fontSize: "0.8rem", opacity: 0.8 }}>
                      {doc.file_type ? doc.file_type.toUpperCase() : "Unknown"} format
                    </p>
                    <button className="btn btn-primary" onClick={openDownload}>Download / Open</button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="modal-footer" style={{ justifyContent: "space-between" }}>
          <button
            className="btn btn-secondary"
            onClick={openDownload}
            disabled={loading || !doc?.file_path}
          >
            ⬇ Download Document
          </button>
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
};
