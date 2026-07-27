import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  Building2,
  User,
  Mail,
  Phone,
  MapPin,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Info,
  Upload,
  FileText,
  Download,
  TrendingUp,
  TrendingDown,
  Wallet,
  ScanLine,
} from "lucide-react";
import { StatusBadge } from "../components/common/StatusBadge";
import { RiskIndicator } from "../components/client/RiskIndicator";
import { ScanInvoiceDialog } from "../components/client/ScanInvoiceDialog";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Separator } from "../components/ui/separator";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import {
  currency,
  transactions,
  gstReturns,
  clientInvoices,
  clientDocuments,
  clientHistory,
  fraudIndicators,
  hsnCodes,
  aiSuggestions,
} from "../data/mock";

const sevMeta = {
  danger: { icon: AlertTriangle, cls: "text-destructive bg-destructive/10" },
  warning: { icon: AlertTriangle, cls: "text-warning bg-warning/10" },
  success: { icon: CheckCircle2, cls: "text-success bg-success/10" },
  info: { icon: Info, cls: "text-info bg-info/10" },
} as const;

function Metric({ label, value, icon: Icon, tone }: { label: string; value: string; icon: any; tone: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", tone)}><Icon className="size-5" /></span>
        <div className="min-w-0">
          <p className="text-xl leading-none tracking-tight">{value}</p>
          <p className="mt-1 truncate text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
    </Card>
  );
}

export function ClientWorkspace() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const { getClient } = useApp();
  const client = getClient(clientId ?? "");
  const [tab, setTab] = useState("overview");
  const [scanOpen, setScanOpen] = useState(false);

  if (!client) {
    return (
      <Card>
        <CardContent className="py-16 text-center">
          <p className="text-muted-foreground">This client could not be found.</p>
          <Button className="mt-4" onClick={() => navigate("/app/workspace")}><ArrowLeft className="size-4" /> Back to Workspace</Button>
        </CardContent>
      </Card>
    );
  }

  const expenses = Math.round(client.revenue * 0.52);
  const profit = client.revenue - expenses;

  const tabs = [
    { v: "overview", l: "Overview" },
    { v: "accounting", l: "Accounting" },
    { v: "gsttax", l: "GST & Tax" },
    { v: "auditing", l: "Auditing" },
    { v: "invoices", l: "Invoices" },
    { v: "documents", l: "Documents" },
    { v: "reports", l: "Reports" },
    { v: "history", l: "History" },
    { v: "insights", l: "AI Insights" },
  ];

  return (
    <>
      {/* Header */}
      <div className="flex flex-col gap-4">
        <Button variant="ghost" size="sm" className="w-fit -ml-2" onClick={() => navigate("/app/workspace")}>
          <ArrowLeft className="size-4" /> Back to Workspace
        </Button>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <Avatar className="size-14"><AvatarFallback className="bg-primary/10 text-primary">{client.avatar}</AvatarFallback></Avatar>
            <div>
              <div className="flex items-center gap-2">
                <h1>{client.company}</h1>
                <StatusBadge value={client.status} />
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">{client.type === "Individual" ? <User className="size-3.5" /> : <Building2 className="size-3.5" />} {client.type}</span>
                <span>· {client.id}</span>
                <span>· {client.name}</span>
                <span className="font-mono">· {client.gstin}</span>
              </p>
            </div>
          </div>
          <RiskIndicator level={client.risk} />
        </div>
      </div>

      {/* Horizontal tabs */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <div className="overflow-x-auto">
          <TabsList className="w-max">
            {tabs.map((t) => <TabsTrigger key={t.v} value={t.v}>{t.l}</TabsTrigger>)}
          </TabsList>
        </div>

        {/* Overview */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Metric label="Annual Revenue" value={currency(client.revenue)} icon={TrendingUp} tone="bg-success/10 text-success" />
            <Metric label="Expenses" value={currency(expenses)} icon={TrendingDown} tone="bg-destructive/10 text-destructive" />
            <Metric label="Net Profit" value={currency(profit)} icon={Wallet} tone="bg-primary/10 text-primary" />
            <Metric label="Risk Level" value={client.risk} icon={AlertTriangle} tone="bg-warning/10 text-warning" />
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader><CardTitle>Compliance Snapshot</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-border p-4"><p className="text-sm text-muted-foreground">GST Filing</p><StatusBadge value={client.gst} className="mt-2" /></div>
                <div className="rounded-lg border border-border p-4"><p className="text-sm text-muted-foreground">Audit</p><StatusBadge value={client.audit} className="mt-2" /></div>
                <div className="rounded-lg border border-border p-4"><p className="text-sm text-muted-foreground">Tax Filing</p><StatusBadge value={client.tax} className="mt-2" /></div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Contact</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="flex items-center gap-2 text-muted-foreground"><User className="size-4" /> {client.name}</p>
                <p className="flex items-center gap-2 text-muted-foreground"><Mail className="size-4" /> {client.name.split(" ")[0].toLowerCase()}@{client.company.split(" ")[0].toLowerCase()}.com</p>
                <p className="flex items-center gap-2 text-muted-foreground"><Phone className="size-4" /> +91 98{client.id.replace(/\D/g, "")} 45678</p>
                <p className="flex items-center gap-2 text-muted-foreground"><MapPin className="size-4" /> Mumbai, Maharashtra</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Accounting */}
        <TabsContent value="accounting" className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Ledger Transactions</CardTitle>
              <Button variant="outline" size="sm"><Upload className="size-4" /> Import entries</Button>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Account</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {transactions.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="text-muted-foreground">{t.date}</TableCell>
                      <TableCell>{t.desc}</TableCell>
                      <TableCell className="text-muted-foreground">{t.account}</TableCell>
                      <TableCell><span className={t.type === "Income" ? "text-success" : "text-destructive"}>{t.type}</span></TableCell>
                      <TableCell className="text-right">{currency(t.amount)}</TableCell>
                      <TableCell><StatusBadge value={t.status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* GST & Tax */}
        <TabsContent value="gsttax" className="space-y-6">
          <Card>
            <CardHeader><CardTitle>GST Returns</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader><TableRow><TableHead>Period</TableHead><TableHead>Form</TableHead><TableHead>Due date</TableHead><TableHead className="text-right">Tax</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {gstReturns.map((g, i) => (
                    <TableRow key={i}>
                      <TableCell>{g.period}</TableCell>
                      <TableCell className="text-muted-foreground">{g.form}</TableCell>
                      <TableCell className="text-muted-foreground">{g.due}</TableCell>
                      <TableCell className="text-right">{currency(g.tax)}</TableCell>
                      <TableCell><StatusBadge value={g.status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>HSN / SAC Summary</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Description</TableHead><TableHead className="text-right">Rate</TableHead></TableRow></TableHeader>
                <TableBody>
                  {hsnCodes.map((h) => (
                    <TableRow key={h.code}><TableCell className="font-mono">{h.code}</TableCell><TableCell>{h.desc}</TableCell><TableCell className="text-right">{h.rate}%</TableCell></TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Auditing */}
        <TabsContent value="auditing" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {fraudIndicators.map((f) => (
              <Card key={f.label} className="p-4">
                <p className="text-2xl leading-none tracking-tight">{f.value}</p>
                <p className="mt-2 text-sm text-muted-foreground">{f.label}</p>
                <StatusBadge value={f.severity === "danger" ? "Flagged" : "Review"} className="mt-2" />
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader><CardTitle>Audit Findings</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {aiSuggestions.map((s) => {
                const meta = sevMeta[s.severity as keyof typeof sevMeta];
                return (
                  <div key={s.id} className="flex items-start gap-2.5 rounded-lg border border-border p-3">
                    <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md", meta.cls)}><meta.icon className="size-3.5" /></span>
                    <p className="text-sm text-muted-foreground">{s.text}</p>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Invoices */}
        <TabsContent value="invoices" className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Invoices & Bills</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setScanOpen(true)}><ScanLine className="size-4" /> Scan invoice</Button>
                <Button variant="outline" size="sm"><Upload className="size-4" /> Upload invoice</Button>
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader><TableRow><TableHead>Number</TableHead><TableHead>Date</TableHead><TableHead>Party</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {clientInvoices.map((inv) => (
                    <TableRow key={inv.id}>
                      <TableCell className="font-mono">{inv.id}</TableCell>
                      <TableCell className="text-muted-foreground">{inv.date}</TableCell>
                      <TableCell>{inv.party}</TableCell>
                      <TableCell className="text-muted-foreground">{inv.type}</TableCell>
                      <TableCell className="text-right">{currency(inv.amount)}</TableCell>
                      <TableCell><StatusBadge value={inv.status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documents */}
        <TabsContent value="documents" className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Documents</CardTitle>
              <Button variant="outline" size="sm"><Upload className="size-4" /> Upload</Button>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {clientDocuments.map((d) => (
                <div key={d.name} className="flex items-center gap-3 rounded-lg border border-border p-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground"><FileText className="size-5" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{d.name}</p>
                    <p className="text-xs text-muted-foreground">{d.type} · {d.size} · {d.date}</p>
                  </div>
                  <Button variant="ghost" size="icon"><Download className="size-4" /></Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Reports */}
        <TabsContent value="reports" className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {["Balance Sheet", "Profit & Loss", "GST Summary", "Tax Computation", "Audit Report", "Cash Flow"].map((r) => (
              <Card key={r} className="p-5">
                <div className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><FileText className="size-5" /></span>
                  <p className="text-sm">{r}</p>
                </div>
                <div className="mt-4 flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1"><Download className="size-4" /> PDF</Button>
                  <Button variant="outline" size="sm" className="flex-1"><Download className="size-4" /> Excel</Button>
                </div>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* History */}
        <TabsContent value="history" className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Activity History</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-0">
                {clientHistory.map((h, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className={cn("mt-1 size-2.5 shrink-0 rounded-full", h.type === "success" ? "bg-success" : "bg-info")} />
                      {i < clientHistory.length - 1 && <span className="my-1 w-px flex-1 bg-border" />}
                    </div>
                    <div className="pb-5">
                      <p className="text-sm">{h.event}</p>
                      <p className="text-xs text-muted-foreground">{h.time}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI Insights */}
        <TabsContent value="insights" className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> AI Insights for {client.company}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {aiSuggestions.map((s, i) => {
                const meta = sevMeta[s.severity as keyof typeof sevMeta];
                return (
                  <div key={s.id}>
                    <div className="flex items-start gap-2.5">
                      <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md", meta.cls)}><meta.icon className="size-3.5" /></span>
                      <p className="text-sm text-muted-foreground">{s.text}</p>
                    </div>
                    {i < aiSuggestions.length - 1 && <Separator className="mt-3" />}
                  </div>
                );
              })}
              <Button className="mt-2" onClick={() => navigate("/app/assistant")}><Sparkles className="size-4" /> Ask AI about this client</Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <ScanInvoiceDialog open={scanOpen} onOpenChange={setScanOpen} />
    </>
  );
}
