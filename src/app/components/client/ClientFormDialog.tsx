import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import type { Client } from "../../data/mock";

type Draft = Omit<Client, "id" | "avatar" | "lastActivity">;

const empty: Draft = {
  company: "",
  name: "",
  type: "Company",
  gstin: "",
  revenue: 0,
  status: "Active",
  gst: "Filed",
  audit: "Pending",
  tax: "Filed",
  risk: "Low",
};

export function ClientFormDialog({
  open,
  onOpenChange,
  initial,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  initial?: Client | null;
  onSubmit: (draft: Draft) => void;
}) {
  const [draft, setDraft] = useState<Draft>(empty);

  useEffect(() => {
    if (open) setDraft(initial ? { ...initial } : empty);
  }, [open, initial]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit Client" : "Add Client"}</DialogTitle>
          <DialogDescription>
            {initial ? "Update this client's profile and compliance status." : "Create a new client file in your workspace."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Company name</Label>
              <Input value={draft.company} onChange={(e) => set("company", e.target.value)} placeholder="Acme Pvt Ltd" />
            </div>
            <div className="space-y-2">
              <Label>Contact person</Label>
              <Input value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Full name" />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Entity type</Label>
              <Select value={draft.type} onValueChange={(v) => set("type", v as Client["type"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Company", "Individual", "LLP", "Partnership"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Annual revenue (₹)</Label>
              <Input type="number" value={draft.revenue} onChange={(e) => set("revenue", +e.target.value || 0)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label>GSTIN</Label>
            <Input value={draft.gstin} onChange={(e) => set("gstin", e.target.value)} placeholder="27AABCN1234R1Z5" className="font-mono" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Client status</Label>
              <Select value={draft.status} onValueChange={(v) => set("status", v as Client["status"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Active", "Review", "Inactive"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Risk indicator</Label>
              <Select value={draft.risk} onValueChange={(v) => set("risk", v as Client["risk"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Low", "Medium", "High"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label>GST status</Label>
              <Select value={draft.gst} onValueChange={(v) => set("gst", v as Client["gst"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Filed", "Due", "Overdue"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Audit status</Label>
              <Select value={draft.audit} onValueChange={(v) => set("audit", v as Client["audit"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Passed", "In Progress", "Pending", "Flagged"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Tax status</Label>
              <Select value={draft.tax} onValueChange={(v) => set("tax", v as Client["tax"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Filed", "Due", "Overdue"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={!draft.company.trim()}
            onClick={() => {
              onSubmit(draft);
              onOpenChange(false);
            }}
          >
            {initial ? "Save changes" : "Add client"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
