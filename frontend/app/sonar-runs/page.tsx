"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import JSONTree from "react-json-tree";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { api, ScanResult } from "@/lib/api";

export default function ScanResultsPage() {
  const [results, setResults] = useState<ScanResult[]>([]);
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
      const res = await api.listScanResultsPaginated(
        params.pageIndex + 1,
        params.pageSize,
        sortBy,
        sortDir,
        params.filters
      );
      setResults(res.items);
      setTotal(res.total || 0);
      setPageIndex(params.pageIndex);
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    handleServerChange({ pageIndex: 0, pageSize: 25, sorting: null, filters: {} }).catch(() => null);
  }, []);

  const columns = useMemo<ColumnDef<ScanResult>[]>(() => {
    return [
      {
        accessorKey: "sonar_project_key",
        header: "Component",
      },
      {
        accessorKey: "sonar_analysis_id",
        header: "Analysis ID",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.sonar_analysis_id}</span>,
      },
      {
        id: "metrics",
        header: "Metrics",
        cell: ({ row }) => {
          const metrics = row.original.metrics || {};
          return (
            <div className="max-h-56 overflow-auto rounded-md border bg-slate-50 p-2 text-xs">
              <JSONTree
                data={metrics as Record<string, unknown>}
                hideRoot
                shouldExpandNodeInitially={(_, __, level) => level < 1}
                theme={{
                  base00: "#ffffff",
                  base01: "#f5f5f5",
                  base02: "#f0f0f0",
                  base03: "#555555",
                  base04: "#777777",
                  base05: "#111111",
                  base06: "#111111",
                  base07: "#111111",
                  base08: "#c92c2c",
                  base09: "#1d7af2",
                  base0A: "#f7b731",
                  base0B: "#1b7c3c",
                  base0C: "#0aa0d2",
                  base0D: "#2e6fd1",
                  base0E: "#8e44ad",
                  base0F: "#ad6800",
                }}
              />
            </div>
          );
        },
      },
      {
        accessorKey: "created_at",
        header: "Thời gian",
        cell: ({ row }) => (
          <span className="text-xs">
            {new Date(row.original.created_at).toLocaleString()}
          </span>
        ),
      },
    ];
  }, []);

  return (
    <section>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Scan results</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
          <DataTable
            columns={columns}
            data={results}
            serverPagination={{
              pageIndex,
              pageSize: 25,
              total,
              onPageChange: (next) => setPageIndex(next),
            }}
            serverOnChange={handleServerChange}
          />
        </CardContent>
      </Card>
    </section>
  );
}
