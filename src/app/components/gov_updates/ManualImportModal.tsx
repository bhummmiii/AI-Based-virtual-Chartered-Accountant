import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { GovSource, GovUpdate, govUpdatesService } from "../../services/govUpdates.service";
import { Upload, FileText, AlertCircle, CheckCircle2 } from "lucide-react";

interface ManualImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sources: GovSource[];
  onSuccess: (newUpdate: GovUpdate) => void;
}

export function ManualImportModal({
  open,
  onOpenChange,
  sources,
  onSuccess,
}: ManualImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [officialUrl, setOfficialUrl] = useState("");
  const [category, setCategory] = useState("GST");
  const [docType, setDocType] = useState("circular");
  const [sourceId, setSourceId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [docNumber, setDocNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!file) {
      setError("Please select an official document file (PDF, HTML, or TXT).");
      return;
    }

    if (!officialUrl.trim()) {
      setError("Please provide the official source URL.");
      return;
    }

    const allowedDomains = [".gov.in", ".nic.in", "rbi.org.in", "icai.org", "sebi.gov.in", "nfra.gov.in", "epfindia.gov.in", "esic.gov.in"];
    const urlLower = officialUrl.toLowerCase();
    if (!allowedDomains.some((d) => urlLower.includes(d))) {
      setError("Official URL must be from an approved statutory domain (.gov.in, .nic.in, rbi.org.in, icai.org, sebi.gov.in, nfra.gov.in, etc.).");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("official_url", officialUrl.trim());
    formData.append("category", category);
    formData.append("doc_type", docType);
    if (sourceId) formData.append("source_id", sourceId);
    if (title.trim()) formData.append("title", title.trim());
    if (docNumber.trim()) formData.append("doc_number", docNumber.trim());
    if (issueDate) formData.append("issue_date", issueDate);
    if (effectiveDate) formData.append("effective_date", effectiveDate);

    setLoading(true);
    try {
      const res = await govUpdatesService.manualImport(formData);
      onSuccess(res);
      onOpenChange(false);
      // Reset form
      setFile(null);
      setOfficialUrl("");
      setTitle("");
      setDocNumber("");
      setIssueDate("");
      setEffectiveDate("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to import circular.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <Upload className="size-5 text-primary" />
            Add Official Circular Manually
          </DialogTitle>
          <DialogDescription className="text-xs">
            Upload statutory circulars, notifications, and press releases for sources where automated sync is blocked by WAF firewalls.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2 text-xs">
          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/20 p-3 text-destructive text-xs flex items-start gap-2">
              <AlertCircle className="size-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* File Upload */}
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold">
              Official Document File (PDF, HTML, TXT &bull; Max 15 MB) <span className="text-destructive">*</span>
            </Label>
            <div className="border border-dashed rounded-lg p-3 text-center bg-muted/20 hover:bg-muted/40 transition-colors">
              <input
                type="file"
                id="circular-file-input"
                accept=".pdf,.html,.htm,.txt"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              <label htmlFor="circular-file-input" className="cursor-pointer block space-y-1">
                <FileText className="size-6 mx-auto text-muted-foreground" />
                <span className="text-xs font-medium text-foreground block">
                  {file ? file.name : "Click to select official file"}
                </span>
                <span className="text-[10px] text-muted-foreground block">
                  {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "Text will be extracted strictly from this document."}
                </span>
              </label>
            </div>
          </div>

          {/* Official URL */}
          <div className="space-y-1">
            <Label className="text-xs font-semibold">
              Official Document URL <span className="text-destructive">*</span>
            </Label>
            <Input
              value={officialUrl}
              onChange={(e) => setOfficialUrl(e.target.value)}
              placeholder="https://taxinformation.cbic.gov.in/... or https://incometaxindia.gov.in/..."
              className="text-xs"
              required
            />
            <p className="text-[10px] text-muted-foreground italic">
              Stored for audit provenance. The server never connects to or fetches this URL.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Category */}
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Category</Label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs text-foreground"
              >
                <option value="GST">GST</option>
                <option value="INCOME_TAX">Income Tax</option>
                <option value="TDS">TDS / TCS</option>
                <option value="BUDGET">Budget / Finance Bill</option>
                <option value="ACCOUNTING">Accounting Standards</option>
                <option value="COMPANIES">Companies Law</option>
                <option value="BANKING">Banking / RBI</option>
                <option value="OTHER">Other</option>
              </select>
            </div>

            {/* Document Type */}
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Document Type</Label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs text-foreground"
              >
                <option value="circular">Circular</option>
                <option value="notification">Notification</option>
                <option value="order">Order / Instruction</option>
                <option value="advisory">Advisory</option>
                <option value="press_release">Press Release</option>
                <option value="standard">Standard</option>
                <option value="rules">Rules / Act</option>
              </select>
            </div>
          </div>

          {/* Statutory Source Registry Selection */}
          <div className="space-y-1">
            <Label className="text-xs font-semibold">Source Authority (Optional)</Label>
            <select
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs text-foreground"
            >
              <option value="">Auto-assign or Other Official Source</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.domain})
                </option>
              ))}
            </select>
          </div>

          {/* Title Override */}
          <div className="space-y-1">
            <Label className="text-xs font-semibold">Title (Optional &bull; Extracted if blank)</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Reduction in E-Invoicing Threshold..."
              className="text-xs"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Document Number */}
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Document Number (Optional)</Label>
              <Input
                value={docNumber}
                onChange={(e) => setDocNumber(e.target.value)}
                placeholder="e.g. Circular No. 214/08/2026-GST"
                className="text-xs font-mono"
              />
            </div>

            {/* Issue Date */}
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Issue Date (Optional)</Label>
              <Input
                type="date"
                value={issueDate}
                onChange={(e) => setIssueDate(e.target.value)}
                className="text-xs"
              />
            </div>
          </div>

          <DialogFooter className="pt-2 gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={loading} className="gap-1.5">
              {loading ? "Importing..." : "Import Circular"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
