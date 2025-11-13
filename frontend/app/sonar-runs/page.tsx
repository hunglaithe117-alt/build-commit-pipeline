"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { api, SonarRun } from "@/lib/api";

export default function SonarRunsPage() {
  const [runs, setRuns] = useState<SonarRun[]>([]);
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
      const res = await api.listRunsPaginated(params.pageIndex + 1, params.pageSize, sortBy, sortDir, params.filters);
      setRuns(res.items);
      setTotal(res.total || 0);
      setPageIndex(params.pageIndex);
    } catch (err: any) {
      setError(err.message);
    }
  };

  // Initial load
  useEffect(() => {
    handleServerChange({
      pageIndex: 0,
      pageSize: 50,
      sorting: null,
      filters: {},
    }).catch((err) => setError(err.message));
  }, []);

  const statusOptions = useMemo(() => Array.from(new Set(runs.map((item) => item.status))).sort(), [runs]);

  const columns = useMemo<ColumnDef<SonarRun>[]>(() => {
    return [
      {
        accessorKey: "project_key",
        header: "Project key",
        cell: ({ row }) => <span className="font-medium">{row.original.project_key}</span>,
      },
      {
        accessorKey: "commit_sha",
        header: "Commit",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.commit_sha || "-"}</span>,
      },
      {
        accessorKey: "component_key",
        header: "Component",
        cell: ({ row }) => <span className="whitespace-nowrap">{row.original.component_key || "-"}</span>,
      },
      {
        accessorKey: "sonar_instance",
        header: "Instance",
        cell: ({ row }) => row.original.sonar_instance || "-",
      },
      {
        accessorKey: "sonar_host",
        header: "Host",
        cell: ({ row }) => <span className="whitespace-nowrap">{row.original.sonar_host || "-"}</span>,
      },
      {
        accessorKey: "analysis_id",
        header: "Analysis ID",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.analysis_id || "-"}</span>,
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
      {
        accessorKey: "started_at",
        header: "Bắt đầu",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-xs">{new Date(row.original.started_at).toLocaleString()}</span>
        ),
      },
      {
        accessorKey: "finished_at",
        header: "Kết thúc",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-xs">
            {row.original.finished_at ? new Date(row.original.finished_at).toLocaleString() : "-"}
          </span>
        ),
      },
      {
        accessorKey: "metrics_path",
        header: "Metrics",
        cell: ({ row }) => <span className="max-w-[200px] truncate text-xs">{row.original.metrics_path || "-"}</span>,
      },
      {
        accessorKey: "log_path",
        header: "Log",
        cell: ({ row }) => <span className="max-w-[200px] truncate text-xs">{row.original.log_path || "-"}</span>,
      },
    ];
  }, []);

  return (
    <section>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Lịch sử quét SonarQube</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
          <DataTable
            pageSize={50}
            columns={columns}
            data={runs}
            serverPagination={{ pageIndex, pageSize: 50, total, onPageChange: (next) => setPageIndex(next) }}
            serverOnChange={handleServerChange}
            emptyMessage="Chưa có Sonar run nào."
            renderToolbar={(table) => (
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <Input
                  className="md:max-w-xs"
                  placeholder="Lọc theo project..."
                  value={(table.getColumn("project_key")?.getFilterValue() as string) ?? ""}
                  onChange={(event) => table.getColumn("project_key")?.setFilterValue(event.target.value)}
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
