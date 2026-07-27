import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download, FileText, FileSpreadsheet, FileType } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "../components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { useApp } from "../context/AppContext";
import { currency, compact, revenueTrend } from "../data/mock";

const exportFormats = [
  { key: "pdf", label: "PDF", icon: FileText },
  { key: "excel", label: "Excel", icon: FileSpreadsheet },
  { key: "csv", label: "CSV", icon: FileType },
] as const;

function ExportButtons({ name }: { name: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm"><Download className="size-4" /> Export</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {exportFormats.map((f) => (
          <DropdownMenuItem key={f.key} onClick={() => toast.success(`${name} exported`, { description: `Downloaded as ${f.label}` })}>
            <f.icon className="size-4" /> Export as {f.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Reports() {
  const { clients } = useApp();
  const [period, setPeriod] = useState("fy26");

  const totalRevenue = clients.reduce((a, c) => a + c.revenue, 0);
  const totalExpenses = Math.round(totalRevenue * 0.52);
  const netProfit = totalRevenue - totalExpenses;
  const gstDue = clients.filter((c) => c.gst === "Due" || c.gst === "Overdue").length;
  const taxDue = clients.filter((c) => c.tax === "Due" || c.tax === "Overdue").length;
  const flagged = clients.filter((c) => c.audit === "Flagged").length;

  const summaryRows = [
    { label: "Revenue Summary", detail: "Total income across all clients", value: currency(totalRevenue) },
    { label: "Expenses Summary", detail: "Aggregate operating expenses", value: currency(totalExpenses) },
    { label: "Net Profit", detail: "Revenue less expenses", value: currency(netProfit) },
    { label: "Tax Summary", detail: `${taxDue} clients with tax filings due`, value: currency(Math.round(netProfit * 0.22)) },
    { label: "GST Summary", detail: `${gstDue} clients with GST filings due`, value: currency(Math.round(totalRevenue * 0.06)) },
    { label: "Audit Summary", detail: `${flagged} client(s) flagged for review`, value: `${clients.length - flagged}/${clients.length} clean` },
  ];

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Consolidated financial summaries across your client base"
        actions={
          <>
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="q1">Q1 FY 2026-27</SelectItem>
                <SelectItem value="fy26">FY 2025-26</SelectItem>
                <SelectItem value="fy25">FY 2024-25</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => toast.success("All reports exported", { description: "6 summaries downloaded" })}>
              <Download className="size-4" /> Export All
            </Button>
          </>
        }
      />

      {/* Summary table */}
      <Card>
        <CardHeader><CardTitle>Financial Summaries</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto p-0">
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
                  <TableCell>{r.label}</TableCell>
                  <TableCell className="text-muted-foreground">{r.detail}</TableCell>
                  <TableCell className="text-right">{r.value}</TableCell>
                  <TableCell className="text-right"><ExportButtons name={r.label} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* One minimal chart */}
      <Card>
        <CardHeader><CardTitle>Revenue by Month — {compact(revenueTrend.reduce((a, r) => a + r.value, 0))} total</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={revenueTrend} margin={{ left: -10 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
              <YAxis tickFormatter={(v) => compact(v)} tickLine={false} axisLine={false} width={64} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
              <Tooltip formatter={(v: number) => currency(v)} cursor={{ fill: "var(--secondary)" }} />
              <Bar dataKey="value" fill="var(--chart-1)" radius={[6, 6, 0, 0]} maxBarSize={44} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </>
  );
}
