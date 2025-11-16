import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ProjectStatus, ScanJobStatus } from "@/lib/api";

const statusClasses: Record<string, string> = {
  succeeded: "border-emerald-200 bg-emerald-50 text-emerald-700",
  running: "border-sky-200 bg-sky-50 text-sky-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  pending: "border-amber-200 bg-amber-50 text-amber-700",
  ready: "border-blue-200 bg-blue-50 text-blue-700",
  processing: "border-sky-200 bg-sky-50 text-sky-700",
  finished: "border-emerald-200 bg-emerald-50 text-emerald-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

export function StatusBadge({
  value,
}: {
  value?: string | ProjectStatus | ScanJobStatus | null | undefined;
}) {
  const tone = String(value ?? "").toLowerCase();
  // Normalize common suffixes like FAILED_TEMP -> failed
  const norm = tone.includes("failed") ? "failed" : tone;
  return (
    <Badge
      variant="secondary"
      className={cn(
        "capitalize",
        statusClasses[norm] ?? "border-slate-200 bg-slate-50"
      )}
    >
      {value}
    </Badge>
  );
}
