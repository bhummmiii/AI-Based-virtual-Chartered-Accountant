import { useState, useEffect, useMemo } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import {
  Download, FileText, FileSpreadsheet, FileType,
  RefreshCw, Users, TrendingUp, TrendingDown,
  Wallet, ShieldCheck, ReceiptText, AlertTriangle,
  CheckCircle2, Info,
} from "lucide-react";
import { toast } from "sonner";
import * as XLSX from "xlsx";
import { PageHeader } from "../components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import {
  Select, SelectContent, SelectItem,
  SelectTrigger, SelectValue,
} from "../components/ui/select";
import {
  DropdownMenu, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow,
} from "../components/ui/table";
import { Badge } from "../components/ui/badge";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import { dbIdMap } from "../context/AppContext";
import { currency, compact } from "../data/mock";
import { clientService } from "../services/client.service";

// ─── Shared download helpers ─────────────────────────────────────────────────
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

type Row = Record<string, string | number>;

function exportCSV(rows: Row[], filename: string) {
  if (!rows.length) { toast.error("No data to export"); return; }
  const headers = Object.keys(rows[0]);
  const lines = [
    headers.join(","),
    ...rows.map((r) =>
      headers.map((h) => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(",")
    ),
  ];
  downloadBlob(new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" }), filename);
  toast.success("CSV downloaded", { description: filename });
}

function exportExcel(rows: Row[], sheetName: string, filename: string) {
  if (!rows.length) { toast.error("No data to export"); return; }
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheetName);
  XLSX.writeFile(wb, filename);
  toast.success("Excel downloaded", { description: filename });
}

function exportPDF(title: string, rows: Row[]) {
  if (!rows.length) { toast.error("No data to export"); return; }
  const headers = Object.keys(rows[0]);
  const headerHtml = headers.map((h) => `<th>${h}</th>`).join("");
  const bodyHtml = rows
    .map(
      (r) =>
        `<tr>${headers.map((h) => `<td>${r[h] ?? ""}</td>`).join("")}</tr>`
    )
    .join("");
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:24px;color:#111}
      h1{font-size:18px;margin-bottom:16px}
      table{width:100%;border-collapse:collapse;font-size:12px}
      th{background:#1e293b;color:#fff;padding:8px 10px;text-align:left}
      td{padding:7px 10px;border-bottom:1px solid #e2e8f0}
      tr:nth-child(even) td{background:#f8fafc}
      @media print{body{padding:0}}
    </style></head><body>
    <h1>${title}</h1>
    <table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>
    <script>window.onload=()=>{window.print();window.onafterprint=()=>window.close()}<\/script>
    </body></html>`;
  const win = window.open("", "_blank", "width=900,height=650");
  if (!win) { toast.error("Popup blocked — allow popups to download PDF"); return; }
  win.document.write(html);
  win.document.close();
  toast.success("PDF ready", { description: "Print dialog opened — choose Save as PDF" });
}

// ─── Export button (receives actual row data) ────────────────────────────────
function ExportBtn({ name, rows }: { name: string; rows: Row[] }) {
  const slug = name.toLowerCase().replace(/\s+/g, "_");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs">
          <Download className="size-3.5" /> Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => exportCSV(rows, `${slug}.csv`)}>
          <FileType className="size-4" /> Export as CSV
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => exportExcel(rows, name, `${slug}.xlsx`)}>
          <FileSpreadsheet className="size-4" /> Export as Excel
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => exportPDF(name, rows)}>
          <FileText className="size-4" /> Export as PDF
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ─── Month-wise chart data builder ───────────────────────────────────────────
const MONTH_LABELS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"];

function buildMonthChart(
  ledgerRows: Array<{ transaction_date: string; credit: string | number; debit: string | number; voucher_type?: string; status?: string }>,
  fy: string // "fy27" | "fy26" | "fy25"
): Array<{ month: string; revenue: number; expenses: number }> {
  // FY 2026-27 → Apr 2026 – Mar 2027
  const fyStartYear =
    fy === "fy27" ? 2026 : fy === "fy26" ? 2025 : 2024;

  const monthly: Record<string, { revenue: number; expenses: number }> = {};
  MONTH_LABELS.forEach((m, i) => {
    const yr = i < 9 ? fyStartYear : fyStartYear + 1;
    const key = `${yr}-${String(i < 9 ? i + 4 : i - 8).padStart(2, "0")}`;
    monthly[key] = { revenue: 0, expenses: 0 };
  });

  ledgerRows.forEach((r) => {
    if (!r.transaction_date) return;
    const mon = r.transaction_date.slice(0, 7); // "YYYY-MM"
    if (!monthly[mon]) return;
    const vt = (r.voucher_type || "").toLowerCase();
    const cr = Number(r.credit) || 0;
    const dr = Number(r.debit)  || 0;
    if (["sales", "income", "receipt"].includes(vt)) {
      monthly[mon].revenue += cr - dr;
    } else if (["purchase", "expense", "payment"].includes(vt)) {
      monthly[mon].expenses += dr - cr;
    }
  });

  return MONTH_LABELS.map((m, i) => {
    const yr = i < 9 ? fyStartYear : fyStartYear + 1;
    const key = `${yr}-${String(i < 9 ? i + 4 : i - 8).padStart(2, "0")}`;
    return { month: m, ...monthly[key] };
  });
}

// ─── Main component ──────────────────────────────────────────────────────────
export function Reports() {
  const { clients } = useApp();

  // Period: fy27 = FY 2026-27, fy26 = FY 2025-26, fy25 = FY 2024-25
  const [period, setPeriod] = useState("fy27");

  // Aggregated overview totals from backend
  const [totalRevenue, setTotalRevenue]   = useState<number | null>(null);
  const [totalExpenses, setTotalExpenses] = useState<number | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  // Aggregated ledger rows for the chart
  const [allLedger, setAllLedger] = useState<any[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);

  // ── Fetch per-client overview from backend ────────────────────────────────
  const fetchOverviews = async () => {
    if (clients.length === 0) return;
    setOverviewLoading(true);
    try {
      const token = localStorage.getItem("ca_token");
      const base  = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

      const results = await Promise.allSettled(
        clients.map((c) => {
          const dbId = dbIdMap.get(c.id);
          if (!dbId) return Promise.resolve(null);
          return fetch(`${base}/clients/${dbId}/overview`, { headers }).then((r) =>
            r.ok ? r.json() : null
          );
        })
      );

      let rev = 0;
      let exp = 0;
      let hasAny = false;
      results.forEach((r) => {
        if (r.status === "fulfilled" && r.value?.annual_revenue != null) {
          rev += Number(r.value.annual_revenue) || 0;
          exp += Number(r.value.expenses)       || 0;
          hasAny = true;
        }
      });
      if (hasAny) {
        setTotalRevenue(rev);
        setTotalExpenses(exp);
      } else {
        setTotalRevenue(0);
        setTotalExpenses(0);
      }
    } catch (err) {
      console.error("[Reports] overview fetch failed", err);
      setTotalRevenue(0);
      setTotalExpenses(0);
    } finally {
      setOverviewLoading(false);
    }
  };

  // ── Fetch all clients' accounting ledger for the chart ────────────────────
  const fetchLedger = async () => {
    if (clients.length === 0) return;
    setLedgerLoading(true);
    try {
      const token = localStorage.getItem("ca_token") || localStorage.getItem("access_token");
      const base  = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

      const results = await Promise.allSettled(
        clients.map((c) => {
          const dbId = dbIdMap.get(c.id);
          if (!dbId) return Promise.resolve(null);
          return fetch(
            `${base}/accounting/drafts?client_id=${dbId}&status=all`,
            { headers }
          ).then((r) => (r.ok ? r.json() : null));
        })
      );

      const rows: any[] = [];
      results.forEach((r) => {
        if (r.status === "fulfilled" && r.value?.data && Array.isArray(r.value.data)) {
          rows.push(...r.value.data);
        }
      });
      setAllLedger(rows);
    } catch (err) {
      console.error("[Reports] ledger fetch failed", err);
    } finally {
      setLedgerLoading(false);
    }
  };

  // Refresh whenever clients list is available
  useEffect(() => {
    if (clients.length > 0) {
      fetchOverviews();
      fetchLedger();
    }
  }, [clients.length]);

  // ── Derived values (real data only) ──────────────────────────────────────
  const netProfit    = (totalRevenue ?? 0) - (totalExpenses ?? 0);
  const hasFinData   = totalRevenue !== null && (totalRevenue > 0 || totalExpenses! > 0);

  // GST / Tax / Audit — derived from the real client list (statuses are live from backend)
  const gstDue    = clients.filter((c) => c.gst  === "Due" || c.gst  === "Overdue").length;
  const gstFiled  = clients.filter((c) => c.gst  === "Filed").length;
  const taxDue    = clients.filter((c) => c.tax  === "Due" || c.tax  === "Overdue").length;
  const taxFiled  = clients.filter((c) => c.tax  === "Filed").length;
  const flagged   = clients.filter((c) => c.audit === "Flagged").length;
  const highRisk  = clients.filter((c) => c.risk  === "High").length;
  const monthly   = clients.filter((c) => (c.clientType ?? "").toLowerCase().includes("month")).length;
  const quarterly = clients.filter((c) => (c.clientType ?? "").toLowerCase().includes("quarter")).length;

  // Chart data — built from real ledger rows
  const chartData = useMemo(
    () => buildMonthChart(allLedger, period),
    [allLedger, period]
  );
  const chartRevTotal = chartData.reduce((s, d) => s + d.revenue, 0);
  const hasChartData  = chartRevTotal > 0 || chartData.some((d) => d.expenses > 0);

  const isLoading = overviewLoading || ledgerLoading;

  // ── Export rows (actual data for file generation) ────────────────────────
  const clientComplianceRows = clients.map((c) => ({
    "Client ID":   c.id,
    "Company":     c.company,
    "Contact":     c.name,
    "Type":        c.type,
    "Filing":      c.clientType ?? "",
    "GST Status":  c.gst,
    "Tax Status":  c.tax,
    "Audit":       c.audit,
    "Risk":        c.risk,
    "Status":      c.status,
    "GSTIN":       c.gstin,
    "Last Activity": c.lastActivity,
  }));

  const financialSummaryRows = [
    { Report: "Revenue Summary",  Detail: `Total income across ${clients.length} clients`, Value: hasFinData ? String(totalRevenue) : "N/A" },
    { Report: "Expenses Summary", Detail: "Aggregate operating expenses",               Value: hasFinData ? String(totalExpenses) : "N/A" },
    { Report: "Net Profit",       Detail: "Revenue minus total expenses",                Value: hasFinData ? String(netProfit) : "N/A" },
    { Report: "Tax Summary",      Detail: `${taxFiled} filed, ${taxDue} pending/overdue`, Value: `${taxFiled}/${clients.length} filed` },
    { Report: "GST Summary",      Detail: `${gstFiled} filed, ${gstDue} pending/overdue`, Value: `${gstFiled}/${clients.length} filed` },
    { Report: "Audit Summary",    Detail: `${flagged} flagged, ${clients.length - flagged} clean`, Value: `${clients.length - flagged}/${clients.length} clean` },
  ];

  const gstRows = clients.map((c) => ({
    "Client ID":  c.id,
    "Company":    c.company,
    "GST Status": c.gst,
    "GSTIN":      c.gstin,
    "Filing":     c.clientType ?? "",
    "Risk":       c.risk,
  }));

  const taxRows = clients.map((c) => ({
    "Client ID":  c.id,
    "Company":    c.company,
    "Tax Status": c.tax,
    "Filing":     c.clientType ?? "",
    "Audit":      c.audit,
    "Risk":       c.risk,
  }));

  const auditRows = clients.map((c) => ({
    "Client ID":    c.id,
    "Company":      c.company,
    "Audit Status": c.audit,
    "Risk":         c.risk,
    "GST":          c.gst,
    "Tax":          c.tax,
  }));

  // ── Summary table rows ────────────────────────────────────────────────────
  const summaryRows = [
    {
      icon: TrendingUp,
      tone: "text-emerald-500 bg-emerald-500/10",
      label: "Revenue Summary",
      detail: `Total income across all ${clients.length} clients`,
      value: hasFinData ? currency(totalRevenue!) : "—",
      sub: hasFinData ? null : "Upload invoices/ledger entries to see real figures",
      exportRows: financialSummaryRows,
    },
    {
      icon: TrendingDown,
      tone: "text-rose-500 bg-rose-500/10",
      label: "Expenses Summary",
      detail: "Aggregate operating expenses across all clients",
      value: hasFinData ? currency(totalExpenses!) : "—",
      sub: null,
      exportRows: financialSummaryRows,
    },
    {
      icon: Wallet,
      tone: "text-primary bg-primary/10",
      label: "Net Profit",
      detail: "Revenue minus total expenses",
      value: hasFinData ? currency(netProfit) : "—",
      sub: null,
      exportRows: financialSummaryRows,
    },
    {
      icon: ReceiptText,
      tone: "text-amber-500 bg-amber-500/10",
      label: "Tax Summary",
      detail: `${taxFiled} filed · ${taxDue} pending/overdue`,
      value: `${taxFiled}/${clients.length} filed`,
      sub: null,
      exportRows: taxRows,
    },
    {
      icon: ShieldCheck,
      tone: "text-blue-500 bg-blue-500/10",
      label: "GST Summary",
      detail: `${gstFiled} filed · ${gstDue} pending/overdue`,
      value: `${gstFiled}/${clients.length} filed`,
      sub: null,
      exportRows: gstRows,
    },
    {
      icon: flagged > 0 ? AlertTriangle : CheckCircle2,
      tone: flagged > 0 ? "text-destructive bg-destructive/10" : "text-emerald-500 bg-emerald-500/10",
      label: "Audit Summary",
      detail: `${flagged} client(s) flagged · ${clients.length - flagged} clean`,
      value: `${clients.length - flagged}/${clients.length} clean`,
      sub: null,
      exportRows: auditRows,
    },
  ];

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Consolidated financial summaries across your client base"
        actions={
          <>
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fy27">FY 2026-27</SelectItem>
                <SelectItem value="fy26">FY 2025-26</SelectItem>
                <SelectItem value="fy25">FY 2024-25</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={() => { fetchOverviews(); fetchLedger(); }}
              disabled={isLoading}
            >
              <RefreshCw className={cn("size-4", isLoading && "animate-spin")} />
              Refresh
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                if (!clients.length) { toast.error("No client data to export"); return; }
                const wb = XLSX.utils.book_new();
                XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(financialSummaryRows), "Financial Summary");
                XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(gstRows),  "GST Details");
                XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(taxRows),  "Tax Details");
                XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(auditRows), "Audit Details");
                XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(clientComplianceRows), "All Clients");
                XLSX.writeFile(wb, "ca_reports_all.xlsx");
                toast.success("All reports exported", { description: "ca_reports_all.xlsx downloaded with 5 sheets" });
              }}
            >
              <Download className="size-4" /> Export All
            </Button>
          </>
        }
      />

      {/* ── Client-base Quick Stats ──────────────────────────── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Users className="size-5" />
            </span>
            <div>
              <p className="text-xl font-bold">{clients.length}</p>
              <p className="text-xs text-muted-foreground">Total Clients</p>
            </div>
          </div>
          <div className="mt-3 flex gap-2 text-[11px]">
            <span className="rounded bg-sky-500/10 text-sky-600 dark:text-sky-400 px-1.5 py-0.5 font-medium">
              {monthly} Monthly
            </span>
            <span className="rounded bg-violet-500/10 text-violet-600 dark:text-violet-400 px-1.5 py-0.5 font-medium">
              {quarterly} Quarterly
            </span>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
              <ShieldCheck className="size-5" />
            </span>
            <div>
              <p className="text-xl font-bold">{gstFiled}</p>
              <p className="text-xs text-muted-foreground">GST Filed</p>
            </div>
          </div>
          {gstDue > 0 && (
            <p className="mt-3 text-[11px] text-amber-500 font-medium">
              {gstDue} overdue / due
            </p>
          )}
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500">
              <ReceiptText className="size-5" />
            </span>
            <div>
              <p className="text-xl font-bold">{taxFiled}</p>
              <p className="text-xs text-muted-foreground">Tax Filed</p>
            </div>
          </div>
          {taxDue > 0 && (
            <p className="mt-3 text-[11px] text-amber-500 font-medium">
              {taxDue} overdue / due
            </p>
          )}
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg",
              highRisk > 0 ? "bg-destructive/10 text-destructive" : "bg-emerald-500/10 text-emerald-500"
            )}>
              {highRisk > 0 ? <AlertTriangle className="size-5" /> : <CheckCircle2 className="size-5" />}
            </span>
            <div>
              <p className="text-xl font-bold">{highRisk > 0 ? highRisk : "All Clear"}</p>
              <p className="text-xs text-muted-foreground">
                {highRisk > 0 ? "High-Risk Clients" : "No High Risk"}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ── Financial Summaries table ────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>Financial Summaries</CardTitle>
          {isLoading && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <RefreshCw className="size-3.5 animate-spin" /> Loading live data…
            </span>
          )}
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {!hasFinData && !isLoading && (
            <div className="flex items-center gap-2 mx-4 mb-3 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
              <Info className="size-3.5 shrink-0 opacity-70" />
              Financial values (Revenue, Expenses, Profit) will appear once invoices or accounting entries are uploaded for your clients.
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Report</TableHead>
                <TableHead>Details</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="w-32 text-right">Export</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summaryRows.map((r) => (
                <TableRow key={r.label}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-md", r.tone)}>
                        <r.icon className="size-3.5" />
                      </span>
                      <span className="font-medium text-sm">{r.label}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {r.detail}
                    {r.sub && (
                      <p className="text-[11px] text-amber-500 mt-0.5">{r.sub}</p>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono font-semibold">
                    {isLoading && r.label.includes("Revenue") || isLoading && r.label.includes("Expenses") || isLoading && r.label === "Net Profit" ? (
                      <span className="text-muted-foreground">Loading…</span>
                    ) : (
                      r.value
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <ExportBtn name={r.label} rows={r.exportRows} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ── Revenue vs Expenses Chart ────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle>
              {hasChartData
                ? `Revenue by Month — ${compact(chartRevTotal)} total`
                : "Revenue & Expenses by Month"}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {hasChartData
                ? "Aggregated from posted ledger entries across all clients"
                : "Chart will populate once accounting entries are uploaded"}
            </p>
          </div>
          {ledgerLoading && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <RefreshCw className="size-3.5 animate-spin" /> Fetching ledger…
            </span>
          )}
        </CardHeader>
        <CardContent>
          {hasChartData ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} margin={{ left: -10 }} barGap={2}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="month"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                />
                <YAxis
                  tickFormatter={(v) => compact(v)}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                  tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                />
                <Tooltip
                  formatter={(v: number, name: string) => [
                    currency(v),
                    name === "revenue" ? "Revenue" : "Expenses",
                  ]}
                  cursor={{ fill: "var(--secondary)" }}
                />
                <Bar dataKey="revenue"  fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={32} name="Revenue" />
                <Bar dataKey="expenses" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={32} name="Expenses" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <span className="flex size-14 items-center justify-center rounded-2xl bg-muted text-2xl">📊</span>
              <div className="space-y-1">
                <p className="text-sm font-medium">No accounting data yet</p>
                <p className="text-xs text-muted-foreground max-w-sm">
                  Upload invoices and accounting entries for your clients and they'll appear here month-by-month.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Per-client breakdown table ───────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>Client Compliance Breakdown</CardTitle>
          <div className="flex gap-2">
            <ExportBtn name="Client Compliance" rows={clientComplianceRows} />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Filing</TableHead>
                <TableHead>GST Status</TableHead>
                <TableHead>Tax Status</TableHead>
                <TableHead>Audit</TableHead>
                <TableHead>Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <div className="font-medium text-sm">{c.company}</div>
                    <div className="text-xs text-muted-foreground">{c.id} · {c.name}</div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{c.type}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px] font-semibold",
                        (c.clientType ?? "").toLowerCase().includes("month")
                          ? "border-sky-500/30 bg-sky-500/5 text-sky-600 dark:text-sky-400"
                          : "border-violet-500/30 bg-violet-500/5 text-violet-600 dark:text-violet-400"
                      )}
                    >
                      {c.clientType ?? "—"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        c.gst === "Filed"   ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600"
                        : c.gst === "Overdue" ? "border-destructive/30 bg-destructive/5 text-destructive"
                        : "border-amber-500/30 bg-amber-500/5 text-amber-600"
                      )}
                    >
                      {c.gst}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        c.tax === "Filed"   ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600"
                        : c.tax === "Overdue" ? "border-destructive/30 bg-destructive/5 text-destructive"
                        : "border-amber-500/30 bg-amber-500/5 text-amber-600"
                      )}
                    >
                      {c.tax}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        c.audit === "Passed"      ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600"
                        : c.audit === "Flagged"   ? "border-destructive/30 bg-destructive/5 text-destructive"
                        : c.audit === "In Progress" ? "border-blue-500/30 bg-blue-500/5 text-blue-600"
                        : "border-border bg-muted/30 text-muted-foreground"
                      )}
                    >
                      {c.audit}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        c.risk === "High"   ? "border-destructive/30 bg-destructive/5 text-destructive"
                        : c.risk === "Medium" ? "border-amber-500/30 bg-amber-500/5 text-amber-600"
                        : "border-emerald-500/30 bg-emerald-500/5 text-emerald-600"
                      )}
                    >
                      {c.risk}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
