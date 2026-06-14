import React, { useState, useEffect } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Button } from "@/components/ui/button"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { ChevronsLeft, ChevronsRight } from "lucide-react"

export interface ColumnDef<T> {
  header: React.ReactNode
  cell: (row: T, index: number) => React.ReactNode
  className?: string
  headerClassName?: string
  stopPropagation?: boolean
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
  }
  onRowClick?: (row: T) => void
  rowKey: (row: T) => string | number
  className?: string
  rowClassName?: (row: T, index: number) => string
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
}: AppDataTableProps<T>) {
  const [page, setPage] = useState(1)

  // Reset page when data reference changes significantly (e.g. new filters applied outside)
  useEffect(() => {
    setPage(1)
  }, [data])

  const pageSize = pagination?.pageSize || data.length || 1
  const totalPages = Math.max(1, Math.ceil(data.length / pageSize))
  const paginatedData = pagination ? data.slice((page - 1) * pageSize, page * pageSize) : data

  return (
    <div className={`rounded-xl sm:rounded-2xl border bg-card text-card-foreground shadow-sm overflow-hidden ${className || ''}`}>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            {columns.map((col, i) => (
              <TableHead key={i} className={`font-semibold ${col.headerClassName || col.className || ''}`}>
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.length === 0 ? (
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
                  className={`animate-fade-in-row ${isClickable ? 'cursor-pointer hover:bg-muted/50 transition-colors' : ''} ${rowClassName ? rowClassName(row, i) : ''}`}
                  style={{ animationDelay: `${(i % pageSize) * 30}ms` }}
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
      {pagination && data.length > pageSize && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t bg-muted/20">
          <p className="text-xs sm:text-sm text-muted-foreground">
            Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, data.length)} of {data.length}
          </p>
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
        </div>
      )}
    </div>
  )
}
