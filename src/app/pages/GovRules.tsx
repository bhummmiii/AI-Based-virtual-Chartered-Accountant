import { useState, useEffect, useCallback } from "react";
import {
  Search,
  Bookmark,
  BookmarkCheck,
  Sparkles,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Calendar,
  Layers,
  ChevronLeft,
  ChevronRight,
  Database,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { PageHeader } from "../components/common/PageHeader";
import { StatusBadge } from "../components/common/StatusBadge";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../components/ui/sheet";
import {
  govUpdatesService,
  GovUpdate,
  GovSource,
  GovMetaResponse,
} from "../services/govUpdates.service";
import { getStoredUser } from "../services/auth.service";

export function GovRules() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("all");
  const [docTypeFilter, setDocTypeFilter] = useState("");
  const [lawVersionFilter, setLawVersionFilter] = useState("");
  const [includeArchive, setIncludeArchive] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const [updates, setUpdates] = useState<GovUpdate[]>([]);
  const [total, setTotal] = useState(0);
  const [meta, setMeta] = useState<GovMetaResponse | null>(null);
  const [sources, setSources] = useState<GovSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Drawers
  const [selectedUpdate, setSelectedUpdate] = useState<GovUpdate | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const user = getStoredUser();
  const isCAOrAdmin = user.role === "ca" || user.role === "admin";

  const fetchMeta = useCallback(async () => {
    try {
      const data = await govUpdatesService.getMeta();
      setMeta(data);
    } catch (err) {
      console.warn("Failed to load gov meta:", err);
    }
  }, []);

  const fetchSources = useCallback(async () => {
    if (!isCAOrAdmin) return;
    try {
      const data = await govUpdatesService.getSources();
      setSources(data);
    } catch (err) {
      console.warn("Failed to load sources:", err);
    }
  }, [isCAOrAdmin]);

  const fetchUpdates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let categoryParam: string | undefined = undefined;
      let savedParam = false;

      if (tab === "gst") categoryParam = "GST";
      else if (tab === "income") categoryParam = "INCOME_TAX";
      else if (tab === "budget") categoryParam = "BUDGET";
      else if (tab === "accounting") categoryParam = "ACCOUNTING";
      else if (tab === "saved") savedParam = true;

      const res = await govUpdatesService.getUpdates({
        category: categoryParam,
        saved: savedParam,
        doc_type: docTypeFilter || undefined,
        law_version: lawVersionFilter || undefined,
        include_archive: includeArchive,
        q: q.trim() || undefined,
        page,
        page_size: pageSize,
      });

      setUpdates(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load government updates";
      setError(msg);
      setUpdates([]);
    } finally {
      setLoading(false);
    }
  }, [tab, docTypeFilter, lawVersionFilter, includeArchive, q, page]);

  useEffect(() => {
    fetchMeta();
    fetchUpdates();
  }, [fetchMeta, fetchUpdates]);

  // Refetch on window focus (J9)
  useEffect(() => {
    const onFocus = () => {
      fetchMeta();
      fetchUpdates();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetchMeta, fetchUpdates]);

  const handleToggleBookmark = async (update: GovUpdate) => {
    try {
      if (update.is_saved) {
        await govUpdatesService.unsaveUpdate(update.id);
        setUpdates((prev) =>
          prev.map((u) => (u.id === update.id ? { ...u, is_saved: false } : u)),
        );
      } else {
        await govUpdatesService.saveUpdate(update.id);
        setUpdates((prev) =>
          prev.map((u) => (u.id === update.id ? { ...u, is_saved: true } : u)),
        );
      }
    } catch (err) {
      console.error("Failed to toggle bookmark:", err);
    }
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      await govUpdatesService.triggerSync();
      await Promise.all([fetchMeta(), fetchUpdates(), fetchSources()]);
    } catch (err) {
      console.error("Sync failed:", err);
    } finally {
      setSyncing(false);
    }
  };

  const handleToggleSource = async (sourceId: string, currentEnabled: boolean) => {
    try {
      const updated = await govUpdatesService.toggleSource(sourceId, !currentEnabled);
      setSources((prev) => prev.map((s) => (s.id === sourceId ? updated : s)));
      fetchMeta();
    } catch (err) {
      console.error("Failed to toggle source:", err);
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;
  const [reprobingId, setReprobingId] = useState<string | null>(null);
  const [manualImportOpen, setManualImportOpen] = useState(false);

  const formatTime = (isoStr?: string | null) => {
    if (!isoStr) return "Never";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "Never";
    }
  };

  const handleReprobeSource = async (sourceId: string) => {
    setReprobingId(sourceId);
    try {
      const updated = await govUpdatesService.reprobeSource(sourceId);
      setSources((prev) => prev.map((s) => (s.id === sourceId ? updated : s)));
      await fetchMeta();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Reprobe failed";
      alert(msg);
    } finally {
      setReprobingId(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Government Rule Engine"
        subtitle="Latest circulars, GST updates & budget highlights — explained simply"
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {meta && (
              <div className="flex flex-col items-end text-xs text-muted-foreground mr-1">
                <span>
                  Last successful sync {formatTime(meta.last_sync_at)} &mdash; {meta.sources_total} sources: {meta.sources_ok} ok / {meta.sources_degraded} degraded / {meta.sources_blocked} blocked / {meta.sources_unreachable} unreachable / {meta.sources_disabled} disabled
                </span>
                {meta.last_attempt_at && (
                  <span className="text-[11px] text-muted-foreground/80">
                    Last attempt {formatTime(meta.last_attempt_at)}
                  </span>
                )}
              </div>
            )}
            {isCAOrAdmin && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    fetchSources();
                    setSourcesOpen(true);
                  }}
                  className="gap-1.5"
                >
                  <Database className="size-3.5" />
                  Sources
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleSyncNow}
                  disabled={syncing}
                  className="gap-1.5"
                >
                  <RefreshCw className={`size-3.5 ${syncing ? "animate-spin" : ""}`} />
                  {syncing ? "Syncing..." : "Sync now"}
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Tabs and Search Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={tab}
          onValueChange={(val) => {
            setTab(val);
            setPage(1);
          }}
        >
          <TabsList className="flex flex-wrap">
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="gst">GST</TabsTrigger>
            <TabsTrigger value="income">Income Tax</TabsTrigger>
            <TabsTrigger value="budget">Budget</TabsTrigger>
            <TabsTrigger value="accounting">Accounting</TabsTrigger>
            <TabsTrigger value="saved">Saved</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="Search circulars, rules, numbers…"
            className="pl-9"
          />
        </div>
      </div>

      {/* Filter Controls */}
      <div className="flex flex-wrap items-center gap-2.5 rounded-lg border bg-card/40 p-2.5 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">Type:</span>
          <select
            value={docTypeFilter}
            onChange={(e) => {
              setDocTypeFilter(e.target.value);
              setPage(1);
            }}
            className="rounded border bg-background px-2 py-1 text-xs text-foreground focus:outline-none"
          >
            <option value="">All Types</option>
            <option value="circular">Circular</option>
            <option value="notification">Notification</option>
            <option value="order">Order</option>
            <option value="advisory">Advisory</option>
            <option value="press_release">Press Release</option>
            <option value="gazette">Gazette</option>
            <option value="standard">Standard</option>
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">Law:</span>
          <select
            value={lawVersionFilter}
            onChange={(e) => {
              setLawVersionFilter(e.target.value);
              setPage(1);
            }}
            className="rounded border bg-background px-2 py-1 text-xs text-foreground focus:outline-none"
          >
            <option value="">All Laws</option>
            <option value="CGST Act 2017">CGST Act 2017</option>
            <option value="Income-tax Act, 2025">Income-tax Act, 2025</option>
            <option value="Income-tax Act, 1961">Income-tax Act, 1961</option>
            <option value="Companies Act 2013">Companies Act 2013</option>
            <option value="RBI Act 1934">RBI Act 1934</option>
          </select>
        </div>

        <label className="ml-auto flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
          <input
            type="checkbox"
            checked={includeArchive}
            onChange={(e) => {
              setIncludeArchive(e.target.checked);
              setPage(1);
            }}
            className="rounded border-border"
          />
          Include archive / superseded
        </label>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="py-20 text-center text-muted-foreground">
          <RefreshCw className="mx-auto size-6 animate-spin opacity-50 mb-2" />
          Loading statutory updates from official registry…
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-12 text-center text-destructive">
            <AlertTriangle className="mx-auto size-8 mb-2 opacity-80" />
            <p className="font-medium">Error loading updates</p>
            <p className="text-xs text-muted-foreground mt-1">{error}</p>
          </CardContent>
        </Card>
      ) : updates.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-muted-foreground">
            {total === 0 && !q && tab === "all" ? (
              <div className="space-y-3">
                <FileText className="mx-auto size-10 opacity-30" />
                <p className="text-base font-medium">No updates synced yet</p>
                <p className="text-xs max-w-sm mx-auto">
                  Click &ldquo;Sync now&rdquo; above to ingest live circulars, notifications, and gazettes from official sources.
                </p>
                {isCAOrAdmin && (
                  <Button size="sm" onClick={handleSyncNow} disabled={syncing} className="gap-1.5">
                    <RefreshCw className={`size-3.5 ${syncing ? "animate-spin" : ""}`} />
                    Sync now
                  </Button>
                )}
              </div>
            ) : (
              <p>No notifications match your filters.</p>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {updates.map((r) => {
              const hasTds = r.category === "TDS" || r.topics?.includes("tds_tcs");
              const isOperative = r.legal_status === "operative_instrument";
              const isPressRelease = r.legal_status === "press_release_not_law";

              return (
                <Card key={r.id} className="gap-0 p-5 transition-shadow hover:shadow-md flex flex-col justify-between">
                  <div>
                    {/* Top Chips Row */}
                    <div className="mb-3 flex items-start justify-between gap-2 flex-wrap">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <StatusBadge value={r.category} className="bg-primary/10 text-primary border-primary/20 text-xs" />
                        {hasTds && r.category !== "TDS" && (
                          <Badge variant="outline" className="bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20 text-xs">
                            TDS
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-xs uppercase">
                          {r.doc_type}
                        </Badge>
                        {isOperative ? (
                          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 text-[10px]">
                            Operative
                          </Badge>
                        ) : isPressRelease ? (
                          <Badge variant="outline" className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 text-[10px]">
                            Press Release — Not Law
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px]">
                            {r.legal_status.replace(/_/g, " ")}
                          </Badge>
                        )}
                        {r.is_new && (
                          <Badge className="bg-emerald-600 text-white font-semibold text-[10px] px-1.5 py-0 animate-pulse">
                            New
                          </Badge>
                        )}
                        {r.status === "superseded" && (
                          <Badge variant="destructive" className="text-[10px]">
                            Superseded
                          </Badge>
                        )}
                        {r.status === "withdrawn" && (
                          <Badge variant="secondary" className="text-[10px]">
                            Withdrawn
                          </Badge>
                        )}
                      </div>

                      <button
                        onClick={() => handleToggleBookmark(r)}
                        className="text-muted-foreground hover:text-primary transition-colors p-1"
                        title={r.is_saved ? "Remove bookmark" : "Save bookmark"}
                      >
                        {r.is_saved ? (
                          <BookmarkCheck className="size-4.5 text-primary" />
                        ) : (
                          <Bookmark className="size-4.5" />
                        )}
                      </button>
                    </div>

                    {/* Title */}
                    <h3 className="text-base font-semibold leading-snug tracking-tight text-foreground">{r.title}</h3>

                    {/* Metadata Sub-line */}
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Calendar className="size-3" />
                        {r.issue_date || "Date not stated"}
                      </span>
                      {r.doc_number && <span className="font-mono text-[11px]">#{r.doc_number}</span>}
                      {r.law_version && r.law_version !== "unknown" && (
                        <span className="text-primary/80 font-medium">{r.law_version}</span>
                      )}
                      <span>{r.source_name || r.source_domain}</span>
                    </div>

                    {/* AI Explanation / Content Excerpt */}
                    <div className="mt-3 rounded-lg bg-accent/60 p-3 text-sm">
                      <div className="flex items-start gap-2">
                        <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                        <div className="space-y-1">
                          <p className="text-sm text-foreground/90 leading-relaxed">
                            {r.ai_summary?.summary || (r.content_text ? r.content_text.slice(0, 280) + "…" : "Official notification issued.")}
                          </p>
                          {r.ai_summary?.who_is_affected && (
                            <p className="text-xs text-muted-foreground">
                              <strong className="text-foreground/80">Affected:</strong> {r.ai_summary.who_is_affected}
                            </p>
                          )}
                          <p className="text-[10px] text-muted-foreground/75 italic pt-0.5">
                            AI-generated simple explanation - verify against the official document
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Actions footer */}
                  <div className="mt-4 flex items-center justify-between pt-2 border-t border-border/40">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedUpdate(r)}
                      className="text-xs font-medium"
                    >
                      Read full circular
                    </Button>
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
                    >
                      Official source
                      <ExternalLink className="size-3" />
                    </a>
                  </div>
                </Card>
              );
            })}
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-between border-t pt-4 text-xs text-muted-foreground">
              <span>
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total} updates
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="size-8 p-0"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <span>
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="size-8 p-0"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Detail Drawer (Sheet) */}
      <Sheet open={!!selectedUpdate} onOpenChange={(open) => !open && setSelectedUpdate(null)}>
        <SheetContent side="right" className="sm:max-w-xl overflow-y-auto">
          {selectedUpdate && (
            <div className="space-y-5">
              <SheetHeader>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
                    {selectedUpdate.category}
                  </Badge>
                  <Badge variant="outline">{selectedUpdate.doc_type}</Badge>
                  <Badge variant="secondary">{selectedUpdate.legal_status.replace(/_/g, " ")}</Badge>
                  {selectedUpdate.law_version && selectedUpdate.law_version !== "unknown" && (
                    <Badge variant="outline">{selectedUpdate.law_version}</Badge>
                  )}
                  {selectedUpdate.is_new && <Badge className="bg-emerald-600 text-white">New</Badge>}
                </div>
                <SheetTitle className="text-xl leading-snug">{selectedUpdate.title}</SheetTitle>
                <SheetDescription className="text-xs">
                  Source: {selectedUpdate.source_name || selectedUpdate.source_domain} • Issued:{" "}
                  {selectedUpdate.issue_date || "Date not stated"}
                </SheetDescription>
              </SheetHeader>

              {/* AI Explanation Box */}
              <div className="rounded-lg border bg-accent/30 p-4 space-y-3">
                <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                  <Sparkles className="size-4" />
                  AI Plain-Language Explanation
                </div>
                <p className="text-sm leading-relaxed">
                  {selectedUpdate.ai_summary?.summary || selectedUpdate.content_text?.slice(0, 400) || "Official notification."}
                </p>

                {selectedUpdate.ai_summary?.who_is_affected && (
                  <div>
                    <strong className="text-xs text-foreground block mb-0.5">Who is affected:</strong>
                    <p className="text-xs text-muted-foreground">{selectedUpdate.ai_summary.who_is_affected}</p>
                  </div>
                )}

                {selectedUpdate.ai_summary?.key_dates && selectedUpdate.ai_summary.key_dates.length > 0 && (
                  <div>
                    <strong className="text-xs text-foreground block mb-0.5">Key Dates:</strong>
                    <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                      {selectedUpdate.ai_summary.key_dates.map((kd, idx) => (
                        <li key={idx}>{kd}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedUpdate.ai_summary?.action_items && selectedUpdate.ai_summary.action_items.length > 0 && (
                  <div>
                    <strong className="text-xs text-foreground block mb-0.5">Action Items:</strong>
                    <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                      {selectedUpdate.ai_summary.action_items.map((ai, idx) => (
                        <li key={idx}>{ai}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <p className="text-[10px] text-muted-foreground border-t pt-2 italic">
                  AI-generated simple explanation - verify against the official document
                </p>
              </div>

              {/* Referenced / Superseding items */}
              {selectedUpdate.supersedes_refs && selectedUpdate.supersedes_refs.length > 0 && (
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs">
                  <strong className="text-amber-600 dark:text-amber-400 block mb-1">
                    Supersedes / Amends Prior Documents:
                  </strong>
                  <div className="flex flex-wrap gap-1">
                    {selectedUpdate.supersedes_refs.map((ref, idx) => (
                      <Badge key={idx} variant="outline" className="font-mono text-[10px]">
                        {ref}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Official Document Text Preview */}
              {selectedUpdate.content_text && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Official Document Text
                  </h4>
                  <div className="rounded-lg bg-muted/50 p-3 text-xs font-mono max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed text-foreground/90 border">
                    {selectedUpdate.content_text}
                  </div>
                </div>
              )}

              {/* CTA Link to Official Portal */}
              <div className="pt-2">
                <a
                  href={selectedUpdate.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  <ExternalLink className="size-4" />
                  Read full circular on official site
                </a>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Sources Health Drawer (Sheet) */}
      <Sheet open={sourcesOpen} onOpenChange={setSourcesOpen}>
        <SheetContent side="right" className="sm:max-w-2xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-primary" />
              Government Source Health & Registry
            </SheetTitle>
            <SheetDescription className="text-xs">
              Monitors robots.txt compliance, Crawl-delay, and WAF challenge detection across official domains.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-5 space-y-3">
            <div className="divide-y rounded-lg border bg-card">
              {sources.map((s) => {
                const isOk = s.status === "ok";
                const isDegraded = s.status === "degraded";
                const isBlocked = s.status === "blocked_requires_verification";
                const isUnreachable = s.status === "unreachable";
                const isErrorStatus = isDegraded || isBlocked || isUnreachable;

                return (
                  <div key={s.id} className="p-3.5 space-y-2 text-xs">
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-foreground">{s.name}</span>
                          <Badge variant="outline" className="text-[10px]">
                            Tier {s.tier}
                          </Badge>
                          <Badge variant="outline" className="text-[10px] uppercase font-mono">
                            {s.method}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground font-mono text-[11px]">{s.domain}</p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {isOk ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 text-[10px] gap-1">
                            <CheckCircle2 className="size-2.5" />
                            OK
                          </Badge>
                        ) : isDegraded ? (
                          <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 text-[10px] gap-1">
                            <AlertTriangle className="size-2.5" />
                            Degraded
                          </Badge>
                        ) : isBlocked ? (
                          <Badge variant="destructive" className="text-[10px] gap-1">
                            <XCircle className="size-2.5" />
                            Blocked (WAF)
                          </Badge>
                        ) : isUnreachable ? (
                          <Badge className="bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20 text-[10px] gap-1">
                            <AlertTriangle className="size-2.5" />
                            Unreachable
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Disabled
                          </Badge>
                        )}

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleToggleSource(s.id, s.enabled)}
                          className="h-6 text-[11px] px-2"
                        >
                          {s.enabled ? "Disable" : "Enable"}
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleReprobeSource(s.id)}
                          disabled={reprobingId === s.id}
                          className="h-6 text-[11px] px-2 gap-1 text-muted-foreground hover:text-foreground"
                          title="Re-probe endpoint (rate-limited 1/hr)"
                        >
                          <RefreshCw className={`size-3 ${reprobingId === s.id ? "animate-spin" : ""}`} />
                          Re-probe
                        </Button>
                      </div>
                    </div>

                    {/* Operational Details Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t text-[11px] text-muted-foreground">
                      <div>
                        <span className="block text-[10px] uppercase font-semibold text-muted-foreground/70">Last Attempt</span>
                        <span>{formatTime(s.last_attempt_at)}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase font-semibold text-muted-foreground/70">Last Success</span>
                        <span>{formatTime(s.last_success_at)}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase font-semibold text-muted-foreground/70">Failures / Stage</span>
                        <span>{s.consecutive_failures ?? 0} &bull; {s.failure_stage || "none"}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase font-semibold text-muted-foreground/70">Next Retry</span>
                        <span>{formatTime(s.next_retry_at)}</span>
                      </div>
                    </div>

                    {/* Red error text ONLY when degraded/blocked/unreachable */}
                    {isErrorStatus && s.last_error && (
                      <p className="text-destructive text-[11px] flex items-center gap-1.5 pt-0.5">
                        <AlertTriangle className="size-3 shrink-0" />
                        <span>{s.last_error}</span>
                      </p>
                    )}

                    {/* Manual Import link for Blocked/Unreachable sources */}
                    {(isBlocked || isUnreachable) && (
                      <div className="pt-1 flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground italic">Automated sync unavailable per robots/WAF policy.</span>
                        <Button
                          variant="link"
                          size="sm"
                          onClick={() => {
                            setSourcesOpen(false);
                            setManualImportOpen(true);
                          }}
                          className="h-auto p-0 text-primary text-[11px] font-medium"
                        >
                          Add circular manually &rarr;
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
