"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { api, ForkResolverRepo } from "@/lib/api";

const PAGE_SIZE = 20;

export default function ForkResolverPage() {
  const [repos, setRepos] = useState<ForkResolverRepo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [githubToken, setGithubToken] = useState("");
  const [enqueueAfterDiscover, setEnqueueAfterDiscover] = useState(false);
  const [forceDiscover, setForceDiscover] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<ForkResolverRepo | null>(null);

  const loadRepos = useCallback(async () => {
    setIsLoading(true);
    setMessage(null);
    try {
      const items = await api.listForkResolverRepos(200);
      setRepos(items);
    } catch (err: any) {
      setMessage(err.message ?? "Không thể tải danh sách repo cần xử lý.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRepos().catch(() => null);
  }, [loadRepos]);

  const columns = useMemo<ColumnDef<ForkResolverRepo>[]>(() => {
    return [
      {
        accessorKey: "repo_slug",
        header: "Repo",
        cell: ({ row }) => (
          <a
            href={`https://github.com/${row.original.repo_slug}`}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-blue-600 underline"
          >
            {row.original.repo_slug}
          </a>
        ),
      },
      {
        accessorKey: "count",
        header: "Failed commits",
      },
      {
        id: "sample",
        header: "Commit sample",
        cell: ({ row }) => (
          <span className="font-mono text-xs">
            {(row.original.commit_shas || []).slice(0, 3).join(", ")}
            {row.original.commit_shas.length > 3 ? "…" : ""}
          </span>
        ),
      },
      {
        accessorKey: "updated_at",
        header: "Cập nhật",
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">
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
          <Button variant="ghost" size="sm" onClick={() => setSelectedRepo(row.original)}>
            Chọn
          </Button>
        ),
      },
    ];
  }, []);

  const handleDiscover = async () => {
    if (!selectedRepo) return;
    setIsLoading(true);
    setMessage(null);
    try {
      await api.discoverForkResolverRepo(selectedRepo.repo_slug, {
        enqueue: enqueueAfterDiscover,
        force: forceDiscover,
        github_token: githubToken || undefined,
      });
      setMessage(`Đã chạy tìm kiếm forks cho ${selectedRepo.repo_slug}`);
      setSelectedRepo(null);
      await loadRepos();
    } catch (err: any) {
      setMessage(err.message ?? "Không thể chạy tìm kiếm forks.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Repos cần tìm fork</CardTitle>
        </CardHeader>
        <CardContent>
          {message && <p className="mb-3 text-sm text-slate-700">{message}</p>}
          <DataTable
            columns={columns}
            data={repos}
            isLoading={isLoading}
            pageSize={PAGE_SIZE}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Xử lý repo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedRepo ? (
            <>
              <div className="rounded-md border p-3 text-sm space-y-1">
                <p>
                  Repo:{" "}
                  <a
                    href={`https://github.com/${selectedRepo.repo_slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 underline"
                  >
                    {selectedRepo.repo_slug}
                  </a>
                </p>
                <p>Failed commits: {selectedRepo.count}</p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={forceDiscover}
                  onChange={(event) => setForceDiscover(event.target.checked)}
                />
                Force chạy lại fork search
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={enqueueAfterDiscover}
                  onChange={(event) => setEnqueueAfterDiscover(event.target.checked)}
                />
                Enqueue scan job nếu tìm thấy
              </label>
              <Input
                placeholder="GitHub tokens (comma/newline separated)"
                value={githubToken}
                onChange={(event) => setGithubToken(event.target.value)}
              />
              <Button onClick={handleDiscover} disabled={isLoading}>
                {isLoading ? "Đang chạy..." : "Tìm commit trong forks"}
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Chọn một repo từ bảng để chạy fork discovery.
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
