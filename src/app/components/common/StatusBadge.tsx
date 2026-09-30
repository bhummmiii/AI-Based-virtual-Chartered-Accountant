import { Badge } from "../ui/badge";
import { cn } from "../ui/utils";

const map: Record<string, string> = {
  // generic positive
  Active: "bg-success/10 text-success border-success/20",
  Passed: "bg-success/10 text-success border-success/20",
  Filed: "bg-success/10 text-success border-success/20",
  Reconciled: "bg-success/10 text-success border-success/20",
  Verified: "bg-success/10 text-success border-success/20",
  verified: "bg-success/10 text-success border-success/20",
  success: "bg-success/10 text-success border-success/20",
  // warning / in progress
  Review: "bg-warning/10 text-warning border-warning/20",
  "In Progress": "bg-info/10 text-info border-info/20",
  Pending: "bg-warning/10 text-warning border-warning/20",
  pending: "bg-warning/10 text-warning border-warning/20",
  Draft: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  draft: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  Posted: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  posted: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  Due: "bg-warning/10 text-warning border-warning/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  info: "bg-info/10 text-info border-info/20",
  // danger
  Flagged: "bg-destructive/10 text-destructive border-destructive/20",
  Overdue: "bg-destructive/10 text-destructive border-destructive/20",
  Inactive: "bg-muted text-muted-foreground border-border",
  danger: "bg-destructive/10 text-destructive border-destructive/20",
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-full", map[value] ?? "bg-muted text-muted-foreground", className)}
    >
      {value}
    </Badge>
  );
}
