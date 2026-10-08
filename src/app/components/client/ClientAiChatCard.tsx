import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  Send,
  RotateCcw,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  FileText,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { Badge } from "../ui/badge";
import { ScrollArea } from "../ui/scroll-area";
import { cn } from "../ui/utils";
import {
  chatbotService,
  type SourceItem,
  type ClientContextMeta,
} from "../../services/chatbot.service";
import { getStoredUser } from "../../services/auth.service";
import { type Client } from "../../data/mock";

interface ClientAiChatCardProps {
  client: Client;
  clientDbId: string;
}

type Msg = {
  id: number;
  role: "user" | "ai";
  text: string;
  sources?: SourceItem[];
  clientContext?: ClientContextMeta;
  error?: boolean;
};

// ── Markdown-Lite Renderer ───────────────────────────────────────────────────
function FormattedMessage({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={idx} className="h-1.5" />;

        // Section headers: ### or ##
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
          <p key={idx} className="text-muted-foreground">
            {renderedLine}
          </p>
        );
      })}
    </div>
  );
}

export function ClientAiChatCard({ client, clientDbId }: ClientAiChatCardProps) {
  const navigate = useNavigate();
  const currentUser = getStoredUser();

  const initialWelcome: Msg = {
    id: 1,
    role: "ai",
    text: `Hi 👋 I'm **FinLedger AI**, scoped specifically to **${client.company}** (${client.id}).\n\nAsk me anything regarding this client's **GST liability**, **ITC reconciliation**, **accounting ledgers**, **unverified documents**, or **tax discrepancies**. All answers are derived directly from verified records.`,
  };

  const storageKey = `fl_client_chat_${client.id}`;
  const sessionKey = `fl_client_session_${client.id}`;

  const [messages, setMessages] = useState<Msg[]>(() => {
    try {
      const saved = localStorage.getItem(`fl_client_chat_${client.id}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // fallback
    }
    return [initialWelcome];
  });
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(() => {
    try {
      return localStorage.getItem(`fl_client_session_${client.id}`) || undefined;
    } catch {
      return undefined;
    }
  });

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync if client.id changes
  useEffect(() => {
    try {
      const saved = localStorage.getItem(`fl_client_chat_${client.id}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
          setSessionId(localStorage.getItem(`fl_client_session_${client.id}`) || undefined);
          return;
        }
      }
    } catch {
      // ignore
    }
    setMessages([initialWelcome]);
    setSessionId(undefined);
  }, [client.id]);

  // Persist messages whenever they change
  useEffect(() => {
    try {
      if (messages.length > 0) {
        localStorage.setItem(`fl_client_chat_${client.id}`, JSON.stringify(messages));
      }
    } catch {
      // ignore
    }
  }, [messages, client.id]);

  // Persist session ID
  useEffect(() => {
    try {
      if (sessionId) {
        localStorage.setItem(`fl_client_session_${client.id}`, sessionId);
      } else {
        localStorage.removeItem(`fl_client_session_${client.id}`);
      }
    } catch {
      // ignore
    }
  }, [sessionId, client.id]);

  // Suggestions tailored to this client
  const suggestions = [
    `Summarise ${client.company}'s tax liability for FY26`,
    `Which invoices are missing from GSTR-2B or unverified?`,
    `Check for duplicate payments or discrepancies`,
    `Is the trial balance balanced for ${client.company}?`,
  ];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  const handleSend = useCallback(
    async (textToSend: string) => {
      const q = textToSend.trim();
      if (!q || typing) return;

      const userMsgId = Date.now();
      setMessages((prev) => [...prev, { id: userMsgId, role: "user", text: q }]);
      setInput("");
      setTyping(true);

      try {
        const res = await chatbotService.sendWithContext({
          client_id: clientDbId,
          message: q,
          session_id: sessionId,
        });

        setSessionId(res.session_id);
        setMessages((prev) => [
          ...prev,
          {
            id: userMsgId + 1,
            role: "ai",
            text: res.reply,
            sources: res.sources,
            clientContext: res.client_context,
          },
        ]);
      } catch (err: unknown) {
        const errMsg =
          err instanceof Error
            ? err.message
            : "Could not retrieve answer from AI assistant.";
        setMessages((prev) => [
          ...prev,
          { id: userMsgId + 1, role: "ai", text: errMsg, error: true },
        ]);
      } finally {
        setTyping(false);
        setTimeout(() => inputRef.current?.focus(), 80);
      }
    },
    [clientDbId, sessionId, typing]
  );

  const handleReset = async () => {
    if (sessionId) {
      try {
        await chatbotService.clearSession(sessionId);
      } catch {
        // ignore
      }
    }
    try {
      localStorage.removeItem(storageKey);
      localStorage.removeItem(sessionKey);
    } catch {
      // ignore
    }
    setSessionId(undefined);
    setMessages([initialWelcome]);
    inputRef.current?.focus();
  };

  return (
    <Card className="border-primary/20 bg-card shadow-sm">
      <CardHeader className="border-b border-border/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="size-4" />
            </span>
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                FinLedger AI Assistant
                <Badge variant="outline" className="text-xs bg-primary/5 text-primary border-primary/20">
                  Client: {client.id}
                </Badge>
              </CardTitle>
              <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                <ShieldCheck className="size-3.5 text-success" />
                Grounded in verified books & statutory GST rules
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              className="h-8 text-xs text-muted-foreground hover:text-foreground"
              title="Reset conversation"
            >
              <RotateCcw className="size-3.5 mr-1" /> Reset
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/app/assistant?client=${client.id}`)}
              className="h-8 text-xs border-border"
            >
              Open Full AI Assistant <ExternalLink className="size-3 ml-1" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {/* Messages scroll area with ALWAYS-VISIBLE Styled Scrollbar */}
        <div
          className="h-[360px] overflow-y-scroll px-4 py-4 sm:px-6 [scrollbar-gutter:stable] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-2.5 [&::-webkit-scrollbar-track]:bg-secondary/40 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-thumb]:bg-primary/60 hover:[&::-webkit-scrollbar-thumb]:bg-primary/90 [&::-webkit-scrollbar-thumb]:rounded-full"
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "hsl(var(--primary) / 0.6) hsl(var(--secondary) / 0.4)",
          }}
        >
          <div className="space-y-4">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  "flex gap-3",
                  m.role === "user" ? "flex-row-reverse" : "flex-row"
                )}
              >
                <Avatar className="size-8 shrink-0">
                  <AvatarFallback
                    className={
                      m.role === "ai"
                        ? "bg-primary/10 text-primary"
                        : "bg-secondary text-secondary-foreground"
                    }
                  >
                    {m.role === "ai" ? (
                      <Sparkles className="size-4" />
                    ) : (
                      currentUser.initials
                    )}
                  </AvatarFallback>
                </Avatar>

                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl px-4 py-3 text-sm",
                    m.role === "ai"
                      ? m.error
                        ? "border border-destructive/30 bg-destructive/10 text-destructive"
                        : "border border-border/50 bg-secondary/40 text-foreground"
                      : "bg-primary text-primary-foreground"
                  )}
                >
                  <FormattedMessage text={m.text} />

                  {/* Grounded verified sources chip list */}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-border/40 space-y-1">
                      <p className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                        <CheckCircle2 className="size-3 text-success" /> Verified Sources:
                      </p>
                      <div className="flex flex-wrap gap-1.5 pt-0.5">
                        {m.sources.map((s, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1 rounded bg-background/80 border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                          >
                            <FileText className="size-2.5 text-primary" />
                            {s.source}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {typing && (
              <div className="flex gap-3">
                <Avatar className="size-8 shrink-0">
                  <AvatarFallback className="bg-primary/10 text-primary">
                    <Sparkles className="size-4" />
                  </AvatarFallback>
                </Avatar>
                <div className="flex items-center gap-1 rounded-2xl bg-secondary/40 border border-border/50 px-4 py-3">
                  <span className="size-1.5 animate-bounce rounded-full bg-primary" />
                  <span
                    className="size-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "0.15s" }}
                  />
                  <span
                    className="size-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "0.3s" }}
                  />
                  <span className="ml-2 text-xs text-muted-foreground">
                    Querying ledger & GST services…
                  </span>
                </div>
              </div>
            )}

            <div ref={endRef} />
          </div>
        </div>

        {/* Suggestion prompt pills */}
        {messages.length <= 2 && (
          <div className="px-4 pb-2 pt-1 border-t border-border/40 bg-muted/20">
            <p className="text-[11px] font-medium text-muted-foreground mb-1.5">
              Suggested queries for {client.company}:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((s, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(s)}
                  disabled={typing}
                  className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-foreground disabled:opacity-50 text-left flex items-center gap-1"
                >
                  <span>{s}</span>
                  <ArrowRight className="size-2.5 text-primary opacity-60" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Query Input Bar */}
        <form
          className="flex items-center gap-2 border-t border-border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(input);
          }}
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend(input);
              }
            }}
            placeholder={`Ask about ${client.company}'s GST, invoices, accounting, or audit…`}
            className="flex-1 bg-background"
            disabled={typing}
          />
          <Button
            type="submit"
            size="sm"
            disabled={typing || !input.trim()}
            className="shrink-0"
          >
            <Send className="size-3.5 mr-1" /> Ask AI
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
