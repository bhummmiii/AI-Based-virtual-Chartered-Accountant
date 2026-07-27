import { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, LucideIcon } from "lucide-react";
import { Card } from "../ui/card";
import { cn } from "../ui/utils";

export function StatCard({
  label,
  value,
  icon: Icon,
  delta,
  tone = "primary",
  footer,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  delta?: { value: string; positive: boolean };
  tone?: "primary" | "success" | "warning" | "danger" | "info";
  footer?: ReactNode;
}) {
  const toneMap = {
    primary: "bg-primary/10 text-primary",
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    danger: "bg-destructive/10 text-destructive",
    info: "bg-info/10 text-info",
  };
  return (
    <Card className="gap-0 p-5 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <div className={cn("flex size-10 items-center justify-center rounded-lg", toneMap[tone])}>
          <Icon className="size-5" />
        </div>
        {delta && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs",
              delta.positive ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {delta.positive ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
            {delta.value}
          </span>
        )}
      </div>
      <div className="mt-4 space-y-1">
        <p className="text-muted-foreground text-sm">{label}</p>
        <p className="text-2xl tracking-tight">{value}</p>
      </div>
      {footer && <div className="mt-3 text-xs text-muted-foreground">{footer}</div>}
    </Card>
  );
}
