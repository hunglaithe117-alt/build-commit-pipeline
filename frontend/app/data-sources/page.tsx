"use client";

import Link from "next/link";
import { ColumnDef } from "@tanstack/react-table";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, DataSource } from "@/lib/api";

export default function DataSourcesPage() {
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [configMode, setConfigMode] = useState<"none" | "file" | "text">("none");
  const [configContent, setConfigContent] = useState("");
  const [configFilename, setConfigFilename] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const list = await api.listDataSources();
    setDataSources(list);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setMessage(err.message));
  }, [refresh]);

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

  const handleConfigFile = useCallback(
    (configFile: File | null) => {
      if (!configFile) {
        setConfigContent("");
        setConfigFilename(null);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setConfigContent(typeof reader.result === "string" ? reader.result : "");
        setConfigFilename(configFile.name);
      };
      reader.onerror = () => {
        setMessage("Không thể đọc file sonar.properties");
      };
      reader.readAsText(configFile);
    },
    []
  );

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setMessage("Chọn file CSV trước khi tải lên");
      return;
    }
    if (configMode !== "none" && !configContent) {
      setMessage("Nhập nội dung sonar.properties hoặc chọn file hợp lệ");
      return;
    }
    setLoading(true);
    try {
      const label = name || file.name.replace(/\.csv$/i, "");
      const options =
        configMode === "none"
          ? undefined
          : {
              configContent,
              configSource: configMode,
              configFilename: configFilename ?? undefined,
            };
      await api.uploadDataSource(file, label, options);
      setName("");
      setFile(null);
      setConfigMode("none");
      setConfigContent("");
      setConfigFilename(null);
      setMessage("Upload thành công, job đã sẵn sàng");
      await refresh();
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  const triggerJob = useCallback(
    async (id: string) => {
      setMessage(null);
      try {
        await api.triggerCollection(id);
        setMessage("Đã queue job thu thập dữ liệu");
        await refresh();
      } catch (error: any) {
        setMessage(error.message);
      }
    },
    [refresh]
  );

  const statusOptions = useMemo(() => Array.from(new Set(dataSources.map((item) => item.status))).sort(), [dataSources]);

  const columns = useMemo<ColumnDef<DataSource>[]>(() => {
    return [
      {
        accessorKey: "name",
        header: "Tên",
        cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
      },
      {
        id: "project",
        header: "Project",
        accessorFn: (row) => row.stats?.project_name || row.stats?.project_key || "",
        cell: ({ row }) => row.original.stats?.project_name || row.original.stats?.project_key || "-",
      },
      {
        accessorKey: "total_builds",
        header: "Số builds",
        accessorFn: (row) => row.stats?.total_builds ?? 0,
        cell: ({ row }) => row.original.stats?.total_builds ?? "-",
        meta: { className: "text-right", cellClassName: "text-right" },
      },
      {
        accessorKey: "total_commits",
        header: "Số commits",
        accessorFn: (row) => row.stats?.total_commits ?? 0,
        cell: ({ row }) => row.original.stats?.total_commits ?? "-",
        meta: { className: "text-right", cellClassName: "text-right" },
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
      {
        id: "actions",
        header: "",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => (
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" asChild>
              <Link href={`/data-sources/${row.original.id}`}>Cấu hình</Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => triggerJob(row.original.id)}>
              Thu thập
            </Button>
          </div>
        ),
      },
    ];
  }, [triggerJob]);

  return (
    <section className="space-y-8">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Số nguồn dữ liệu" value={dataSources.length} hint="CSV đã upload" />
        <MetricCard label="Tổng builds" value={totals.builds} />
        <MetricCard label="Tổng commits" value={totals.commits} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Tải CSV TravisTorrent</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4 md:flex-row md:items-end" onSubmit={handleUpload}>
            <div className="w-full space-y-2 md:flex-1">
              <Label htmlFor="csv-upload">File CSV</Label>
              <Input
                id="csv-upload"
                type="file"
                accept=".csv"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </div>
            <div className="w-full space-y-2 md:flex-1">
              <Label htmlFor="dataset-name">Tên hiển thị</Label>
              <Input
                id="dataset-name"
                type="text"
                placeholder="Ví dụ: angularjs-commits"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <Button className="md:self-auto" type="submit" disabled={loading}>
              {loading ? "Đang tải..." : "Upload"}
            </Button>
          </form>
          {message && <p className="mt-4 text-sm text-slate-700">{message}</p>}
          <div className="mt-6 space-y-3">
            <Label>Tùy chọn sonar.properties</Label>
            <div className="flex flex-wrap gap-2 text-sm">
              <Button
                type="button"
                variant={configMode === "none" ? "default" : "outline"}
                size="sm"
                onClick={() => setConfigMode("none")}
              >
                Không cấu hình
              </Button>
              <Button
                type="button"
                variant={configMode === "file" ? "default" : "outline"}
                size="sm"
                onClick={() => setConfigMode("file")}
              >
                Tải file
              </Button>
              <Button
                type="button"
                variant={configMode === "text" ? "default" : "outline"}
                size="sm"
                onClick={() => setConfigMode("text")}
              >
                Nhập text
              </Button>
            </div>
            {configMode === "file" && (
              <div className="space-y-2">
                <input
                  type="file"
                  accept=".properties,.txt"
                  onChange={(event) => handleConfigFile(event.target.files?.[0] || null)}
                />
                {configFilename && <p className="text-sm text-muted-foreground">Đã chọn: {configFilename}</p>}
              </div>
            )}
            {configMode === "text" && (
              <Textarea
                placeholder="sonar.projectKey=my-project&#10;sonar.sources=src"
                value={configContent}
                onChange={(event) => setConfigContent(event.target.value)}
              />
            )}
            {configMode === "none" && (
              <p className="text-sm text-muted-foreground">Giữ nguyên cấu hình mặc định của pipeline.</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="text-xl">Danh sách nguồn dữ liệu</CardTitle>
            <p className="text-sm text-muted-foreground">Quản lý các kho TravisTorrent đã upload</p>
          </div>
          <Badge variant="secondary">{dataSources.length} datasets</Badge>
        </CardHeader>
        <CardContent>
          <DataTable
            pageSize={20}
            columns={columns}
            data={dataSources}
            emptyMessage="Chưa có dữ liệu. Hãy upload file CSV đầu tiên của bạn."
            renderToolbar={(table) => (
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <Input
                  className="md:max-w-xs"
                  placeholder="Lọc theo project..."
                  value={(table.getColumn("project")?.getFilterValue() as string) ?? ""}
                  onChange={(event) => table.getColumn("project")?.setFilterValue(event.target.value)}
                />
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Trạng thái</span>
                  <select
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    value={(table.getColumn("status")?.getFilterValue() as string) ?? ""}
                    onChange={(event) => table.getColumn("status")?.setFilterValue(event.target.value || undefined)}
                  >
                    <option value="">Tất cả</option>
                    {statusOptions.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          />
        </CardContent>
      </Card>
    </section>
  );
}
