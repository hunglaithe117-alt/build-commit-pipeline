export function StatusBadge({ value }: { value: string }) {
  const tone = value.toLowerCase();
  const palette: Record<string, string> = {
    succeeded: "#22c55e",
    running: "#3b82f6",
    failed: "#ef4444",
    pending: "#f97316",
    ready: "#0ea5e9",
  };
  const color = palette[tone] ?? "#475569";
  return (
    <span className="badge" style={{ background: `${color}22`, color }}>
      {value}
    </span>
  );
}
