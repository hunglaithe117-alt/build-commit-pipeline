"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api, DataSource } from "@/lib/api";

export default function DataSourceDetailPage() {
  const params = useParams<{ id: string }>();
  const dataSourceId = params?.id as string;
  const [dataSource, setDataSource] = useState<DataSource | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [configDraft, setConfigDraft] = useState("");
  const [configFilename, setConfigFilename] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!dataSourceId) {
      return;
    }
    setLoading(true);
    try {
      const record = await api.getDataSource(dataSourceId);
      setDataSource(record);
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }, [dataSourceId]);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (dataSource?.sonar_config?.content) {
      setConfigDraft(dataSource.sonar_config.content);
    } else {
      setConfigDraft("");
    }
  }, [dataSource]);

  const handleImportFile = (file: File | null) => {
    if (!file) {
      setConfigFilename(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setConfigDraft(typeof reader.result === "string" ? reader.result : "");
      setConfigFilename(file.name);
    };
    reader.onerror = () => {
      setMessage("Không thể đọc file sonar.properties đã chọn.");
    };
    reader.readAsText(file);
  };

  const handleSaveConfig = async () => {
    if (!dataSourceId) {
      return;
    }
    if (!configDraft) {
      setMessage("Nội dung sonar.properties không được để trống.");
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateDataSourceConfig(dataSourceId, {
        content: configDraft,
        source: configFilename ? "file" : "text",
        filename: configFilename ?? undefined,
      });
      setDataSource(updated);
      setMessage("Đã lưu cấu hình sonar.properties.");
      setConfigFilename(updated.sonar_config?.filename || configFilename);
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  };

  const stats = useMemo(() => dataSource?.stats, [dataSource]);

  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Nguồn dữ liệu</p>
          <h1 className="text-2xl font-semibold">{dataSource?.name || "Đang tải..."}</h1>
        </div>
        <Button variant="outline" asChild>
          <Link href="/data-sources">Quay lại danh sách</Link>
        </Button>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Đang tải dữ liệu...</p>}

      {message && <p className="text-sm text-slate-600">{message}</p>}

      {dataSource && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <MetricCard label="Tổng builds" value={stats?.total_builds ?? "-"} />
            <MetricCard label="Tổng commits" value={stats?.total_commits ?? "-"} />
            <MetricCard label="Branch" value={stats?.unique_branches ?? "-"} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Thông tin chung</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid gap-2 md:grid-cols-2">
                <div>
                  <p className="text-muted-foreground">File gốc</p>
                  <p className="font-medium break-all">{dataSource.filename}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Project key</p>
                  <p className="font-medium">{stats?.project_key ?? "Chưa xác định"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Project name</p>
                  <p className="font-medium">{stats?.project_name ?? "Chưa xác định"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Trạng thái</p>
                  <p className="font-medium capitalize">{dataSource.status}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Cấu hình sonar.properties</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                value={configDraft}
                onChange={(event) => setConfigDraft(event.target.value)}
                placeholder="sonar.projectKey=my-project&#10;sonar.sources=src"
              />
              <div className="flex flex-wrap gap-3">
                <input
                  ref={importInputRef}
                  type="file"
                  accept=".properties,.txt"
                  className="hidden"
                  onChange={(event) => handleImportFile(event.target.files?.[0] || null)}
                />
                <Button type="button" variant="outline" onClick={() => importInputRef.current?.click()}>
                  Tải nội dung từ file
                </Button>
                <Button type="button" onClick={handleSaveConfig} disabled={saving}>
                  {saving ? "Đang lưu..." : "Lưu cấu hình"}
                </Button>
              </div>
              {dataSource.sonar_config?.updated_at && (
                <p className="text-xs text-muted-foreground">
                  Cập nhật lần cuối: {new Date(dataSource.sonar_config.updated_at).toLocaleString()}
                </p>
              )}
              {configFilename && <p className="text-xs text-muted-foreground">Nguồn: {configFilename}</p>}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
