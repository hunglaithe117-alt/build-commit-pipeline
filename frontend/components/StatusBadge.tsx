import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusClasses: Record<string, string> = {
  succeeded: "border-emerald-200 bg-emerald-50 text-emerald-700",
  running: "border-sky-200 bg-sky-50 text-sky-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  pending: "border-amber-200 bg-amber-50 text-amber-700",
  ready: "border-blue-200 bg-blue-50 text-blue-700",
};

export function StatusBadge({ value }: { value: string }) {
  const tone = value?.toLowerCase();
  return (
    <Badge variant="secondary" className={cn("capitalize", statusClasses[tone] ?? "border-slate-200 bg-slate-50")}>
      {value}
    </Badge>
  );
}
