"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { api, OutputDataset } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function OutputsPage() {
  const [outputs, setOutputs] = useState<OutputDataset[]>([]);
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
      const res = await api.listOutputsPaginated(params.pageIndex + 1, params.pageSize, sortBy, sortDir, params.filters);
      setOutputs(res.items);
      setTotal(res.total || 0);
      setPageIndex(params.pageIndex);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const statusOptions = useMemo(() => ["ready"], []);

  const columns = useMemo<ColumnDef<OutputDataset>[]>(() => {
    return [
      {
        id: "project",
        header: "Tên repo",
        accessorFn: (row) => row.repo_name ?? row.project_key ?? row.job_id.slice(-8),
        cell: ({ row }) => (
          <span className="font-medium">
            {row.original.repo_name ?? row.original.project_key ?? row.original.job_id.slice(-8)}
          </span>
        ),
      },
      {
        accessorKey: "record_count",
        header: "Số bản ghi đã quét",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => row.original.record_count,
      },
      {
        id: "status",
        header: "Trạng thái",
        accessorFn: () => "ready",
        cell: () => <StatusBadge value="ready" />,
      },
      {
        id: "download",
        header: "Tải xuống",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => (
          <Button asChild variant="link" className="px-0">
            <a href={`${API_BASE_URL}/api/outputs/${row.original.id}/download`} target="_blank" rel="noreferrer">
              Download
            </a>
          </Button>
        ),
      },
    ];
  }, []);

  return (
    <section>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Dữ liệu đầu ra</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
          <DataTable
            pageSize={20}
            columns={columns}
            data={outputs}
            serverPagination={{ pageIndex, pageSize: 20, total, onPageChange: (next) => setPageIndex(next) }}
            serverOnChange={handleServerChange}
            emptyMessage="Chưa có dataset nào được tạo."
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
