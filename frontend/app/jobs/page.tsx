"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, Job } from "@/lib/api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [total, setTotal] = useState(0);

  const handleServerChange = async (params: {
    pageIndex: number;
    pageSize: number;
    sorting?: { id: string; desc?: boolean } | null;
    filters: Record<string, any>;
  }) => {
    setError(null);
    try {
      const sortBy = params.sorting?.id;
      const sortDir = params.sorting?.desc ? "desc" : "asc";
      const res = await api.listJobsPaginated(
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

  // Initial load only
  useEffect(() => {
    handleServerChange({
      pageIndex: 0,
      pageSize: 20,
      sorting: null,
      filters: {},
    }).catch((err) => setError(err.message));
  }, []);

  // Auto-refresh current page every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      handleServerChange({
        pageIndex,
        pageSize: 20,
        sorting: null,
        filters: {},
      }).catch(console.error);
    }, 5000);
    return () => clearInterval(interval);
  }, [pageIndex]);

  const statusOptions = useMemo(
    () => Array.from(new Set(jobs.map((item) => item.status))).sort(),
    [jobs]
  );

  const columns = useMemo<ColumnDef<Job>[]>(() => {
    return [
      {
        accessorKey: "id",
        header: "Job",
        cell: ({ row }) => (
          <span className="font-medium">{row.original.id.slice(-8)}</span>
        ),
      },
      {
        id: "project",
        header: "Project",
        accessorFn: (row) => row.sonar_instance || row.id,
        cell: ({ row }) =>
          row.original.sonar_instance || row.original.id.slice(-8),
      },
      {
        accessorKey: "processed",
        header: "Số commit xử lý",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => row.original.processed,
      },
      {
        accessorKey: "total",
        header: "Tổng commit",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => row.original.total,
      },
      {
        accessorKey: "current_commit",
        header: "Commit đang chạy",
        cell: ({ row }) => (
          <span className="font-mono text-xs">
            {row.original.current_commit || "-"}
          </span>
        ),
      },
      {
        id: "progress",
        header: "Tiến độ",
        cell: ({ row }) => {
          const progress = row.original.total
            ? Math.round((row.original.processed / row.original.total) * 100)
            : 0;
          return (
            <div className="flex items-center gap-3">
              <Progress value={progress} className="w-40" />
              <span className="text-sm font-medium text-slate-700">
                {progress}%
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
    ];
  }, []);

  return (
    <section>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Job thu thập dữ liệu</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
          <DataTable
            pageSize={20}
            columns={columns}
            data={jobs}
            serverPagination={{
              pageIndex,
              pageSize: 20,
              total,
              onPageChange: (next) => setPageIndex(next),
            }}
            serverOnChange={handleServerChange}
            emptyMessage="Chưa có job nào chạy gần đây."
            renderToolbar={(table) => (
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <Input
                  className="md:max-w-xs"
                  placeholder="Lọc theo project..."
                  value={
                    (table.getColumn("project")?.getFilterValue() as string) ??
                    ""
                  }
                  onChange={(event) =>
                    table
                      .getColumn("project")
                      ?.setFilterValue(event.target.value)
                  }
                />
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    Trạng thái
                  </span>
                  <select
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    value={
                      (table.getColumn("status")?.getFilterValue() as string) ??
                      ""
                    }
                    onChange={(event) =>
                      table
                        .getColumn("status")
                        ?.setFilterValue(event.target.value || undefined)
                    }
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
