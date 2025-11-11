export function MetricCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="card">
      <p style={{ color: "#475569", marginBottom: "0.25rem" }}>{label}</p>
      <h3 style={{ fontSize: "2rem", margin: 0 }}>{value}</h3>
      {hint && <small style={{ color: "#94a3b8" }}>{hint}</small>}
    </div>
  );
}
