"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, FailedCommit } from "@/lib/api";

const PAGE_SIZE = 20;
const STATUS_OPTIONS = [
  { value: "", label: "Tất cả" },
  { value: "pending", label: "Pending" },
  { value: "queued", label: "Queued" },
  { value: "resolved", label: "Resolved" },
];

type TableParams = {
  pageIndex: number;
  pageSize: number;
  sorting?: { id: string; desc?: boolean } | null;
  filters: Record<string, any>;
};

export default function FailedCommitsPage() {
  const [records, setRecords] = useState<FailedCommit[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [selected, setSelected] = useState<FailedCommit | null>(null);
  const [configDraft, setConfigDraft] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [enqueueAfterDiscover, setEnqueueAfterDiscover] = useState(false);
  const [forceDiscover, setForceDiscover] = useState(false);
  const [isTableLoading, setIsTableLoading] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const selectedIdRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastQueryRef = useRef<TableParams | null>(null);

  const loadPage = useCallback(
    async (params: TableParams) => {
      setMessage(null);
      setIsTableLoading(true);
      const mergedFilters = {
        ...(params.filters || {}),
        status: statusFilter || undefined,
        reason: { $ne: "missing-fork" },
      };
      try {
        const sortBy = params.sorting?.id;
        const sortDir = params.sorting?.desc ? "desc" : "asc";
        const res = await api.listFailedCommitsPaginated(
          params.pageIndex + 1,
          params.pageSize,
          sortBy,
          sortDir,
          mergedFilters
        );
        lastQueryRef.current = { ...params, filters: mergedFilters };
        setRecords(res.items);
        setTotal(res.total || 0);
        setPageIndex(params.pageIndex);
        if (selectedIdRef.current) {
          const match = res.items.find((item) => item.id === selectedIdRef.current);
          if (match) {
            setSelected(match);
            setConfigDraft(match.config_override || "");
          }
        }
      } catch (err: any) {
        setMessage(err.message ?? "Không thể tải danh sách failed commits");
      } finally {
        setIsTableLoading(false);
      }
    },
    [statusFilter]
  );

  const handleServerChange = useCallback(
    (params: TableParams) => {
      loadPage(params).catch(() => null);
    },
    [loadPage]
  );

  useEffect(() => {
    handleServerChange({ pageIndex: 0, pageSize: PAGE_SIZE, sorting: null, filters: {} });
  }, [handleServerChange, statusFilter]);

  useEffect(() => {
    if (selected) {
      selectedIdRef.current = selected.id;
      setConfigDraft(selected.config_override || "");
    } else {
      selectedIdRef.current = null;
      setConfigDraft("");
    }
  }, [selected]);

  const refreshCurrentPage = useCallback(async () => {
    const last =
      lastQueryRef.current ?? ({
        pageIndex,
        pageSize: PAGE_SIZE,
        sorting: null,
        filters: {},
      } as TableParams);
    await loadPage(last);
  }, [loadPage, pageIndex]);

  const handleSelect = (record: FailedCommit) => {
    setSelected(record);
  };

  const handleImportFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setConfigDraft(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => setMessage("Không thể đọc file cấu hình.");
    reader.readAsText(file);
  };

  const handleDiscoverFork = async () => {
    if (!selected) return;
    setIsDiscovering(true);
    setMessage(null);
    try {
      const updated = await api.discoverFailedCommitFork(selected.id, {
        enqueue: enqueueAfterDiscover,
        force: forceDiscover,
        github_token: githubToken || undefined,
      });
      setSelected(updated);
      setMessage("Đã chạy tìm kiếm forks.");
      await refreshCurrentPage();
    } catch (err: any) {
      setMessage(err.message ?? "Không thể tìm fork cho commit này.");
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleRetry = async () => {
    if (!selected) return;
    setIsRetrying(true);
    setMessage(null);
    try {
      const updated = await api.retryFailedCommit(selected.id, {
        config_override: configDraft || undefined,
        config_source: configDraft ? "text" : selected.config_source ?? undefined,
      });
      setSelected(updated);
      setMessage("Đã enqueue retry cho commit.");
      await refreshCurrentPage();
    } catch (err: any) {
      setMessage(err.message ?? "Không thể retry commit.");
    } finally {
      setIsRetrying(false);
    }
  };

  const columns = useMemo<ColumnDef<FailedCommit>[]>(() => {
    return [
      {
        accessorKey: "payload.project_key",
        header: "Project",
        cell: ({ row }) => (
          <span className="font-medium">{row.original.payload?.project_key || "-"}</span>
        ),
      },
      {
        accessorKey: "payload.commit_sha",
        header: "Commit",
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.payload?.commit_sha}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
      {
        id: "error",
        header: "Lỗi",
        cell: ({ row }) => (
          <span className="text-xs text-red-600">
            {row.original.payload?.error || row.original.reason || "-"}
          </span>
        ),
      },
      {
        accessorKey: "fork_search.status",
        header: "Fork search",
        cell: ({ row }) => (
          <span className="text-xs">
            {row.original.fork_search?.status ? (
              <StatusBadge value={row.original.fork_search?.status} />
            ) : (
              "Chưa chạy"
            )}
          </span>
        ),
      },
      {
        accessorKey: "updated_at",
        header: "Cập nhật",
        cell: ({ row }) => (
          <span className="text-xs">
            {row.original.updated_at
              ? new Date(row.original.updated_at).toLocaleString()
              : "-"}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button variant="ghost" size="sm" onClick={() => handleSelect(row.original)}>
            Chọn
          </Button>
        ),
      },
    ];
  }, []);

  const toolbar = useCallback(
    (table: any) => (
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <Input
            placeholder="Lọc project"
            className="md:w-56"
            value={(table.getColumn("payload.project_key")?.getFilterValue() as string) ?? ""}
            onChange={(event) => table.getColumn("payload.project_key")?.setFilterValue(event.target.value)}
          />
          <Input
            placeholder="Lọc commit"
            className="md:w-56"
            value={(table.getColumn("payload.commit_sha")?.getFilterValue() as string) ?? ""}
            onChange={(event) => table.getColumn("payload.commit_sha")?.setFilterValue(event.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Status</label>
          <select
            className="rounded-md border px-3 py-2 text-sm"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    ),
    [statusFilter]
  );

  const selectedPayload = selected?.payload ?? {};
  const forkSearch = selected?.fork_search;

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Failed commits</CardTitle>
        </CardHeader>
        <CardContent>
          {message && <p className="mb-3 text-sm text-slate-700">{message}</p>}
          <DataTable
            columns={columns}
            data={records}
            isLoading={isTableLoading}
            serverPagination={{
              pageIndex,
              pageSize: PAGE_SIZE,
              total,
              onPageChange: (next) => setPageIndex(next),
            }}
            serverOnChange={handleServerChange}
            renderToolbar={toolbar}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-xl">Chi tiết & xử lý</CardTitle>
            {selected && (
              <p className="text-sm text-muted-foreground">
                {selectedPayload.project_key || "-"} · {selectedPayload.commit_sha}
              </p>
            )}
          </div>
          {selected && (
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
              Bỏ chọn
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-6">
          {selected ? (
            <>
              <div className="grid gap-3 rounded-md border p-3 text-sm md:grid-cols-2">
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Project</p>
                  <p className="font-medium">{selectedPayload.project_key || "-"}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Commit</p>
                  <p className="font-mono text-xs">{selectedPayload.commit_sha}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Status</p>
                  <StatusBadge value={selected.status} />
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Job ID</p>
                  <p className="font-mono text-xs">{selectedPayload.job_id || "-"}</p>
                </div>
                <div className="md:col-span-2">
                  <p className="text-xs uppercase text-muted-foreground">Lỗi</p>
                  <p className="text-sm text-red-600">{selectedPayload.error || selected.reason || "-"}</p>
                </div>
              </div>

              <div className="space-y-3 rounded-md border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold">Fork search</p>
                    <p className="text-xs text-muted-foreground">
                      {forkSearch?.checked_at
                        ? `Lần cuối: ${new Date(forkSearch.checked_at).toLocaleString()}`
                        : "Chưa chạy"}
                    </p>
                  </div>
                  <StatusBadge value={forkSearch?.status ?? "pending"} />
                </div>
                {forkSearch?.fork_full_name && (
                  <p className="text-sm">
                    Đã tìm thấy trong fork: {" "}
                    <a
                      href={`https://github.com/${forkSearch.fork_full_name}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 underline"
                    >
                      {forkSearch.fork_full_name}
                    </a>
                  </p>
                )}
                {forkSearch?.message && (
                  <p className="text-sm text-muted-foreground">Ghi chú: {forkSearch.message}</p>
                )}
                <div className="flex flex-col gap-2 md:flex-row md:items-center">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={forceDiscover}
                      onChange={(event) => setForceDiscover(event.target.checked)}
                    />
                    Force chạy lại
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={enqueueAfterDiscover}
                      onChange={(event) => setEnqueueAfterDiscover(event.target.checked)}
                    />
                    Enqueue scan nếu tìm thấy
                  </label>
                </div>
                <Input
                  placeholder="GitHub tokens (comma/newline separated)"
                  value={githubToken}
                  onChange={(event) => setGithubToken(event.target.value)}
                />
                <Button onClick={handleDiscoverFork} disabled={isDiscovering}>
                  {isDiscovering ? "Đang tìm..." : "Tìm trong forks"}
                </Button>
              </div>

              <div className="space-y-3 rounded-md border p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold">Retry commit</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfigDraft("")}
                    disabled={isRetrying}
                  >
                    Xoá nội dung
                  </Button>
                </div>
                <Textarea
                  rows={8}
                  value={configDraft}
                  onChange={(event) => setConfigDraft(event.target.value)}
                  placeholder="sonar.projectKey=example\nsonar.sources=src"
                />
                <div className="flex flex-wrap gap-3">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".properties,.txt"
                    className="hidden"
                    onChange={(event) => handleImportFile(event.target.files?.[0] || null)}
                  />
                  <Button variant="outline" onClick={() => fileInputRef.current?.click()}>
                    Tải nội dung từ file
                  </Button>
                  <Button onClick={handleRetry} disabled={isRetrying}>
                    {isRetrying ? "Đang enqueue..." : "Retry commit"}
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Chọn một failed commit ở bảng trên để xem thông tin và thao tác.
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
