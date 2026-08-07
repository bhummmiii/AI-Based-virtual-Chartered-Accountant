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
  ImageOff, PenLine,
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

  return {
    fields: body.fields ?? {},
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
  const [ocrMessage, setOcrMessage] = useState<string>("");
  const [noContentMsg, setNoContentMsg] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setStage("idle");
      setFile(null);
      setFields({});
      setOcrMessage("");
      setNoContentMsg("");
      setErrorMsg("");
    }
  }, [open, category]);

  const resetToIdle = () => {
    setStage("idle");
    setFile(null);
    setFields({});
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

      setFields(result.fields);
      setOcrMessage(result.message);
      setStage("preview");
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

    // Double-guard: never allow saving if we somehow have no fields at all
    const hasData = Object.values(fields).some((v) => v && v.trim() !== "");
    if (!hasData) {
      toast.warning("Nothing to save", {
        description: "No fields were extracted. Please fill in the details manually or scan a different document.",
      });
      return;
    }

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

              <Separator />
              <p className="text-xs text-muted-foreground">
                Review and edit the extracted fields before saving.
              </p>

              <div className="grid gap-3">
                {Object.entries(fields).map(([key, val]) => (
                  <div key={key} className="space-y-1">
                    <Label className="capitalize text-xs">{key.replace(/_/g, " ")}</Label>
                    <Input
                      value={val}
                      onChange={(e) => setField(key, e.target.value)}
                      className="h-8 text-sm"
                      placeholder="—"
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
