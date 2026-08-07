/**
 * UploadDocumentModal — Step 2 (Upload path)
 * Shows dynamic form fields based on the selected document category.
 * Handles file selection, validation, form fill, and backend POST.
 */
import { useEffect, useRef, useState } from "react";
import { Upload, X, FileText, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../ui/select";
import { type DocumentCategory } from "./DocumentCategoryModal";
import api from "../../services/api";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  category: DocumentCategory | null;
  clientId: string;          // UUID string from dbIdMap
  onSuccess: () => void;
}

type FormState = Record<string, string>;

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;

function validateGstin(v: string) {
  return !v || GSTIN_RE.test(v.trim().toUpperCase());
}

export function UploadDocumentModal({ open, onOpenChange, category, clientId, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<FormState>({});
  const [submitting, setSubmitting] = useState(false);
  const [gstinErr, setGstinErr] = useState("");

  useEffect(() => {
    if (open) { setFile(null); setForm({}); setGstinErr(""); }
  }, [open, category]);

  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
  };

  const handleSubmit = async () => {
    if (!category) return;
    if (form.gstin && !validateGstin(form.gstin)) {
      setGstinErr("Invalid GSTIN format. Example: 27AABCN1234R1Z5");
      return;
    }
    setGstinErr("");
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("document_category", category.id);
      fd.append("document_type", "upload");
      Object.entries(form).forEach(([k, v]) => { if (v) fd.append(k, v); });
      if (file) fd.append("file", file);

      // Use raw fetch with auth token since api.post serialises to JSON
      const token = localStorage.getItem("ca_token");
      const res = await fetch(
        `${(import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1"}/invoices/${clientId}/upload`,
        { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd }
      );
      const body = await res.json();
      if (!res.ok) {
        const msg = Array.isArray(body?.detail)
          ? body.detail.map((e: any) => e.msg).join(", ")
          : (body?.detail ?? "Upload failed");
        throw new Error(msg);
      }
      toast.success("Document uploaded", { description: `${category.label} saved successfully.` });
      onSuccess();
      onOpenChange(false);
    } catch (err: unknown) {
      toast.error("Upload failed", { description: err instanceof Error ? err.message : "Unknown error" });
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
            <span>{category.icon}</span> Upload — {category.label}
          </DialogTitle>
          <DialogDescription>{category.description}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <DynamicFields category={category} form={form} set={set} gstinErr={gstinErr} setGstinErr={setGstinErr} />

          {/* File drop zone */}
          <div className="space-y-2">
            <Label>Attach File</Label>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border p-6 text-center transition-colors hover:border-primary/50 hover:bg-secondary/40"
            >
              {file ? (
                <div className="flex items-center gap-2 text-sm">
                  <FileText className="size-5 text-primary" />
                  <span className="truncate max-w-[200px]">{file.name}</span>
                  <span className="text-xs text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span>
                  <button type="button" onClick={(e) => { e.stopPropagation(); setFile(null); if (fileRef.current) fileRef.current.value = ""; }}
                    className="ml-1 text-muted-foreground hover:text-destructive"><X className="size-4" /></button>
                </div>
              ) : (
                <>
                  <Upload className="size-7 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Click to browse or drag & drop</p>
                  <p className="text-xs text-muted-foreground">
                    All formats accepted — PDF, Images (JPG, PNG, WEBP…), Excel, Word, CSV, JSON, XML, ZIP, etc.
                  </p>
                </>
              )}
            </button>
            <input ref={fileRef} type="file" hidden accept="*/*" onChange={handleFile} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Uploading…" : "Save Document"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Dynamic form fields per category ─────────────────────── */
function DynamicFields({ category, form, set, gstinErr, setGstinErr }: {
  category: DocumentCategory;
  form: FormState;
  set: (k: string, v: string) => void;
  gstinErr: string;
  setGstinErr: (e: string) => void;
}) {
  const f = (label: string, key: string, placeholder = "", type = "text") => (
    <div className="space-y-2" key={key}>
      <Label>{label}</Label>
      <Input type={type} value={form[key] ?? ""} onChange={(e) => set(key, e.target.value)} placeholder={placeholder} />
    </div>
  );

  const gstinField = (
    <div className="space-y-2" key="gstin">
      <Label>GSTIN</Label>
      <Input
        value={(form.gstin ?? "").toUpperCase()}
        onChange={(e) => { set("gstin", e.target.value.toUpperCase()); setGstinErr(""); }}
        placeholder="27AABCN1234R1Z5"
        className="font-mono"
      />
      {gstinErr && <p className="text-xs text-destructive">{gstinErr}</p>}
    </div>
  );

  const amountFields = (
    <div className="grid grid-cols-2 gap-3" key="tax_fields">
      {f("Taxable Amount (₹)", "taxable_amount", "0.00", "number")}
      {f("CGST (₹)", "cgst", "0.00", "number")}
      {f("SGST (₹)", "sgst", "0.00", "number")}
      {f("IGST (₹)", "igst", "0.00", "number")}
      {f("CESS (₹)", "cess", "0.00", "number")}
      {f("Total Amount (₹)", "amount", "0.00", "number")}
    </div>
  );

  switch (category.id) {
    case "sales_records":
    case "b2b_invoice":
      return <>{f("Company / Vendor", "vendor", "Company name")} {f("Invoice Number", "invoice_number", "INV-2024-001")} {f("Invoice Date", "invoice_date", "YYYY-MM-DD", "date")} {f("Customer", "customer", "Customer name")} {gstinField} {f("HSN Code", "hsn", "8471")} {amountFields}</>;
    case "b2c_invoice":
      return <>{f("Customer", "customer", "Customer name")} {f("Invoice Number", "invoice_number", "INV-2024-001")} {f("Invoice Date", "invoice_date", "", "date")} {f("HSN Code", "hsn", "8471")} {amountFields}</>;
    case "purchase_records":
      return <>{f("Vendor", "vendor", "Supplier name")} {gstinField} {f("Invoice Number", "invoice_number", "BILL-001")} {f("Purchase Date", "invoice_date", "", "date")} {f("HSN Code", "hsn", "8471")} {amountFields}</>;
    case "credit_note":
      return <>{f("Original Invoice Number", "invoice_number", "INV-2024-001")} {f("Credit Note Number", "notice_number", "CN-001")} {f("Date", "invoice_date", "", "date")} {f("Reason", "vendor", "Reason for return")} {f("Customer", "customer", "Customer name")} {f("Amount (₹)", "amount", "0.00", "number")} {gstinField}</>;
    case "debit_note":
      return <>{f("Original Invoice Number", "invoice_number", "INV-2024-001")} {f("Debit Note Number", "notice_number", "DN-001")} {f("Date", "invoice_date", "", "date")} {f("Reason", "vendor", "Reason for return")} {f("Amount (₹)", "amount", "0.00", "number")} {gstinField}</>;
    case "gst_return":
      return (
        <>
          <div className="space-y-2">
            <Label>Return Type</Label>
            <Select value={form.gst_return_type ?? ""} onValueChange={(v) => set("gst_return_type", v)}>
              <SelectTrigger><SelectValue placeholder="Select return type" /></SelectTrigger>
              <SelectContent>
                {["GSTR-1", "GSTR-3B", "Annual Return"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {f("Financial Year", "financial_year", "2025-26")}
          {f("Month", "month", "July 2026")}
          {f("Filed Date", "filed_date", "", "date")}
          {f("ARN Number", "arn", "AA123456789012X")}
        </>
      );
    case "gst_notice":
      return (
        <>
          {f("Notice Number", "notice_number", "GSTN/2026/001")}
          {f("Department", "vendor", "GST Department")}
          {f("Notice Date", "notice_date", "", "date")}
          {f("Response Due Date", "response_due_date", "", "date")}
          <div className="space-y-2">
            <Label>Priority</Label>
            <Select value={form.priority ?? ""} onValueChange={(v) => set("priority", v)}>
              <SelectTrigger><SelectValue placeholder="Select priority" /></SelectTrigger>
              <SelectContent>
                {["low", "medium", "high"].map((p) => <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </>
      );
    case "e_invoice":
    case "e_way_bill":
    case "gst_challan":
      return <>{f("Reference Number", "invoice_number", "Ref / IRN number")} {f("Date", "invoice_date", "", "date")} {gstinField} {f("Amount (₹)", "amount", "0.00", "number")}</>;
    case "hsn_sac":
    case "document_list":
    default:
      return <>{f("Document Name / Description", "vendor", "Description (optional)")}</>;
  }
}
