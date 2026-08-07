/**
 * ScanDocumentModal — Step 2 (Scan path)
 * Allows camera/file upload → calls backend OCR API →
 * shows editable preview → saves to backend.
 */
import { useEffect, useRef, useState } from "react";
import { ScanLine, Loader2, CheckCircle2, AlertCircle, FileText } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { type DocumentCategory } from "./DocumentCategoryModal";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  category: DocumentCategory | null;
  clientId: string;
  onSuccess: () => void;
}

type Stage = "idle" | "scanning" | "preview" | "error";

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

/** Call the backend OCR endpoint and return extracted fields. */
async function callOcrExtract(
  file: File,
  categoryId: string
): Promise<{ fields: Record<string, string>; message: string; rawText: string }> {
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

  return {
    fields: body.fields ?? {},
    message: body.message ?? "OCR complete",
    rawText: body.raw_text ?? "",
  };
}

export function ScanDocumentModal({ open, onOpenChange, category, clientId, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [ocrMessage, setOcrMessage] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setStage("idle");
      setFile(null);
      setFields({});
      setOcrMessage("");
      setErrorMsg("");
    }
  }, [open, category]);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    setFile(f);
    setStage("scanning");
    setErrorMsg("");

    try {
      const { fields: extracted, message } = await callOcrExtract(f, category?.id ?? "");
      setFields(extracted);
      setOcrMessage(message);

      // Check if text was actually found in the image
      const hasData = Object.values(extracted).some((v) => v && v.trim() !== "");
      if (!hasData) {
        setOcrMessage(
          "No document text could be detected. Please upload a clear image of an invoice or document."
        );
        setStage("preview"); // still show empty fields the user can fill manually
      } else {
        setStage("preview");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "OCR failed";
      setErrorMsg(msg);
      setStage("error");
      toast.error("OCR failed", { description: msg });
    }
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
      toast.error("Save failed", { description: err instanceof Error ? err.message : "Unknown error" });
    } finally {
      setSubmitting(false);
    }
  };

  const resetToIdle = () => {
    setStage("idle");
    setFile(null);
    setFields({});
    setOcrMessage("");
    setErrorMsg("");
    if (fileRef.current) fileRef.current.value = "";
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
                <p className="text-xs text-muted-foreground">
                  Camera · PDF · Images (JPG, PNG, WEBP, HEIC…) · Any format
                </p>
              </div>
            </button>
          )}

          {/* Scanning */}
          {stage === "scanning" && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border p-10">
              <Loader2 className="size-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Scanning &amp; extracting fields…</p>
              {file && <p className="text-xs text-muted-foreground">{file.name}</p>}
            </div>
          )}

          {/* Error */}
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
              {ocrMessage && (
                <p className="text-xs text-muted-foreground italic">{ocrMessage}</p>
              )}
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
                onClick={resetToIdle}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Scan another document
              </button>
            </div>
          )}

          {/* Accept ALL file formats — no restriction */}
          <input ref={fileRef} type="file" hidden accept="*/*" capture="environment" onChange={handleFile} />
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
