import React from "react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Download, ChevronDown, FileText, FileSpreadsheet, Loader2 } from "lucide-react"

export interface ExportDropdownProps {
  onExportCsv: () => void | Promise<void>
  onExportXlsx: () => void | Promise<void>
  disabled?: boolean
  exporting?: boolean
  className?: string
}

export function ExportDropdown({
  onExportCsv,
  onExportXlsx,
  disabled = false,
  exporting = false,
  className = "",
}: ExportDropdownProps) {
  return (
    <div className={`inline-flex items-center rounded-md border shadow-xs bg-background ${className}`}>
      <Button
        variant="ghost"
        aria-label="Export CSV"
        className="gap-2 h-9 px-3 rounded-r-none border-0 hover:bg-muted font-medium text-xs sm:text-sm"
        onClick={onExportCsv}
        disabled={disabled || exporting}
      >
        {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
        <span className="hidden sm:inline">{exporting ? "Exporting…" : "Export CSV"}</span>
      </Button>
      <div className="h-5 w-px bg-border my-auto" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Export options"
            className="h-9 w-8 px-0 rounded-l-none border-0 hover:bg-muted"
            disabled={disabled || exporting}
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuItem onClick={onExportCsv} disabled={disabled || exporting}>
            <FileText className="w-4 h-4 mr-2" />
            <span>Export CSV</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onExportXlsx} disabled={disabled || exporting}>
            <FileSpreadsheet className="w-4 h-4 mr-2" />
            <span>Export Excel (XLSX)</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
