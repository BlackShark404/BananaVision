import React, { useState, useEffect } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ChevronsLeft, ChevronsRight, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react"

export interface ColumnDef<T> {
  header: React.ReactNode
  cell: (row: T, index: number) => React.ReactNode
  className?: string
  headerClassName?: string
  stopPropagation?: boolean
  sortable?: boolean
  sortKey?: string | ((row: T) => any)
}

export interface AppDataTableProps<T> {
  data: T[]
  columns: ColumnDef<T>[]
  emptyState?: {
    icon: React.ElementType
    title: string
    description: React.ReactNode
  }
  pagination?: {
    pageSize: number
    pageSizeOptions?: number[]
    onPageSizeChange?: (pageSize: number) => void
  }
  serverState?: {
    page: number
    total: number
    sort: { key: string; direction: "asc" | "desc" }
    onPageChange: (page: number) => void
    onSortChange: (key: string, direction: "asc" | "desc") => void
  }
  onRowClick?: (row: T) => void
  rowKey: (row: T) => string | number
  className?: string
  rowClassName?: (row: T, index: number) => string
  loading?: boolean
  onSortedData?: (sorted: T[]) => void
}

export function AppDataTable<T>({
  data,
  columns,
  emptyState,
  pagination,
  onRowClick,
  rowKey,
  className,
  rowClassName,
  serverState,
  loading = false,
  onSortedData,
}: AppDataTableProps<T>) {
  const [localPage, setLocalPage] = useState(1)
  const [localSort, setSortConfig] = useState<{ columnIdx: number, direction: 'asc' | 'desc' } | null>(null)
  const page = serverState?.page ?? localPage
  const setPage = (next: number) => serverState ? serverState.onPageChange(next) : setLocalPage(next)
  const sortConfig = serverState ? { columnIdx: columns.findIndex(column => column.sortKey === serverState.sort.key), direction: serverState.sort.direction } : localSort

  const pageSize = pagination?.pageSize || data.length || 1
  const total = serverState?.total ?? data.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // Clamp page if data shrinks so the current page exceeds the new total
  useEffect(() => {
    setLocalPage((prev) => (prev > totalPages ? totalPages : prev))
  }, [totalPages])

  const handleSort = (colIdx: number, column: ColumnDef<T>) => {
    if (loading || !column.sortable) return
    if (serverState && typeof column.sortKey === "string") {
      serverState.onSortChange(column.sortKey, serverState.sort.key === column.sortKey && serverState.sort.direction === "asc" ? "desc" : "asc")
      return
    }

    setSortConfig(current => {
      if (current?.columnIdx === colIdx) {
        if (current.direction === 'asc') return { columnIdx: colIdx, direction: 'desc' }
        return null // remove sort
      }
      return { columnIdx: colIdx, direction: 'asc' }
    })
  }

  const sortedData = React.useMemo(() => {
    if (serverState || !sortConfig) return data

    const column = columns[sortConfig.columnIdx]
    if (!column || !column.sortable) return data

    return [...data].sort((a, b) => {
      let valA: any
      let valB: any
      
      if (typeof column.sortKey === 'function') {
        valA = column.sortKey(a)
        valB = column.sortKey(b)
      } else if (typeof column.sortKey === 'string') {
        valA = (a as any)[column.sortKey]
        valB = (b as any)[column.sortKey]
      } else {
        return 0
      }

      // Handle null/undefined values
      if (valA == null) valA = ''
      if (valB == null) valB = ''

      if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1
      if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1
      return 0
    })
  }, [data, sortConfig, columns, serverState])

  // Notify observers of the sorted rows. The callback must only write to a ref
  // or trigger navigation, never setState during export, so a new sorted array
  // identity cannot loop back into a render via setState.
  useEffect(() => {
    onSortedData?.(sortedData)
  }, [sortedData, onSortedData])

  const paginatedData = pagination && !serverState ? sortedData.slice((page - 1) * pageSize, page * pageSize) : sortedData

  return (
    <div aria-busy={loading || undefined} className={`rounded-xl sm:rounded-2xl border bg-card text-card-foreground shadow-sm overflow-hidden ${className || ''}`}>
      {loading && <span role="status" className="sr-only">Loading records…</span>}
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            {columns.map((col, i) => (
              <TableHead 
                key={i} 
                className={`font-semibold ${col.headerClassName || col.className || ''} ${col.sortable ? 'cursor-pointer select-none hover:text-foreground hover:bg-muted/50 transition-colors' : ''}`}
                onClick={col.sortable ? () => handleSort(i, col) : undefined}
              >
                <div className={`flex items-center gap-1.5 ${col.className?.includes('text-right') ? 'justify-end' : ''} ${col.className?.includes('text-center') ? 'justify-center' : ''}`}>
                  {col.header}
                  {col.sortable && (
                    <span className="text-muted-foreground shrink-0">
                      {sortConfig?.columnIdx === i ? (
                        sortConfig.direction === 'asc' ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 opacity-50" />
                      )}
                    </span>
                  )}
                </div>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? Array.from({ length: 5 }, (_, index) => <TableRow key={index} aria-hidden="true" className="hover:bg-transparent">
            {columns.map((col, colIdx) => <TableCell key={colIdx} className={col.className}><Skeleton className="h-5 my-2 w-full min-w-12" /></TableCell>)}
          </TableRow>) : data.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columns.length} className="h-64">
                {emptyState ? (
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <emptyState.icon className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">{emptyState.title}</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        {emptyState.description}
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    No data available
                  </div>
                )}
              </TableCell>
            </TableRow>
          ) : (
            paginatedData.map((row, i) => {
              const isClickable = !!onRowClick
              return (
                <TableRow
                  key={rowKey(row)}
                  onClick={isClickable ? () => onRowClick(row) : undefined}
                  className={`${isClickable ? 'cursor-pointer hover:bg-muted/50 transition-colors' : ''} ${rowClassName ? rowClassName(row, i) : ''}`}
                >
                  {columns.map((col, colIdx) => (
                    <TableCell 
                      key={colIdx} 
                      className={col.className} 
                      onClick={isClickable && col.stopPropagation ? (e) => e.stopPropagation() : undefined}
                    >
                      {col.cell(row, i)}
                    </TableCell>
                  ))}
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>

      {/* Pagination */}
      {!loading && pagination && (total > pageSize || (pagination.pageSizeOptions && pagination.pageSizeOptions.length > 0)) && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t bg-muted/20">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs sm:text-sm text-muted-foreground">
              Showing {total === 0 ? 0 : ((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, total)} of {total}
            </p>
            {pagination.pageSizeOptions && pagination.onPageSizeChange && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="hidden sm:inline">Rows per page:</span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(val) => pagination.onPageSizeChange?.(Number(val))}
                >
                  <SelectTrigger className="h-7 w-[72px] text-xs" aria-label="Rows per page">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {pagination.pageSizeOptions.map((opt) => (
                      <SelectItem key={opt} value={String(opt)} className="text-xs">
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          {total > pageSize && (
            <div className="flex justify-end">
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(1)}
                    disabled={page <= 1}
                    title="First page"
                  >
                    <ChevronsLeft className="w-4 h-4" />
                  </Button>
                </PaginationItem>
                <PaginationItem>
                  <PaginationPrevious 
                    href="#" 
                    onClick={(e) => { e.preventDefault(); if (page > 1) setPage(page - 1) }}
                    className={page <= 1 ? "pointer-events-none opacity-50" : ""}
                  />
                </PaginationItem>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => {
                  if (totalPages <= 7) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationLink
                          href="#"
                          onClick={(e) => { e.preventDefault(); setPage(p) }}
                          isActive={p === page}
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }
                  if (p === 1 || p === totalPages || (p >= page - 1 && p <= page + 1)) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationLink
                          href="#"
                          onClick={(e) => { e.preventDefault(); setPage(p) }}
                          isActive={p === page}
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }
                  if (p === page - 2 || p === page + 2) {
                    return (
                      <PaginationItem key={p}>
                        <PaginationEllipsis />
                      </PaginationItem>
                    )
                  }
                  return null
                })}
                <PaginationItem>
                  <PaginationNext 
                    href="#" 
                    onClick={(e) => { e.preventDefault(); if (page < totalPages) setPage(page + 1) }}
                    className={page >= totalPages ? "pointer-events-none opacity-50" : ""}
                  />
                </PaginationItem>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(totalPages)}
                    disabled={page >= totalPages}
                    title="Last page"
                  >
                    <ChevronsRight className="w-4 h-4" />
                  </Button>
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        )}
      </div>
    )}
    </div>
  )
}
