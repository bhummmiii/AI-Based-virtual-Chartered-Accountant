import { useState } from "react";
import { ScanLine, Loader2, Languages, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Separator } from "../ui/separator";
import { cn } from "../ui/utils";

// Target languages the scanned invoice can be converted to.
const languages = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "mr", label: "Marathi" },
  { code: "gu", label: "Gujarati" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "bn", label: "Bengali" },
  { code: "kn", label: "Kannada" },
  { code: "fr", label: "French" },
  { code: "es", label: "Spanish" },
  { code: "de", label: "German" },
  { code: "ar", label: "Arabic" },
];

// Illustrative extracted fields (mock OCR result).
const extracted = {
  invoiceNo: "INV-2211",
  date: "24 Jul 2026",
  vendor: "Zenith Corp",
  gstin: "27AABCZ4567Q1Z3",
  taxable: "₹2,10,000",
  gst: "₹37,800",
  total: "₹2,47,800",
};

// Sample localized labels to preview the language conversion.
const labelSets: Record<string, { title: string; fields: Record<string, string> }> = {
  en: { title: "Invoice details", fields: { invoiceNo: "Invoice No.", date: "Date", vendor: "Vendor", gstin: "GSTIN", taxable: "Taxable value", gst: "GST", total: "Total amount" } },
  hi: { title: "चालान विवरण", fields: { invoiceNo: "चालान संख्या", date: "दिनांक", vendor: "विक्रेता", gstin: "जीएसटीआईएन", taxable: "कर योग्य मूल्य", gst: "जीएसटी", total: "कुल राशि" } },
  mr: { title: "पावती तपशील", fields: { invoiceNo: "पावती क्रमांक", date: "दिनांक", vendor: "विक्रेता", gstin: "जीएसटीआयएन", taxable: "करपात्र मूल्य", gst: "जीएसटी", total: "एकूण रक्कम" } },
  fr: { title: "Détails de la facture", fields: { invoiceNo: "N° de facture", date: "Date", vendor: "Fournisseur", gstin: "GSTIN", taxable: "Valeur imposable", gst: "TVA", total: "Montant total" } },
};

export function ScanInvoiceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [stage, setStage] = useState<"idle" | "scanning" | "done">("idle");
  const [language, setLanguage] = useState("en");

  const reset = () => setStage("idle");

  const startScan = () => {
    setStage("scanning");
    setTimeout(() => setStage("done"), 1600);
  };

  const labels = labelSets[language] ?? labelSets.en;
  const langLabel = languages.find((l) => l.code === language)?.label ?? "English";

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ScanLine className="size-5 text-primary" /> Scan Invoice</DialogTitle>
          <DialogDescription>
            Scan a physical or digital invoice with OCR, then convert the extracted details into your preferred language.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* Language selector */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2"><Languages className="size-4" /> Convert to language</Label>
            <Select value={language} onValueChange={setLanguage}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {languages.map((l) => <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {/* Scan surface / result */}
          {stage !== "done" ? (
            <button
              type="button"
              onClick={startScan}
              disabled={stage === "scanning"}
              className={cn(
                "flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border p-10 text-center transition-colors",
                stage === "scanning" ? "opacity-80" : "hover:border-primary/50 hover:bg-secondary/40",
              )}
            >
              {stage === "scanning" ? (
                <>
                  <Loader2 className="size-8 animate-spin text-primary" />
                  <p className="text-sm text-muted-foreground">Scanning & extracting fields…</p>
                </>
              ) : (
                <>
                  <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary"><ScanLine className="size-6" /></span>
                  <div>
                    <p className="text-sm">Tap to scan an invoice</p>
                    <p className="text-xs text-muted-foreground">Use camera or select an image / PDF</p>
                  </div>
                </>
              )}
            </button>
          ) : (
            <div className="rounded-xl border border-border p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm">{labels.title}</p>
                <span className="inline-flex items-center gap-1 text-xs text-success"><CheckCircle2 className="size-3.5" /> Converted to {langLabel}</span>
              </div>
              <Separator className="my-3" />
              <dl className="space-y-2 text-sm">
                {Object.entries(labels.fields).map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between gap-4">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="text-right">{extracted[key as keyof typeof extracted]}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>

        <DialogFooter>
          {stage === "done" ? (
            <>
              <Button variant="outline" onClick={reset}>Scan another</Button>
              <Button
                onClick={() => {
                  toast.success("Invoice saved", { description: `${extracted.invoiceNo} · converted to ${langLabel}` });
                  onOpenChange(false);
                  reset();
                }}
              >
                Save invoice
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
