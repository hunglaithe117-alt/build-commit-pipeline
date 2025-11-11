"use client";

import { useEffect, useState } from "react";

import { api, OutputDataset } from "../../lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function OutputsPage() {
  const [outputs, setOutputs] = useState<OutputDataset[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listOutputs()
      .then(setOutputs)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section className="card">
      <h2>Dữ liệu đầu ra</h2>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Metrics</th>
            <th>Số bản ghi</th>
            <th>Tải xuống</th>
          </tr>
        </thead>
        <tbody>
          {outputs.map((output) => (
            <tr key={output.id}>
              <td>{output.job_id.slice(-8)}</td>
              <td>{output.metrics.join(", ")}</td>
              <td>{output.record_count}</td>
              <td>
                <a
                  href={`${API_BASE_URL}/api/outputs/${output.id}/download`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
