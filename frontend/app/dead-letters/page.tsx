"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, DeadLetter } from "@/lib/api";

export default function DeadLettersPage() {
  const [items, setItems] = useState<DeadLetter[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<DeadLetter | null>(null);
  const [configDraft, setConfigDraft] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listDeadLetters();
      setItems(data);
      if (selected) {
        const next = data.find((item) => item.id === selected.id);
        if (next) {
          setSelected(next);
        }
      }
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    setConfigDraft(selected?.config_override ?? "");
    setActionMessage(null);
  }, [selected]);

  const handleSelect = useCallback((row: DeadLetter) => {
    setSelected(row);
  }, []);

  const handleImportFile = (file: File | null) => {
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setConfigDraft(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      setActionMessage("Không thể đọc file config.");
    };
    reader.readAsText(file);
  };

  const handleSaveConfig = async () => {
    if (!selected) {
      return;
    }
    if (!configDraft) {
      setActionMessage("Vui lòng nhập nội dung sonar.properties.");
      return;
    }
    setBusy(true);
    try {
      const updated = await api.updateDeadLetter(selected.id, {
        config_override: configDraft,
        config_source: "text",
      });
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(updated);
      setActionMessage("Đã lưu cấu hình.");
    } catch (error: any) {
      setActionMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async () => {
    if (!selected) {
      return;
    }
    if (!configDraft) {
      setActionMessage("Vui lòng nhập nội dung sonar.properties trước khi retry.");
      return;
    }
    setBusy(true);
    try {
      const updated = await api.retryDeadLetter(selected.id, {
        config_override: configDraft,
        config_source: "text",
      });
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(updated);
      setActionMessage("Đã gửi commit chạy lại.");
    } catch (error: any) {
      setActionMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const statusOptions = useMemo(() => Array.from(new Set(items.map((item) => item.status))).sort(), [items]);

  const columns = useMemo<ColumnDef<DeadLetter>[]>(
    () => [
      {
        accessorKey: "project",
        header: "Project",
        accessorFn: (row) => (row.payload?.commit?.project_key as string) ?? "unknown",
        cell: ({ row }) => <span className="font-medium">{row.original.payload?.commit?.project_key ?? "unknown"}</span>,
      },
      {
        accessorKey: "commit_sha",
        header: "Commit",
        accessorFn: (row) => row.payload?.commit?.commit_sha ?? "",
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.payload?.commit?.commit_sha ?? "-"}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Trạng thái",
        cell: ({ row }) => <StatusBadge value={row.original.status} />,
      },
      {
        accessorKey: "reason",
        header: "Lý do",
        cell: ({ row }) => row.original.reason,
      },
      {
        accessorKey: "created_at",
        header: "Tạo lúc",
        cell: ({ row }) => new Date(row.original.created_at).toLocaleString(),
      },
      {
        id: "actions",
        header: "",
        meta: { className: "text-right", cellClassName: "text-right" },
        cell: ({ row }) => (
          <Button size="sm" variant="outline" onClick={() => handleSelect(row.original)}>
            Cấu hình
          </Button>
        ),
      },
    ],
    [handleSelect]
  );

  return (
    <section className="space-y-8">
      <div>
        <p className="text-sm text-muted-foreground">Sonar Deadletter</p>
        <h1 className="text-2xl font-semibold">Commit lỗi cần xử lý</h1>
      </div>

      {message && <p className="text-sm text-destructive">{message}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Danh sách commit lỗi</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            pageSize={50}
            columns={columns}
            data={items}
            emptyMessage={loading ? "Đang tải..." : "Không có commit lỗi nào."}
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

      {selected && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">
              Chỉnh sonar.properties cho {selected.payload?.commit?.project_key ?? "unknown"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Lỗi: {selected.payload?.error ?? "Không rõ"} (commit {selected.payload?.commit?.commit_sha ?? "-"})
            </p>
            <Textarea value={configDraft} onChange={(event) => setConfigDraft(event.target.value)} />
            <div className="flex flex-wrap gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept=".properties,.txt"
                className="hidden"
                onChange={(event) => handleImportFile(event.target.files?.[0] || null)}
              />
              <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
                Lấy nội dung từ file
              </Button>
              <Button type="button" onClick={handleSaveConfig} disabled={busy}>
                {busy ? "Đang lưu..." : "Lưu config"}
              </Button>
              <Button type="button" variant="secondary" onClick={handleRetry} disabled={busy}>
                {busy ? "Đang xử lý..." : "Lưu & Retry"}
              </Button>
            </div>
            {actionMessage && <p className="text-sm text-slate-600">{actionMessage}</p>}
          </CardContent>
        </Card>
      )}
    </section>
  );
}
