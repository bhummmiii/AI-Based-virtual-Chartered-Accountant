/**
 * ScanDocumentModal — Step 2 (Scan path)
 * Allows camera/file upload → simulates OCR extraction →
 * shows editable preview → saves to backend.
 */
import { useEffect, useRef, useState } from "react";
import { ScanLine, Loader2, CheckCircle2, Upload, X, FileText, Languages } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../ui/select";
import { type DocumentCategory } from "./DocumentCategoryModal";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  category: DocumentCategory | null;
  clientId: string;
  onSuccess: () => void;
}

type Stage = "idle" | "scanning" | "preview";

// Mock OCR extraction result — in production this calls backend OCR service
function mockExtract(categoryId: string): Record<string, string> {
  const base: Record<string, string> = {
    invoice_number: "INV-" + Math.floor(Math.random() * 9000 + 1000),
    vendor: "Sample Vendor Pvt Ltd",
    customer: "Client Corp",
    gstin: "27AABCS1234R1Z5",
    invoice_date: new Date().toISOString().split("T")[0],
    amount: (Math.random() * 100000 + 5000).toFixed(2),
    taxable_amount: (Math.random() * 85000 + 4000).toFixed(2),
    cgst: (Math.random() * 7000 + 500).toFixed(2),
    sgst: (Math.random() * 7000 + 500).toFixed(2),
    igst: "0.00",
    cess: "0.00",
    hsn: "9983",
  };
  if (categoryId === "gst_notice") {
    return { notice_number: "GSTN/2026/" + Math.floor(Math.random() * 999 + 1), notice_date: base.invoice_date, response_due_date: "" };
  }
  if (categoryId === "gst_return") {
    return { gst_return_type: "GSTR-3B", financial_year: "2025-26", month: "July 2026", arn: "AA" + Math.floor(Math.random() * 1e12) };
  }
  return base;
}

export function ScanDocumentModal({ open, onOpenChange, category, clientId, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) { setStage("idle"); setFile(null); setFields({}); }
  }, [open, category]);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    setFile(f);
    setStage("scanning");
    // Simulate OCR processing delay
    setTimeout(() => {
      setFields(mockExtract(category?.id ?? ""));
      setStage("preview");
    }, 1800);
  };

  const setField = (k: string, v: string) => setFields((p) => ({ ...p, [k]: v }));

  const handleSave = async () => {
    if (!category) return;
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("document_category", category.id);
      fd.append("document_type", "scan");
      Object.entries(fields).forEach(([k, v]) => { if (v) fd.append(k, v); });
      if (file) fd.append("file", file);

      const token = localStorage.getItem("ca_token");
      const res = await fetch(
        `${(import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1"}/invoices/${clientId}/upload`,
        { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd }
      );
      const body = await res.json();
      if (!res.ok) {
        const msg = Array.isArray(body?.detail)
          ? body.detail.map((e: any) => e.msg).join(", ")
          : (body?.detail ?? "Save failed");
        throw new Error(msg);
      }
      toast.success("Document saved", { description: `${category.label} saved from scan.` });
      onSuccess();
      onOpenChange(false);
    } catch (err: unknown) {
      toast.error("Save failed", { description: err instanceof Error ? err.message : "Unknown error" });
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
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">

          {/* Idle — drop zone */}
          {stage === "idle" && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border p-10 text-center transition-colors hover:border-primary/50 hover:bg-secondary/40"
            >
              <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <ScanLine className="size-6" />
              </span>
              <div>
                <p className="text-sm">Tap to scan or upload a document</p>
                <p className="text-xs text-muted-foreground">Camera · Scanner · PDF · Image</p>
              </div>
            </button>
          )}

          {/* Scanning */}
          {stage === "scanning" && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border p-10">
              <Loader2 className="size-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Scanning & extracting fields…</p>
              {file && <p className="text-xs text-muted-foreground">{file.name}</p>}
            </div>
          )}

          {/* Preview — editable OCR result */}
          {stage === "preview" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-success/10 px-3 py-2">
                <span className="flex items-center gap-2 text-sm text-success">
                  <CheckCircle2 className="size-4" /> OCR extraction complete
                </span>
                {file && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <FileText className="size-3.5" /> {file.name}
                  </span>
                )}
              </div>
              <Separator />
              <p className="text-xs text-muted-foreground">Review and edit before saving.</p>
              <div className="grid gap-3">
                {Object.entries(fields).map(([key, val]) => (
                  <div key={key} className="space-y-1">
                    <Label className="capitalize text-xs">{key.replace(/_/g, " ")}</Label>
                    <Input
                      value={val}
                      onChange={(e) => setField(key, e.target.value)}
                      className="h-8 text-sm"
                    />
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => { setStage("idle"); setFile(null); setFields({}); if (fileRef.current) fileRef.current.value = ""; }}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Scan another document
              </button>
            </div>
          )}

          <input ref={fileRef} type="file" hidden accept="image/*,application/pdf,.json,.xml" capture="environment" onChange={handleFile} />
        </div>

        <DialogFooter>
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
