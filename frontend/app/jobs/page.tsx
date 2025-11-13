"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import Link from "next/link";
import { api, Job, WorkersStats } from "@/lib/api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [workersStats, setWorkersStats] = useState<WorkersStats | null>(null);
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

  const fetchWorkersStats = async () => {
    try {
      const stats = await api.getWorkersStats();
      setWorkersStats(stats);
    } catch (err: any) {
      console.error("Failed to fetch workers stats:", err);
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

    fetchWorkersStats();
  }, [pageIndex, handleServerChange, fetchWorkersStats]);

  // Auto-refresh current page and workers stats every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      handleServerChange({
        pageIndex,
        pageSize: 20,
        sorting: null,
        filters: {},
      }).catch(console.error);

      fetchWorkersStats();
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
        header: "Job ID",
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.id.slice(-8)}</span>
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
        id: "progress",
        header: "Tiến độ",
        cell: ({ row }) => {
          const progress = row.original.total
            ? Math.round((row.original.processed / row.original.total) * 100)
            : 0;
          const failedCount = row.original.failed_count || 0;
          return (
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <Progress value={progress} className="w-32" />
                <span className="text-sm font-medium text-slate-700 min-w-[45px]">
                  {progress}%
                </span>
              </div>
              <div className="text-xs text-slate-500 flex items-center gap-2">
                <span>
                  {row.original.processed} / {row.original.total} commits
                </span>
                {failedCount > 0 && (
                  <span className="text-red-600 font-medium">
                    • {failedCount} lỗi
                  </span>
                )}
              </div>
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
        accessorKey: "created_at",
        header: "Tạo lúc",
        cell: ({ row }) => (
          <span className="text-xs text-slate-600">
            {new Date(row.original.created_at).toLocaleString("vi-VN")}
          </span>
        ),
      },
      {
        id: "actions",
        header: "Hành động",
        cell: ({ row }) => {
          const failed = row.original.failed_count || 0;
          return (
            <div className="flex items-center gap-2">
              {failed > 0 && (
                <button
                  className="text-xs text-red-600 hover:underline"
                  onClick={async () => {
                    const ok = confirm(
                      `Retry ${failed} failed commit(s) for job ${row.original.id.slice(
                        -8
                      )}?`
                    );
                    if (!ok) return;
                    try {
                      // Fetch pending dead letters for this job
                      const res = await api.listDeadLettersPaginated(
                        1,
                        1000,
                        undefined,
                        undefined,
                        { "payload.job_id": row.original.id, status: "pending" }
                      );
                      const items = res.items || [];
                      for (const item of items) {
                        try {
                          await api.retryDeadLetter(item.id, {});
                        } catch (e) {
                          console.error(
                            "Failed to retry dead letter",
                            item.id,
                            e
                          );
                        }
                      }
                      // Refresh jobs and workers
                      handleServerChange({
                        pageIndex,
                        pageSize: 20,
                        sorting: null,
                        filters: {},
                      });
                      fetchWorkersStats();
                      alert(
                        `Enqueued ${items.length} retried commit(s) at high priority.`
                      );
                    } catch (err) {
                      console.error(err);
                      alert(
                        "Failed to enqueue retries. Check console for details."
                      );
                    }
                  }}
                >
                  Retry
                </button>
              )}
            </div>
          );
        },
      },
    ];
  }, []);

  return (
    <section className="space-y-6">
      {/* Workers Stats Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">
            Thông tin Workers SonarScanner
          </CardTitle>
        </CardHeader>
        <CardContent>
          {workersStats ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                  <div className="text-sm text-blue-600 font-medium">
                    Số Workers
                  </div>
                  <div className="text-2xl font-bold text-blue-900 mt-1">
                    {workersStats.total_workers}
                  </div>
                </div>
                <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                  <div className="text-sm text-green-600 font-medium">
                    Concurrency (max)
                  </div>
                  <div className="text-2xl font-bold text-green-900 mt-1">
                    {workersStats.max_concurrency}
                  </div>
                </div>
                <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                  <div className="text-sm text-purple-600 font-medium">
                    Đang scan
                  </div>
                  <div className="text-2xl font-bold text-purple-900 mt-1">
                    {workersStats.active_scan_tasks}
                  </div>
                </div>
                <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                  <div className="text-sm text-orange-600 font-medium">
                    Đang chờ
                  </div>
                  <div className="text-2xl font-bold text-orange-900 mt-1">
                    {workersStats.queued_scan_tasks}
                  </div>
                </div>
              </div>

              {/* Worker Details */}
              {workersStats.workers.length > 0 && (
                <div className="space-y-3 mt-6">
                  <h3 className="font-semibold text-sm text-slate-700">
                    Chi tiết Workers:
                  </h3>
                  {workersStats.workers.map((worker, idx) => (
                    <div
                      key={idx}
                      className="border rounded-lg p-4 bg-slate-50"
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="font-medium text-sm text-slate-900">
                          {worker.name}
                        </div>
                        <div className="text-xs text-slate-600">
                          {worker.active_tasks} / {worker.max_concurrency} tasks
                        </div>
                      </div>

                      {worker.tasks.length > 0 && (
                        <div className="space-y-2">
                          {worker.tasks.map((task, taskIdx) => (
                            <div
                              key={taskIdx}
                              className="bg-white rounded p-3 text-xs border border-slate-200"
                            >
                              <div className="grid grid-cols-2 gap-2">
                                <div>
                                  <span className="font-semibold text-slate-600">
                                    Commit:
                                  </span>{" "}
                                  <span className="font-mono text-slate-800">
                                    {task.current_commit?.substring(0, 8) ||
                                      "N/A"}
                                  </span>
                                </div>
                                <div className="truncate">
                                  <span className="font-semibold text-slate-600">
                                    Repo:
                                  </span>{" "}
                                  <span className="text-slate-800">
                                    {task.current_repo ? (
                                      <Link
                                        href={`/dead-letters?project=${encodeURIComponent(
                                          task.current_repo
                                        )}`}
                                      >
                                        <span className="hover:underline">
                                          {task.current_repo}
                                        </span>
                                      </Link>
                                    ) : (
                                      "N/A"
                                    )}
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {worker.tasks.length === 0 && (
                        <div className="text-xs text-slate-500 italic">
                          Không có task đang chạy
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {workersStats.workers.length === 0 && (
                <div className="text-sm text-slate-500 text-center py-4">
                  Không có worker nào đang hoạt động
                </div>
              )}

              {workersStats.error && (
                <div className="text-xs text-amber-600 mt-2">
                  Lưu ý: {workersStats.error}
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              Đang tải thông tin workers...
            </div>
          )}
        </CardContent>
      </Card>

      {/* Jobs Table */}
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
