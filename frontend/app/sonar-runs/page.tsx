"use client";

import { useEffect, useState } from "react";

import { api, SonarRun } from "../../lib/api";
import { StatusBadge } from "../../components/StatusBadge";

export default function SonarRunsPage() {
  const [runs, setRuns] = useState<SonarRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRuns()
      .then(setRuns)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section className="card">
      <h2>Lịch sử quét SonarQube</h2>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ minWidth: 960, tableLayout: "auto" }}>
          <thead>
            <tr>
              <th>Project key</th>
              <th>Commit</th>
              <th>Component</th>
              <th>Instance</th>
              <th>Host</th>
              <th>Analysis ID</th>
              <th>Trạng thái</th>
              <th>Bắt đầu</th>
              <th>Kết thúc</th>
              <th>Metrics</th>
              <th>Log</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{run.project_key}</td>
                <td style={{ fontFamily: "monospace", whiteSpace: "nowrap" }}>
                  {run.commit_sha || "-"}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>{run.component_key || "-"}</td>
                <td>{run.sonar_instance || "-"}</td>
                <td style={{ whiteSpace: "nowrap" }}>{run.sonar_host || "-"}</td>
                <td style={{ whiteSpace: "nowrap" }}>{run.analysis_id || "-"}</td>
                <td>
                  <StatusBadge value={run.status} />
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {new Date(run.started_at).toLocaleString()}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {run.finished_at ? new Date(run.finished_at).toLocaleString() : "-"}
                </td>
                <td
                  style={{
                    maxWidth: 200,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {run.metrics_path ? run.metrics_path : "-"}
                </td>
                <td
                  style={{
                    maxWidth: 200,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {run.log_path ? run.log_path : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
