import React, { useState, useEffect, useMemo } from "react";
import {
  FileText,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Eye,
  Plus,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Landmark,
  Receipt,
  FileSpreadsheet,
  Layers,
  Scale,
  Calendar,
  Building2,
  DollarSign,
  TrendingUp,
  Download,
  Info,
  Check,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";
import { StatusBadge } from "../common/StatusBadge";
import { currency } from "../../data/mock";
import { cn } from "../ui/utils";
import { toast } from "sonner";

/**
 * Statutory GST Currency Formatter
 * Preserves 2 decimal places (paise) to guarantee exact mathematical parity
 * (e.g., CGST ₹424.50 + SGST ₹424.50 = Total Output Tax ₹849.00).
 */
export const formatGstCurrency = (val: number | string | null | undefined): string => {
  const num = Number(val ?? 0);
  if (isNaN(num)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
};

interface GstWorkspaceViewProps {
  clientId: string; // UUID
  clientCode: string; // e.g. "C-1068"
  clientName: string; // e.g. "Bhumiiiii"
  clientGstin?: string;
  returnFrequency?: string; // Monthly | Quarterly
  uploadedDocs: any[];
  ledgerRecords: any[];
  onViewDoc: (docId: string) => void;
  onViewVoucher: (voucherId: string, docId?: string) => void;
}

type GstTab = "gstr3b" | "gstr1" | "gstr2b" | "discrepancies" | "returns" | "hsn";

export function GstWorkspaceView({
  clientId,
  clientCode,
  clientName,
  clientGstin,
  returnFrequency = "Quarterly",
  uploadedDocs,
  ledgerRecords,
  onViewDoc,
  onViewVoucher,
}: GstWorkspaceViewProps) {
  const [activeTab, setActiveTab] = useState<GstTab>("gstr3b");
  const [loading, setLoading] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState<string>("2026-Q2");

  // Live GST data states from backend
  const [gstr1Data, setGstr1Data] = useState<any>(null);
  const [hsnData, setHsnData] = useState<any>(null);
  const [gstr2bData, setGstr2bData] = useState<any>(null);
  const [gstr3bData, setGstr3bData] = useState<any>(null);
  const [discrepancyData, setDiscrepancyData] = useState<any>(null);
  const [filingRecords, setFilingRecords] = useState<any[]>([]);

  // Record filing modal state
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [filingPeriod, setFilingPeriod] = useState("2026-09");
  const [filingForm, setFilingForm] = useState("GSTR-3B");
  const [filingTaxable, setFilingTaxable] = useState("");
  const [filingTax, setFilingTax] = useState("");
  const [filingDueDate, setFilingDueDate] = useState("2026-10-20");
  const [submittingFiling, setSubmittingFiling] = useState(false);

  // ── Fetch all GST reconciliation data ──────────────────────────
  const fetchGstData = async () => {
    if (!clientId) return;
    setLoading(true);
    const token = localStorage.getItem("ca_token") || localStorage.getItem("access_token");
    const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const periodParam = selectedPeriod && selectedPeriod !== "all" ? `&period=${selectedPeriod}` : "";

    try {
      const [r1, rHsn, r2, r3, rDisc, rRecords] = await Promise.allSettled([
        fetch(`${base}/gst/reconciliation/gstr1?client_id=${clientId}${periodParam}`, { headers }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/gst/reconciliation/table12-hsn?client_id=${clientId}${periodParam}`, { headers }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/gst/reconciliation/gstr2b?client_id=${clientId}${periodParam}`, { headers }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/gst/reconciliation/gstr3b?client_id=${clientId}${periodParam}`, { headers }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/gst/reconciliation/discrepancies?client_id=${clientId}${periodParam}`, { headers }).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/gst/records/${clientId}${selectedPeriod && selectedPeriod !== "all" ? `?period=${selectedPeriod}` : ""}`, { headers }).then((r) => (r.ok ? r.json() : null)),
      ]);

      if (r1.status === "fulfilled" && r1.value?.data) setGstr1Data(r1.value.data);
      if (rHsn.status === "fulfilled" && rHsn.value?.data) setHsnData(rHsn.value.data);
      if (r2.status === "fulfilled" && r2.value?.data) setGstr2bData(r2.value.data);
      if (r3.status === "fulfilled" && r3.value?.data) setGstr3bData(r3.value.data);
      if (rDisc.status === "fulfilled" && rDisc.value?.data) setDiscrepancyData(rDisc.value.data);
      if (rRecords.status === "fulfilled" && rRecords.value?.data) setFilingRecords(rRecords.value.data);
    } catch (err) {
      console.error("[GST] Failed to load GST reconciliation data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGstData();
  }, [clientId, selectedPeriod]);

  // ── 4-State Governance Counts (Design Principle 5) ─────────────
  const extractedCount = useMemo(() => uploadedDocs.length, [uploadedDocs]);
  const verifiedCount = useMemo(
    () => uploadedDocs.filter((d) => d.status === "verified").length,
    [uploadedDocs]
  );
  const postedCount = useMemo(
    () => ledgerRecords.filter((r) => r.status === "posted").length,
    [ledgerRecords]
  );
  const filedCount = useMemo(
    () => filingRecords.filter((r) => r.filing_status === "filed").length,
    [filingRecords]
  );



  // ── Calculations for Display ───────────────────────────────────
  const outwardTaxable = Number(gstr1Data?.total_outward_taxable || gstr3bData?.table_3_1_outward?.taxable_value || 0);
  const outwardTax = Number(gstr1Data?.total_outward_tax || 0) || (Number(gstr3bData?.table_3_1_outward?.cgst || 0) + Number(gstr3bData?.table_3_1_outward?.sgst || 0) + Number(gstr3bData?.table_3_1_outward?.igst || 0));
  const outwardIgst = Number(gstr3bData?.table_3_1_outward?.igst ?? gstr1Data?.total_outward_igst ?? 0);
  const outwardCgst = Number(gstr3bData?.table_3_1_outward?.cgst ?? gstr1Data?.total_outward_cgst ?? 0);
  const outwardSgst = Number(gstr3bData?.table_3_1_outward?.sgst ?? gstr1Data?.total_outward_sgst ?? 0);

  const inwardTaxable = Number(gstr2bData?.total_inward_taxable || 0);
  const eligibleItc = Number(gstr2bData?.total_eligible_itc || 0);
  const eligibleIgst = Number(gstr3bData?.table_4_net_itc?.igst ?? gstr2bData?.eligible_itc_igst ?? 0);
  const eligibleCgst = Number(gstr3bData?.table_4_net_itc?.cgst ?? gstr2bData?.eligible_itc_cgst ?? 0);
  const eligibleSgst = Number(gstr3bData?.table_4_net_itc?.sgst ?? gstr2bData?.eligible_itc_sgst ?? 0);
  const ineligibleItc = Number(gstr2bData?.ineligible_itc || 0);

  const netCashPayable = Number(gstr3bData?.tax_payable_in_cash || Math.max(0, outwardTax - eligibleItc));
  const totalDiscrepancies = discrepancyData?.total_discrepancies ?? 0;
  const highRiskCount = discrepancyData?.high_count ?? 0;
  const isFilingBlocked = outwardTax < 0 || highRiskCount > 0;

  // ── Statutory Due Date Calculator ──────────────────────────────
  const computeStatutoryDueDate = (period: string, form: string, freq: string): string => {
    let year = 2026;
    let month = 9;

    if (period && period.includes("-Q")) {
      const parts = period.split("-Q");
      year = parseInt(parts[0], 10) || 2026;
      const q = parseInt(parts[1], 10) || 2;
      if (q === 1) month = 6;
      else if (q === 2) month = 9;
      else if (q === 3) month = 12;
      else if (q === 4) { month = 3; year += 1; }
    } else if (period && period.includes("-")) {
      const parts = period.split("-");
      year = parseInt(parts[0], 10) || 2026;
      month = parseInt(parts[1], 10) || 9;
    }

    let dueYear = year;
    let dueMonth = month + 1;
    if (dueMonth > 12) {
      dueMonth = 1;
      dueYear += 1;
    }

    const pad = (n: number) => String(n).padStart(2, "0");

    if (form === "GSTR-1") {
      const day = freq.toLowerCase().includes("quarter") ? "13" : "11";
      return `${dueYear}-${pad(dueMonth)}-${day}`;
    } else if (form === "GSTR-3B") {
      const day = freq.toLowerCase().includes("quarter") ? "22" : "20";
      return `${dueYear}-${pad(dueMonth)}-${day}`;
    } else if (form === "GSTR-9") {
      return `${dueYear}-12-31`;
    }
    return `${dueYear}-${pad(dueMonth)}-20`;
  };

  // Open modal with prefilled statutory values
  const openFilingModal = () => {
    const targetPeriod = selectedPeriod && selectedPeriod !== "all" ? selectedPeriod : "2026-09";
    setFilingPeriod(targetPeriod);
    const form = filingForm || "GSTR-3B";
    if (form === "GSTR-1") {
      setFilingTaxable(outwardTaxable.toFixed(2));
      setFilingTax(outwardTax.toFixed(2));
    } else {
      setFilingTaxable(outwardTaxable.toFixed(2));
      setFilingTax(netCashPayable.toFixed(2));
    }
    setFilingDueDate(computeStatutoryDueDate(targetPeriod, form, returnFrequency));
    setRecordModalOpen(true);
  };

  const handleFormChange = (newForm: string) => {
    setFilingForm(newForm);
    if (newForm === "GSTR-1") {
      setFilingTaxable(outwardTaxable.toFixed(2));
      setFilingTax(outwardTax.toFixed(2));
    } else {
      setFilingTaxable(outwardTaxable.toFixed(2));
      setFilingTax(netCashPayable.toFixed(2));
    }
    setFilingDueDate(computeStatutoryDueDate(filingPeriod, newForm, returnFrequency));
  };

  // ── Handle Record Filing Submission ────────────────────────────
  const handleRecordFiling = async () => {
    if (!clientId) return;
    if (isFilingBlocked) {
      toast.error("Statutory filing blocked", {
        description: highRiskCount > 0
          ? `${highRiskCount} unresolved high-risk discrepancy(ies) must be resolved first.`
          : "Outward tax liability cannot be negative.",
      });
      return;
    }
    setSubmittingFiling(true);
    const token = localStorage.getItem("ca_token") || localStorage.getItem("access_token");
    const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

    try {
      const taxableNum = parseFloat(filingTaxable) || (gstr3bData?.table_3_1_outward?.taxable_value ? parseFloat(gstr3bData.table_3_1_outward.taxable_value) : 0);
      const taxNum = parseFloat(filingTax) || (gstr3bData?.tax_payable_in_cash ? parseFloat(gstr3bData.tax_payable_in_cash) : 0);

      const payload = {
        client_id: clientId,
        gst_period: filingPeriod,
        gst_type: filingForm,
        taxable_amount: taxableNum,
        cgst: taxNum / 2,
        sgst: taxNum / 2,
        igst: 0,
        total_tax: taxNum,
        filing_status: "filed",
        due_date: filingDueDate,
      };

      const res = await fetch(`${base}/gst/records`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json();
        throw new Error(body?.detail || "Failed to record filing");
      }

      toast.success(`${filingForm} return recorded for ${filingPeriod}`, {
        description: "Filing acknowledgement saved. 4-state lifecycle updated.",
      });
      setRecordModalOpen(false);
      fetchGstData();
    } catch (err: any) {
      toast.error("Filing record failed", { description: err.message });
    } finally {
      setSubmittingFiling(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── 1. The 4-State Governance Banner (Design Principle 5) ─────── */}
      <div className="rounded-xl border border-border/80 bg-gradient-to-r from-card/80 via-card to-card/90 p-4 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ShieldCheck className="size-4" />
              </span>
              <h3 className="font-semibold text-foreground text-sm tracking-tight">
                FinLedger 4-State Governance — Multi-Tier Source Verification
              </h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Strict multi-tier governance: States 1–2 track Document Extraction &amp; Validation; State 3 tracks Ledger Posting; State 4 tracks Statutory Return Filings (GSTR-1, GSTR-3B) with portal acknowledgements.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:gap-3">
            {/* 1. Extracted */}
            <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-background/50 px-3 py-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-blue-500/10 text-blue-500 font-bold text-xs">
                1
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-foreground">Extracted</span>
                  <Badge variant="outline" className="border-blue-500/30 bg-blue-500/5 text-[10px] text-blue-500 py-0 px-1.5">
                    {extractedCount}
                  </Badge>
                </div>
                <p className="truncate text-[10px] text-muted-foreground">Source Documents</p>
              </div>
            </div>

            {/* 2. Verified */}
            <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-background/50 px-3 py-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-purple-500/10 text-purple-500 font-bold text-xs">
                2
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-foreground">Verified</span>
                  <Badge variant="outline" className="border-purple-500/30 bg-purple-500/5 text-[10px] text-purple-500 py-0 px-1.5">
                    {verifiedCount}
                  </Badge>
                </div>
                <p className="truncate text-[10px] text-muted-foreground">Verified Invoices</p>
              </div>
            </div>

            {/* 3. Posted */}
            <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-background/50 px-3 py-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500 font-bold text-xs">
                3
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-foreground">Posted</span>
                  <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/5 text-[10px] text-emerald-500 py-0 px-1.5">
                    {postedCount}
                  </Badge>
                </div>
                <p className="truncate text-[10px] text-muted-foreground">Ledger Vouchers</p>
              </div>
            </div>

            {/* 4. Filed */}
            <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-background/50 px-3 py-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-amber-500/10 text-amber-500 font-bold text-xs">
                4
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-foreground">Filed</span>
                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/5 text-[10px] text-amber-500 py-0 px-1.5">
                    {filedCount}
                  </Badge>
                </div>
                <p className="truncate text-[10px] text-muted-foreground">Statutory Returns</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 2. Top KPI Metric Strip ─────────────────────────────────── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Outward Supplies (GSTR-1) */}
        <Card className="p-4 bg-card/70 border-border/70 hover:border-primary/40 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              GSTR-1 Outward
            </span>
            <span className="rounded-md bg-emerald-500/10 p-1.5 text-emerald-500">
              <TrendingUp className="size-4" />
            </span>
          </div>
          <div className="mt-2">
            <p className="text-xl font-bold font-mono text-foreground">{formatGstCurrency(outwardTaxable)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Tax Liability: <span className="font-semibold text-emerald-500 font-mono">{formatGstCurrency(outwardTax)}</span>
            </p>
          </div>
        </Card>

        {/* Inward Purchases & ITC (GSTR-2B) */}
        <Card className="p-4 bg-card/70 border-border/70 hover:border-primary/40 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Purchase Register (ITC)
            </span>
            <span className="rounded-md bg-blue-500/10 p-1.5 text-blue-500">
              <Receipt className="size-4" />
            </span>
          </div>
          <div className="mt-2">
            <p className="text-xl font-bold font-mono text-foreground">{formatGstCurrency(inwardTaxable)}</p>
            <div className="mt-1 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Eligible ITC: <span className="font-semibold text-blue-500 font-mono">{formatGstCurrency(eligibleItc)}</span>
              </span>
              {ineligibleItc > 0 && (
                <span className="text-[10px] text-amber-500 font-medium font-mono" title="Quarantined under Sec 16(2) due to missing supplier GSTIN">
                  Ineligible: {formatGstCurrency(ineligibleItc)}
                </span>
              )}
            </div>
          </div>
        </Card>

        {/* Net Tax Payable in Cash (GSTR-3B) */}
        <Card className="p-4 bg-card/70 border-border/70 hover:border-primary/40 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              GSTR-3B Cash Due
            </span>
            <span className="rounded-md bg-amber-500/10 p-1.5 text-amber-500">
              <Landmark className="size-4" />
            </span>
          </div>
          <div className="mt-2">
            <p className="text-xl font-bold font-mono text-amber-500">{formatGstCurrency(netCashPayable)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Net Tax = Outward ({formatGstCurrency(outwardTax)}) − ITC ({formatGstCurrency(eligibleItc)})
            </p>
          </div>
        </Card>

        {/* Discrepancy Health Check */}
        <Card className="p-4 bg-card/70 border-border/70 hover:border-primary/40 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Audit Exceptions
            </span>
            <span className={cn("rounded-md p-1.5", totalDiscrepancies > 0 ? "bg-destructive/10 text-destructive" : "bg-emerald-500/10 text-emerald-500")}>
              {totalDiscrepancies > 0 ? <AlertTriangle className="size-4" /> : <CheckCircle2 className="size-4" />}
            </span>
          </div>
          <div className="mt-2">
            <p className={cn("text-xl font-bold font-mono", totalDiscrepancies > 0 ? "text-destructive" : "text-emerald-500")}>
              {totalDiscrepancies} Issue{totalDiscrepancies === 1 ? "" : "s"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {highRiskCount > 0 ? (
                <span className="text-destructive font-medium">{highRiskCount} High-Severity action items</span>
              ) : totalDiscrepancies > 0 ? (
                <span className="text-amber-500 font-medium">{totalDiscrepancies} Action items requiring review</span>
              ) : (
                <span className="text-muted-foreground">All vouchers matched</span>
              )}
            </p>
          </div>
        </Card>
      </div>

      {/* ── 3. Sub-Tab Switcher & Actions ───────────────────────────── */}
      <Card className="border-border/80">
        <CardHeader className="flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant={activeTab === "gstr3b" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("gstr3b")}
            >
              <Scale className="size-3.5 mr-1.5" /> GSTR-3B Summary
            </Button>
            <Button
              variant={activeTab === "gstr1" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("gstr1")}
            >
              <TrendingUp className="size-3.5 mr-1.5" /> GSTR-1 Outward (Sales)
            </Button>
            <Button
              variant={activeTab === "gstr2b" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("gstr2b")}
            >
              <Receipt className="size-3.5 mr-1.5" /> Purchase Register (ITC)
            </Button>
            <Button
              variant={activeTab === "discrepancies" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("discrepancies")}
            >
              <AlertTriangle className="size-3.5 mr-1.5" /> Discrepancies ({totalDiscrepancies})
            </Button>
            <Button
              variant={activeTab === "returns" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("returns")}
            >
              <Landmark className="size-3.5 mr-1.5" /> Filed Returns ({filingRecords.length})
            </Button>
            <Button
              variant={activeTab === "hsn" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs font-medium"
              onClick={() => setActiveTab("hsn")}
            >
              <FileSpreadsheet className="size-3.5 mr-1.5" /> HSN / SAC Summary
            </Button>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground font-medium">Period:</span>
              <select
                value={selectedPeriod}
                onChange={(e) => setSelectedPeriod(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="2026-Q2">Q2 FY 2026-27 (Jul–Sep)</option>
                <option value="2026-Q1">Q1 FY 2026-27 (Apr–Jun)</option>
                <option value="2026-09">Sep 2026</option>
                <option value="2026-08">Aug 2026</option>
                <option value="2026-07">Jul 2026</option>
                <option value="all">All Available</option>
              </select>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={fetchGstData}
              disabled={loading}
              title="Refresh live reconciliation calculations"
            >
              <RefreshCw className={cn("size-3.5 mr-1.5", loading && "animate-spin")} />
              Refresh
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white"
              onClick={openFilingModal}
            >
              <Plus className="size-3.5 mr-1" /> Record Return Filing
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 1: GSTR-3B Consolidated Return Workings             */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "gstr3b" && (
            <div className="space-y-6 p-4">
              {/* Table 3.1: Details of Outward Supplies */}
              <div className="rounded-lg border border-border/70 overflow-hidden bg-card/60">
                <div className="bg-muted/60 px-4 py-2.5 border-b border-border/70 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs text-primary uppercase tracking-wider font-mono">
                      Table 3.1
                    </span>
                    <span className="text-xs font-medium text-foreground">
                      Details of Outward Supplies and Inward Supplies Liable to Reverse Charge
                    </span>
                  </div>
                  <Badge variant="outline" className="text-[10px] font-mono border-primary/30 text-primary">
                    Outward Tax: {formatGstCurrency(outwardTax)}
                  </Badge>
                </div>
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/30 text-muted-foreground border-b border-border/50">
                      <TableHead className="w-1/3 min-w-[200px]">Nature of Supplies</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[120px]">Total Taxable Value</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">Integrated Tax (IGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">Central Tax (CGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">State Tax (SGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px] font-semibold text-foreground">Total Tax</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    <TableRow className="hover:bg-muted/20">
                      <TableCell className="font-medium text-foreground">
                        (a) Outward taxable supplies (other than zero rated, nil rated and exempted)
                      </TableCell>
                      <TableCell className="text-right font-mono font-semibold whitespace-nowrap text-foreground">
                        {formatGstCurrency(Number(gstr3bData?.table_3_1_outward?.taxable_value || outwardTaxable))}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground whitespace-nowrap">
                        {formatGstCurrency(outwardIgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                        {formatGstCurrency(outwardCgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                        {formatGstCurrency(outwardSgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono font-bold text-foreground whitespace-nowrap">
                        {formatGstCurrency(outwardTax)}
                      </TableCell>
                    </TableRow>
                    <TableRow className="hover:bg-muted/20 text-muted-foreground">
                      <TableCell>(b) Outward taxable supplies (zero rated - exports &amp; SEZ)</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                    </TableRow>
                    <TableRow className="hover:bg-muted/20 text-muted-foreground">
                      <TableCell>(c) Inward supplies liable to reverse charge (RCM)</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
                {/* Table 3.1 Audit Parity Footnote */}
                <div className="bg-muted/30 px-4 py-2 border-t border-border/60 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="size-3.5 text-emerald-500 shrink-0" />
                    <span>
                      <strong className="text-foreground">Reconciliation Parity:</strong> B2B Supplies ({formatGstCurrency(gstr1Data?.b2b_summary?.taxable_amount || 0)}) + B2CL Supplies ({formatGstCurrency(gstr1Data?.b2cl_summary?.taxable_amount || 0)}) + B2CS Supplies ({formatGstCurrency(gstr1Data?.b2cs_summary?.taxable_amount || 0)}) − Credit Notes ({formatGstCurrency(Math.abs(Number(gstr1Data?.credit_notes_summary?.taxable_amount || 0)))}) + Debit Notes ({formatGstCurrency(gstr1Data?.debit_notes_summary?.taxable_amount || 0)}) = Net Taxable <strong className="text-foreground">{formatGstCurrency(outwardTaxable)}</strong>.
                    </span>
                  </div>
                  <span className="font-mono text-emerald-600 dark:text-emerald-400 font-medium">
                    {outwardIgst > 0 ? `IGST ${formatGstCurrency(outwardIgst)} + ` : ""}CGST {formatGstCurrency(outwardCgst)} + SGST {formatGstCurrency(outwardSgst)} = Total Tax {formatGstCurrency(outwardTax)}
                  </span>
                </div>
              </div>

              {/* Table 4: Eligible Input Tax Credit (ITC) */}
              <div className="rounded-lg border border-border/70 overflow-hidden bg-card/60">
                <div className="bg-muted/60 px-4 py-2.5 border-b border-border/70 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs text-blue-500 uppercase tracking-wider font-mono">
                      Table 4
                    </span>
                    <span className="text-xs font-medium text-foreground">
                      Eligible Input Tax Credit (ITC) as per GSTR-2B Purchase Register
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px] font-mono border-blue-500/30 text-blue-500">
                      Net Claimable ITC: {formatGstCurrency(eligibleItc)}
                    </Badge>
                    {ineligibleItc > 0 && (
                      <Badge variant="outline" className="text-[10px] font-mono border-amber-500/30 text-amber-500">
                        Ineligible (Sec 16(2)): {formatGstCurrency(ineligibleItc)}
                      </Badge>
                    )}
                  </div>
                </div>
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/30 text-muted-foreground border-b border-border/50">
                      <TableHead className="w-1/3 min-w-[200px]">Details</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">Integrated Tax (IGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">Central Tax (CGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[100px]">State Tax (SGST)</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[80px]">Cess</TableHead>
                      <TableHead className="text-right whitespace-nowrap min-w-[110px] font-semibold text-foreground">Net Eligible Credit</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    <TableRow className="hover:bg-muted/20">
                      <TableCell className="font-medium text-foreground">
                        (A) ITC Available (whether in full or part) - All other ITC from registered suppliers
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleIgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleCgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleSgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">₹0.00</TableCell>
                      <TableCell className="text-right font-mono font-bold text-foreground">
                        {formatGstCurrency(eligibleItc)}
                      </TableCell>
                    </TableRow>
                    <TableRow className="hover:bg-muted/20 text-muted-foreground">
                      <TableCell>(B) ITC Reversed - As per rules 38, 42 &amp; 43 of CGST Rules</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                    </TableRow>
                    <TableRow className="bg-muted/20 font-semibold border-t border-border/70">
                      <TableCell className="text-foreground">(C) Net ITC Available (A) − (B)</TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleIgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleCgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                        {formatGstCurrency(eligibleSgst)}
                      </TableCell>
                      <TableCell className="text-right font-mono">₹0.00</TableCell>
                      <TableCell className="text-right font-mono text-blue-500 font-bold">
                        {formatGstCurrency(eligibleItc)}
                      </TableCell>
                    </TableRow>
                    {ineligibleItc > 0 && (
                      <TableRow className="bg-amber-500/5 text-amber-600 dark:text-amber-400">
                        <TableCell className="font-medium">
                          (D) Ineligible ITC under Section 16(2) / Section 17(5) - Missing Supplier GSTIN
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatGstCurrency(Number(gstr2bData?.ineligible_itc_igst || 0))}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatGstCurrency(Number(ineligibleItc) / 2)}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatGstCurrency(Number(ineligibleItc) / 2)}
                        </TableCell>
                        <TableCell className="text-right font-mono">₹0.00</TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {formatGstCurrency(ineligibleItc)} (Ineligible)
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
                {/* Table 4 Statutory Explanation Banner */}
                {ineligibleItc > 0 ? (
                  <div className="bg-amber-500/10 border-t border-amber-500/20 px-4 py-2.5 flex items-start gap-2 text-[11px] text-amber-700 dark:text-amber-300">
                    <AlertTriangle className="size-4 shrink-0 mt-0.5 text-amber-500" />
                    <div>
                      <p className="font-semibold text-amber-600 dark:text-amber-400">
                        Section 16(2) Statutory Compliance Notice — Quarantined Ineligible ITC
                      </p>
                      <p className="mt-0.5 text-muted-foreground">
                        Total inward purchases are <strong className="text-foreground font-mono">{formatGstCurrency(inwardTaxable)}</strong>.
                        Under CGST Section 16(2), ITC can only be claimed if the supplier invoice contains a valid 15-character GSTIN.
                        Inward invoice(s) without valid supplier GSTIN have tax of <strong className="text-amber-500 font-mono">{formatGstCurrency(ineligibleItc)}</strong> quarantined as <strong className="text-foreground">Ineligible ITC</strong>.
                        Net claimable ITC in Table 4 is correctly <strong className="text-foreground font-mono">{formatGstCurrency(eligibleItc)}</strong>.
                      </p>
                    </div>
                  </div>
                ) : (gstr2bData?.invoices?.length || 0) > 0 ? (
                  <div className="bg-emerald-500/10 border-t border-emerald-500/20 px-4 py-2.5 flex items-start gap-2 text-[11px] text-emerald-700 dark:text-emerald-300">
                    <CheckCircle2 className="size-4 shrink-0 mt-0.5 text-emerald-500" />
                    <div>
                      <p className="font-semibold text-emerald-600 dark:text-emerald-400">
                        Section 16(2) Statutory Compliance — 100% Eligible ITC
                      </p>
                      <p className="mt-0.5 text-muted-foreground">
                        All inward purchase invoices contain verified supplier GSTINs compliant with CGST Section 16(2).
                        100% of inward tax (<strong className="text-foreground font-mono">{formatGstCurrency(eligibleItc)}</strong>) is claimable as Net Eligible Input Tax Credit in Table 4.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="bg-muted/40 border-t border-border/60 px-4 py-2.5 flex items-start gap-2 text-[11px] text-muted-foreground">
                    <Info className="size-4 shrink-0 mt-0.5 text-muted-foreground" />
                    <div>
                      <p className="font-semibold text-foreground">
                        No Inward Purchases in Period
                      </p>
                      <p className="mt-0.5 text-muted-foreground">
                        No inward purchase invoices recorded for this period. Eligible ITC is ₹0.00.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Table 6: Payment of Tax (Cash Computation) */}
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-500 font-mono text-xs">
                      Table 6 — Settlement
                    </Badge>
                    <h4 className="font-semibold text-foreground text-sm">
                      Net Tax Payable in Cash (Electronic Cash Ledger)
                    </h4>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Output Tax Liability ({formatGstCurrency(outwardTax)}) minus Net Eligible ITC ({formatGstCurrency(eligibleItc)}).
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-2xl font-bold font-mono text-amber-500">{formatGstCurrency(netCashPayable)}</p>
                    <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider">
                      Cash Payment Required
                    </span>
                  </div>
                  <Button size="sm" className="bg-amber-600 hover:bg-amber-500 text-white" onClick={openFilingModal}>
                    Pay &amp; File GSTR-3B
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 2: GSTR-1 Outward Supplies Register                 */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "gstr1" && (
            <div className="space-y-4 p-4">
              {/* Category Breakdown Cards */}
              <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    4A, 4B B2B Invoices
                  </span>
                  <div className="mt-1 flex items-baseline justify-between">
                    <p className="text-base font-bold font-mono text-foreground">
                      {formatGstCurrency(Number(gstr1Data?.b2b_summary?.taxable_amount || 0))}
                    </p>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {gstr1Data?.b2b_summary?.invoice_count ?? 0} inv
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Tax: {formatGstCurrency(Number(gstr1Data?.b2b_summary?.total_tax || 0))}
                  </p>
                </div>

                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    5A, 5B B2C (Large) Invoices
                  </span>
                  <div className="mt-1 flex items-baseline justify-between">
                    <p className="text-base font-bold font-mono text-foreground">
                      {formatGstCurrency(Number(gstr1Data?.b2cl_summary?.taxable_amount || 0))}
                    </p>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {gstr1Data?.b2cl_summary?.invoice_count ?? 0} inv
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Tax: {formatGstCurrency(Number(gstr1Data?.b2cl_summary?.total_tax || 0))}
                  </p>
                </div>

                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    7 B2C (Small) Invoices
                  </span>
                  <div className="mt-1 flex items-baseline justify-between">
                    <p className="text-base font-bold font-mono text-foreground">
                      {formatGstCurrency(Number(gstr1Data?.b2cs_summary?.taxable_amount || 0))}
                    </p>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {gstr1Data?.b2cs_summary?.invoice_count ?? 0} inv
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Tax: {formatGstCurrency(Number(gstr1Data?.b2cs_summary?.total_tax || 0))}
                  </p>
                </div>

                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    9B Credit Notes
                  </span>
                  <div className="mt-1 flex items-baseline justify-between">
                    <p className="text-base font-bold font-mono text-foreground">
                      -{formatGstCurrency(Math.abs(Number(gstr1Data?.credit_notes_summary?.taxable_amount || 0)))}
                    </p>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {gstr1Data?.credit_notes_summary?.invoice_count ?? 0} note
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Tax: -{formatGstCurrency(Math.abs(Number(gstr1Data?.credit_notes_summary?.total_tax || 0)))}
                  </p>
                </div>

                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    9B Debit Notes
                  </span>
                  <div className="mt-1 flex items-baseline justify-between">
                    <p className="text-base font-bold font-mono text-foreground">
                      {formatGstCurrency(Number(gstr1Data?.debit_notes_summary?.taxable_amount || 0))}
                    </p>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {gstr1Data?.debit_notes_summary?.invoice_count ?? 0} note
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Tax: {formatGstCurrency(Number(gstr1Data?.debit_notes_summary?.total_tax || 0))}
                  </p>
                </div>
              </div>

              {/* Invoices List */}
              <div className="rounded-lg border border-border/70 overflow-x-auto">
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/40 text-muted-foreground">
                      <TableHead>Invoice Date</TableHead>
                      <TableHead>Invoice / Ref #</TableHead>
                      <TableHead>Recipient / Customer</TableHead>
                      <TableHead>Party GSTIN</TableHead>
                      <TableHead>Supply Type</TableHead>
                      <TableHead className="text-right">Taxable Value</TableHead>
                      <TableHead className="text-right">IGST</TableHead>
                      <TableHead className="text-right">CGST</TableHead>
                      <TableHead className="text-right">SGST</TableHead>
                      <TableHead className="text-right">Total Tax</TableHead>
                      <TableHead className="text-center">Reconciliation</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {!gstr1Data?.invoices || gstr1Data.invoices.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={12} className="py-8 text-center text-muted-foreground">
                          No outward invoices found in the sales register for this client.
                        </TableCell>
                      </TableRow>
                    ) : (
                      gstr1Data.invoices.map((inv: any, idx: number) => (
                        <TableRow key={idx} className="hover:bg-muted/20">
                          <TableCell className="font-mono whitespace-nowrap text-muted-foreground">
                            {inv.invoice_date || "—"}
                          </TableCell>
                          <TableCell className="font-semibold text-foreground font-mono">
                            {inv.invoice_number || "—"}
                          </TableCell>
                          <TableCell className="font-medium text-foreground">
                            {inv.party_name || "—"}
                          </TableCell>
                          <TableCell className="font-mono text-muted-foreground text-[11px]">
                            {inv.party_gstin || <span className="italic text-muted-foreground/60">Unregistered</span>}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-[10px] font-mono border-primary/20 text-primary">
                              {inv.supply_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono font-medium">
                            {formatGstCurrency(Number(inv.taxable_amount || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono text-primary">
                            {formatGstCurrency(Number(inv.igst || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono text-emerald-600 dark:text-emerald-400">
                            {formatGstCurrency(Number(inv.cgst || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono text-emerald-600 dark:text-emerald-400">
                            {formatGstCurrency(Number(inv.sgst || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono font-semibold text-foreground">
                            {formatGstCurrency(Number(inv.total_tax || 0))}
                          </TableCell>
                          <TableCell className="text-center">
                            {inv.is_posted ? (
                              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                                <Check className="size-3" /> Reconciled
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                                <AlertCircle className="size-3" /> Unposted Draft
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1.5">
                              {inv.document_id && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-[11px] text-primary hover:text-primary hover:bg-primary/10"
                                  onClick={() => onViewDoc(inv.document_id)}
                                  title="View Source Document"
                                >
                                  <FileText className="size-3 mr-1" /> Doc
                                </Button>
                              )}
                              {inv.is_posted && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-[11px] text-emerald-600 hover:text-emerald-600 hover:bg-emerald-500/10"
                                  onClick={() => onViewVoucher(inv.voucher_id, inv.document_id)}
                                  title="View Double-Entry Voucher"
                                >
                                  <Eye className="size-3 mr-1" /> Voucher
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 3: GSTR-2B Inward Supplies & ITC Register            */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "gstr2b" && (
            <div className="space-y-4 p-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-muted-foreground">
                    Total Inward Purchases
                  </span>
                  <p className="mt-1 text-base font-bold font-mono text-foreground">
                    {formatGstCurrency(inwardTaxable)}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {gstr2bData?.invoices?.length ?? 0} Inward invoice(s)
                  </p>
                </div>
                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-blue-500">
                    Eligible Input Tax Credit (ITC)
                  </span>
                  <p className="mt-1 text-base font-bold font-mono text-blue-500">
                    {formatGstCurrency(eligibleItc)}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Claimable under CGST Sec 16(2)
                  </p>
                </div>
                <div className="rounded-lg border border-border/70 bg-card/60 p-3">
                  <span className="text-[11px] font-semibold uppercase text-amber-500">
                    Blocked / Ineligible ITC
                  </span>
                  <p className="mt-1 text-base font-bold font-mono text-amber-500">
                    {formatGstCurrency(ineligibleItc)}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Quarantined under Sec 16(2) (No Supplier GSTIN)
                  </p>
                </div>
              </div>

              <div className="rounded-lg border border-border/70 overflow-x-auto">
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/40 text-muted-foreground">
                      <TableHead>Invoice Date</TableHead>
                      <TableHead>Invoice #</TableHead>
                      <TableHead>Supplier / Vendor</TableHead>
                      <TableHead>Supplier GSTIN</TableHead>
                      <TableHead className="text-right">Inward Taxable</TableHead>
                      <TableHead className="text-right">Gross Tax</TableHead>
                      <TableHead className="text-right">Eligible IGST</TableHead>
                      <TableHead className="text-right">Eligible CGST</TableHead>
                      <TableHead className="text-right">Eligible SGST</TableHead>
                      <TableHead className="text-right">Eligible ITC</TableHead>
                      <TableHead className="text-center">ITC Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {!gstr2bData?.invoices || gstr2bData.invoices.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={12} className="py-8 text-center text-muted-foreground">
                          No inward purchase invoices found for this client.
                        </TableCell>
                      </TableRow>
                    ) : (
                      gstr2bData.invoices.map((inv: any, idx: number) => {
                        const hasValidGstin = Boolean(inv.party_gstin && inv.party_gstin.trim().length >= 15);
                        return (
                          <TableRow key={idx} className="hover:bg-muted/20">
                            <TableCell className="font-mono whitespace-nowrap text-muted-foreground">
                              {inv.invoice_date || "—"}
                            </TableCell>
                            <TableCell className="font-semibold text-foreground font-mono">
                              {inv.invoice_number || "—"}
                            </TableCell>
                            <TableCell className="font-medium text-foreground">
                              {inv.party_name || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-muted-foreground text-[11px]">
                              {hasValidGstin ? (
                                <span className="text-foreground">{inv.party_gstin}</span>
                              ) : (
                                <span className="italic text-amber-500 font-medium">Missing (Unregistered)</span>
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono font-medium">
                              {formatGstCurrency(Number(inv.taxable_amount || 0))}
                            </TableCell>
                            <TableCell className="text-right font-mono text-muted-foreground">
                              {formatGstCurrency(Number(inv.total_tax || (Number(inv.cgst || 0) + Number(inv.sgst || 0) + Number(inv.igst || 0))))}
                            </TableCell>
                            <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                              {hasValidGstin ? formatGstCurrency(Number(inv.igst || 0)) : "₹0.00"}
                            </TableCell>
                            <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                              {hasValidGstin ? formatGstCurrency(Number(inv.cgst || 0)) : "₹0.00"}
                            </TableCell>
                            <TableCell className="text-right font-mono text-blue-600 dark:text-blue-400">
                              {hasValidGstin ? formatGstCurrency(Number(inv.sgst || 0)) : "₹0.00"}
                            </TableCell>
                            <TableCell className="text-right font-mono font-bold text-blue-500">
                              {hasValidGstin ? formatGstCurrency(Number(inv.total_tax || 0)) : "₹0.00"}
                            </TableCell>
                            <TableCell className="text-center">
                              {hasValidGstin ? (
                                <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
                                  <ShieldCheck className="size-3" /> Eligible ITC
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400" title="Section 16(2): Cannot claim ITC without valid 15-digit supplier GSTIN">
                                  <AlertTriangle className="size-3" /> Ineligible (Sec 16(2))
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="text-right whitespace-nowrap">
                              <div className="flex items-center justify-end gap-1.5">
                                {inv.document_id && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-[11px] text-primary hover:text-primary hover:bg-primary/10"
                                    onClick={() => onViewDoc(inv.document_id)}
                                    title="View Purchase Bill"
                                  >
                                    <FileText className="size-3 mr-1" /> Doc
                                  </Button>
                                )}
                                {inv.is_posted && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-[11px] text-emerald-600 hover:text-emerald-600 hover:bg-emerald-500/10"
                                    onClick={() => onViewVoucher(inv.voucher_id, inv.document_id)}
                                    title="View Purchase Voucher"
                                  >
                                    <Eye className="size-3 mr-1" /> Voucher
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 4: Discrepancy & CA Exception Engine                */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "discrepancies" && (
            <div className="space-y-4 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-foreground text-sm">
                    Automated Reconciliation Discrepancies &amp; Audit Exceptions
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Identifies missing GSTINs, unposted drafts, tax rounding variances, and timing differences.
                  </p>
                </div>
                <Badge
                  variant={totalDiscrepancies > 0 ? "destructive" : "secondary"}
                  className="text-xs font-mono font-medium"
                >
                  {totalDiscrepancies} Discrepanc{totalDiscrepancies === 1 ? "y" : "ies"}
                </Badge>
              </div>

              {!discrepancyData?.discrepancies || discrepancyData.discrepancies.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                  <div className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
                    <CheckCircle2 className="size-6" />
                  </div>
                  <h4 className="text-sm font-semibold text-foreground">Clean Audit — Zero Discrepancies</h4>
                  <p className="max-w-md text-xs text-muted-foreground">
                    All outward and inward invoices match posted journal entries with zero tax variances.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3">
                  {discrepancyData.discrepancies.map((d: any, idx: number) => {
                    const isHigh = d.severity === "HIGH";
                    return (
                      <div
                        key={idx}
                        className={cn(
                          "rounded-lg border p-3.5 space-y-2 transition-colors",
                          isHigh
                            ? "border-destructive/30 bg-destructive/5 hover:border-destructive/50"
                            : "border-border/70 bg-card/60 hover:border-primary/40"
                        )}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant={isHigh ? "destructive" : "outline"}
                              className={cn(
                                "text-[10px] font-mono uppercase font-semibold",
                                !isHigh && "border-amber-500/30 bg-amber-500/10 text-amber-500"
                              )}
                            >
                              {d.severity} RISK
                            </Badge>
                            <span className="font-mono text-xs font-semibold text-foreground">
                              {d.rule_code}
                            </span>
                          </div>
                          {d.variance_amount && Number(d.variance_amount) > 0 && (
                            <span className="font-mono text-xs text-destructive font-semibold">
                              Tax at risk: {currency(Number(d.variance_amount))}
                            </span>
                          )}
                        </div>

                        <div>
                          <p className="font-medium text-xs text-foreground">{d.title}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{d.description}</p>
                        </div>

                        {d.statutory_reference && (
                          <div className="flex items-center gap-1.5 text-[11px] text-primary/80 font-mono">
                            <Info className="size-3" />
                            <span>Statutory: {d.statutory_reference}</span>
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px]">
                          <span className="text-muted-foreground">
                            <span className="font-semibold text-foreground">Action:</span> {d.recommended_action}
                          </span>
                          {d.document_id && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-[11px] text-primary"
                              onClick={() => onViewDoc(d.document_id)}
                            >
                              Inspect Doc <ArrowRight className="size-3 ml-1" />
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 5: Filed Returns Log & Evidence                     */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "returns" && (
            <div className="space-y-4 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-foreground text-sm">
                    Statutory GST Filing Log &amp; Acknowledgements
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Preserves historical filed snapshots without modifying underlying posted transactions.
                  </p>
                </div>
                <Button size="sm" className="h-8 text-xs font-medium" onClick={openFilingModal}>
                  <Plus className="size-3.5 mr-1" /> Log Filed Return
                </Button>
              </div>

              <div className="rounded-lg border border-border/70 overflow-x-auto">
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/40 text-muted-foreground">
                      <TableHead>Return Period</TableHead>
                      <TableHead>Form</TableHead>
                      <TableHead>Due Date</TableHead>
                      <TableHead className="text-right">Taxable Turnover</TableHead>
                      <TableHead className="text-right">Tax Amount</TableHead>
                      <TableHead>Filing Status</TableHead>
                      <TableHead>Recorded At</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {filingRecords.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                          No filing records recorded yet. Use &quot;Record Return Filing&quot; to log filed returns.
                        </TableCell>
                      </TableRow>
                    ) : (
                      filingRecords.map((r: any, idx: number) => (
                        <TableRow key={idx} className="hover:bg-muted/20">
                          <TableCell className="font-semibold font-mono text-foreground">
                            {r.gst_period}
                          </TableCell>
                          <TableCell className="font-mono text-primary font-medium">
                            {r.gst_type}
                          </TableCell>
                          <TableCell className="font-mono text-muted-foreground">
                            {r.due_date || "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatGstCurrency(Number(r.taxable_amount || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono font-semibold text-foreground">
                            {formatGstCurrency(Number(r.total_tax || 0))}
                          </TableCell>
                          <TableCell>
                            <StatusBadge value={r.filing_status === "filed" ? "Filed" : "Pending"} />
                          </TableCell>
                          <TableCell className="font-mono text-muted-foreground text-[11px]">
                            {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* ═════════════════════════════════════════════════════════ */}
          {/* TAB 6: Dynamic HSN / SAC Summary (Table 12)             */}
          {/* ═════════════════════════════════════════════════════════ */}
          {activeTab === "hsn" && (
            <div className="space-y-4 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-foreground text-sm">
                    GSTR-1 Table 12 HSN / SAC Rate-wise Product Breakdown
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Aggregated directly from posted outward supply ledger lines and line items.
                  </p>
                </div>
                <Badge variant="outline" className="text-xs font-mono">
                  {(hsnData?.hsn_items?.length || 0)} Classified Codes
                </Badge>
              </div>

              <div className="rounded-lg border border-border/70 overflow-x-auto">
                <Table className="text-xs">
                  <TableHeader>
                    <tr className="bg-muted/40 text-muted-foreground">
                      <TableHead className="w-24">HSN / SAC</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead className="text-right w-24">GST Rate</TableHead>
                      <TableHead className="text-right">Taxable Turnover</TableHead>
                      <TableHead className="text-right">Tax Amount</TableHead>
                      <TableHead className="text-center w-24">Entries</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {(hsnData?.hsn_items || []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                          No HSN/SAC data available for this period.
                        </TableCell>
                      </TableRow>
                    ) : (
                      hsnData.hsn_items.map((h: any, idx: number) => (
                        <TableRow key={idx} className="hover:bg-muted/20">
                          <TableCell className="font-mono font-bold text-foreground">
                            {h.hsn_sac}
                          </TableCell>
                          <TableCell className="text-foreground font-medium">
                            {h.description || "Outward Supplies"}
                          </TableCell>
                          <TableCell className="text-right font-mono text-primary font-semibold">
                            {h.gst_rate !== null && h.gst_rate !== undefined ? `${h.gst_rate}%` : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatGstCurrency(Number(h.taxable_amount || 0))}
                          </TableCell>
                          <TableCell className="text-right font-mono font-medium text-foreground">
                            {formatGstCurrency(Number(h.total_tax || 0))}
                          </TableCell>
                          <TableCell className="text-center">
                            {h.invoice_count > 0 ? (
                              <Badge variant="outline" className="text-[10px] font-mono border-primary/20 text-primary">
                                {h.invoice_count} voucher{h.invoice_count > 1 ? "s" : ""}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground text-[11px]">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Record Filing Modal Dialog ─────────────────────────────── */}
      <Dialog open={recordModalOpen} onOpenChange={setRecordModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Record GST Return Filing</DialogTitle>
            <DialogDescription>
              Log an authorized statutory return filing with the GST portal to advance from State 3 (Posted) to State 4 (Filed).
            </DialogDescription>
          </DialogHeader>

          {/* Statutory Blocking Alert Banner */}
          {highRiskCount > 0 && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-destructive text-xs flex items-start gap-2.5">
              <AlertTriangle className="size-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-xs">Statutory Filing Blocked</p>
                <p className="mt-0.5 text-[11px] leading-relaxed opacity-90">
                  {highRiskCount} unresolved high-risk discrepancy(ies) detected for this period. Resolve all discrepancies in the Discrepancies tab before recording statutory return filing.
                </p>
              </div>
            </div>
          )}
          {outwardTax < 0 && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-destructive text-xs flex items-start gap-2.5">
              <AlertTriangle className="size-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-xs">Negative Tax Liability Blocked</p>
                <p className="mt-0.5 text-[11px] leading-relaxed opacity-90">
                  Outward tax liability is negative (₹{outwardTax.toFixed(2)}). Under statutory GST rules, return filings cannot be submitted with negative liability.
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-3 py-2 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Filing Period</Label>
                <Input
                  className="h-8 text-xs font-mono bg-muted/30 cursor-not-allowed"
                  value={filingPeriod}
                  readOnly
                  placeholder="2026-09"
                />
                <p className="text-[10px] text-muted-foreground">Locked to selected period</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Return Form</Label>
                <Select value={filingForm} onValueChange={handleFormChange}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="GSTR-3B">GSTR-3B (Monthly/Quarterly Summary)</SelectItem>
                    <SelectItem value="GSTR-1">GSTR-1 (Outward Supplies)</SelectItem>
                    <SelectItem value="GSTR-9">GSTR-9 (Annual Return)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">{returnFrequency} filing profile</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Taxable Value (₹)</Label>
                <Input
                  type="text"
                  className="h-8 text-xs font-mono bg-muted/30 font-semibold cursor-not-allowed"
                  value={filingTaxable ? formatGstCurrency(parseFloat(filingTaxable)) : "₹0.00"}
                  readOnly
                />
                <p className="text-[10px] text-muted-foreground">Derived from posted ledger lines</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{filingForm === "GSTR-1" ? "Outward Tax (₹)" : "Net Cash Tax (₹)"}</Label>
                <Input
                  type="text"
                  className="h-8 text-xs font-mono bg-muted/30 font-semibold text-primary cursor-not-allowed"
                  value={filingTax ? formatGstCurrency(parseFloat(filingTax)) : "₹0.00"}
                  readOnly
                />
                <p className="text-[10px] text-muted-foreground">Derived statutory liability</p>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Statutory Due Date</Label>
              <Input
                type="date"
                className="h-8 text-xs font-mono bg-muted/30 cursor-not-allowed"
                value={filingDueDate}
                readOnly
              />
              <p className="text-[10px] text-muted-foreground">Computed by GST rules for {returnFrequency} {filingForm}</p>
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setRecordModalOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleRecordFiling}
              disabled={submittingFiling || isFilingBlocked}
              className={isFilingBlocked ? "opacity-50 cursor-not-allowed" : ""}
            >
              {submittingFiling ? "Recording…" : isFilingBlocked ? "Filing Blocked" : "Save Filing Record"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
