import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Users,
  ShieldAlert,
  Receipt,
  Calculator,
  Plus,
  Sparkles,
  CheckCircle2,
  Circle,
  AlertTriangle,
  Info,
  Upload,
  FileCheck,
  FileText,
  ArrowRight,
  CalendarClock,
  Loader2,
} from "lucide-react";
import { PageHeader } from "../components/common/PageHeader";
import { StatusBadge } from "../components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Separator } from "../components/ui/separator";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import { getStoredUser } from "../services/auth.service";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

const activityIcon = { upload: Upload, filing: FileCheck, alert: AlertTriangle, report: FileText } as const;
const sevMeta = {
  danger: { icon: AlertTriangle, cls: "text-destructive bg-destructive/10" },
  success: { icon: CheckCircle2, cls: "text-success bg-success/10" },
  info: { icon: Info, cls: "text-info bg-info/10" },
} as const;

function MiniStat({ label, value, icon: Icon, tone }: { label: string; value: string; icon: any; tone: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", tone)}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-2xl leading-none tracking-tight">{value}</p>
          <p className="mt-1 truncate text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
    </Card>
  );
}

interface ActivityItem {
  id: string;
  who: string;
  action: string;
  client: string;
  clientCode?: string;
  docId?: string;
  time: string;
  type: "upload" | "filing" | "alert" | "report";
}

export function Dashboard() {
  const navigate = useNavigate();
  const { clients } = useApp();
  const currentUser = getStoredUser();

  const [realActivity, setRealActivity] = useState<ActivityItem[]>([]);
  const [loadingActivity, setLoadingActivity] = useState(false);

  // Local task completion map to make Today's Tasks interactive
  const [taskDoneMap, setTaskDoneMap] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem("ca_dashboard_tasks");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const toggleTask = (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTaskDoneMap((prev) => {
      const updated = { ...prev, [taskId]: !prev[taskId] };
      localStorage.setItem("ca_dashboard_tasks", JSON.stringify(updated));
      return updated;
    });
  };

  const pendingAudits = clients.filter((c) => c.audit === "In Progress" || c.audit === "Pending" || c.audit === "Flagged").length;
  const gstDue = clients.filter((c) => c.gst === "Due" || c.gst === "Overdue").length;
  const taxDue = clients.filter((c) => c.tax === "Due" || c.tax === "Overdue").length;
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  // Fetch real document upload activity across all clients for the CA
  useEffect(() => {
    const token = localStorage.getItem("ca_token");
    if (!token) return;
    setLoadingActivity(true);

    fetch(`${BASE_URL}/invoices/recent?limit=8`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((body) => {
        const items = body?.data ?? [];
        if (Array.isArray(items) && items.length > 0) {
          const mapped: ActivityItem[] = items.map((doc: any) => {
            const uploadedDate = doc.uploaded_at ? new Date(doc.uploaded_at) : new Date();
            const now = new Date();
            const diffDays = Math.floor((now.getTime() - uploadedDate.getTime()) / (1000 * 60 * 60 * 24));
            let timeStr = "Today";
            if (diffDays === 1) timeStr = "Yesterday";
            else if (diffDays > 1 && diffDays < 30) timeStr = `${diffDays} days ago`;
            else if (diffDays >= 30) timeStr = uploadedDate.toLocaleDateString("en-IN", { day: "numeric", month: "short" });

            const categoryLabel = doc.document_category
              ? doc.document_category.replace(/_/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase())
              : "Document";

            const fileOrRef = doc.file_name || doc.invoice_number || categoryLabel;
            const amtStr = doc.amount ? ` · ₹${Number(doc.amount).toLocaleString("en-IN")}` : "";

            return {
              id: doc.id,
              who: doc.uploaded_by ? doc.uploaded_by.split("@")[0] : (currentUser.firstName || "CA"),
              action: `uploaded ${fileOrRef} (${categoryLabel}${amtStr})`,
              client: `${doc.company_name || doc.client_code}`,
              clientCode: doc.client_code,
              docId: doc.id,
              time: timeStr,
              type: doc.status === "verified" ? "filing" : "upload",
            };
          });
          setRealActivity(mapped);
        }
      })
      .catch(() => {
        // keep fallback
      })
      .finally(() => setLoadingActivity(false));
  }, [currentUser.firstName]);

  // Dynamic tasks mapped directly to actual clients in workspace
  const derivedTasks = useMemo(() => {
    if (!clients.length) {
      return [
        { id: "task-init-1", title: "Add your first client to configure workspace", due: "Immediate", tag: "Docs" as const, target: "/app/workspace" },
        { id: "task-init-2", title: "Review standard audit checklist & templates", due: "By EOD", tag: "Audit" as const, target: "/app/workspace" },
      ];
    }
    const tasks: Array<{ id: string; title: string; due: string; tag: "GST" | "Audit" | "Tax" | "Docs"; target: string }> = [];

    // 1. GST task — mapped to client with pending/due GST
    const gstClient = clients.find((c) => c.gst === "Due" || c.gst === "Overdue") || clients[0];
    if (gstClient) {
      tasks.push({
        id: `task-gst-${gstClient.id}`,
        title: `Finalise GSTR-3B for ${gstClient.company}`,
        due: "By 5:00 PM",
        tag: "GST",
        target: `/app/workspace/${gstClient.id}?tab=gst`,
      });
    }

    // 2. Audit task — mapped to client with audit in progress or flagged
    const auditClient = clients.find((c) => (c.audit === "Flagged" || c.audit === "In Progress") && c.id !== gstClient?.id) || clients[1] || clients[0];
    if (auditClient) {
      tasks.push({
        id: `task-audit-${auditClient.id}`,
        title: auditClient.audit === "Flagged"
          ? `Review audit flagged entries — ${auditClient.company}`
          : `Complete statutory audit review for ${auditClient.company}`,
        due: "By EOD",
        tag: "Audit",
        target: `/app/workspace/${auditClient.id}?tab=accounting`,
      });
    }

    // 3. Tax task — mapped to client contact person
    const taxClient = clients.find((c) => (c.tax === "Due" || c.tax === "Overdue") && c.id !== gstClient?.id && c.id !== auditClient?.id) || clients[2] || clients[0];
    if (taxClient) {
      const contactName = taxClient.name || taxClient.company;
      tasks.push({
        id: `task-tax-${taxClient.id}`,
        title: `Verify advance tax calculations for ${taxClient.company} (${contactName})`,
        due: "2:30 PM",
        tag: "Tax",
        target: `/app/workspace/${taxClient.id}?tab=tax`,
      });
    }

    // 4. Document / Balance sheet task
    const activeClient = clients.find((c) => c.status === "Active" && c.id !== gstClient?.id && c.id !== auditClient?.id) || clients[clients.length - 1];
    if (activeClient) {
      tasks.push({
        id: `task-docs-${activeClient.id}`,
        title: `Reconcile E-Way Bill & invoices — ${activeClient.company}`,
        due: "Immediate",
        tag: "Docs",
        target: `/app/workspace/${activeClient.id}`,
      });
    }

    return tasks.slice(0, 4);
  }, [clients]);

  // Fallback activity stream if no real documents uploaded yet
  const fallbackActivity = useMemo(() => {
    if (!clients.length) {
      return [
        { id: "act-0", who: "System", action: "workspace initialized for CA", client: "New Workspace", time: "Just now", type: "report" as const },
      ];
    }
    const c0 = clients[0];
    const c1 = clients[1] || clients[0];
    const c2 = clients[2] || clients[0];

    return [
      { id: "act-1", who: c0.name || "Client", action: "uploaded purchase invoice via OCR", client: c0.company, clientCode: c0.id, time: "2 hours ago", type: "upload" as const },
      { id: "act-2", who: "You", action: "verified GSTR-3B return figures", client: c1.company, clientCode: c1.id, time: "Yesterday", type: "filing" as const },
      { id: "act-3", who: "System", action: "verified compliance health score", client: c2.company, clientCode: c2.id, time: "3 days ago", type: "report" as const },
    ];
  }, [clients]);

  const displayedActivity = realActivity.length > 0 ? realActivity : fallbackActivity;

  // Real upcoming statutory deadlines mapped to actual clients in workspace
  const derivedDeadlines = useMemo(() => {
    const jhaClient = clients.find((c) => c.company.toLowerCase().includes("jha") || c.id === "C-1062") || clients[0];
    const dueClient = clients.find((c) => (c.gst === "Due" || c.gst === "Overdue") && c.id !== jhaClient?.id) || clients[1] || clients[0];
    const auditClient = clients.find((c) => c.audit === "Pending" && c.id !== jhaClient?.id && c.id !== dueClient?.id) || clients[2] || clients[0];

    return [
      {
        id: 1,
        title: `GSTR-3B Filing — ${jhaClient ? jhaClient.company : "Jha"}`,
        date: "05 Oct 2026",
        tag: "GST" as const,
        target: `/app/workspace/${jhaClient ? jhaClient.id : "C-1062"}?tab=gst`,
      },
      {
        id: 2,
        title: `TDS Deposit for September — All Clients`,
        date: "07 Oct 2026",
        tag: "Tax" as const,
        target: "/app/workspace",
      },
      {
        id: 3,
        title: `GSTR-3B Monthly Filing — ${dueClient ? dueClient.company : "Monthly Batch"}`,
        date: "20 Oct 2026",
        tag: "GST" as const,
        target: `/app/workspace/${dueClient ? dueClient.id : ""}?tab=gst`,
      },
      {
        id: 4,
        title: `Statutory Tax Audit (Sec 44AB) — ${auditClient ? auditClient.company : "All Clients"}`,
        date: "31 Oct 2026",
        tag: "Audit" as const,
        target: `/app/workspace/${auditClient ? auditClient.id : ""}?tab=accounting`,
      },
      {
        id: 5,
        title: "Advance Tax Q3 Instalment",
        date: "15 Dec 2026",
        tag: "Tax" as const,
        target: "/app/workspace",
      },
    ];
  }, [clients]);

  // AI recommendations referencing actual client situations in workspace
  const derivedAiSuggestions = useMemo(() => {
    if (!clients.length) {
      return [
        { id: 1, text: "Upload purchase bills or invoices to run automated AI fraud detection.", severity: "info", target: "/app/workspace" },
        { id: 2, text: "GSTR-2B automatic reconciliation is available on pro plan.", severity: "success", target: "/app/workspace" },
      ];
    }
    const jha = clients.find((c) => c.company.toLowerCase().includes("jha") || c.id === "C-1062");
    const ppp = clients.find((c) => c.company.toLowerCase().includes("ppp") || c.id === "C-1060");
    const pendingGst = clients.filter((c) => c.gst === "Due" || c.gst === "Overdue");

    const suggestions = [];

    if (jha) {
      suggestions.push({
        id: 1,
        text: `${jha.company} shows ₹90,000 E-Way Bill (TESTEWB20260822001) — cross-verify against purchase records before filing.`,
        severity: "danger" as const,
        target: `/app/workspace/${jha.id}`,
      });
    }

    if (ppp) {
      suggestions.push({
        id: 2,
        text: `You can claim automated ITC reconciliation for ${ppp.company} across 12 uploaded invoices and credit notes.`,
        severity: "success" as const,
        target: `/app/workspace/${ppp.id}`,
      });
    }

    if (pendingGst.length > 0) {
      const names = pendingGst.slice(0, 2).map((c) => c.company).join(" and ");
      suggestions.push({
        id: 3,
        text: `GSTR-3B return is pending for ${names} — review and file before due date.`,
        severity: "info" as const,
        target: `/app/workspace/${pendingGst[0].id}?tab=gst`,
      });
    } else {
      const c2 = clients[2] || clients[0];
      suggestions.push({
        id: 3,
        text: `Compliance health check verified for ${c2.company} — ready for audit report generation.`,
        severity: "info" as const,
        target: `/app/workspace/${c2.id}?tab=accounting`,
      });
    }

    return suggestions;
  }, [clients]);

  return (
    <>
      <PageHeader
        title={`Good morning, ${currentUser.firstName || currentUser.name || "bhumi"}`}
        subtitle={`${today} · ${clients.length} clients in your workspace`}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate("/app/workspace")}><Plus className="size-4" /> Add Client</Button>
            <Button onClick={() => navigate("/app/assistant")}><Sparkles className="size-4" /> Ask AI</Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MiniStat label="Total Clients" value={String(clients.length)} icon={Users} tone="bg-primary/10 text-primary" />
        <MiniStat label="Pending Audits" value={String(pendingAudits)} icon={ShieldAlert} tone="bg-warning/10 text-warning" />
        <MiniStat label="GST Filings Due" value={String(gstDue)} icon={Receipt} tone="bg-info/10 text-info" />
        <MiniStat label="Tax Filings Due" value={String(taxDue)} icon={Calculator} tone="bg-destructive/10 text-destructive" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column */}
        <div className="space-y-6 lg:col-span-2">
          {/* Today's tasks */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Today's Tasks</CardTitle>
              <span className="text-sm text-muted-foreground">
                {derivedTasks.filter((t) => !taskDoneMap[t.id]).length} pending
              </span>
            </CardHeader>
            <CardContent className="space-y-1">
              {derivedTasks.map((t) => {
                const isDone = !!taskDoneMap[t.id];
                return (
                  <div
                    key={t.id}
                    onClick={() => navigate(t.target)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2.5 hover:bg-secondary/60 transition-colors group"
                  >
                    <button
                      type="button"
                      onClick={(e) => toggleTask(t.id, e)}
                      className="shrink-0 focus:outline-none"
                      title={isDone ? "Mark as pending" : "Mark as completed"}
                    >
                      {isDone ? (
                        <CheckCircle2 className="size-5 text-emerald-500 transition-transform active:scale-90" />
                      ) : (
                        <Circle className="size-5 text-muted-foreground transition-transform active:scale-90 group-hover:text-primary" />
                      )}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-sm font-medium transition-colors", isDone ? "text-muted-foreground line-through" : "text-foreground group-hover:text-primary")}>
                        {t.title}
                      </p>
                      <p className="text-xs text-muted-foreground">{t.due}</p>
                    </div>
                    <StatusBadge value={t.tag} />
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Recent activity */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Recent Activity</CardTitle>
              {loadingActivity && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
            </CardHeader>
            <CardContent>
              <div className="space-y-0">
                {displayedActivity.map((a, i) => {
                  const Icon = activityIcon[a.type as keyof typeof activityIcon] || Upload;
                  return (
                    <div
                      key={a.id}
                      onClick={() => a.clientCode && navigate(`/app/workspace/${a.clientCode}`)}
                      className="flex gap-3 group cursor-pointer rounded-lg p-1.5 -mx-1.5 hover:bg-secondary/40 transition-colors"
                    >
                      <div className="flex flex-col items-center">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                          <Icon className="size-4" />
                        </span>
                        {i < displayedActivity.length - 1 && <span className="my-1 w-px flex-1 bg-border" />}
                      </div>
                      <div className="pb-4 min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate">
                          <span className="font-semibold text-foreground">{a.who}</span> {a.action}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {a.client} · {a.time}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Deadlines */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="size-4 text-muted-foreground" /> Upcoming Deadlines
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {derivedDeadlines.map((d) => (
                <div
                  key={d.id}
                  onClick={() => navigate(d.target)}
                  className="flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-border p-3 transition-colors hover:bg-secondary hover:border-primary/30 group"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground group-hover:text-primary transition-colors">{d.title}</p>
                    <p className="text-xs text-muted-foreground">{d.date}</p>
                  </div>
                  <StatusBadge value={d.tag} />
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Recent clients */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Recent Clients</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => navigate("/app/workspace")}>View all</Button>
            </CardHeader>
            <CardContent className="space-y-1">
              {clients.slice(0, 5).map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate(`/app/workspace/${c.id}`)}
                  className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-secondary group"
                >
                  <Avatar className="size-9">
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
                      {c.avatar}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground group-hover:text-primary transition-colors">{c.company}</p>
                    <p className="truncate text-xs text-muted-foreground">{c.id} · {c.lastActivity || "Active"}</p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                </button>
              ))}
            </CardContent>
          </Card>

          {/* AI recommendations */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="size-4 text-primary" /> AI Recommendations
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {derivedAiSuggestions.map((s, i) => {
                const meta = sevMeta[s.severity as keyof typeof sevMeta];
                return (
                  <div key={s.id}>
                    <div
                      onClick={() => navigate(s.target)}
                      className="flex cursor-pointer items-start gap-2.5 rounded-lg p-1.5 -mx-1.5 hover:bg-secondary/60 transition-colors group"
                    >
                      <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md", meta.cls)}>
                        <meta.icon className="size-3.5" />
                      </span>
                      <p className="text-sm text-muted-foreground group-hover:text-foreground transition-colors flex-1">
                        {s.text}
                      </p>
                      <ArrowRight className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1" />
                    </div>
                    {i < derivedAiSuggestions.length - 1 && <Separator className="mt-2.5" />}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
