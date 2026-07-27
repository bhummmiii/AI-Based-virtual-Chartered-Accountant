import { useState } from "react";
import { Search, Bookmark, BookmarkCheck, Sparkles } from "lucide-react";
import { PageHeader } from "../components/common/PageHeader";
import { StatusBadge } from "../components/common/StatusBadge";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { govRules } from "../data/mock";

export function GovRules() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("all");
  const [saved, setSaved] = useState<Record<number, boolean>>(
    Object.fromEntries(govRules.map((r) => [r.id, r.bookmarked])),
  );

  const list = govRules.filter((r) => {
    const matchesTab = tab === "all" || (tab === "saved" ? saved[r.id] : r.tag.toLowerCase().includes(tab));
    const matchesQ = r.title.toLowerCase().includes(q.toLowerCase()) || r.summary.toLowerCase().includes(q.toLowerCase());
    return matchesTab && matchesQ;
  });

  return (
    <>
      <PageHeader title="Government Rule Engine" subtitle="Latest circulars, GST updates & budget highlights — explained simply" />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="gst">GST</TabsTrigger>
            <TabsTrigger value="income">Income Tax</TabsTrigger>
            <TabsTrigger value="budget">Budget</TabsTrigger>
            <TabsTrigger value="saved">Saved</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search notifications…" className="pl-9" />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {list.map((r) => (
          <Card key={r.id} className="gap-0 p-5 transition-shadow hover:shadow-md">
            <div className="mb-3 flex items-start justify-between gap-2">
              <StatusBadge value={r.tag} className="bg-primary/10 text-primary" />
              <button onClick={() => setSaved((s) => ({ ...s, [r.id]: !s[r.id] }))} className="text-muted-foreground hover:text-primary">
                {saved[r.id] ? <BookmarkCheck className="size-4.5 text-primary" /> : <Bookmark className="size-4.5" />}
              </button>
            </div>
            <h3 className="text-base">{r.title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{r.date}</p>
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-accent/60 p-3 text-sm">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
              <p>{r.summary}</p>
            </div>
            <Button variant="ghost" size="sm" className="mt-3 self-start">Read full circular</Button>
          </Card>
        ))}
      </div>
      {list.length === 0 && (
        <Card><CardContent className="py-16 text-center text-muted-foreground">No notifications match your filters.</CardContent></Card>
      )}
    </>
  );
}
