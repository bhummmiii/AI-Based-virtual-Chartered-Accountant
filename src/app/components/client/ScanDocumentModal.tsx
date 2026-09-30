/**
 * ScanDocumentModal — Step 2 (Scan path)
 * Allows camera/file upload → calls backend OCR API →
 * shows editable preview → saves to backend.
 *
 * Stages:
 *   idle       — drop zone
 *   scanning   — calling OCR
 *   no_content — OCR ran but found no document text (face/blank/random image)
 *                → Save button is BLOCKED, only "Try another file" is shown
 *   preview    — OCR found text, fields shown, Save is enabled
 *   error      — network/server error
 */
import { useEffect, useRef, useState } from "react";
import {
  ScanLine, Loader2, CheckCircle2, AlertCircle, FileText,
  ImageOff, PenLine, Package,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Badge } from "../ui/badge";
import { type DocumentCategory } from "./DocumentCategoryModal";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  category: DocumentCategory | null;
  clientId: string;
  onSuccess: () => void;
}

type Stage = "idle" | "scanning" | "no_content" | "preview" | "error";

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

interface OcrResult {
  fields: Record<string, string>;
  message: string;
  rawText: string;
  hasContent: boolean;
}

/**
 * Category field definitions — mirrors UploadDocumentModal DynamicFields.
 * key: DB/API field key, label: human-readable label.
 */
const CATEGORY_FIELDS: Record<string, { key: string; label: string }[]> = {
  sales_records: [
    { key: "vendor", label: "Company / Vendor" },
    { key: "invoice_number", label: "Invoice Number" },
    { key: "invoice_date", label: "Invoice Date" },
    { key: "customer", label: "Customer" },
    { key: "gstin", label: "GSTIN" },
    { key: "hsn", label: "HSN Code" },
    { key: "taxable_amount", label: "Taxable Amount (₹)" },
    { key: "cgst", label: "CGST (₹)" },
    { key: "sgst", label: "SGST (₹)" },
    { key: "igst", label: "IGST (₹)" },
    { key: "cess", label: "CESS (₹)" },
    { key: "amount", label: "Total Amount (₹)" },
  ],
  b2b_invoice: [
    { key: "vendor", label: "Company / Vendor" },
    { key: "invoice_number", label: "Invoice Number" },
    { key: "invoice_date", label: "Invoice Date" },
    { key: "customer", label: "Customer" },
    { key: "gstin", label: "GSTIN" },
    { key: "hsn", label: "HSN Code" },
    { key: "taxable_amount", label: "Taxable Amount (₹)" },
    { key: "cgst", label: "CGST (₹)" },
    { key: "sgst", label: "SGST (₹)" },
    { key: "igst", label: "IGST (₹)" },
    { key: "cess", label: "CESS (₹)" },
    { key: "amount", label: "Total Amount (₹)" },
  ],
  purchase_records: [
    { key: "vendor", label: "Vendor" },
    { key: "gstin", label: "GSTIN" },
    { key: "invoice_number", label: "Invoice Number" },
    { key: "invoice_date", label: "Purchase Date" },
    { key: "hsn", label: "HSN Code" },
    { key: "taxable_amount", label: "Taxable Amount (₹)" },
    { key: "cgst", label: "CGST (₹)" },
    { key: "sgst", label: "SGST (₹)" },
    { key: "igst", label: "IGST (₹)" },
    { key: "cess", label: "CESS (₹)" },
    { key: "amount", label: "Total Amount (₹)" },
  ],
  b2c_invoice: [
    { key: "customer", label: "Customer" },
    { key: "invoice_number", label: "Invoice Number" },
    { key: "invoice_date", label: "Invoice Date" },
    { key: "hsn", label: "HSN Code" },
    { key: "taxable_amount", label: "Taxable Amount (₹)" },
    { key: "cgst", label: "CGST (₹)" },
    { key: "sgst", label: "SGST (₹)" },
    { key: "igst", label: "IGST (₹)" },
    { key: "cess", label: "CESS (₹)" },
    { key: "amount", label: "Total Amount (₹)" },
  ],
  credit_note: [
    { key: "invoice_number", label: "Original Invoice Number" },
    { key: "notice_number", label: "Credit Note Number" },
    { key: "invoice_date", label: "Date" },
    { key: "vendor", label: "Reason" },
    { key: "customer", label: "Customer" },
    { key: "amount", label: "Amount (₹)" },
    { key: "gstin", label: "GSTIN" },
  ],
  debit_note: [
    { key: "invoice_number", label: "Original Invoice Number" },
    { key: "notice_number", label: "Debit Note Number" },
    { key: "invoice_date", label: "Date" },
    { key: "vendor", label: "Reason" },
    { key: "amount", label: "Amount (₹)" },
    { key: "gstin", label: "GSTIN" },
  ],
  gst_return: [
    { key: "gst_return_type", label: "Return Type" },
    { key: "financial_year", label: "Financial Year" },
    { key: "month", label: "Month" },
    { key: "filed_date", label: "Filed Date" },
    { key: "arn", label: "ARN Number" },
  ],
  gst_notice: [
    { key: "notice_number", label: "Notice Number" },
    { key: "vendor", label: "Department" },
    { key: "notice_date", label: "Notice Date" },
    { key: "response_due_date", label: "Response Due Date" },
    { key: "priority", label: "Priority" },
  ],
  e_invoice: [
    { key: "invoice_number", label: "Reference Number" },
    { key: "invoice_date", label: "Date" },
    { key: "gstin", label: "GSTIN" },
    { key: "amount", label: "Amount (₹)" },
  ],
  e_way_bill: [
    { key: "invoice_number", label: "Reference Number" },
    { key: "invoice_date", label: "Date" },
    { key: "gstin", label: "GSTIN" },
    { key: "amount", label: "Amount (₹)" },
  ],
  gst_challan: [
    { key: "invoice_number", label: "Reference Number" },
    { key: "invoice_date", label: "Date" },
    { key: "gstin", label: "GSTIN" },
    { key: "amount", label: "Amount (₹)" },
  ],
  hsn_sac: [
    { key: "vendor", label: "Document Name / Description" },
  ],
};

/** Call the backend OCR endpoint and return extracted fields. */
async function callOcrExtract(file: File, categoryId: string): Promise<OcrResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("category", categoryId);

  const token = localStorage.getItem("ca_token");
  const res = await fetch(`${API_BASE}/ocr/extract`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });

  const body = await res.json();

  if (!res.ok) {
    const msg = Array.isArray(body?.detail)
      ? body.detail.map((e: { msg: string }) => e.msg).join(", ")
      : (body?.detail ?? "OCR extraction failed");
    throw new Error(msg);
  }

  const parsedFields: Record<string, string> = {};

  // Only include fields that actually have values — skip missing/empty ones
  const extractValue = (v: any): string => {
    if (v == null) return "";
    if (typeof v === "object" && "value" in v) return String(v.value ?? "").trim();
    return String(v).trim();
  };

  if (body.core_fields) {
    Object.entries(body.core_fields).forEach(([k, v]: [string, any]) => {
      const val = extractValue(v);
      if (val) parsedFields[k] = val;  // Only add non-empty values
    });
  }
  if (body.metadata_fields) {
    Object.entries(body.metadata_fields).forEach(([k, v]: [string, any]) => {
      const val = extractValue(v);
      if (val) parsedFields[k] = val;  // Only add non-empty values
    });
  }

  // Fallback for older backend format
  if (!body.core_fields && body.fields) {
    Object.entries(body.fields).forEach(([k, v]: [string, any]) => {
      const val = extractValue(v);
      if (val) parsedFields[k] = val;
    });
  }

  const tableData = body.table_data ?? null;
  const lineItems = (body.records?.[0]?.line_items && body.records[0].line_items.length > 0)
    ? body.records[0].line_items
    : (body.table_data?.rows ?? []);

  return {
    fields: parsedFields,
    tableData,
    lineItems,
    message: body.message ?? "OCR complete",
    rawText: body.raw_text ?? "",
    hasContent: body.has_content !== false, // default true for backward compat
  };
}

export function ScanDocumentModal({ open, onOpenChange, category, clientId, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [lineItems, setLineItems] = useState<Array<Record<string, unknown>>>([]);
  const [tableData, setTableData] = useState<any>(null);
  const [ocrMessage, setOcrMessage] = useState<string>("");
  const [noContentMsg, setNoContentMsg] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setStage("idle");
      setFile(null);
      setFields({});
      setLineItems([]);
      setTableData(null);
      setOcrMessage("");
      setNoContentMsg("");
      setErrorMsg("");
    }
  }, [open, category]);

  const resetToIdle = () => {
    setStage("idle");
    setFile(null);
    setFields({});
    setLineItems([]);
    setTableData(null);
    setOcrMessage("");
    setNoContentMsg("");
    setErrorMsg("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    setFile(f);
    setStage("scanning");
    setErrorMsg("");
    setNoContentMsg("");

    try {
      const result = await callOcrExtract(f, category?.id ?? "");

      if (!result.hasContent) {
        // Backend confirmed: no document text found — block saving entirely
        setNoContentMsg(result.message);
        setStage("no_content");
        return;
      }

      // Merge extracted values into the full category field set.
      // This ensures all category fields appear in the preview (empty ones editable)
      // and extracted values are pre-filled.
      const categoryFields = CATEGORY_FIELDS[category?.id ?? ""] ?? [];
      const mergedFields: Record<string, string> = {};
      // Start with empty slots for all defined category fields
      categoryFields.forEach(({ key }) => { mergedFields[key] = ""; });
      // Overlay with actually extracted values
      Object.entries(result.fields).forEach(([k, v]) => {
        if (v) mergedFields[k] = v;
      });

      setFields(mergedFields);
      setTableData(result.tableData ?? null);
      setLineItems(result.lineItems ?? []);
      setOcrMessage(result.message);
      setStage("preview");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Document text was detected, but no matching fields could be identified.";
      setErrorMsg(msg);
      setStage("error");
      toast.error("Extraction failed", { description: msg });
    }
  };

  const setField = (k: string, v: string) => setFields((p) => ({ ...p, [k]: v }));

  const handleSave = async () => {
    if (!category) return;

    // Double-guard: never allow saving if we somehow have no fields at all
    const hasData = Object.values(fields).some((v) => v != null && String(v).trim() !== "");
    if (!hasData) {
      toast.warning("No readable text was found in this document.", {
        description: "No fields were extracted. Please fill in the details manually or scan a different document.",
      });
      return;
    }

    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("document_category", category.id);
      fd.append("document_type", "scan");

      const knownKeys = new Set([
        "invoice_type", "invoice_number", "gstin", "vendor", "customer",
        "invoice_date", "amount", "taxable_amount", "cgst", "sgst", "igst",
        "cess", "hsn", "gst_return_type", "financial_year", "month",
        "filed_date", "arn", "notice_number", "notice_date",
        "response_due_date", "priority"
      ]);

      const meta: Record<string, any> = {};
      Object.entries(fields).forEach(([k, v]) => {
        if (!v) return;
        if (knownKeys.has(k)) {
          fd.append(k, v);
        } else {
          meta[k] = v;
        }
      });

      if (lineItems && lineItems.length > 0) {
        meta["line_items"] = lineItems;
      }
      if (tableData) {
        meta["table_data"] = tableData;
      }

      if (!file) {
        toast.warning("File Required", {
          description: "A document file is required. Please scan or select a document first.",
        });
        return;
      }
      fd.append("file", file);

      const token = localStorage.getItem("ca_token");
      const res = await fetch(
        `${API_BASE}/invoices/${clientId}/upload`,
        { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd }
      );
      const body = await res.json();
      if (!res.ok) {
        const msg = Array.isArray(body?.detail)
          ? body.detail.map((e: { msg: string }) => e.msg).join(", ")
          : (body?.detail ?? "Save failed");
        throw new Error(msg);
      }
      toast.success("Document saved", { description: `${category.label} saved from scan.` });
      onSuccess();
      onOpenChange(false);
    } catch (err: unknown) {
      toast.error("Document could not be saved. Please try again.", { description: err instanceof Error ? err.message : "Unknown error" });
    } finally {
      setSubmitting(false);
    }
  };

  if (!category) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScanLine className="size-5 text-primary" /> Scan — {category.label}
          </DialogTitle>
          <DialogDescription>
            Upload or capture the document. OCR will extract the fields automatically.
            Works with printed and handwritten documents.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">

          {/* ── Idle — drop zone ────────────────────────────── */}
          {stage === "idle" && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border p-10 text-center transition-colors hover:border-primary/50 hover:bg-secondary/40"
            >
              <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <ScanLine className="size-6" />
              </span>
              <div className="space-y-1">
                <p className="text-sm font-medium">Tap to scan or upload a document</p>
                <p className="text-xs text-muted-foreground">
                  Supports printed &amp; handwritten documents
                </p>
                <p className="text-xs text-muted-foreground">
                  Camera · PDF · Images (JPG, PNG, WEBP, HEIC…) · Any format
                </p>
              </div>
              <span className="flex items-center gap-1.5 rounded-md bg-secondary px-3 py-1 text-xs text-muted-foreground">
                <PenLine className="size-3" /> Handwriting supported
              </span>
            </button>
          )}

          {/* ── Scanning ──────────────────────────────────── */}
          {stage === "scanning" && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border p-10">
              <Loader2 className="size-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Scanning &amp; extracting fields…</p>
              <p className="text-xs text-muted-foreground opacity-70">
                Analysing text with multiple OCR passes
              </p>
              {file && <p className="text-xs text-muted-foreground">{file.name}</p>}
            </div>
          )}

          {/* ── No Content — not a document image ─────────── */}
          {stage === "no_content" && (
            <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-amber-500/30 bg-amber-500/5 p-8 text-center">
              <ImageOff className="size-10 text-amber-500" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                  No document text detected
                </p>
                <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
                  {noContentMsg}
                </p>
              </div>
              <div className="rounded-lg bg-amber-500/10 px-4 py-2 text-xs text-amber-700 dark:text-amber-300">
                ⚠️ This document cannot be saved because no readable content was found.
              </div>
              {file && (
                <p className="text-xs text-muted-foreground">
                  File: <span className="font-medium">{file.name}</span>
                </p>
              )}
              <Button size="sm" variant="outline" onClick={resetToIdle}>
                Try another file
              </Button>
            </div>
          )}

          {/* ── Error ──────────────────────────────────────── */}
          {stage === "error" && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-8 text-center">
              <AlertCircle className="size-8 text-destructive" />
              <p className="text-sm font-medium text-destructive">OCR could not process the file</p>
              <p className="text-xs text-muted-foreground max-w-xs">{errorMsg}</p>
              <Button size="sm" variant="outline" onClick={resetToIdle}>
                Try another file
              </Button>
            </div>
          )}

          {/* ── Preview — editable OCR result ──────────────── */}
          {stage === "preview" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-green-500/10 px-3 py-2">
                <span className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 className="size-4" /> OCR extraction complete
                </span>
                {file && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <FileText className="size-3.5" /> {file.name}
                  </span>
                )}
              </div>

              {ocrMessage && (
                <p className="text-xs text-muted-foreground italic">{ocrMessage}</p>
              )}

              {/* ── Extracted Products / Line Items Table ────────── */}
              {lineItems && lineItems.length > 0 && (
                <div className="space-y-2 rounded-lg border border-border bg-card/60 p-3">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-primary">
                      <Package className="size-3.5" /> Extracted Products ({lineItems.length})
                    </span>
                    <Badge variant="outline" className="border-primary/30 bg-primary/5 text-[10px] text-primary">
                      {lineItems.length} item{lineItems.length > 1 ? "s" : ""}
                    </Badge>
                  </div>
                  <div className="max-h-48 overflow-x-auto overflow-y-auto rounded border border-border/60 bg-background">
                    <table className="w-full border-collapse text-[11px]">
                      <thead>
                        <tr className="bg-muted/60 text-muted-foreground">
                          <th className="px-2.5 py-1.5 text-left font-semibold">#</th>
                          <th className="px-2.5 py-1.5 text-left font-semibold">Product Description</th>
                          <th className="px-2.5 py-1.5 text-left font-semibold">HSN</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">Qty</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">Rate</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">Taxable</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">CGST</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">SGST</th>
                          <th className="px-2.5 py-1.5 text-right font-semibold">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lineItems.map((item, idx) => (
                          <tr key={idx} className="border-t border-border/40 hover:bg-muted/20">
                            <td className="px-2.5 py-1.5 text-muted-foreground">{item.sr_no || idx + 1}</td>
                            <td className="px-2.5 py-1.5 font-medium text-foreground">
                              {String(item.item_name || item.particulars || item.description || "—")}
                              {item.company_name && (
                                <span className="block text-[10px] text-muted-foreground">
                                  {String(item.company_name)}
                                </span>
                              )}
                            </td>
                            <td className="px-2.5 py-1.5 text-muted-foreground">{String(item.hsn || "—")}</td>
                            <td className="px-2.5 py-1.5 text-right">{String(item.quantity || "1")}</td>
                            <td className="px-2.5 py-1.5 text-right">{String(item.rate || "—")}</td>
                            <td className="px-2.5 py-1.5 text-right">{String(item.taxable_amount || "—")}</td>
                            <td className="px-2.5 py-1.5 text-right">{String(item.cgst_amount || "—")}</td>
                            <td className="px-2.5 py-1.5 text-right">{String(item.sgst_amount || "—")}</td>
                            <td className="px-2.5 py-1.5 text-right font-semibold text-foreground">{String(item.total_amount || "—")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Separator />
              <p className="text-xs text-muted-foreground">
                Review and edit the extracted fields before saving. Highlighted fields were auto-filled by OCR.
              </p>

              <div className="grid gap-3">
                {(() => {
                  const catFields = CATEGORY_FIELDS[category.id] ?? [];
                  const catKeys = new Set(catFields.map((f) => f.key));
                  const extraFields = Object.keys(fields)
                    .filter((k) => !catKeys.has(k) && fields[k])
                    .map((k) => ({ key: k, label: k.replace(/_/g, " ") }));
                  return [...catFields, ...extraFields].map(({ key, label }) => (
                    <div key={key} className="space-y-1">
                      <Label className="capitalize text-xs">{label}</Label>
                      <Input
                        value={fields[key] ?? ""}
                        onChange={(e) => setField(key, e.target.value)}
                        className={`h-8 text-sm ${fields[key] ? "border-green-500/50 bg-green-500/5" : ""}`}
                        placeholder="—"
                      />
                    </div>
                  ));
                })()}
              </div>

              <button
                type="button"
                onClick={resetToIdle}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Scan another document
              </button>
            </div>
          )}

          {/* Accept ALL file formats */}
          <input ref={fileRef} type="file" hidden accept="*/*" capture="environment" onChange={handleFile} />
        </div>

        <DialogFooter>
          {/* Save button is ONLY shown in "preview" stage — never for no_content/error/idle/scanning */}
          {stage === "preview" ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={handleSave} disabled={submitting}>
                {submitting ? "Saving…" : "Save Document"}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
