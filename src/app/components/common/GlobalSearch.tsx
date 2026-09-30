import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  X,
  Building2,
  FileText,
  Sparkles,
  ArrowRight,
  Loader2,
  LayoutDashboard,
  FolderKanban,
  Landmark,
  FileBarChart,
  Settings,
} from "lucide-react";
import { useApp } from "../../context/AppContext";
import { Badge } from "../ui/badge";
import { cn } from "../ui/utils";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

interface SearchDocResult {
  id: string;
  client_id: string;
  client_code: string;
  company_name: string;
  document_category: string;
  document_type: string;
  invoice_number?: string | null;
  vendor?: string | null;
  customer?: string | null;
  amount?: number | null;
  status: string;
  file_name?: string | null;
  uploaded_at?: string | null;
}

const PAGES = [
  { label: "Dashboard", to: "/app", icon: LayoutDashboard, keywords: ["home", "stats", "overview"] },
  { label: "Workspace", to: "/app/workspace", icon: FolderKanban, keywords: ["clients", "invoices", "list"] },
  { label: "AI Assistant", to: "/app/assistant", icon: Sparkles, keywords: ["chat", "gemini", "ai", "ask"] },
  { label: "Government Updates", to: "/app/updates", icon: Landmark, keywords: ["gst", "circulars", "notifications", "rules"] },
  { label: "Reports", to: "/app/reports", icon: FileBarChart, keywords: ["balance sheet", "p&l", "audit", "financial"] },
  { label: "Settings", to: "/app/settings", icon: Settings, keywords: ["profile", "firm", "preferences"] },
];

export function GlobalSearch() {
  const navigate = useNavigate();
  const { clients } = useApp();

  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [docResults, setDocResults] = useState<SearchDocResult[]>([]);
  const [searchingDocs, setSearchingDocs] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<any>(null);

  // Filter clients locally
  const matchingClients = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return clients
      .filter((c) => {
        return (
          c.company.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q) ||
          (c.name && c.name.toLowerCase().includes(q)) ||
          (c.gstin && c.gstin.toLowerCase().includes(q))
        );
      })
      .slice(0, 6);
  }, [query, clients]);

  // Filter app navigation pages
  const matchingPages = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return PAGES.filter((p) => {
      return (
        p.label.toLowerCase().includes(q) ||
        p.keywords.some((k) => k.includes(q))
      );
    }).slice(0, 3);
  }, [query]);

  // Fetch matching documents from backend with debounce
  const fetchDocMatches = useCallback((searchTerm: string) => {
    if (!searchTerm.trim()) {
      setDocResults([]);
      setSearchingDocs(false);
      return;
    }
    const token = localStorage.getItem("ca_token");
    setSearchingDocs(true);

    fetch(`${BASE_URL}/invoices/search?q=${encodeURIComponent(searchTerm)}&limit=6`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error("Search failed");
        return res.json();
      })
      .then((data) => {
        setDocResults(data.data ?? []);
      })
      .catch(() => {
        setDocResults([]);
      })
      .finally(() => {
        setSearchingDocs(false);
      });
  }, []);

  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    if (!query.trim()) {
      setDocResults([]);
      setSearchingDocs(false);
      return;
    }
    debounceTimerRef.current = setTimeout(() => {
      fetchDocMatches(query);
    }, 200);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query, fetchDocMatches]);

  // Global keyboard shortcut: Ctrl+K or Cmd+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
      if (e.key === "Escape") {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const handleSelectClient = (clientId: string) => {
    setIsOpen(false);
    setQuery("");
    navigate(`/app/workspace/${clientId}`);
  };

  const handleSelectDoc = (clientCode: string, docId: string) => {
    setIsOpen(false);
    setQuery("");
    navigate(`/app/workspace/${clientCode}`);
  };

  const handleSelectPage = (to: string) => {
    setIsOpen(false);
    setQuery("");
    navigate(to);
  };

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = query.trim();
    if (!q) return;

    // 1. If exact or single client match, navigate directly to client
    if (matchingClients.length > 0) {
      handleSelectClient(matchingClients[0].id);
      return;
    }
    // 2. If single document match, navigate to document's client
    if (docResults.length > 0) {
      handleSelectDoc(docResults[0].client_code, docResults[0].id);
      return;
    }
    // 3. Fallback: navigate to workspace with search parameter
    setIsOpen(false);
    navigate(`/app/workspace?search=${encodeURIComponent(q)}`);
  };

  const hasAnyResults = matchingClients.length > 0 || docResults.length > 0 || matchingPages.length > 0;
  const isQueryActive = query.trim().length > 0;

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <form onSubmit={handleSearchSubmit} className="relative">
        <button
          type="button"
          onClick={() => handleSearchSubmit()}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          title="Search"
        >
          <Search className="size-4" />
        </button>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search clients, invoices, reports…"
          className="h-10 w-full rounded-md border border-input bg-background/80 px-9 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary transition-all duration-200"
        />

        <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
          {query ? (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setDocResults([]);
                inputRef.current?.focus();
              }}
              className="rounded p-0.5 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              title="Clear search"
            >
              <X className="size-3.5" />
            </button>
          ) : (
            <kbd className="pointer-events-none hidden select-none items-center gap-0.5 rounded border border-border bg-muted/60 px-1.5 font-mono text-[10px] font-medium text-muted-foreground sm:inline-flex">
              <span className="text-xs">⌘</span>K
            </kbd>
          )}
        </div>
      </form>

      {/* ── Search Dropdown ─────────────────────────────────── */}
      {isOpen && isQueryActive && (
        <div className="absolute left-0 right-0 top-full mt-2 z-50 max-h-[80vh] overflow-y-auto rounded-xl border border-border bg-card/95 backdrop-blur-md shadow-2xl p-2 animate-in fade-in-0 zoom-in-95 duration-150">
          {/* Clients group */}
          {matchingClients.length > 0 && (
            <div className="mb-2">
              <div className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Clients ({matchingClients.length})
              </div>
              <div className="space-y-0.5">
                {matchingClients.map((c) => (
                  <button
                    key={`client-${c.id}`}
                    type="button"
                    onClick={() => handleSelectClient(c.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors hover:bg-primary/10 hover:text-primary group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary text-xs font-semibold">
                        <Building2 className="size-3.5" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-foreground group-hover:text-primary">
                          {c.company}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {c.id} {c.name ? `· ${c.name}` : ""} {c.gstin ? `· ${c.gstin}` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge variant="outline" className="text-[10px] capitalize">
                        {c.status}
                      </Badge>
                      <ArrowRight className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Invoices & Documents group */}
          {(searchingDocs || docResults.length > 0) && (
            <div className="mb-2 border-t border-border/50 pt-2">
              <div className="flex items-center justify-between px-2.5 py-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Documents & Invoices
                </span>
                {searchingDocs && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
              </div>
              <div className="space-y-0.5">
                {docResults.map((doc) => (
                  <button
                    key={`doc-${doc.id}`}
                    type="button"
                    onClick={() => handleSelectDoc(doc.client_code, doc.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors hover:bg-primary/10 hover:text-primary group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                        <FileText className="size-3.5" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-foreground group-hover:text-primary">
                          {doc.invoice_number || doc.file_name || doc.document_category.replace(/_/g, " ")}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {doc.company_name} ({doc.client_code}) · {doc.document_category.replace(/_/g, " ")}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {doc.amount !== null && doc.amount !== undefined && (
                        <span className="font-mono text-xs font-medium text-emerald-500">
                          ₹{Number(doc.amount).toLocaleString("en-IN")}
                        </span>
                      )}
                      <ArrowRight className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quick Navigation Pages */}
          {matchingPages.length > 0 && (
            <div className="border-t border-border/50 pt-2">
              <div className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Navigation
              </div>
              <div className="space-y-0.5">
                {matchingPages.map((page) => {
                  const Icon = page.icon;
                  return (
                    <button
                      key={`page-${page.to}`}
                      type="button"
                      onClick={() => handleSelectPage(page.to)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors hover:bg-primary/10 hover:text-primary group"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                          <Icon className="size-3.5" />
                        </div>
                        <span className="font-medium text-foreground group-hover:text-primary">
                          {page.label}
                        </span>
                      </div>
                      <ArrowRight className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!hasAnyResults && !searchingDocs && (
            <div className="py-6 px-4 text-center">
              <p className="text-sm font-medium text-muted-foreground">No matches found for "{query}"</p>
              <p className="mt-1 text-xs text-muted-foreground/80">
                Press Enter to search all clients in the workspace.
              </p>
              <button
                type="button"
                onClick={() => handleSearchSubmit()}
                className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-secondary px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/80 transition-colors"
              >
                Search workspace for "{query}"
                <ArrowRight className="size-3" />
              </button>
            </div>
          )}

          {/* Footer prompt */}
          {hasAnyResults && (
            <div className="mt-1 flex items-center justify-between border-t border-border/50 px-2.5 pt-2 text-[11px] text-muted-foreground">
              <span>Press <kbd className="rounded border bg-muted px-1">↵ Enter</kbd> to open first match</span>
              <span><kbd className="rounded border bg-muted px-1">Esc</kbd> to close</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
