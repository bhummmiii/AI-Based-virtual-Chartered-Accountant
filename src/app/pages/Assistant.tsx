import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Plus, Mic, Paperclip, MessageSquare } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { ScrollArea } from "../components/ui/scroll-area";
import { cn } from "../components/ui/utils";
import { chatHistory, suggestedPrompts } from "../data/mock";

type Msg = { id: number; role: "user" | "ai"; text: string };

const canned: Record<string, string> = {
  default:
    "Based on the ledgers I can see, here's a summary. For a precise figure I'd reconcile against GSTR-2B, but the headline numbers look consistent with your filed returns. Would you like me to generate a detailed breakdown or export a report?",
};

export function Assistant() {
  const [messages, setMessages] = useState<Msg[]>([
    { id: 1, role: "ai", text: "Hi Rahul 👋 I'm your AI CA assistant. Ask me anything about accounting, GST, taxation or auditing — or pick a suggestion below." },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  const send = (text: string) => {
    if (!text.trim()) return;
    const id = Date.now();
    setMessages((m) => [...m, { id, role: "user", text }]);
    setInput("");
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      setMessages((m) => [...m, { id: id + 1, role: "ai", text: canned.default }]);
    }, 900);
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* History */}
      <Card className="hidden w-64 shrink-0 flex-col gap-0 p-3 lg:flex">
        <Button className="mb-3 w-full" onClick={() => setMessages(messages.slice(0, 1))}><Plus className="size-4" /> New chat</Button>
        <p className="px-2 pb-2 text-xs uppercase tracking-wider text-muted-foreground">Conversations</p>
        <ScrollArea className="flex-1">
          <div className="space-y-1">
            {chatHistory.map((c) => (
              <button key={c.id} className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-secondary">
                <MessageSquare className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0"><span className="block truncate">{c.title}</span><span className="text-xs text-muted-foreground">{c.time}</span></span>
              </button>
            ))}
          </div>
        </ScrollArea>
      </Card>

      {/* Chat */}
      <Card className="flex min-w-0 flex-1 flex-col gap-0 overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
          <div><p className="text-sm">FinLedger AI Assistant</p><p className="text-xs text-success">● Online</p></div>
        </div>

        <ScrollArea className="flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-2xl space-y-5">
            {messages.map((m) => (
              <div key={m.id} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
                <Avatar className="size-8 shrink-0">
                  <AvatarFallback className={m.role === "ai" ? "bg-primary/10 text-primary" : "bg-secondary"}>
                    {m.role === "ai" ? <Sparkles className="size-4" /> : "RK"}
                  </AvatarFallback>
                </Avatar>
                <div className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-sm", m.role === "ai" ? "bg-secondary" : "bg-primary text-primary-foreground")}>
                  {m.text}
                </div>
              </div>
            ))}
            {typing && (
              <div className="flex gap-3">
                <Avatar className="size-8"><AvatarFallback className="bg-primary/10 text-primary"><Sparkles className="size-4" /></AvatarFallback></Avatar>
                <div className="flex items-center gap-1 rounded-2xl bg-secondary px-4 py-3">
                  {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${i * 0.15}s` }} />)}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        </ScrollArea>

        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 px-4 pb-3 sm:px-6">
            {suggestedPrompts.map((p) => (
              <button key={p} onClick={() => send(p)} className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-foreground">
                {p}
              </button>
            ))}
          </div>
        )}

        <form
          className="flex items-center gap-2 border-t border-border p-3 sm:p-4"
          onSubmit={(e) => { e.preventDefault(); send(input); }}
        >
          <Button type="button" variant="ghost" size="icon"><Paperclip className="size-5" /></Button>
          <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about GST, tax, audit…" className="flex-1" />
          <Button type="button" variant="ghost" size="icon"><Mic className="size-5" /></Button>
          <Button type="submit" size="icon"><Send className="size-4" /></Button>
        </form>
      </Card>
    </div>
  );
}
