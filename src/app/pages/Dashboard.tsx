import { useNavigate } from "react-router";
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
} from "lucide-react";
import { PageHeader } from "../components/common/PageHeader";
import { StatusBadge } from "../components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Separator } from "../components/ui/separator";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import {
  deadlines,
  aiSuggestions,
  todaysTasks,
  recentActivity,
} from "../data/mock";

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

export function Dashboard() {
  const navigate = useNavigate();
  const { clients } = useApp();

  const pendingAudits = clients.filter((c) => c.audit === "In Progress" || c.audit === "Pending" || c.audit === "Flagged").length;
  const gstDue = clients.filter((c) => c.gst === "Due" || c.gst === "Overdue").length;
  const taxDue = clients.filter((c) => c.tax === "Due" || c.tax === "Overdue").length;
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <>
      <PageHeader
        title="Good morning, Rahul"
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
              <span className="text-sm text-muted-foreground">{todaysTasks.filter((t) => !t.done).length} pending</span>
            </CardHeader>
            <CardContent className="space-y-1">
              {todaysTasks.map((t) => (
                <div key={t.id} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-secondary/60">
                  {t.done ? <CheckCircle2 className="size-5 shrink-0 text-success" /> : <Circle className="size-5 shrink-0 text-muted-foreground" />}
                  <div className="min-w-0 flex-1">
                    <p className={cn("text-sm", t.done && "text-muted-foreground line-through")}>{t.title}</p>
                    <p className="text-xs text-muted-foreground">{t.due}</p>
                  </div>
                  <StatusBadge value={t.tag} />
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Recent activity */}
          <Card>
            <CardHeader><CardTitle>Recent Activity</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-0">
                {recentActivity.map((a, i) => {
                  const Icon = activityIcon[a.type as keyof typeof activityIcon];
                  return (
                    <div key={a.id} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-muted-foreground">
                          <Icon className="size-4" />
                        </span>
                        {i < recentActivity.length - 1 && <span className="my-1 w-px flex-1 bg-border" />}
                      </div>
                      <div className="pb-5">
                        <p className="text-sm">
                          <span className="text-foreground">{a.who}</span> {a.action}
                        </p>
                        <p className="text-xs text-muted-foreground">{a.client} · {a.time}</p>
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
              <CardTitle className="flex items-center gap-2"><CalendarClock className="size-4 text-muted-foreground" /> Upcoming Deadlines</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {deadlines.map((d) => (
                <div key={d.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{d.title}</p>
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
                  className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-secondary"
                >
                  <Avatar className="size-9"><AvatarFallback className="bg-primary/10 text-primary text-xs">{c.avatar}</AvatarFallback></Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{c.company}</p>
                    <p className="truncate text-xs text-muted-foreground">{c.id} · {c.lastActivity}</p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </CardContent>
          </Card>

          {/* AI recommendations */}
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> AI Recommendations</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {aiSuggestions.map((s, i) => {
                const meta = sevMeta[s.severity as keyof typeof sevMeta];
                return (
                  <div key={s.id}>
                    <div className="flex items-start gap-2.5">
                      <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md", meta.cls)}>
                        <meta.icon className="size-3.5" />
                      </span>
                      <p className="text-sm text-muted-foreground">{s.text}</p>
                    </div>
                    {i < aiSuggestions.length - 1 && <Separator className="mt-3" />}
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
