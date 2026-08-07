/**
 * FilePreviewModal — opens when user clicks a filename in the Invoices table.
 * Fetches the file from the backend download endpoint and renders it inline.
 *
 * Images  → rendered as <img>
 * PDFs    → rendered as <iframe>
 * Others  → shows metadata + download button only
 */
import { useEffect, useState } from "react";
import { Download, X, FileText, Loader2, AlertCircle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  docId: string;        // UUID
  fileName: string;
  fileType: string | null;
}

const IMAGE_EXTS = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp", "svg"]);
const PDF_EXTS   = new Set(["pdf"]);

export function FilePreviewModal({ open, onOpenChange, docId, fileName, fileType }: Props) {
  const [blobUrl, setBlobUrl]   = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const ext = (fileType ?? fileName.split(".").pop() ?? "").toLowerCase();
  const isImage = IMAGE_EXTS.has(ext);
  const isPdf   = PDF_EXTS.has(ext);
  const canPreview = isImage || isPdf;

  // Load the file when the modal opens
  useEffect(() => {
    if (!open || !canPreview) return;
    setBlobUrl(null);
    setError(null);
    setLoading(true);

    const token = localStorage.getItem("ca_token");
    const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

    fetch(`${base}/invoices/document/${docId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const blob = await res.blob();
        setBlobUrl(URL.createObjectURL(blob));
      })
      .catch((e) => setError(e.message ?? "Failed to load file"))
      .finally(() => setLoading(false));

    // Cleanup blob URL on close
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, docId]);

  // Also revoke when component unmounts or blobUrl changes
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  const handleDownload = () => {
    if (!blobUrl) return;
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = fileName;
    a.click();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] w-full overflow-hidden p-0 sm:max-w-4xl flex flex-col">
        {/* Header */}
        <DialogHeader className="flex-row items-center justify-between border-b border-border px-4 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium truncate max-w-[60%]">
            <FileText className="size-4 shrink-0 text-primary" />
            <span className="truncate">{fileName}</span>
          </DialogTitle>
          <div className="flex items-center gap-2">
            {blobUrl && (
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="size-4" /> Download
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>

        {/* Body */}
        <div className="flex-1 overflow-auto bg-secondary/30 flex items-center justify-center min-h-[300px]">
          {loading && (
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
              <Loader2 className="size-8 animate-spin text-primary" />
              <p className="text-sm">Loading file…</p>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center gap-3 text-destructive">
              <AlertCircle className="size-8" />
              <p className="text-sm">{error}</p>
            </div>
          )}

          {blobUrl && isImage && (
            <img
              src={blobUrl}
              alt={fileName}
              className="max-h-[70vh] max-w-full rounded object-contain shadow"
            />
          )}

          {blobUrl && isPdf && (
            <iframe
              src={blobUrl}
              title={fileName}
              className="h-[70vh] w-full border-0"
            />
          )}

          {!loading && !error && !canPreview && (
            <div className="flex flex-col items-center gap-4 p-10 text-center">
              <FileText className="size-14 text-muted-foreground" />
              <div>
                <p className="text-sm">{fileName}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Preview not available for .{ext} files.
                </p>
              </div>
              <Button variant="outline" onClick={() => {
                const token = localStorage.getItem("ca_token");
                const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
                window.open(`${base}/invoices/document/${docId}/download${token ? `?token=${token}` : ""}`, "_blank");
              }}>
                <Download className="size-4" /> Download file
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
