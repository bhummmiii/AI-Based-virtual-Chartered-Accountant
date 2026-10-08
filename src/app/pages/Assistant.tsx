import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  Send,
  Sparkles,
  Plus,
  MessageSquare,
  AlertTriangle,
  Wifi,
  WifiOff,
  Building2,
  ExternalLink,
  ShieldCheck,
  RotateCcw,
  Copy,
  Check,
  Layers,
  ArrowRight,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { cn } from "../components/ui/utils";
import {
  chatbotService,
  type SourceItem,
  type ClientContextMeta,
} from "../services/chatbot.service";
import { getStoredUser } from "../services/auth.service";
import { useApp, dbIdMap } from "../context/AppContext";

// ── Types ─────────────────────────────────────────────────────────────────────

type Msg = {
  id: number;
  role: "user" | "ai";
  text: string;
  sources?: SourceItem[];
  clientContext?: ClientContextMeta;
  dataAvailable?: boolean;
  error?: boolean;
};

export interface SavedConversation {
  id: string;
  title: string;
  scope: string; // "all" | client_code e.g. "C-1073"
  clientName?: string;
  messages: Msg[];
  sessionId?: string;
  updatedAt: string;
  timestamp: number;
}

// ── Time Ago Formatter ────────────────────────────────────────────────────────

function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return "Just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return "Today";
  if (diff < 172800000) return "Yesterday";
  return `${Math.floor(diff / 86400000)}d ago`;
}

// ── Markdown-Lite Renderer ───────────────────────────────────────────────────
function MessageText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={idx} className="h-1.5" />;

        // Section headers
        if (trimmed.startsWith("###") || trimmed.startsWith("##")) {
          const headerText = trimmed.replace(/^#+\s*/, "");
          return (
            <h4
              key={idx}
              className="mt-2 text-xs font-semibold uppercase tracking-wider text-primary"
            >
              {headerText}
            </h4>
          );
        }

        // Bullet points
        const isBullet = trimmed.startsWith("•") || trimmed.startsWith("-");
        const cleanLine = isBullet ? trimmed.replace(/^[•\-]\s*/, "") : trimmed;

        const parts = cleanLine.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);

        const renderedLine = parts.map((part, pIdx) => {
          if (/^\*\*[^*]+\*\*$/.test(part)) {
            return (
              <strong key={pIdx} className="font-semibold text-foreground">
                {part.slice(2, -2)}
              </strong>
            );
          }
          if (/^`[^`]+`$/.test(part)) {
            return (
              <code
                key={pIdx}
                className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-primary"
              >
                {part.slice(1, -1)}
              </code>
            );
          }
          return part;
        });

        if (isBullet) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary/70" />
              <p className="flex-1 text-muted-foreground">{renderedLine}</p>
            </div>
          );
        }

        return (
          <p key={idx} className="text-foreground/90">
            {renderedLine}
          </p>
        );
      })}
    </div>
  );
}

// ── Workspace AI Assistant Component ──────────────────────────────────────────

export function Assistant() {
  const currentUser = getStoredUser();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { clients } = useApp();

  // URL ?client= parameter
  const urlClientCode = searchParams.get("client") || "all";

  // Selected client scope: "all" for whole workspace, or client_code
  const [selectedScope, setSelectedScope] = useState<string>(urlClientCode);

  // Active client object if a specific scope is selected
  const activeClient = useMemo(() => {
    if (selectedScope === "all") return null;
    return clients.find((c) => c.id === selectedScope) ?? null;
  }, [selectedScope, clients]);

  // Active client UUID for backend API
  const activeClientDbId = useMemo(() => {
    if (!activeClient) return undefined;
    return dbIdMap.get(activeClient.id);
  }, [activeClient]);

  // Helper: create initial greeting message for a given scope
  const createGreeting = useCallback(
    (scope: string, clientObj: typeof activeClient): Msg => {
      if (clientObj) {
        return {
          id: 1,
          role: "ai",
          text: `Hello! 👋 I'm **FinLedger AI**, focused specifically on **${clientObj.company}** (${clientObj.id}).\n\nI have direct access to this client's verified GST filings, ledger vouchers, trial balance, and compliance records. Ask me anything about their accounts or pick a suggestion below.`,
        };
      }
      return {
        id: 1,
        role: "ai",
        text: `Hello 👋 I'm **FinLedger AI**, your workspace-wide AI Chartered Accountant.\n\nI have access to **all registered clients** in your workspace. You can ask about any client by name or code (e.g. *"${clients[0]?.company ?? "Client"}"* or *"${clients[0]?.id ?? "C-1042"}"*), compare clients, or request workspace-level compliance summaries.\n\nAll numerical figures are strictly verified against live database records with zero hallucination.`,
      };
    },
    [clients],
  );

  // ── Conversation History State (Real User Conversations Only) ───────────────
  const [conversations, setConversations] = useState<SavedConversation[]>(() => {
    try {
      const saved = localStorage.getItem("fl_assistant_chat_history");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          // Filter out any mock/seed dummy items
          const userOnly = parsed.filter(
            (c: any) =>
              c &&
              typeof c === "object" &&
              !String(c.id || "").startsWith("seed-") &&
              c.title !== "GST ITC reconciliation help" &&
              c.title !== "Old vs new regime for ₹18L salary" &&
              c.title !== "Depreciation on plant & machinery" &&
              c.title !== "Section 80C deduction limits"
          );
          try {
            localStorage.setItem("fl_assistant_chat_history", JSON.stringify(userOnly));
          } catch {
            // ignore
          }
          return userOnly;
        }
      }
    } catch {
      // fallback
    }
    return [];
  });

  const [currentConvId, setCurrentConvId] = useState<string | null>(null);

  // Persist conversation history
  useEffect(() => {
    try {
      localStorage.setItem("fl_assistant_chat_history", JSON.stringify(conversations));
    } catch {
      // ignore
    }
  }, [conversations]);

  // ── Active Chat State ──────────────────────────────────────────────────────
  // For "all" clients, we restore previous chat history if available
  const [messages, setMessages] = useState<Msg[]>(() => {
    if (urlClientCode === "all") {
      try {
        const savedAll = localStorage.getItem("fl_workspace_chat_messages");
        if (savedAll) {
          const parsed = JSON.parse(savedAll);
          if (Array.isArray(parsed) && parsed.length > 0) return parsed;
        }
      } catch {
        // fallback
      }
    }
    const targetClient = clients.find((c) => c.id === urlClientCode) ?? null;
    return [createGreeting(urlClientCode, targetClient)];
  });

  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(() => {
    if (urlClientCode === "all") {
      return localStorage.getItem("fl_workspace_chat_session") || undefined;
    }
    return undefined;
  });
  const [aiReady, setAiReady] = useState<boolean | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Persist "all clients" workspace messages
  useEffect(() => {
    if (selectedScope === "all" && messages.length > 0) {
      try {
        localStorage.setItem("fl_workspace_chat_messages", JSON.stringify(messages));
        if (sessionId) {
          localStorage.setItem("fl_workspace_chat_session", sessionId);
        }
      } catch {
        // ignore
      }
    }
  }, [messages, sessionId, selectedScope]);

  // ── Sync when URL ?client parameter changes ────────────────────────────────
  const prevScopeRef = useRef<string>(urlClientCode);

  useEffect(() => {
    if (urlClientCode !== prevScopeRef.current) {
      const prevScope = prevScopeRef.current;
      prevScopeRef.current = urlClientCode;
      setSelectedScope(urlClientCode);

      if (urlClientCode === "all") {
        // For All Clients: restore previous workspace chat history
        try {
          const savedAll = localStorage.getItem("fl_workspace_chat_messages");
          if (savedAll) {
            const parsed = JSON.parse(savedAll);
            if (Array.isArray(parsed) && parsed.length > 0) {
              setMessages(parsed);
              setSessionId(localStorage.getItem("fl_workspace_chat_session") || undefined);
              setCurrentConvId(null);
              return;
            }
          }
        } catch {
          // ignore
        }
        setMessages([createGreeting("all", null)]);
        setSessionId(undefined);
        setCurrentConvId(null);
      } else {
        // For a new individual client: CLEAR previous questions & answers!
        const targetClient = clients.find((c) => c.id === urlClientCode) ?? null;
        setMessages([createGreeting(urlClientCode, targetClient)]);
        setSessionId(undefined);
        setCurrentConvId(null);
        setInput("");
      }
    }
  }, [urlClientCode, clients, createGreeting]);

  // Auto-scroll on messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  // Status check on mount
  useEffect(() => {
    chatbotService
      .getStatus()
      .then((s) => setAiReady(s.ready))
      .catch(() => setAiReady(false));
  }, []);

  // Copy message helper
  const handleCopy = (id: number, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopiedId(null), 2000);
  };

  // ── Send Message ───────────────────────────────────────────────────────────
  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || typing) return;
      const userMsgId = Date.now();

      const userMsg: Msg = { id: userMsgId, role: "user", text: trimmed };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setTyping(true);

      // Manage conversation in chat history
      const convIdToUse = currentConvId || `conv_${userMsgId}`;
      if (!currentConvId) {
        setCurrentConvId(convIdToUse);
      }

      try {
        const result = await chatbotService.send({
          message: trimmed,
          session_id: sessionId,
          client_id: activeClientDbId,
        });

        const newSessionId = result.session_id;
        setSessionId(newSessionId);

        const aiMsg: Msg = {
          id: userMsgId + 1,
          role: "ai",
          text: result.reply,
          sources: result.sources,
          clientContext: result.client_context,
          dataAvailable: result.data_available,
        };

        setMessages((m) => {
          const updated = [...m, aiMsg];

          // Save / update in conversations history list
          setConversations((prevList) => {
            const existingIndex = prevList.findIndex((c) => c.id === convIdToUse);
            const convTitle =
              trimmed.length > 38 ? `${trimmed.slice(0, 38)}…` : trimmed;

            if (existingIndex >= 0) {
              const updatedList = [...prevList];
              updatedList[existingIndex] = {
                ...updatedList[existingIndex],
                messages: updated,
                sessionId: newSessionId,
                updatedAt: "Just now",
                timestamp: Date.now(),
              };
              return updatedList;
            } else {
              const newRecord: SavedConversation = {
                id: convIdToUse,
                title: convTitle,
                scope: selectedScope,
                clientName: activeClient?.company,
                messages: updated,
                sessionId: newSessionId,
                updatedAt: "Just now",
                timestamp: Date.now(),
              };
              return [newRecord, ...prevList];
            }
          });

          return updated;
        });
      } catch (err: unknown) {
        const msg =
          err instanceof Error
            ? err.message
            : "Something went wrong processing your request.";
        setMessages((m) => [
          ...m,
          { id: userMsgId + 1, role: "ai", text: msg, error: true },
        ]);
        toast.error("AI assistant error", { description: msg });
      } finally {
        setTyping(false);
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    },
    [typing, sessionId, activeClientDbId, currentConvId, selectedScope, activeClient],
  );

  // ── New Chat handler ───────────────────────────────────────────────────────
  const handleNewChat = async () => {
    if (sessionId) {
      try {
        await chatbotService.clearSession(sessionId);
      } catch {
        // ignore
      }
    }

    if (selectedScope === "all") {
      try {
        localStorage.removeItem("fl_workspace_chat_messages");
        localStorage.removeItem("fl_workspace_chat_session");
      } catch {
        // ignore
      }
    }

    setSessionId(undefined);
    setCurrentConvId(null);
    setMessages([createGreeting(selectedScope, activeClient)]);
    inputRef.current?.focus();
  };

  // ── Scope switcher handler ─────────────────────────────────────────────────
  const handleScopeChange = (newScope: string) => {
    if (newScope === selectedScope) return;

    prevScopeRef.current = newScope;
    setSelectedScope(newScope);

    if (newScope === "all") {
      setSearchParams({});
      // For All Clients: restore previous workspace chat
      try {
        const savedAll = localStorage.getItem("fl_workspace_chat_messages");
        if (savedAll) {
          const parsed = JSON.parse(savedAll);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setMessages(parsed);
            setSessionId(localStorage.getItem("fl_workspace_chat_session") || undefined);
            setCurrentConvId(null);
            return;
          }
        }
      } catch {
        // ignore
      }
      setMessages([createGreeting("all", null)]);
      setSessionId(undefined);
      setCurrentConvId(null);
    } else {
      // For a new individual client: CLEAR previous questions & answers!
      setSearchParams({ client: newScope });
      const targetClient = clients.find((c) => c.id === newScope) ?? null;
      setMessages([createGreeting(newScope, targetClient)]);
      setSessionId(undefined);
      setCurrentConvId(null);
      setInput("");
    }
  };

  // ── Select a Conversation from History ─────────────────────────────────────
  const handleSelectConversation = (conv: SavedConversation) => {
    setCurrentConvId(conv.id);
    setMessages(conv.messages);
    setSessionId(conv.sessionId);

    if (conv.scope !== selectedScope) {
      prevScopeRef.current = conv.scope;
      setSelectedScope(conv.scope);
      if (conv.scope === "all") {
        setSearchParams({});
      } else {
        setSearchParams({ client: conv.scope });
      }
    }
  };

  // ── Delete a Conversation from History ─────────────────────────────────────
  const handleDeleteConversation = (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (currentConvId === id) {
      handleNewChat();
    }
    toast.success("Conversation removed");
  };

  // ── Dynamic Suggested Prompts ──────────────────────────────────────────────
  const suggestedPrompts = useMemo(() => {
    if (activeClient) {
      return [
        `What is the GSTR-3B tax summary for ${activeClient.company}?`,
        `Check ITC claimed vs available in GSTR-2B for ${activeClient.company}`,
        `Show recent accounting ledger entries and cash outflows`,
        `Are there any compliance discrepancies or audit risks?`,
      ];
    }
    return [
      "Which clients have pending GST reconciliation discrepancies?",
      "List all clients with ITC mismatch or delayed filings",
      "Summary of total revenue and tax obligations across workspace",
      "Compare sales vs expenses across active clients",
    ];
  }, [activeClient]);

  // Online status indicator
  const statusEl =
    aiReady === null ? (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground" />
        Connecting…
      </span>
    ) : aiReady ? (
      <span className="flex items-center gap-1 text-xs text-success font-medium">
        <Wifi className="size-3" /> Online & Grounded
      </span>
    ) : (
      <span className="flex items-center gap-1 text-xs text-warning">
        <WifiOff className="size-3" /> Offline (Deterministic live fallback)
      </span>
    );

  const isFirstMessage = messages.length <= 1;

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* ── Left Sidebar: Scope & Scrollable Chat History ── */}
      <Card className="hidden w-76 shrink-0 flex-col gap-0 p-3 lg:flex border-border/80 shadow-xs min-h-0">
        {/* New chat button */}
        <Button className="mb-3 w-full shadow-sm" onClick={handleNewChat}>
          <Plus className="size-4 mr-1.5" /> New chat
        </Button>

        {/* Scope Selector */}
        <div className="mb-3 space-y-1.5 rounded-lg border border-border/60 bg-muted/30 p-2.5">
          <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Layers className="size-3.5 text-primary" /> Assistant Scope
            </span>
            {activeClient ? (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                Filtered
              </Badge>
            ) : (
              <Badge
                variant="outline"
                className="text-[10px] px-1.5 py-0 h-4 text-primary border-primary/20"
              >
                Workspace
              </Badge>
            )}
          </div>
          <Select value={selectedScope} onValueChange={handleScopeChange}>
            <SelectTrigger className="w-full text-xs h-8 bg-background">
              <SelectValue placeholder="Select client scope" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                <span className="font-medium">🌐 All Workspace Clients</span>
              </SelectItem>
              {clients.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  <span className="font-mono text-muted-foreground mr-1.5">{c.id}</span>
                  <span>{c.company}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[10px] text-muted-foreground leading-tight">
            {activeClient
              ? `Focused on ${activeClient.company}. Previous chats cleared for new client.`
              : "Cross-client enabled. All clients previous chat available."}
          </p>
        </div>

        {aiReady === false && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>Deterministic engine active. Zero hallucination.</span>
          </div>
        )}

        {/* Previous Chats / Chat History Section */}
        <div className="flex items-center justify-between px-2 pt-1 pb-1.5 shrink-0">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <MessageSquare className="size-3.5 text-primary" /> Previous Chats
          </span>
          <span className="text-[10px] text-muted-foreground font-mono">
            {conversations.length} saved
          </span>
        </div>

        {/* Scrollable Chat History Container with ALWAYS-VISIBLE Styled Scrollbar */}
        <div className="flex-1 min-h-0 flex flex-col mt-0.5">
          <div
            className="flex-1 min-h-0 overflow-y-scroll pr-1.5 space-y-1 select-none [scrollbar-gutter:stable] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-2.5 [&::-webkit-scrollbar-track]:bg-secondary/40 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-thumb]:bg-primary/60 hover:[&::-webkit-scrollbar-thumb]:bg-primary/90 [&::-webkit-scrollbar-thumb]:rounded-full"
            style={{
              scrollbarWidth: "thin",
              scrollbarColor: "hsl(var(--primary) / 0.6) hsl(var(--secondary) / 0.4)",
            }}
          >
            {conversations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 px-2 text-center text-xs text-muted-foreground/60 space-y-1.5">
                <MessageSquare className="size-5 text-muted-foreground/30" />
                <p className="font-medium text-muted-foreground/80">No previous chats yet</p>
                <p className="text-[11px] text-muted-foreground/50">
                  Your questions & answers will be saved here
                </p>
              </div>
            ) : (
              conversations.map((conv) => {
                const isActive = conv.id === currentConvId;
                const isClientScope = conv.scope !== "all";
                return (
                  <div
                    key={conv.id}
                    className={cn(
                      "group relative flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors cursor-pointer",
                      isActive
                        ? "bg-primary/10 text-primary font-medium border border-primary/20"
                        : "hover:bg-secondary text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => handleSelectConversation(conv)}
                  >
                    <MessageSquare
                      className={cn(
                        "mt-0.5 size-3.5 shrink-0",
                        isActive ? "text-primary" : "text-muted-foreground",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{conv.title}</span>
                      <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-muted-foreground">
                        <span
                          className={cn(
                            "rounded px-1 py-0 font-mono text-[9px]",
                            isClientScope
                              ? "bg-primary/10 text-primary"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          {isClientScope ? conv.scope : "All"}
                        </span>
                        <span>•</span>
                        <span>{conv.updatedAt || formatTimeAgo(conv.timestamp)}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteConversation(conv.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 hover:text-destructive p-1 rounded transition-opacity"
                      title="Delete chat"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </Card>

      {/* ── Main Chat Panel ── */}
      <Card className="flex min-w-0 flex-1 flex-col gap-0 overflow-hidden p-0 border-border/80 shadow-sm">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border bg-card/60 px-5 py-3.5 backdrop-blur-sm">
          <span className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary shadow-xs">
            <Sparkles className="size-4.5" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold tracking-tight text-foreground truncate">
                {activeClient
                  ? `FinLedger AI — ${activeClient.company}`
                  : "FinLedger AI CA Assistant"}
              </h2>
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px] font-normal py-0 px-2 h-4.5",
                  activeClient
                    ? "border-primary/30 text-primary bg-primary/5"
                    : "border-border text-muted-foreground",
                )}
              >
                {activeClient ? `Client: ${activeClient.id}` : "Workspace-Wide"}
              </Badge>
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              {statusEl}
              <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                <ShieldCheck className="size-3 text-success" /> Live Grounded Data
              </span>
            </div>
          </div>

          {/* Right actions */}
          <div className="ml-auto flex items-center gap-2">
            {activeClient && (
              <Button
                variant="outline"
                size="sm"
                className="hidden sm:inline-flex text-xs h-8"
                onClick={() => navigate(`/app/workspace/${activeClient.id}`)}
              >
                <Building2 className="size-3.5 mr-1" />
                Open Workspace
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-8 text-muted-foreground hover:text-foreground"
              onClick={handleNewChat}
              title="Reset conversation"
            >
              <RotateCcw className="size-3.5 mr-1" />
              Reset
            </Button>
          </div>
        </div>

        {/* Message Stream with ALWAYS-VISIBLE Styled Scrollbar */}
        <div
          className="flex-1 min-h-0 overflow-y-scroll px-4 py-6 sm:px-6 bg-linear-to-b from-background to-muted/10 [scrollbar-gutter:stable] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-2.5 [&::-webkit-scrollbar-track]:bg-secondary/40 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-thumb]:bg-primary/60 hover:[&::-webkit-scrollbar-thumb]:bg-primary/90 [&::-webkit-scrollbar-thumb]:rounded-full"
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "hsl(var(--primary) / 0.6) hsl(var(--secondary) / 0.4)",
          }}
        >
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((m) => {
              const isAi = m.role === "ai";
              return (
                <div
                  key={m.id}
                  className={cn("flex gap-3", !isAi && "flex-row-reverse")}
                >
                  <Avatar className="size-8 shrink-0 mt-0.5 shadow-xs">
                    <AvatarFallback
                      className={
                        isAi
                          ? "bg-primary/10 text-primary font-semibold"
                          : "bg-secondary font-medium"
                      }
                    >
                      {isAi ? <Sparkles className="size-4" /> : currentUser.initials}
                    </AvatarFallback>
                  </Avatar>

                  <div className={cn("max-w-[85%] space-y-2", !isAi && "items-end")}>
                    {/* Message Bubble */}
                    <div
                      className={cn(
                        "rounded-2xl px-4 py-3 text-sm shadow-xs transition-shadow",
                        isAi
                          ? m.error
                            ? "border border-destructive/30 bg-destructive/10 text-destructive"
                            : "bg-card border border-border/70 text-card-foreground"
                          : "bg-primary text-primary-foreground",
                      )}
                    >
                      {isAi ? (
                        <MessageText text={m.text} />
                      ) : (
                        <p className="leading-relaxed">{m.text}</p>
                      )}
                    </div>

                    {/* Client Context Banner if resolved */}
                    {isAi && m.clientContext && (
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
                        <div className="flex items-center gap-2">
                          <Building2 className="size-3.5 text-primary" />
                          <span className="font-medium text-foreground">
                            {m.clientContext.name}
                          </span>
                          <span className="font-mono text-muted-foreground text-[11px]">
                            ({m.clientContext.code})
                          </span>
                          {m.clientContext.gstin && (
                            <span className="text-[11px] text-muted-foreground hidden sm:inline">
                              GSTIN: {m.clientContext.gstin}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() =>
                            navigate(
                              `/app/workspace/${m.clientContext?.code || m.clientContext?.id}`,
                            )
                          }
                          className="inline-flex items-center gap-1 font-medium text-primary hover:underline text-[11px]"
                        >
                          View Client Workspace <ExternalLink className="size-3" />
                        </button>
                      </div>
                    )}

                    {/* Verified Sources Pill Bar */}
                    {isAi && m.sources && m.sources.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                        <span className="flex items-center gap-1 text-[11px] font-medium text-success mr-1">
                          <ShieldCheck className="size-3 text-success" /> Verified Sources:
                        </span>
                        {m.sources.map((s, sIdx) => (
                          <Badge
                            key={sIdx}
                            variant="secondary"
                            className="text-[10px] font-mono px-2 py-0 h-4.5 bg-muted/80 text-foreground/80 hover:bg-muted"
                          >
                            {s.title}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Copy action */}
                    {isAi && !m.error && (
                      <div className="flex items-center gap-2 px-1">
                        <button
                          onClick={() => handleCopy(m.id, m.text)}
                          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {copiedId === m.id ? (
                            <>
                              <Check className="size-3 text-success" /> Copied
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" /> Copy
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Typing Indicator */}
            {typing && (
              <div className="flex gap-3">
                <Avatar className="size-8 shrink-0">
                  <AvatarFallback className="bg-primary/10 text-primary">
                    <Sparkles className="size-4" />
                  </AvatarFallback>
                </Avatar>
                <div className="flex items-center gap-1.5 rounded-2xl bg-card border border-border px-4 py-3 shadow-xs">
                  <span className="size-1.5 animate-bounce rounded-full bg-primary" />
                  <span
                    className="size-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "0.15s" }}
                  />
                  <span
                    className="size-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "0.3s" }}
                  />
                  <span className="ml-2 text-xs text-muted-foreground font-medium">
                    {activeClient
                      ? `Querying ${activeClient.company} live records…`
                      : "Querying workspace records across all clients…"}
                  </span>
                </div>
              </div>
            )}

            <div ref={endRef} />
          </div>
        </div>

        {/* Suggested Prompts */}
        {isFirstMessage && (
          <div className="border-t border-border/50 bg-muted/20 px-4 py-3 sm:px-6">
            <p className="text-[11px] font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
              <Sparkles className="size-3 text-primary" />
              {activeClient
                ? `Suggested questions for ${activeClient.company}:`
                : "Suggested workspace queries across all clients:"}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggestedPrompts.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => send(p)}
                  disabled={typing}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-foreground disabled:opacity-50 text-left"
                >
                  <span>{p}</span>
                  <ArrowRight className="size-2.5 text-primary opacity-60" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input Bar */}
        <form
          className="flex items-center gap-2 border-t border-border p-3 sm:p-4 bg-background"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder={
              activeClient
                ? `Ask about ${activeClient.company}'s GST, vouchers, P&L, or audit…`
                : "Ask about any client (e.g. 'Show GSTR-3B for Nexus'), compare clients, or tax laws…"
            }
            className="flex-1 bg-background"
            disabled={typing}
          />
          <Button
            type="submit"
            size="default"
            disabled={typing || !input.trim()}
            className="shrink-0 px-4 shadow-xs"
          >
            <Send className="size-4 mr-1.5" /> Ask AI
          </Button>
        </form>
      </Card>
    </div>
  );
}
