"use client";

import * as React from "react";
import {
  ColumnDef,
  ColumnFiltersState,
  ColumnMeta,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  PaginationState,
  SortingState,
  Table as TanStackTable,
  useReactTable,
} from "@tanstack/react-table";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table";

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData, TValue> {
    className?: string;
    cellClassName?: string;
  }
}

type DataTableProps<TData, TValue> = {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  emptyMessage?: string;
  className?: string;
  pageSize?: number;
  renderToolbar?: (table: TanStackTable<TData>) => React.ReactNode;
  serverPagination?: {
    pageIndex: number;
    pageSize: number;
    total: number;
    onPageChange: (newPageIndex: number) => void;
  };
  serverOnChange?: (params: {
    pageIndex: number;
    pageSize: number;
    sorting?: { id: string; desc?: boolean } | null;
    filters: Record<string, any>;
  }) => void;
};

export function DataTable<TData, TValue>({
  columns,
  data,
  emptyMessage = "Không có dữ liệu.",
  className,
  pageSize = 10,
  renderToolbar,
  serverPagination,
  serverOnChange,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize,
  });

  React.useEffect(() => {
    setPagination((prev) => ({ ...prev, pageSize, pageIndex: 0 }));
  }, [pageSize, data]);

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      pagination,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  React.useEffect(() => {
    if (!serverOnChange) return;
    const sort = sorting && sorting.length > 0 ? sorting[0] : null;
    const filtersObj: Record<string, any> = {};
    columnFilters.forEach((f) => {
      filtersObj[f.id] = f.value;
    });
    serverOnChange({ pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting: sort, filters: filtersObj });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.pageIndex, pagination.pageSize, JSON.stringify(sorting), JSON.stringify(columnFilters)]);

  return (
    <div className={cn("rounded-lg border", className)}>
      {renderToolbar && <div className="border-b p-4">{renderToolbar(table)}</div>}
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                return (
                  <TableHead key={header.id} className={cn(header.column.columnDef.meta?.className)}>
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows?.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className={cn(cell.column.columnDef.meta?.cellClassName)}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center text-sm text-muted-foreground">
                {emptyMessage}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between px-4 py-3">
        {serverPagination ? (
          // Server-controlled pagination UI
          <>
            <p className="text-sm text-muted-foreground">
              Trang {serverPagination.pageIndex + 1} / {Math.max(Math.ceil(serverPagination.total / serverPagination.pageSize), 1)}
            </p>
            <div className="space-x-2">
              <Button
                variant="outline"
                size="sm"
                disabled={serverPagination.pageIndex <= 0}
                onClick={() => serverPagination.onPageChange(Math.max(0, serverPagination.pageIndex - 1))}
              >
                Trang trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(serverPagination.pageIndex + 1) * serverPagination.pageSize >= serverPagination.total}
                onClick={() => serverPagination.onPageChange(serverPagination.pageIndex + 1)}
              >
                Trang sau
              </Button>
            </div>
          </>
        ) : (
          // Client-side pagination UI
          <>
            <p className="text-sm text-muted-foreground">
              Trang {table.getState().pagination.pageIndex + 1} / {Math.max(table.getPageCount(), 1)}
            </p>
            <div className="space-x-2">
              <Button variant="outline" size="sm" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
                Trang trước
              </Button>
              <Button variant="outline" size="sm" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
                Trang sau
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
