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

type Draft = Omit<Client, "id" | "avatar" | "lastActivity" | "audit" | "tax">;

const empty: Draft = {
  company: "",
  name: "",
  type: "Company",
  gstin: "",
  revenue: 0,
  status: "Active",
  gst: "Filed",
  // audit and tax are auto-assigned by backend — never sent from form
  risk: "Low",
  clientType: "Monthly",
  contactNumber: "",
  emailAddress: "",
  location: "",
};

// Simple validators — inline, no new deps
function isValidPhone(v: string) {
  const digits = v.replace(/[\s\-\+\(\)]/g, "");
  return /^\d{10,15}$/.test(digits);
}
function isValidEmail(v: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}
// GSTIN: 15-char format 99AAAAA9999A9Z9
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
function isValidGstin(v: string) {
  return GSTIN_RE.test(v.trim().toUpperCase());
}

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
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (open) {
      setDraft(initial ? { ...initial } : empty);
      setTouched({});
    }
  }, [open, initial]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const touch = (k: string) =>
    setTouched((t) => ({ ...t, [k]: true }));

  const phoneErr  = touched.contactNumber  && draft.contactNumber  && !isValidPhone(draft.contactNumber)
    ? "Enter a valid 10–15 digit mobile number" : "";
  const emailErr  = touched.emailAddress   && draft.emailAddress   && !isValidEmail(draft.emailAddress)
    ? "Enter a valid email address" : "";
  const locErr    = touched.location       && !draft.location?.trim()
    ? "Location is required" : "";
  const gstinErr  = touched.gstin && draft.gstin && draft.gstin.trim() && !isValidGstin(draft.gstin)
    ? "Invalid GSTIN format. Example: 27AABCN1234R1Z5" : "";

  // Button enabled once company + contact person are filled.
  // If GSTIN is entered, it must be valid; phone/email are validated on blur only.
  const canSubmit =
    !!draft.company.trim() &&
    !!draft.name.trim() &&
    (!draft.gstin?.trim() || isValidGstin(draft.gstin)) &&
    (!draft.contactNumber || isValidPhone(draft.contactNumber)) &&
    (!draft.emailAddress  || isValidEmail(draft.emailAddress));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit Client" : "Add Client"}</DialogTitle>
          <DialogDescription>
            {initial
              ? "Update this client's profile and compliance status."
              : "Create a new client file in your workspace."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">

          {/* Row 1: Company name + Contact person */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Company name</Label>
              <Input
                value={draft.company}
                onChange={(e) => set("company", e.target.value)}
                placeholder="Acme Pvt Ltd"
              />
            </div>
            <div className="space-y-2">
              <Label>Contact person</Label>
              <Input
                value={draft.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Full name"
              />
            </div>
          </div>

          {/* Row 2: Entity type + Client Type (NEW) */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Entity type</Label>
              <Select value={draft.type} onValueChange={(v) => set("type", v as Client["type"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Company", "Individual", "LLP", "Partnership"].map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Client type</Label>
              <Select
                value={draft.clientType ?? "Monthly"}
                onValueChange={(v) => set("clientType", v as "Monthly" | "Quarterly")}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Monthly">Monthly</SelectItem>
                  <SelectItem value="Quarterly">Quarterly</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 3: Annual revenue */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Annual revenue (₹)</Label>
              <Input
                type="number"
                value={draft.revenue}
                onChange={(e) => set("revenue", +e.target.value || 0)}
              />
            </div>
          </div>

          {/* GSTIN */}
          <div className="space-y-2">
            <Label>GSTIN</Label>
            <Input
              value={draft.gstin}
              onChange={(e) => set("gstin", e.target.value)}
              onBlur={() => touch("gstin")}
              placeholder="27AABCN1234R1Z5"
              className="font-mono"
            />
            {gstinErr && (
              <p className="text-xs text-destructive">{gstinErr}</p>
            )}
          </div>

          {/* Row 4: Contact Number (NEW) + Email Address (NEW) */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Contact number</Label>
              <Input
                value={draft.contactNumber ?? ""}
                onChange={(e) => set("contactNumber", e.target.value)}
                onBlur={() => touch("contactNumber")}
                placeholder="Enter mobile number"
                inputMode="numeric"
              />
              {phoneErr && (
                <p className="text-xs text-destructive">{phoneErr}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Email address</Label>
              <Input
                type="email"
                value={draft.emailAddress ?? ""}
                onChange={(e) => set("emailAddress", e.target.value)}
                onBlur={() => touch("emailAddress")}
                placeholder="example@company.com"
              />
              {emailErr && (
                <p className="text-xs text-destructive">{emailErr}</p>
              )}
            </div>
          </div>

          {/* Location (NEW) */}
          <div className="space-y-2">
            <Label>Location</Label>
            <Input
              value={draft.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
              onBlur={() => touch("location")}
              placeholder="City, State"
            />
            {locErr && (
              <p className="text-xs text-destructive">{locErr}</p>
            )}
          </div>

          {/* Row 5: Client status + Risk indicator */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Client status</Label>
              <Select value={draft.status} onValueChange={(v) => set("status", v as Client["status"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Active", "Review", "Inactive"].map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Risk indicator</Label>
              <Select value={draft.risk} onValueChange={(v) => set("risk", v as Client["risk"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Low", "Medium", "High"].map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 6: GST status only — Audit and Tax are auto-assigned to Pending */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>GST status</Label>
              <Select value={draft.gst} onValueChange={(v) => set("gst", v as Client["gst"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["Filed", "Due", "Overdue"].map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={!canSubmit}
            onClick={() => {
              // Normalize GSTIN to uppercase before submitting
              const payload = {
                ...draft,
                gstin: draft.gstin?.trim().toUpperCase() || "",
              };
              onSubmit(payload);
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
