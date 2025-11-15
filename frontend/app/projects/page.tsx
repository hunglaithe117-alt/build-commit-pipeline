"use client";

import Link from "next/link";
import { ColumnDef } from "@tanstack/react-table";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, Project } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [sonarConfigFile, setSonarConfigFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [total, setTotal] = useState(0);

  const refresh = useCallback(async () => {
    const res = await api.listProjectsPaginated(pageIndex + 1, 20);
    setProjects(res.items);
    setTotal(res.total || 0);
  }, [pageIndex]);

  useEffect(() => {
    refresh().catch((err) => setMessage(err.message));
  }, [refresh]);

  const totals = useMemo(() => {
    return projects.reduce(
      (acc, item) => {
        acc.builds += Number(item.total_builds ?? 0);
        acc.commits += Number(item.total_commits ?? 0);
        return acc;
      },
      { builds: 0, commits: 0 }
    );
  }, [projects]);

  const handleServerChange = async (params: {
    pageIndex: number;
    pageSize: number;
    sorting?: { id: string; desc?: boolean } | null;
    filters: Record<string, any>;
  }) => {
    try {
      const sortBy = params.sorting?.id;
      const sortDir = params.sorting?.desc ? "desc" : "asc";
      const res = await api.listProjectsPaginated(
        params.pageIndex + 1,
        params.pageSize,
        sortBy,
        sortDir,
        params.filters
      );
      setProjects(res.items);
      setTotal(res.total || 0);
      setPageIndex(params.pageIndex);
    } catch (err: any) {
      setMessage(err.message);
    }
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setMessage("Chọn file CSV trước khi tải lên");
      return;
    }
    setLoading(true);
    try {
      const label = name || file.name.replace(/\.csv$/i, "");
      await api.uploadProject(file, label, {
        sonarConfig: sonarConfigFile ?? undefined,
      });
      setName("");
      setFile(null);
      setSonarConfigFile(null);
      setMessage("Upload thành công, file đang được xử lý");
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
        setMessage("Đã queue pipeline xử lý commits");
      } catch (error: any) {
        setMessage(error.message);
      }
    },
    []
  );

  const columns = useMemo<ColumnDef<Project>[]>(() => {
    return [
      {
        accessorKey: "project_name",
        header: "Tên",
        cell: ({ row }) => <span className="font-semibold">{row.original.project_name}</span>,
      },
      {
        accessorKey: "project_key",
        header: "Project key",
      },
      {
        accessorKey: "total_builds",
        header: "Builds",
        meta: { className: "text-right", cellClassName: "text-right" },
      },
      {
        accessorKey: "total_commits",
        header: "Commits",
        meta: { className: "text-right", cellClassName: "text-right" },
      },
      {
        id: "progress",
        header: "Tiến độ",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => {
          const processed = row.original.processed_commits ?? 0;
          const failed = row.original.failed_commits ?? 0;
          return (
            <div className="text-right text-sm">
              <div>{processed} đã quét</div>
              <div className="text-yellow-700">{failed} lỗi</div>
            </div>
          );
        },
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
              <Link href={`/projects/${row.original.id}`}>Chi tiết</Link>
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
        <MetricCard label="Số project" value={projects.length} hint="CSV đã upload" />
        <MetricCard label="Tổng builds" value={totals.builds} />
        <MetricCard label="Tổng commits" value={totals.commits} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Tải CSV TravisTorrent</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-3" onSubmit={handleUpload}>
            <div className="space-y-2">
              <Label htmlFor="csv-upload">File CSV</Label>
              <Input id="csv-upload" type="file" accept=".csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dataset-name">Tên hiển thị</Label>
              <Input id="dataset-name" type="text" placeholder="Ví dụ: angularjs-commits" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sonar-config">sonar.properties (tùy chọn)</Label>
              <Input id="sonar-config" type="file" accept=".properties" onChange={(event) => setSonarConfigFile(event.target.files?.[0] || null)} />
            </div>
            <div className="md:col-span-3">
              <Button type="submit" disabled={loading}>
                {loading ? "Đang tải..." : "Upload"}
              </Button>
            </div>
          </form>
          {message && <p className="mt-4 text-sm text-slate-700">{message}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Danh sách project</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={projects}
            serverPagination={{
              pageIndex,
              pageSize: 20,
              total,
              onPageChange: (next) => setPageIndex(next),
            }}
            serverOnChange={handleServerChange}
          />
        </CardContent>
      </Card>
    </section>
  );
}
