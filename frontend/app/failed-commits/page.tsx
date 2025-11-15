"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, ScanJob } from "@/lib/api";

export default function FailedCommitsPage() {
  const [jobs, setJobs] = useState<ScanJob[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<ScanJob | null>(null);
  const [configDraft, setConfigDraft] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedIdRef = useRef<string | null>(null);

  const loadPage = useCallback(
    async (params: {
      pageIndex: number;
      pageSize: number;
      sorting?: { id: string; desc?: boolean } | null;
      filters: Record<string, any>;
    }) => {
      setMessage(null);
      try {
        const sortBy = params.sorting?.id;
        const sortDir = params.sorting?.desc ? "desc" : "asc";
        const filters = {
          ...(params.filters || {}),
          status: "FAILED_PERMANENT",
        };
        const res = await api.listScanJobsPaginated(
          params.pageIndex + 1,
          params.pageSize,
          sortBy,
          sortDir,
          filters
        );
        setJobs(res.items);
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
        setMessage(err.message);
      }
    },
    []
  );

  useEffect(() => {
    loadPage({ pageIndex: 0, pageSize: 20, sorting: null, filters: {} }).catch(() => null);
  }, [loadPage]);

  useEffect(() => {
    if (selected) {
      selectedIdRef.current = selected.id;
      setConfigDraft(selected.config_override || "");
    } else {
      selectedIdRef.current = null;
      setConfigDraft("");
    }
  }, [selected]);

  const handleSelect = (job: ScanJob) => {
    setSelected(job);
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

  const handleRetry = async () => {
    if (!selected) return;
    setMessage(null);
    try {
      await api.retryScanJob(selected.id, {
        config_override: configDraft || undefined,
        config_source: configDraft ? "text" : selected.config_source,
      });
      setMessage("Đã gửi lại commit.");
      setSelected(null);
      await loadPage({ pageIndex, pageSize: 20, sorting: null, filters: {} });
    } catch (err: any) {
      setMessage(err.message);
    }
  };

  const columns = useMemo<ColumnDef<ScanJob>[]>(() => {
    return [
      {
        accessorKey: "project_key",
        header: "Project",
        cell: ({ row }) => <span className="font-medium">{row.original.project_key || "-"}</span>,
      },
      {
        accessorKey: "commit_sha",
        header: "Commit",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.commit_sha}</span>,
      },
      {
        accessorKey: "last_error",
        header: "Lỗi",
        cell: ({ row }) => <span className="text-xs text-red-600">{row.original.last_error || "-"}</span>,
      },
      {
        accessorKey: "updated_at",
        header: "Cập nhật",
        cell: ({ row }) => <span className="text-xs">{new Date(row.original.updated_at).toLocaleString()}</span>,
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

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Failed commits</CardTitle>
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
            renderToolbar={(table) => (
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <Input
                  placeholder="Lọc theo project"
                  className="md:w-60"
                  value={(table.getColumn("project_key")?.getFilterValue() as string) ?? ""}
                  onChange={(event) => table.getColumn("project_key")?.setFilterValue(event.target.value)}
                />
                <span className="text-sm text-muted-foreground">
                  Đang hiển thị các commit FAILED_PERMANENT
                </span>
              </div>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Retry failed commit</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {message && <p className="text-sm text-slate-700">{message}</p>}
          {selected ? (
            <div className="space-y-4">
              <div className="rounded-md border p-3 text-sm space-y-1">
                <p>
                  <span className="text-muted-foreground">Project:</span> {selected.project_key || "-"}
                </p>
                <p>
                  <span className="text-muted-foreground">Commit:</span> {selected.commit_sha}
                </p>
                <p>
                  <span className="text-muted-foreground">Lỗi:</span> {selected.last_error || "-"}
                </p>
                <p className="text-muted-foreground">Status: <StatusBadge value={selected.status} /></p>
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
                <Button onClick={handleRetry}>Retry commit</Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Chọn commit ở bảng bên trái để chỉnh cấu hình và chạy lại.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
