import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
  Trash2,
} from "lucide-react";
import { StatusBadge } from "../components/common/StatusBadge";
import { RiskIndicator } from "../components/client/RiskIndicator";
import { DocumentCategoryModal, type DocAction, type DocumentCategory } from "../components/client/DocumentCategoryModal";
import { UploadDocumentModal } from "../components/client/UploadDocumentModal";
import { ScanDocumentModal } from "../components/client/ScanDocumentModal";
import { FilePreviewModal } from "../components/client/FilePreviewModal";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Separator } from "../components/ui/separator";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import { dbIdMap } from "../context/AppContext";
import {
  currency,
  transactions,
  gstReturns,
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
  // ── Invoice modal state ────────────────────────────────────
  const [docAction, setDocAction] = useState<DocAction>("upload");
  const [catModalOpen, setCatModalOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  // ── Uploaded documents list ────────────────────────────────
  const [uploadedDocs, setUploadedDocs] = useState<any[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  // ── File preview state ─────────────────────────────────────
  const [previewDoc, setPreviewDoc] = useState<{ id: string; fileName: string; fileType: string | null } | null>(null);

  // Get the UUID db_id — must come after client guard so we compute it lazily
  const clientDbId = client ? (dbIdMap.get(client.id) ?? "") : "";

  const openCategoryModal = (action: DocAction) => {
    setDocAction(action);
    setCatModalOpen(true);
  };

  const handleCategorySelect = (cat: DocumentCategory) => {
    setSelectedCategory(cat);
    if (docAction === "upload") {
      setUploadOpen(true);
    } else {
      setScanOpen(true);
    }
  };

  // ── Fetch uploaded documents from backend ──────────────────
  const fetchDocs = async () => {
    if (!clientDbId) return;
    setDocsLoading(true);
    try {
      const token = localStorage.getItem("ca_token");
      const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/invoices/${clientDbId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const body = await res.json();
        setUploadedDocs(body.data ?? []);
      }
    } catch {
      // silently ignore — table stays empty
    } finally {
      setDocsLoading(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    const token = localStorage.getItem("ca_token");
    const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
    try {
      await fetch(`${base}/invoices/document/${docId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      setUploadedDocs((prev) => prev.filter((d) => d.id !== docId));
    } catch {
      /* ignore */
    } finally {
      setDeletingDocId(null);
    }
  };

  // Fetch documents whenever the invoices tab is opened or clientDbId is available
  useEffect(() => {
    if (tab === "invoices" && clientDbId) {
      fetchDocs();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, clientDbId]);

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
    { v: "overview",    l: "Overview" },
    { v: "invoices",    l: "Invoices" },
    { v: "accounting",  l: "Accounting" },
    { v: "gsttax",      l: "GST" },
    { v: "reports",     l: "Reports" },
    { v: "insights",    l: "AI Insights" },
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
              <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-1">
                <div className="rounded-lg border border-border p-4"><p className="text-sm text-muted-foreground">GST Filing</p><StatusBadge value={client.gst} className="mt-2" /></div>
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

        {/* Invoices */}
        <TabsContent value="invoices" className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Invoices & Bills</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => openCategoryModal("scan")}><ScanLine className="size-4" /> Scan invoice</Button>
                <Button variant="outline" size="sm" onClick={() => openCategoryModal("upload")}><Upload className="size-4" /> Upload invoice</Button>
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              {docsLoading ? (
                <div className="py-10 text-center text-sm text-muted-foreground">Loading documents…</div>
              ) : uploadedDocs.length === 0 ? (
                <div className="py-10 text-center text-sm text-muted-foreground">
                  No documents yet. Use Scan or Upload to add one.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Category</TableHead>
                      <TableHead>Invoice #</TableHead>
                      <TableHead>Vendor / Party</TableHead>
                      <TableHead>Customer</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>File</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {uploadedDocs.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell className="text-xs text-muted-foreground capitalize">
                          {doc.document_category?.replace(/_/g, " ")}
                        </TableCell>
                        <TableCell className="font-mono text-sm">{doc.invoice_number ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{doc.vendor ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{doc.customer ?? "—"}</TableCell>
                        <TableCell className="text-right">
                          {doc.amount ? currency(Number(doc.amount)) : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{doc.document_type}</TableCell>
                        <TableCell><StatusBadge value={doc.status ?? "pending"} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {doc.file_name ? (
                            <button
                              type="button"
                              onClick={() => setPreviewDoc({ id: doc.id, fileName: doc.file_name, fileType: doc.file_type })}
                              className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-secondary hover:text-foreground transition-colors"
                              title="Click to preview file"
                            >
                              <FileText className="size-3.5 text-primary" />
                              <span className="truncate max-w-[80px] underline underline-offset-2">{doc.file_name}</span>
                            </button>
                          ) : "—"}
                        </TableCell>
                        <TableCell>
                          {deletingDocId === doc.id ? (
                            <span className="text-xs text-muted-foreground">Deleting…</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => { setDeletingDocId(doc.id); handleDeleteDoc(doc.id); }}
                              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                              title="Delete document"
                            >
                              <Trash2 className="size-4" />
                            </button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Reports */}
        <TabsContent value="reports" className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {["Balance Sheet", "Profit & Loss", "GST Summary", "Cash Flow"].map((r) => (
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

      <DocumentCategoryModal
        open={catModalOpen}
        onOpenChange={setCatModalOpen}
        action={docAction}
        onSelect={handleCategorySelect}
      />
      <UploadDocumentModal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        category={selectedCategory}
        clientId={clientDbId}
        onSuccess={fetchDocs}
      />
      <ScanDocumentModal
        open={scanOpen}
        onOpenChange={setScanOpen}
        category={selectedCategory}
        clientId={clientDbId}
        onSuccess={fetchDocs}
      />
      <FilePreviewModal
        open={!!previewDoc}
        onOpenChange={(o) => { if (!o) setPreviewDoc(null); }}
        docId={previewDoc?.id ?? ""}
        fileName={previewDoc?.fileName ?? ""}
        fileType={previewDoc?.fileType ?? null}
      />
    </>
  );
}
