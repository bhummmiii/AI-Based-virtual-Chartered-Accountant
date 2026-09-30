import { useEffect, useRef, useState, useCallback } from "react";
import {
  Send,
  Sparkles,
  Plus,
  Mic,
  Paperclip,
  MessageSquare,
  AlertTriangle,
  Wifi,
  WifiOff,
} from "lucide-react";
import { toast } from "sonner";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { ScrollArea } from "../components/ui/scroll-area";
import { cn } from "../components/ui/utils";
import { chatbotService } from "../services/chatbot.service";
import { getStoredUser } from "../services/auth.service";
import { chatHistory, suggestedPrompts } from "../data/mock";

// ── Types ─────────────────────────────────────────────────────────────────────

type Msg = {
  id: number;
  role: "user" | "ai";
  text: string;
  error?: boolean;
};

// ── Helper: render message text with basic markdown-lite ────────────────────
function MessageText({ text }: { text: string }) {
  // Convert **bold**, `code`, and newlines to JSX
  const lines = text.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-2" />;
        // Bold
        const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
        return (
          <p key={i} className="leading-relaxed">
            {parts.map((part, j) => {
              if (/^\*\*[^*]+\*\*$/.test(part))
                return <strong key={j}>{part.slice(2, -2)}</strong>;
              if (/^`[^`]+`$/.test(part))
                return (
                  <code
                    key={j}
                    className="rounded bg-muted px-1 py-0.5 font-mono text-xs"
                  >
                    {part.slice(1, -1)}
                  </code>
                );
              return part;
            })}
          </p>
        );
      })}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function Assistant() {
  const currentUser = getStoredUser();
  const [messages, setMessages] = useState<Msg[]>([
    {
      id: 1,
      role: "ai",
      text: "Hi 👋 I'm **FinLedger AI**, your AI Chartered Accountant assistant.\n\nAsk me anything about **GST**, **Income Tax**, **Audit**, **Accounting** or Indian compliance — or pick a suggestion below.",
    },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [aiReady, setAiReady] = useState<boolean | null>(null); // null = checking
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Scroll to bottom on new messages ──────────────────────────────────────
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  // ── Check AI status on mount ──────────────────────────────────────────────
  useEffect(() => {
    chatbotService
      .getStatus()
      .then((s) => setAiReady(s.ready))
      .catch(() => setAiReady(false));
  }, []);

  // ── Send message ──────────────────────────────────────────────────────────
  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || typing) return;
      const id = Date.now();

      // Append user message immediately
      setMessages((m) => [...m, { id, role: "user", text: text.trim() }]);
      setInput("");
      setTyping(true);

      try {
        const result = await chatbotService.send({
          message: text.trim(),
          session_id: sessionId,
        });

        // Persist session ID for multi-turn conversation
        setSessionId(result.session_id);

        setMessages((m) => [
          ...m,
          { id: id + 1, role: "ai", text: result.reply },
        ]);
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Something went wrong. Please try again.";
        setMessages((m) => [
          ...m,
          { id: id + 1, role: "ai", text: msg, error: true },
        ]);
        toast.error("AI assistant error", { description: msg });
      } finally {
        setTyping(false);
        // Refocus input after response
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    },
    [typing, sessionId],
  );

  // ── New chat ──────────────────────────────────────────────────────────────
  const handleNewChat = async () => {
    // Clear server-side history
    if (sessionId) {
      try {
        await chatbotService.clearSession(sessionId);
      } catch {
        // ignore — local reset is enough
      }
    }
    setSessionId(undefined);
    setMessages([
      {
        id: Date.now(),
        role: "ai",
        text: "Hi 👋 I'm **FinLedger AI**, your AI Chartered Accountant assistant.\n\nAsk me anything about **GST**, **Income Tax**, **Audit**, **Accounting** or Indian compliance — or pick a suggestion below.",
      },
    ]);
    inputRef.current?.focus();
  };

  // ── Status indicator ──────────────────────────────────────────────────────
  const statusEl =
    aiReady === null ? (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground" />
        Connecting…
      </span>
    ) : aiReady ? (
      <span className="flex items-center gap-1 text-xs text-success">
        <Wifi className="size-3" /> Online
      </span>
    ) : (
      <span className="flex items-center gap-1 text-xs text-warning">
        <WifiOff className="size-3" /> API key not set
      </span>
    );

  const isFirstMessage = messages.length <= 1;

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* ── Sidebar: conversation history ── */}
      <Card className="hidden w-64 shrink-0 flex-col gap-0 p-3 lg:flex">
        <Button className="mb-3 w-full" onClick={handleNewChat}>
          <Plus className="size-4" /> New chat
        </Button>

        {aiReady === false && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-2.5 text-xs text-warning">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Gemini API key not configured.{" "}
              <span className="font-mono">backend/.env → GEMINI_API_KEY=…</span>
            </span>
          </div>
        )}

        <p className="px-2 pb-2 text-xs uppercase tracking-wider text-muted-foreground">
          Conversations
        </p>
        <ScrollArea className="flex-1">
          <div className="space-y-1">
            {/* Current session as first item if messages exist */}
            {!isFirstMessage && (
              <button className="flex w-full items-start gap-2 rounded-lg bg-secondary px-2 py-2 text-left text-sm">
                <MessageSquare className="mt-0.5 size-4 shrink-0 text-primary" />
                <span className="min-w-0">
                  <span className="block truncate">
                    {messages.find((m) => m.role === "user")?.text.slice(0, 40) ?? "New conversation"}
                  </span>
                  <span className="text-xs text-muted-foreground">Just now</span>
                </span>
              </button>
            )}
            {chatHistory.map((c) => (
              <button
                key={c.id}
                className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-secondary"
              >
                <MessageSquare className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0">
                  <span className="block truncate">{c.title}</span>
                  <span className="text-xs text-muted-foreground">{c.time}</span>
                </span>
              </button>
            ))}
          </div>
        </ScrollArea>
      </Card>

      {/* ── Main chat panel ── */}
      <Card className="flex min-w-0 flex-1 flex-col gap-0 overflow-hidden p-0">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-5 py-3.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="size-4" />
          </span>
          <div>
            <p className="text-sm font-medium">FinLedger AI Assistant</p>
            {statusEl}
          </div>

          {/* Mobile: New chat button */}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto lg:hidden"
            onClick={handleNewChat}
          >
            <Plus className="size-4" />
          </Button>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-2xl space-y-5">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}
              >
                <Avatar className="size-8 shrink-0">
                  <AvatarFallback
                    className={
                      m.role === "ai"
                        ? "bg-primary/10 text-primary"
                        : "bg-secondary"
                    }
                  >
                    {m.role === "ai" ? <Sparkles className="size-4" /> : currentUser.initials}
                  </AvatarFallback>
                </Avatar>
                <div
                  className={cn(
                    "max-w-[82%] rounded-2xl px-4 py-3 text-sm",
                    m.role === "ai"
                      ? m.error
                        ? "border border-destructive/30 bg-destructive/10 text-destructive"
                        : "bg-secondary"
                      : "bg-primary text-primary-foreground",
                  )}
                >
                  {m.role === "ai" ? (
                    <MessageText text={m.text} />
                  ) : (
                    <p className="leading-relaxed">{m.text}</p>
                  )}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {typing && (
              <div className="flex gap-3">
                <Avatar className="size-8">
                  <AvatarFallback className="bg-primary/10 text-primary">
                    <Sparkles className="size-4" />
                  </AvatarFallback>
                </Avatar>
                <div className="flex items-center gap-1 rounded-2xl bg-secondary px-4 py-3">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            )}

            <div ref={endRef} />
          </div>
        </ScrollArea>

        {/* Suggested prompts — shown only before first message */}
        {isFirstMessage && (
          <div className="flex flex-wrap gap-2 px-4 pb-3 sm:px-6">
            {suggestedPrompts.map((p) => (
              <button
                key={p}
                onClick={() => send(p)}
                disabled={typing}
                className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-foreground disabled:opacity-50"
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {/* Input bar */}
        <form
          className="flex items-center gap-2 border-t border-border p-3 sm:p-4"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <Button type="button" variant="ghost" size="icon" disabled>
            <Paperclip className="size-5" />
          </Button>
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
            placeholder="Ask about GST, Income Tax, Audit, Accounting…"
            className="flex-1"
            disabled={typing}
          />
          <Button type="button" variant="ghost" size="icon" disabled>
            <Mic className="size-5" />
          </Button>
          <Button type="submit" size="icon" disabled={typing || !input.trim()}>
            <Send className="size-4" />
          </Button>
        </form>
      </Card>
    </div>
  );
}
