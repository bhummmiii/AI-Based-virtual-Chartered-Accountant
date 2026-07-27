import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
  Plus,
  Search,
  Upload,
  Download,
  Pencil,
  Trash2,
  MoreVertical,
  LayoutGrid,
  List,
  Building2,
  User,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "../components/common/PageHeader";
import { StatusBadge } from "../components/common/StatusBadge";
import { RiskIndicator } from "../components/client/RiskIndicator";
import { ClientFormDialog } from "../components/client/ClientFormDialog";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { cn } from "../components/ui/utils";
import { useApp } from "../context/AppContext";
import { currency, type Client } from "../data/mock";

export function Workspace() {
  const navigate = useNavigate();
  const { clients, addClient, updateClient, deleteClient } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [risk, setRisk] = useState("all");
  const [view, setView] = useState<"grid" | "table">("grid");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [deleting, setDeleting] = useState<Client | null>(null);

  const filtered = useMemo(
    () =>
      clients.filter((c) => {
        const q = query.toLowerCase();
        const matchesQ =
          c.company.toLowerCase().includes(q) ||
          c.name.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q);
        const matchesStatus = status === "all" || c.status === status;
        const matchesRisk = risk === "all" || c.risk === risk;
        return matchesQ && matchesStatus && matchesRisk;
      }),
    [clients, query, status, risk],
  );

  const openAdd = () => { setEditing(null); setFormOpen(true); };
  const openEdit = (c: Client) => { setEditing(c); setFormOpen(true); };

  const handleSubmit = (draft: Omit<Client, "id" | "avatar" | "lastActivity">) => {
    if (editing) {
      updateClient(editing.id, draft);
      toast.success("Client updated", { description: draft.company });
    } else {
      addClient(draft);
      toast.success("Client added", { description: draft.company });
    }
  };

  const handleExport = () => {
    const headers = ["Client Code", "Company", "Contact", "Type", "GSTIN", "Revenue", "Status", "GST", "Audit", "Tax", "Risk"];
    const rows = clients.map((c) => [c.id, c.company, c.name, c.type, c.gstin, c.revenue, c.status, c.gst, c.audit, c.tax, c.risk]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "clients.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Clients exported", { description: `${clients.length} records → clients.csv` });
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) toast.success("Import started", { description: `Parsing ${file.name}…` });
    e.target.value = "";
  };

  return (
    <>
      <PageHeader
        title="Workspace"
        subtitle="Manage all your client files in one place"
        actions={
          <>
            <input ref={fileRef} type="file" accept=".csv,.xlsx" hidden onChange={handleImport} />
            <Button variant="outline" onClick={() => fileRef.current?.click()}><Upload className="size-4" /> Import</Button>
            <Button variant="outline" onClick={handleExport}><Download className="size-4" /> Export</Button>
            <Button onClick={openAdd}><Plus className="size-4" /> Add Client</Button>
          </>
        }
      />

      {/* Toolbar */}
      <Card className="p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by company, contact or client code…" className="pl-9" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-36"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="Active">Active</SelectItem>
                <SelectItem value="Review">Review</SelectItem>
                <SelectItem value="Inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
            <Select value={risk} onValueChange={setRisk}>
              <SelectTrigger className="w-36"><SelectValue placeholder="Risk" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All risk</SelectItem>
                <SelectItem value="Low">Low risk</SelectItem>
                <SelectItem value="Medium">Medium risk</SelectItem>
                <SelectItem value="High">High risk</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex overflow-hidden rounded-lg border border-border">
              <button onClick={() => setView("grid")} className={cn("flex size-9 items-center justify-center", view === "grid" ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60")}><LayoutGrid className="size-4" /></button>
              <button onClick={() => setView("table")} className={cn("flex size-9 items-center justify-center border-l border-border", view === "table" ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60")}><List className="size-4" /></button>
            </div>
          </div>
        </div>
      </Card>

      <p className="text-sm text-muted-foreground">{filtered.length} of {clients.length} clients</p>

      {/* Client List — cards */}
      {view === "grid" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((c) => (
            <Card
              key={c.id}
              onClick={() => navigate(`/app/workspace/${c.id}`)}
              className="cursor-pointer gap-0 p-5 transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <Avatar className="size-11"><AvatarFallback className="bg-primary/10 text-primary">{c.avatar}</AvatarFallback></Avatar>
                  <div className="min-w-0">
                    <p className="truncate">{c.company}</p>
                    <p className="text-xs text-muted-foreground">{c.id}</p>
                  </div>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="icon" className="-mr-2 -mt-1"><MoreVertical className="size-4" /></Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenuItem onClick={() => navigate(`/app/workspace/${c.id}`)}>Open workspace</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => openEdit(c)}><Pencil className="size-4" /> Edit</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" onClick={() => setDeleting(c)}><Trash2 className="size-4" /> Delete</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                {c.type === "Individual" ? <User className="size-4" /> : <Building2 className="size-4" />}
                {c.name} · {c.type}
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <div className="rounded-lg bg-secondary/50 p-2 text-center">
                  <p className="text-xs text-muted-foreground">GST</p>
                  <StatusBadge value={c.gst} className="mt-1" />
                </div>
                <div className="rounded-lg bg-secondary/50 p-2 text-center">
                  <p className="text-xs text-muted-foreground">Audit</p>
                  <StatusBadge value={c.audit} className="mt-1" />
                </div>
                <div className="rounded-lg bg-secondary/50 p-2 text-center">
                  <p className="text-xs text-muted-foreground">Tax</p>
                  <StatusBadge value={c.tax} className="mt-1" />
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
                <RiskIndicator level={c.risk} />
                <span className="text-xs text-muted-foreground">{c.lastActivity}</span>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>GST</TableHead>
                  <TableHead>Audit</TableHead>
                  <TableHead>Tax</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((c) => (
                  <TableRow key={c.id} className="cursor-pointer" onClick={() => navigate(`/app/workspace/${c.id}`)}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Avatar className="size-8"><AvatarFallback className="bg-primary/10 text-primary text-xs">{c.avatar}</AvatarFallback></Avatar>
                        {c.company}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{c.id}</TableCell>
                    <TableCell className="text-muted-foreground">{c.name}</TableCell>
                    <TableCell><StatusBadge value={c.gst} /></TableCell>
                    <TableCell><StatusBadge value={c.audit} /></TableCell>
                    <TableCell><StatusBadge value={c.tax} /></TableCell>
                    <TableCell><RiskIndicator level={c.risk} showLabel={false} /></TableCell>
                    <TableCell className="text-muted-foreground">{c.lastActivity}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon"><MoreVertical className="size-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openEdit(c)}><Pencil className="size-4" /> Edit</DropdownMenuItem>
                          <DropdownMenuItem variant="destructive" onClick={() => setDeleting(c)}><Trash2 className="size-4" /> Delete</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {filtered.length === 0 && (
        <Card><CardContent className="py-16 text-center text-muted-foreground">No clients match your filters.</CardContent></Card>
      )}

      <ClientFormDialog open={formOpen} onOpenChange={setFormOpen} initial={editing} onSubmit={handleSubmit} />

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete client?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove <span className="text-foreground">{deleting?.company}</span> ({deleting?.id}) and all associated records from your workspace. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => {
                if (deleting) {
                  deleteClient(deleting.id);
                  toast.success("Client deleted", { description: deleting.company });
                }
                setDeleting(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
