import { cn } from "../ui/utils";

const map = {
  Low: { dot: "bg-success", text: "text-success", label: "Low risk" },
  Medium: { dot: "bg-warning", text: "text-warning", label: "Medium risk" },
  High: { dot: "bg-destructive", text: "text-destructive", label: "High risk" },
} as const;

export function RiskIndicator({ level, showLabel = true }: { level: "Low" | "Medium" | "High"; showLabel?: boolean }) {
  const m = map[level];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", m.text)}>
      <span className={cn("size-2 rounded-full", m.dot)} />
      {showLabel && m.label}
    </span>
  );
}
