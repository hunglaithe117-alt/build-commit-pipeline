"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ScanJob, WorkersStats } from "@/lib/api";

export default function ScanJobsPage() {
  const [jobs, setJobs] = useState<ScanJob[]>([]);
  const [workersStats, setWorkersStats] = useState<WorkersStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [total, setTotal] = useState(0);

  const loadPage = async (params: {
    pageIndex: number;
    pageSize: number;
    sorting?: { id: string; desc?: boolean } | null;
    filters: Record<string, any>;
  }) => {
    setError(null);
    try {
      const sortBy = params.sorting?.id;
      const sortDir = params.sorting?.desc ? "desc" : "asc";
      const res = await api.listScanJobsPaginated(
        params.pageIndex + 1,
        params.pageSize,
        sortBy,
        sortDir,
        params.filters
      );
      setJobs(res.items);
      setTotal(res.total || 0);
      setPageIndex(params.pageIndex);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const refreshWorkers = async () => {
    try {
      const stats = await api.getWorkersStats();
      setWorkersStats(stats);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadPage({ pageIndex: 0, pageSize: 20, sorting: null, filters: {} }).catch(() => null);
    refreshWorkers();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      loadPage({ pageIndex, pageSize: 20, sorting: null, filters: {} }).catch(() => null);
      refreshWorkers();
    }, 5000);
    return () => clearInterval(interval);
  }, [pageIndex]);

  const columns = useMemo<ColumnDef<ScanJob>[]>(() => {
    return [
      {
        accessorKey: "commit_sha",
        header: "Commit",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.commit_sha.slice(0, 12)}</span>,
      },
      {
        accessorKey: "project_key",
        header: "Project",
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
      {
        id: "retries",
        header: "Retries",
        cell: ({ row }) => (
          <span className="text-sm">
            {row.original.retry_count} / {row.original.max_retries}
          </span>
        ),
      },
      {
        accessorKey: "last_error",
        header: "Lỗi gần nhất",
        cell: ({ row }) => (
          <span className="text-xs text-red-600">
            {row.original.last_error || "-"}
          </span>
        ),
      },
      {
        accessorKey: "updated_at",
        header: "Cập nhật",
        cell: ({ row }) => (
          <span className="text-xs text-slate-600">
            {new Date(row.original.updated_at).toLocaleTimeString()}
          </span>
        ),
      },
    ];
  }, []);

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Worker status</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-sm text-muted-foreground">Workers</p>
            <p className="text-2xl font-semibold">{workersStats?.total_workers ?? 0}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Đang chạy</p>
            <p className="text-2xl font-semibold">{workersStats?.active_scan_tasks ?? 0}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Chờ</p>
            <p className="text-2xl font-semibold">{workersStats?.queued_scan_tasks ?? 0}</p>
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Scan jobs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={jobs}
            serverPagination={{
              pageIndex,
              pageSize: 20,
              total,
              onPageChange: (next) => setPageIndex(next),
            }}
            serverOnChange={loadPage}
          />
        </CardContent>
      </Card>
    </section>
  );
}
