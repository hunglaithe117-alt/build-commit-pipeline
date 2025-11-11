"use client";

import { useEffect, useState } from "react";

import { api, Job } from "../../lib/api";
import { StatusBadge } from "../../components/StatusBadge";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    const data = await api.listJobs();
    setJobs(data);
  };

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
    const interval = setInterval(() => {
      refresh().catch(console.error);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="card">
      <h2>Job thu thập dữ liệu</h2>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Số commit xử lý</th>
            <th>Tổng commit</th>
            <th>Commit đang chạy</th>
            <th>Tiến độ</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const progress = job.total ? Math.round((job.processed / job.total) * 100) : 0;
            return (
              <tr key={job.id}>
                <td>{job.id.slice(-8)}</td>
                <td>{job.processed}</td>
                <td>{job.total}</td>
                <td style={{ fontFamily: "monospace" }}>{job.current_commit || "-"}</td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <div
                      style={{
                        background: "#e2e8f0",
                        borderRadius: "999px",
                        width: "120px",
                        height: "8px",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${progress}%`,
                          height: "8px",
                          background: "#2563eb",
                        }}
                      />
                    </div>
                    <span>{progress}%</span>
                  </div>
                </td>
                <td>
                  <StatusBadge value={job.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
