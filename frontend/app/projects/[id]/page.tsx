"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { api, Project } from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params?.id as string;
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [configFile, setConfigFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const record = await api.getProject(projectId);
      setProject(record);
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  const handleSaveConfig = async () => {
    if (!projectId || !configFile) {
      setMessage("Chọn file sonar.properties trước khi cập nhật");
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateProjectConfig(projectId, configFile);
      setProject(updated);
      setConfigFile(null);
      setMessage("Đã cập nhật sonar.properties");
    } catch (error: any) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Project</p>
          <h1 className="text-2xl font-semibold">{project?.project_name ?? "Đang tải..."}</h1>
        </div>
        <Button variant="outline" asChild>
          <Link href="/projects">Quay lại danh sách</Link>
        </Button>
      </div>

      {message && <p className="text-sm text-slate-700">{message}</p>}
      {loading && <p className="text-sm text-muted-foreground">Đang tải dữ liệu...</p>}

      {project && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <MetricCard label="Commits" value={project.total_commits} />
            <MetricCard label="Builds" value={project.total_builds} />
            <MetricCard label="Trạng thái" value={project.status} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Thông tin chung</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="text-muted-foreground">Project key</p>
                <p className="font-medium">{project.project_key}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Đã xử lý</p>
                <p className="font-medium">
                  {project.processed_commits} OK / {project.failed_commits} lỗi
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">File CSV</p>
                <p className="font-medium break-all">{project.source_filename ?? "Không xác định"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Cập nhật</p>
                <p className="font-medium">
                  {new Date(project.updated_at).toLocaleString()}
                </p>
              </div>
            </CardContent>
          </Card>
          <div className="flex gap-3">
            <Button asChild variant="outline">
              <a href={`/api/projects/${projectId}/results/export`} target="_blank" rel="noreferrer">
                Download kết quả (CSV)
              </a>
            </Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">sonar.properties</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="config-upload">Chọn file mới</Label>
                <input
                  id="config-upload"
                  type="file"
                  accept=".properties,.txt"
                  onChange={(event) => setConfigFile(event.target.files?.[0] || null)}
                />
              </div>
              <Button type="button" onClick={handleSaveConfig} disabled={saving || !configFile}>
                {saving ? "Đang lưu..." : "Cập nhật"}
              </Button>
              {project.sonar_config?.updated_at && (
                <p className="text-xs text-muted-foreground">
                  Lần cập nhật gần nhất: {new Date(project.sonar_config.updated_at).toLocaleString()}
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
