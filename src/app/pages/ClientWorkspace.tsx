import { useState, useEffect, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
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
  Eye,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { StatusBadge } from "../components/common/StatusBadge";
import { RiskIndicator } from "../components/client/RiskIndicator";
import { toast } from "sonner";
import { DocumentCategoryModal, DOCUMENT_CATEGORIES, type DocAction, type DocumentCategory } from "../components/client/DocumentCategoryModal";
import { UploadDocumentModal } from "../components/client/UploadDocumentModal";
import { ScanDocumentModal } from "../components/client/ScanDocumentModal";
import { FilePreviewModal } from "../components/client/FilePreviewModal";
import { DocumentDetailModal } from "../components/client/DocumentDetailModal";
import {
  VoucherDetailModal,
  parseLedgerDescription,
  type ParsedLedgerTransaction,
} from "../components/client/VoucherDetailModal";
import { GstWorkspaceView } from "../components/client/GstWorkspaceView";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
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
  const [searchParams] = useSearchParams();
  const urlTab = searchParams.get("tab");
  const { getClient } = useApp();
  const client = getClient(clientId ?? "");
  const [tab, setTab] = useState(() => {
    if (urlTab === "gst") return "gsttax";
    if (urlTab) return urlTab;
    return "overview";
  });

  useEffect(() => {
    if (urlTab) {
      setTab(urlTab === "gst" ? "gsttax" : urlTab);
    }
  }, [urlTab]);

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
  const [docCategoryFilter, setDocCategoryFilter] = useState<string>("all");

  // ── Accounting Ledger records list ─────────────────────────
  const [ledgerRecords, setLedgerRecords] = useState<any[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [selectedVoucher, setSelectedVoucher] = useState<ParsedLedgerTransaction | null>(null);
  const [ledgerSearch, setLedgerSearch] = useState<string>("");
  const [ledgerTypeFilter, setLedgerTypeFilter] = useState<string>("all");
  const [ledgerStatusFilter, setLedgerStatusFilter] = useState<string>("all");

  const displayedDocs = useMemo(() => {
    if (docCategoryFilter === "all") return uploadedDocs;
    return uploadedDocs.filter((d) => d.document_category === docCategoryFilter);
  }, [uploadedDocs, docCategoryFilter]);
  // ── File preview state ─────────────────────────────────────
  const [previewDoc, setPreviewDoc] = useState<{ id: string; fileName: string; fileType: string | null } | null>(null);
  // ── Document detail (View) state ───────────────────────────
  const [viewDocId, setViewDocId] = useState<string | null>(null);

  // Get the UUID db_id — must come after client guard so we compute it lazily
  const clientDbId = client ? (dbIdMap.get(client.id) ?? "") : "";

  const openCategoryModal = (action: DocAction) => {
    setDocAction(action);
    setCatModalOpen(true);
  };

  const openDocumentListUpload = () => {
    const cat = DOCUMENT_CATEGORIES.find((c) => c.id === "document_list") ?? {
      id: "document_list",
      label: "Document List",
      description: "General compliance, identity, and financial documents.",
      usedFor: ["PAN Card", "Aadhaar Card", "Electricity Bill", "Bank Statement"],
      icon: "📁",
    };
    setSelectedCategory(cat);
    setDocAction("upload");
    setUploadOpen(true);
  };

  const handleDownloadDoc = async (docId: string, fileName?: string) => {
    if (!fileName) {
      toast.info("No file attached", {
        description: "This document record contains field data only.",
      });
      return;
    }
    const token = localStorage.getItem("ca_token");
    const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
    const url = `${base}/invoices/document/${docId}/download${token ? `?token=${token}` : ""}`;
    const targetName = fileName || "document";

    try {
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = targetName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
      toast.success("Download started", { description: targetName });
    } catch {
      toast.error("Download failed", {
        description: "The document file was not found on the server.",
      });
    }
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

  // ── Fetch accounting ledger records from backend ───────────
  const fetchLedger = async () => {
    if (!clientDbId) return;
    setLedgerLoading(true);
    try {
      const token = localStorage.getItem("ca_token") || localStorage.getItem("access_token");
      const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/accounting/drafts?client_id=${clientDbId}&status=all`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const body = await res.json();
        if (body?.data && Array.isArray(body.data)) {
          setLedgerRecords(body.data);
        }
      }
    } catch {
      // silently ignore
    } finally {
      setLedgerLoading(false);
    }
  };

  // Fetch documents or ledger records whenever tab is opened or clientDbId is available
  useEffect(() => {
    if (clientDbId) {
      if (tab === "invoices") {
        fetchDocs();
      } else if (tab === "accounting") {
        fetchLedger();
      } else if (tab === "gsttax") {
        fetchDocs();
        fetchLedger();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, clientDbId]);

  // Compute live accounting ledger records with fallback to mock data
  const displayTransactions: ParsedLedgerTransaction[] = useMemo(() => {
    if (ledgerRecords.length > 0) {
      return ledgerRecords.map((r) => {
        const isDebit = Number(r.debit) > 0;
        const amountVal = isDebit ? Number(r.debit) : Number(r.credit);
        const voucher = (r.voucher_type || "").toUpperCase();
        const account = r.category
          ? r.category.replace(/_/g, " ").toUpperCase()
          : voucher || "GENERAL";

        const parsed = parseLedgerDescription(
          r.description,
          r.reference_number,
          voucher,
          r.category || "",
          account
        );

        return {
          id: r.id,
          date: r.transaction_date,
          partyName: parsed.partyName,
          refNo: parsed.refNo,
          taxableAmount: parsed.taxableAmount,
          taxableFormatted: parsed.taxableFormatted,
          taxBreakdown: parsed.taxBreakdown,
          postedAt: parsed.postedAt,
          account,
          type: voucher || (isDebit ? "EXPENSE" : "INCOME"),
          isDebit,
          amount: amountVal,
          debit: Number(r.debit) || 0,
          credit: Number(r.credit) || 0,
          status:
            r.status === "posted"
              ? "Posted"
              : r.status === "draft"
              ? "Draft"
              : r.status || "Posted",
          documentId: r.document_id,
          rawDesc: r.description || "",
        };
      });
    }

    return transactions.map((t) => {
      const isDebit = t.type === "Expense";
      const parsed = parseLedgerDescription(
        t.desc,
        undefined,
        t.type,
        "",
        t.account
      );
      return {
        id: t.id,
        date: t.date,
        partyName: parsed.partyName,
        refNo: parsed.refNo,
        taxableAmount: null,
        taxableFormatted: null,
        taxBreakdown: [],
        postedAt: null,
        account: t.account,
        type: t.type.toUpperCase(),
        isDebit,
        amount: t.amount,
        debit: isDebit ? t.amount : 0,
        credit: !isDebit ? t.amount : 0,
        status: t.status,
        documentId: undefined,
        rawDesc: t.desc,
      };
    });
  }, [ledgerRecords]);

  // Filter transactions by search query, voucher type, and status
  const filteredTransactions = useMemo(() => {
    return displayTransactions.filter((t) => {
      if (ledgerTypeFilter !== "all" && t.type.toLowerCase() !== ledgerTypeFilter.toLowerCase()) {
        return false;
      }
      if (ledgerStatusFilter !== "all" && t.status.toLowerCase() !== ledgerStatusFilter.toLowerCase()) {
        return false;
      }
      if (ledgerSearch.trim()) {
        const q = ledgerSearch.toLowerCase();
        const matchParty = t.partyName.toLowerCase().includes(q);
        const matchRef = t.refNo.toLowerCase().includes(q);
        const matchAcc = t.account.toLowerCase().includes(q);
        const matchDesc = t.rawDesc.toLowerCase().includes(q);
        return matchParty || matchRef || matchAcc || matchDesc;
      }
      return true;
    });
  }, [displayTransactions, ledgerTypeFilter, ledgerStatusFilter, ledgerSearch]);

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
            <CardHeader className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-xl font-bold">Ledger Transactions</CardTitle>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                      {filteredTransactions.length} {filteredTransactions.length === 1 ? "entry" : "entries"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Structured double-entry ledger postings from verified documents and approved vouchers.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={fetchLedger} disabled={ledgerLoading}>
                    <RefreshCw className={cn("size-3.5 mr-1.5", ledgerLoading && "animate-spin")} />
                    Refresh
                  </Button>
                  <Button variant="outline" size="sm">
                    <Upload className="size-4 mr-1.5" /> Import entries
                  </Button>
                </div>
              </div>

              {/* Filter and Search Bar for CA Review */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/40">
                <div className="relative flex-1 min-w-[220px] max-w-sm">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search party, invoice ref, account..."
                    value={ledgerSearch}
                    onChange={(e) => setLedgerSearch(e.target.value)}
                    className="pl-8 h-8 text-xs bg-background"
                  />
                  {ledgerSearch && (
                    <button
                      onClick={() => setLedgerSearch("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Voucher Type Filter */}
                  <Select value={ledgerTypeFilter} onValueChange={setLedgerTypeFilter}>
                    <SelectTrigger className="h-8 text-xs w-[130px]">
                      <SelectValue placeholder="Voucher Type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="sales">Sales</SelectItem>
                      <SelectItem value="purchase">Purchase</SelectItem>
                      <SelectItem value="payment">Payment</SelectItem>
                      <SelectItem value="journal">Journal</SelectItem>
                    </SelectContent>
                  </Select>

                  {/* Status Filter */}
                  <Select value={ledgerStatusFilter} onValueChange={setLedgerStatusFilter}>
                    <SelectTrigger className="h-8 text-xs w-[120px]">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="posted">Posted</SelectItem>
                      <SelectItem value="draft">Draft</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>

            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[110px]">Date</TableHead>
                    <TableHead className="min-w-[280px]">Particulars & Reference</TableHead>
                    <TableHead>Account Head</TableHead>
                    <TableHead>Voucher Type</TableHead>
                    <TableHead className="text-right">Debit / Credit</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center w-[120px]">Audit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledgerLoading && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                        <RefreshCw className="size-5 animate-spin mx-auto mb-2 text-primary" />
                        Loading ledger transactions…
                      </TableCell>
                    </TableRow>
                  )}
                  {!ledgerLoading && filteredTransactions.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                        No transactions found matching your filter criteria.
                      </TableCell>
                    </TableRow>
                  )}
                  {!ledgerLoading && filteredTransactions.map((t) => (
                    <TableRow key={t.id} className="hover:bg-muted/40 transition-colors">
                      {/* Date */}
                      <TableCell className="text-muted-foreground font-mono text-xs whitespace-nowrap align-top py-3">
                        {t.date}
                      </TableCell>

                      {/* Particulars & Reference */}
                      <TableCell className="align-top py-3">
                        <div className="flex flex-col gap-1.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-foreground text-sm tracking-tight">
                              {t.partyName}
                            </span>
                            {t.refNo && (
                              <span className="inline-flex items-center gap-1 font-mono text-[11px] px-2 py-0.5 rounded-md bg-muted/80 text-muted-foreground border border-border/60">
                                <FileText className="size-3 text-primary/70 shrink-0" />
                                {t.refNo}
                              </span>
                            )}
                          </div>

                          {/* Tax Breakdown & Meta Badges */}
                          {(t.taxableFormatted || t.taxBreakdown.length > 0) && (
                            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                              {t.taxableFormatted && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-mono font-medium">
                                  Taxable: {t.taxableFormatted}
                                </span>
                              )}
                              {t.taxBreakdown.map((tb, idx) => (
                                <span
                                  key={idx}
                                  className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-700 dark:text-blue-400 font-mono"
                                >
                                  {tb.head}: {tb.formatted}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </TableCell>

                      {/* Account Head */}
                      <TableCell className="align-top py-3 text-sm text-muted-foreground">
                        {t.account}
                      </TableCell>

                      {/* Voucher Type Badge */}
                      <TableCell className="align-top py-3">
                        <span
                          className={cn(
                            "inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wider",
                            t.type === "SALES" || t.type === "INCOME" || t.type === "RECEIPT"
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                              : t.type === "PURCHASE" || t.type === "EXPENSE"
                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                              : "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                          )}
                        >
                          {t.type}
                        </span>
                      </TableCell>

                      {/* Amount with Debit / Credit tag */}
                      <TableCell className="align-top py-3 text-right">
                        <div className="flex flex-col items-end">
                          <span
                            className={cn(
                              "font-mono font-semibold text-sm",
                              t.isDebit
                                ? "text-blue-600 dark:text-blue-400"
                                : "text-emerald-600 dark:text-emerald-400"
                            )}
                          >
                            {currency(t.amount)}
                          </span>
                          <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground font-medium">
                            {t.isDebit ? "Debit (Dr)" : "Credit (Cr)"}
                          </span>
                        </div>
                      </TableCell>

                      {/* Status */}
                      <TableCell className="align-top py-3">
                        <StatusBadge value={t.status} />
                      </TableCell>

                      {/* Action: View Voucher */}
                      <TableCell className="align-top py-3 text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2.5 text-xs font-medium text-primary hover:text-primary hover:bg-primary/10 border border-transparent hover:border-primary/20"
                          onClick={() => setSelectedVoucher(t)}
                          title="View double-entry voucher breakdown"
                        >
                          <Eye className="size-3.5 mr-1" />
                          Voucher
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* GST & Tax */}
        <TabsContent value="gsttax" className="space-y-6">
          <GstWorkspaceView
            clientId={clientDbId}
            clientCode={client?.id ?? clientId ?? ""}
            clientName={client?.company ?? ""}
            clientGstin={client?.gstin ?? ""}
            uploadedDocs={uploadedDocs}
            ledgerRecords={ledgerRecords}
            onViewDoc={(docId) => setViewDocId(docId)}
            onViewVoucher={(voucherId, docId) => {
              const v = displayTransactions.find(
                (t) => t.id === voucherId || (docId && t.documentId === docId)
              );
              if (v) {
                setSelectedVoucher(v);
              } else {
                setTab("accounting");
              }
            }}
          />
        </TabsContent>

        {/* Invoices */}
        <TabsContent value="invoices" className="space-y-6">
          <Card>
            <CardHeader className="flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle>Invoices &amp; Bills</CardTitle>
                <p className="text-xs text-muted-foreground mt-1">
                  View, scan, and upload client documents user-wise
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={docCategoryFilter} onValueChange={setDocCategoryFilter}>
                  <SelectTrigger className="h-8 w-[160px] text-xs">
                    <SelectValue placeholder="All Categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    <SelectItem value="document_list">📁 Document List</SelectItem>
                    <SelectItem value="b2b_invoice">🏢 B2B Invoice</SelectItem>
                    <SelectItem value="b2c_invoice">👤 B2C Invoice</SelectItem>
                    <SelectItem value="sales_records">📤 Sales Records</SelectItem>
                    <SelectItem value="purchase_records">📥 Purchase Records</SelectItem>
                    <SelectItem value="gst_challan">💳 GST Challan</SelectItem>
                    <SelectItem value="credit_note">↩️ Credit Note</SelectItem>
                    <SelectItem value="debit_note">↪️ Debit Note</SelectItem>
                    <SelectItem value="hsn_sac">📋 HSN / SAC</SelectItem>
                    <SelectItem value="e_invoice">⚡ E-Invoice</SelectItem>
                    <SelectItem value="e_way_bill">🚚 E-Way Bill</SelectItem>
                    <SelectItem value="gst_return">📊 GST Return</SelectItem>
                    <SelectItem value="gst_notice">📨 GST Notice</SelectItem>
                  </SelectContent>
                </Select>
                {docCategoryFilter === "document_list" ? (
                  <Button size="sm" onClick={openDocumentListUpload}>
                    <Plus className="size-4" /> Upload Document
                  </Button>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={() => openCategoryModal("scan")}><ScanLine className="size-4" /> Scan invoice</Button>
                    <Button variant="outline" size="sm" onClick={() => openCategoryModal("upload")}><Upload className="size-4" /> Upload invoice</Button>
                  </>
                )}
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              {docsLoading ? (
                <div className="py-10 text-center text-sm text-muted-foreground">Loading documents…</div>
              ) : displayedDocs.length === 0 ? (
                docCategoryFilter === "document_list" ? (
                  <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
                    <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-2xl text-primary">
                      📁
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-foreground">No KYC or Financial Documents Yet</h4>
                      <p className="max-w-md text-xs text-muted-foreground">
                        Upload customer identity proofs (Aadhaar, PAN), residential proofs (Electricity bill, Rent agreement), bank statements, and compliance certificates for CA inspection.
                      </p>
                    </div>
                    <Button size="sm" className="mt-2" onClick={openDocumentListUpload}>
                      <Plus className="size-4" /> Upload Document
                    </Button>
                  </div>
                ) : (
                  <div className="py-10 text-center text-sm text-muted-foreground">
                    {uploadedDocs.length === 0
                      ? "No documents yet. Use Scan or Upload to add one."
                      : "No documents found for the selected category."}
                  </div>
                )
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Category</TableHead>
                      <TableHead>{docCategoryFilter === "document_list" ? "Ref / ID #" : "Invoice / Ref #"}</TableHead>
                      <TableHead>{docCategoryFilter === "document_list" ? "Document Title / Type" : "Vendor / Party / Title"}</TableHead>
                      <TableHead>{docCategoryFilter === "document_list" ? "Person / Entity" : "Customer / User"}</TableHead>
                      {docCategoryFilter !== "document_list" && (
                        <TableHead className="text-right">Amount</TableHead>
                      )}
                      <TableHead>Type</TableHead>
                      <TableHead>Uploaded By</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>File</TableHead>
                      <TableHead className="w-[140px] text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {displayedDocs.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell className="text-xs text-muted-foreground capitalize">
                          {doc.document_category === "document_list" ? (
                            <span className="inline-flex items-center gap-1 font-medium text-foreground">
                              📁 Document List
                            </span>
                          ) : (
                            doc.document_category?.replace(/_/g, " ")
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-sm">{doc.invoice_number ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground font-medium">{doc.vendor ?? "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{doc.customer ?? "—"}</TableCell>
                        {docCategoryFilter !== "document_list" && (
                          <TableCell className="text-right">
                            {doc.amount ? currency(Number(doc.amount)) : "—"}
                          </TableCell>
                        )}
                        <TableCell className="text-xs">
                          <span
                            className={cn(
                              "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize",
                              doc.document_type === "upload"
                                ? "bg-blue-500/10 text-blue-500 border border-blue-500/20"
                                : "bg-purple-500/10 text-purple-500 border border-purple-500/20"
                            )}
                          >
                            {doc.document_type}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {doc.uploaded_by ? (
                            <span
                              className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-[11px] font-medium"
                              title={doc.uploaded_by}
                            >
                              <User className="size-3 text-muted-foreground" />
                              <span className="truncate max-w-[100px]">{doc.uploaded_by.split("@")[0]}</span>
                            </span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
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
                        <TableCell className="text-right">
                          {deletingDocId === doc.id ? (
                            <span className="text-xs text-muted-foreground">Deleting…</span>
                          ) : (
                            <div className="flex items-center justify-end gap-1">
                              <button
                                type="button"
                                onClick={() => setViewDocId(doc.id)}
                                className="inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-2 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10 focus:outline-none focus:ring-2 focus:ring-primary/40"
                                title="View document details"
                              >
                                <Eye className="size-3.5" />
                                View
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDownloadDoc(doc.id, doc.file_name)}
                                className={cn(
                                  "inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-medium transition-colors focus:outline-none",
                                  doc.file_name
                                    ? "bg-secondary/50 text-muted-foreground hover:bg-secondary hover:text-foreground"
                                    : "bg-secondary/20 text-muted-foreground/40 cursor-not-allowed"
                                )}
                                title={doc.file_name ? "Download file" : "No file attached"}
                              >
                                <Download className="size-3.5" />
                                Download
                              </button>
                              <button
                                type="button"
                                onClick={() => { setDeletingDocId(doc.id); handleDeleteDoc(doc.id); }}
                                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                                title="Delete document"
                              >
                                <Trash2 className="size-4" />
                              </button>
                            </div>
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
      <DocumentDetailModal
        open={!!viewDocId}
        onOpenChange={(o) => { if (!o) setViewDocId(null); }}
        docId={viewDocId ?? ""}
        onUpdate={() => {
          fetchDocs();
          fetchLedger();
        }}
        onNavigateTab={(targetTab) => setTab(targetTab)}
        onViewVoucher={(voucherId) => {
          setTab("accounting");
          const v = displayTransactions.find((t) => t.id === voucherId || t.documentId === viewDocId);
          if (v) setSelectedVoucher(v);
        }}
        allDocs={uploadedDocs}
      />
      <VoucherDetailModal
        open={!!selectedVoucher}
        onOpenChange={(o) => { if (!o) setSelectedVoucher(null); }}
        voucher={selectedVoucher}
        onViewSourceDoc={(docId) => {
          setSelectedVoucher(null);
          setViewDocId(docId);
        }}
      />
    </>
  );
}
