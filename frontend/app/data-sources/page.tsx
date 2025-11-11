"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { api, DataSource } from "../../lib/api";
import { MetricCard } from "../../components/MetricCard";
import { StatusBadge } from "../../components/StatusBadge";

export default function DataSourcesPage() {
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = async () => {
    const list = await api.listDataSources();
    setDataSources(list);
  };

  useEffect(() => {
    refresh().catch((err) => setMessage(err.message));
  }, []);

  const totals = useMemo(() => {
    if (!dataSources.length) {
      return { builds: 0, commits: 0 };
    }
    return dataSources.reduce(
      (acc, item) => {
        acc.builds += item.stats?.total_builds || 0;
        acc.commits += item.stats?.total_commits || 0;
        return acc;
      },
      { builds: 0, commits: 0 }
    );
  }, [dataSources]);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setMessage("Chọn file CSV trước khi tải lên");
      return;
    }
    setLoading(true);
    try {
      const label = name || file.name.replace(/\.csv$/i, "");
      await api.uploadDataSource(file, label);
      setName("");
      setFile(null);
      setMessage("Upload thành công, job đã sẵn sàng");
      await refresh();
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const triggerJob = async (id: string) => {
    setMessage(null);
    try {
      await api.triggerCollection(id);
      setMessage("Đã queue job thu thập dữ liệu");
    } catch (error: any) {
      setMessage(error.message);
    }
  };

  return (
    <section>
      <div className="grid">
        <MetricCard label="Số nguồn dữ liệu" value={dataSources.length} hint="CSV đã upload" />
        <MetricCard label="Tổng builds" value={totals.builds} />
        <MetricCard label="Tổng commits" value={totals.commits} />
      </div>
      <div className="card">
        <h2>Tải CSV TravisTorrent</h2>
        <form onSubmit={handleUpload} style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <input type="file" accept=".csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <input
            type="text"
            placeholder="Tên hiển thị"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button className="button" type="submit" disabled={loading}>
            {loading ? "Đang tải..." : "Upload"}
          </button>
        </form>
        {message && <p style={{ color: "#0f172a", marginTop: "0.5rem" }}>{message}</p>}
      </div>

      <div className="card">
        <h2>Danh sách nguồn dữ liệu</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Tên</th>
              <th>Project</th>
              <th>Số builds</th>
              <th>Số commits</th>
              <th>Trạng thái</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {dataSources.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.stats?.project_name || item.stats?.project_key}</td>
                <td>{item.stats?.total_builds ?? "-"}</td>
                <td>{item.stats?.total_commits ?? "-"}</td>
                <td>
                  <StatusBadge value={item.status} />
                </td>
                <td>
                  <button className="button" onClick={() => triggerJob(item.id)}>
                    Thu thập dữ liệu
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
