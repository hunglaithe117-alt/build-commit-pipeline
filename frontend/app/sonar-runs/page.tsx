"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

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
            <div className="text-xs text-slate-600">
              {Object.entries(metrics).map(([k, v]) => (
                <div key={k}>
                  <span className="font-medium">{k}</span>: {v}
                </div>
              ))}
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
