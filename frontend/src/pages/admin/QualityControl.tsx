import { useState, useMemo } from "react"
import { useApp } from "@/context/AppContext"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { StatsCard } from "@/components/shared/stats-card"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { ShieldCheck, Flag, MessageSquare, Edit, AlertTriangle, CheckCircle, Banana, ChevronsLeft, ChevronsRight, Download, Filter, Thermometer, Droplets } from "lucide-react"
import { toast } from "sonner"
import { getSpoilageDays } from "@/lib/utils"
import type { ScanResult, Cultivar, Ripeness } from "@/types"
import { ChangePreview } from "@/components/ChangePreview"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ActionButton } from "@/components/shared/action-button"
import { AppTableFilters } from "@/components/AppTableFilters"
import { AppPageHeader } from "@/components/AppPageHeader"
import { StatusBadge } from "@/components/shared/status-badge"

const PAGE_SIZE = 15

export default function QualityControl() {
  const { scans, flagScan, addScanNote, getScanNotes, updateScanData, config } = useApp()
  const [selectedScan, setSelectedScan] = useState<ScanResult | null>(null)
  const [noteText, setNoteText] = useState("")
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState<Partial<Omit<ScanResult, 'fingerCount' | 'spoilageDays'> & { fingerCount: number | string; spoilageDays: string }>>({})
  const [filterView, setFilterView] = useState<"all" | "flagged" | "low-confidence" | "overridden">("all")
  const [sourceFilter, setSourceFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [page, setPage] = useState(1)

  const activeSources = useMemo(() => {
    return Array.from(new Set(scans.map(s => s.source).filter(Boolean)))
  }, [scans])

  const filteredScans = useMemo(() => {
    let filtered = scans
    
    if (filterView === "flagged") {
      filtered = filtered.filter(s => s.flagged)
    } else if (filterView === "low-confidence") {
      filtered = filtered.filter(s => s.confidence < config.confidenceThreshold)
    } else if (filterView === "overridden") {
      filtered = filtered.filter(s => s.isOverridden)
    }
    
    if (sourceFilter !== "all") {
      filtered = filtered.filter(s => s.source === sourceFilter)
    }
    
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter(s =>
        s.operator.toLowerCase().includes(q) ||
        s.cultivar.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q) ||
        (s.source && s.source.toLowerCase().includes(q))
      )
    }
    
    return filtered.sort((a, b) => new Date(b.dateTime).getTime() - new Date(a.dateTime).getTime())
  }, [scans, filterView, sourceFilter, searchQuery, config.confidenceThreshold])

  const totalPages = Math.max(1, Math.ceil(filteredScans.length / PAGE_SIZE))
  const paginated = filteredScans.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleFlag = (scan: ScanResult) => {
    const isNowFlagged = !scan.flagged
    flagScan(scan.id, isNowFlagged)
    
    // Update local modal state so the UI reflects the change immediately
    if (selectedScan?.id === scan.id) {
      setSelectedScan(prev => prev ? { ...prev, flagged: isNowFlagged } : null)
    }
    
    toast.success(isNowFlagged ? "Scan flagged for review" : "Flag removed")
  }

  const handleAddNote = () => {
    if (selectedScan && noteText.trim()) {
      addScanNote(selectedScan.id, noteText.trim())
      setNoteText("")
      toast.success("Note added successfully")
    }
  }

  const handleSaveEdit = () => {
    if (selectedScan && editData) {
      const saveData = {
        ...editData,
        fingerCount: typeof editData.fingerCount === 'string' ? (parseInt(editData.fingerCount) || 0) : editData.fingerCount,
        spoilageDays: editData.spoilageDays,
        isOverridden: true,
        originalAiResult: selectedScan.originalAiResult || {
          cultivar: selectedScan.cultivar,
          ripeness: selectedScan.ripeness,
          fingerCount: selectedScan.fingerCount,
          spoilageDays: selectedScan.spoilageDays,
        }
      } as Partial<ScanResult>
      updateScanData(selectedScan.id, saveData)
      setEditMode(false)
      setSelectedScan(null)
      setEditData({})
      toast.success("Scan data updated successfully")
    }
  }

  const openScanDetails = (scan: ScanResult) => {
    setSelectedScan(scan)
    setEditMode(false)
    setEditData({
      cultivar: scan.cultivar,
      ripeness: scan.ripeness,
      spoilageDays: scan.spoilageDays,
      fingerCount: scan.fingerCount,
    })
  }

  const lowConfidenceCount = scans.filter(s => s.confidence < config.confidenceThreshold).length
  const flaggedCount = scans.filter(s => s.flagged).length
  const sourcesWithIssues = useMemo(() => {
    const sourceNames = new Set(
      scans
        .filter(s => s.flagged || s.confidence < config.confidenceThreshold)
        .map(s => s.source)
        .filter(Boolean)
    )
    return sourceNames.size
  }, [scans, config.confidenceThreshold])

  const exportToCSV = () => {
    const headers = ["Scan ID", "Date/Time", "Operator", "Cultivar", "Ripeness", "Confidence (%)", "Temperature (°C)", "Humidity (%)", "Spoilage (days)", "Fingers", "Source", "Flagged", "Status"]
    const rows = filteredScans.map(scan => [
      scan.id,
      new Date(scan.dateTime).toLocaleString(),
      scan.operator,
      scan.cultivar,
      scan.ripeness,
      scan.confidence,
      scan.temperature || "—",
      scan.humidity || "—",
      scan.spoilageDays,
      scan.fingerCount,
      scan.source || "—",
      scan.flagged ? "Yes" : "No",
      scan.flagged ? "Flagged" : scan.confidence < config.confidenceThreshold ? "Review" : "Verified"
    ])

    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(","))
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const link = document.createElement("a")
    const url = URL.createObjectURL(blob)
    link.setAttribute("href", url)
    link.setAttribute("download", `quality-control-${new Date().toISOString().split('T')[0]}.csv`)
    link.style.visibility = "hidden"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    toast.success("Export successful", { description: `${filteredScans.length} scans exported to CSV` })
  }

  return (
    <TooltipProvider>
    <div className="space-y-4 sm:space-y-6">
      <AppPageHeader
        title="Quality Control"
        description="Review and manage scan quality"
        icon={ShieldCheck}
        action={
          <Button variant="outline" className="gap-2 w-full sm:w-auto" onClick={exportToCSV}>
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Export CSV</span>
          </Button>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatsCard
          title="Low Confidence"
          value={lowConfidenceCount}
          icon={AlertTriangle}
          iconColor="text-yellow-600"
          iconBgColor="bg-yellow-500/10"
          delay={50}
          description="Below threshold"
          trend={{ value: 5, isPositive: false }}
        />
        <StatsCard
          title="Flagged"
          value={flaggedCount}
          icon={Flag}
          iconColor="text-red-600"
          iconBgColor="bg-red-500/10"
          delay={100}
          description="Needs review"
          trend={{ value: 2, isPositive: false }}
        />
        <StatsCard
          title="Sources with Issues"
          value={sourcesWithIssues}
          icon={CheckCircle}
          iconColor="text-orange-600"
          iconBgColor="bg-orange-500/10"
          delay={150}
          description="Flagged or low confidence"
          trend={{ value: 3, isPositive: false }}
        />
      </div>

      {/* Filter Tabs */}
      <AppTableFilters 
        searchQuery={searchQuery}
        onSearchChange={(v) => { setSearchQuery(v); setPage(1) }}
        searchPlaceholder="Search by operator, cultivar, source, or ID..."
        hasActiveFilters={filterView !== "all" || sourceFilter !== "all" || searchQuery !== ""}
        onClearFilters={() => {
          setFilterView("all")
          setSourceFilter("all")
          setSearchQuery("")
          setPage(1)
        }}
      >
        <Select value={filterView} onValueChange={(v) => { setFilterView(v as typeof filterView); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-45 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Scans" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Scans</SelectItem>
            <SelectItem value="low-confidence">Low Confidence</SelectItem>
            <SelectItem value="flagged">Flagged</SelectItem>
            <SelectItem value="overridden">Overridden</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v); setPage(1) }}>
          <SelectTrigger className="w-full sm:w-47.5 h-10!">
            <Filter className="w-3.5 h-3.5 mr-1.5" />
            <SelectValue placeholder="All Sources" />
          </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              {activeSources.map((source) => (
                <SelectItem key={source as string} value={source as string}>
                  {source}
                </SelectItem>
              ))}
            </SelectContent>
        </Select>
      </AppTableFilters>

      {/* Scans Table */}
      <Card className="rounded-xl sm:rounded-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="font-semibold w-20">Image</TableHead>
              <TableHead className="font-semibold">Date/Time</TableHead>
              <TableHead className="font-semibold">Operator</TableHead>
              <TableHead className="font-semibold">Cultivar</TableHead>
              <TableHead className="font-semibold">Ripeness</TableHead>
              <TableHead className="font-semibold">Source</TableHead>
              <TableHead className="font-semibold">Confidence</TableHead>
              <TableHead className="font-semibold">IoT Data</TableHead>
              <TableHead className="font-semibold">Status</TableHead>
              <TableHead className="font-semibold text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredScans.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="h-64">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="size-12 rounded-full bg-primary/10 text-primary [&_svg]:size-6">
                        <ShieldCheck className="w-4 h-4" />
                      </EmptyMedia>
                      <EmptyTitle className="text-base sm:text-lg font-semibold mt-1">No scans to review</EmptyTitle>
                      <EmptyDescription className="text-sm sm:text-base max-w-md mx-auto text-balance">
                        {filterView !== "all" || sourceFilter !== "all"
                          ? "Try adjusting your filters"
                          : "All scans have been reviewed"
                        }
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            ) : (
              paginated.map((scan, i) => (
                <TableRow key={scan.id} className="cursor-pointer hover:bg-muted/50 animate-fade-in-row" style={{ animationDelay: `${i * 40}ms` }} onClick={() => openScanDetails(scan)}>
                  <TableCell>
                    <div className="w-14">
                      <AspectRatio ratio={1} className="rounded-lg overflow-hidden bg-muted/50 border">
                        {scan.thumbnailUrl ? (
                          <img src={scan.thumbnailUrl} alt={scan.cultivar} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Banana className="w-6 h-6 text-muted-foreground/40" />
                          </div>
                        )}
                      </AspectRatio>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {new Date(scan.dateTime).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    <br />
                    <span className="text-xs text-muted-foreground">{new Date(scan.dateTime).toLocaleTimeString()}</span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Avatar className="w-8 h-8">
                        <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                          {scan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-sm font-medium">{scan.operator}</span>
                    </div>
                  </TableCell>
                  <TableCell className="font-medium">{scan.cultivar}</TableCell>
                  <TableCell>
                    <StatusBadge type="ripeness" status={scan.ripeness} size="md" />
                  </TableCell>
                  <TableCell>
                    {scan.source ? (
                      <div className="text-xs">
                        <p className="font-medium">{scan.source}</p>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${scan.confidence < config.confidenceThreshold ? 'text-yellow-600' : ''}`}>
                        {scan.confidence}%
                      </span>
                      {scan.confidence < config.confidenceThreshold && (
                        <AlertTriangle className="w-4 h-4 text-yellow-600" />
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col text-[10px] text-muted-foreground">
                      {scan.temperature !== undefined ? (
                        <span className="flex items-center gap-1"><Thermometer className="w-3 h-3" />{scan.temperature}°C</span>
                      ) : (
                        <span className="flex items-center gap-1 opacity-50"><Thermometer className="w-3 h-3" />—</span>
                      )}
                      {scan.humidity !== undefined ? (
                        <span className="flex items-center gap-1"><Droplets className="w-3 h-3" />{scan.humidity}%</span>
                      ) : (
                        <span className="flex items-center gap-1 opacity-50"><Droplets className="w-3 h-3" />—</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {scan.isOverridden && (
                      <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs mr-1.5 mb-1.5 sm:mb-0">
                        <Edit className="w-3 h-3 mr-1" />
                        Overridden
                      </Badge>
                    )}
                    {scan.flagged ? (
                      <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs">
                        <Flag className="w-3 h-3 mr-1" />
                        Flagged
                      </Badge>
                    ) : scan.confidence < config.confidenceThreshold ? (
                      <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 text-xs">
                        <AlertTriangle className="w-3 h-3 mr-1" />
                        Review
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Verified
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <ActionButton
                      tooltip={scan.flagged ? "Unflag Issue" : "Flag for Review"}
                      icon={Flag}
                      iconClassName={scan.flagged ? 'fill-current text-red-600' : ''}
                      onClick={() => handleFlag(scan)}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {/* Pagination */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t bg-muted/20">
          <p className="text-xs sm:text-sm text-muted-foreground">
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filteredScans.length)} of {filteredScans.length}
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
      </Card>

      {/* Scan Details Dialog */}
      <Dialog open={!!selectedScan} onOpenChange={() => { setSelectedScan(null); setEditMode(false); setNoteText("") }}>
        <DialogContent className="sm:max-w-2xl rounded-2xl max-h-[90vh] flex flex-col p-0 gap-0">
          <DialogHeader className="px-6 pt-6 pb-4 border-b">
            <div className="flex items-center justify-between pr-8">
              <DialogTitle>Scan Details</DialogTitle>
              {selectedScan && (
                <div className="flex items-center gap-2">
                  {selectedScan.isOverridden && (
                    <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs">
                      <Edit className="w-3 h-3 mr-1" />
                      Overridden
                    </Badge>
                  )}
                  <Badge variant="outline" className={`text-xs ${selectedScan.flagged ? 'bg-red-50 text-red-700 border-red-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>
                    {selectedScan.flagged ? 'Flagged' : 'Verified'}
                  </Badge>
                </div>
              )}
            </div>
            <DialogDescription>
              Review and manage scan quality
            </DialogDescription>
          </DialogHeader>

          {selectedScan && (
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
              {/* Scan Metadata Section */}
              <div className="grid grid-cols-2 gap-3 p-4 bg-muted/30 rounded-xl">
                <div>
                  <Label className="text-xs text-muted-foreground">Scan ID</Label>
                  <p className="font-mono text-sm mt-0.5">{selectedScan.id}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Date/Time</Label>
                  <p className="text-sm mt-0.5">{new Date(selectedScan.dateTime).toLocaleString()}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Operator</Label>
                  <div className="flex items-center gap-2 mt-1">
                    <Avatar className="w-7 h-7">
                      <AvatarFallback className="bg-primary/10 text-primary font-semibold text-[10px]">
                        {selectedScan.operator.split(' ').map(n => n[0]).join('').toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-sm font-medium">{selectedScan.operator}</span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Confidence</Label>
                  <div className="flex items-center gap-2 mt-1">
                    <p className={`text-sm font-semibold ${selectedScan.confidence < config.confidenceThreshold ? 'text-yellow-600' : 'text-emerald-600'}`}>
                      {selectedScan.confidence}%
                    </p>
                    {selectedScan.confidence < config.confidenceThreshold && (
                      <AlertTriangle className="w-4 h-4 text-yellow-600" />
                    )}
                  </div>
                </div>
                {selectedScan.source && (
                  <div className="col-span-2">
                    <Label className="text-xs text-muted-foreground">Source</Label>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs font-medium">
                        {selectedScan.source}
                      </Badge>
                    </div>
                  </div>
                )}
              </div>

              {/* Camera Views Grid with Bounding Boxes */}
              <div>
                <Label className="text-sm font-semibold mb-3 block">Camera Views with Detection Boxes</Label>
                <div className="grid grid-cols-2 gap-3">
                  {config.cameraIds.split(",").map(s => s.trim()).filter(Boolean).map((camId, idx) => (
                    <div key={camId}>
                      <AspectRatio ratio={4/3} className="rounded-lg overflow-hidden bg-muted/50 border-2 relative group">
                        {selectedScan.thumbnailUrl ? (
                          <>
                            <img src={selectedScan.thumbnailUrl} alt={`${camId} view`} className="w-full h-full object-cover" />
                            {/* Bounding Box Overlay - simulated detection boxes */}
                            <div className="absolute inset-0 pointer-events-none">
                              {/* Main detection box */}
                              <div 
                                className="absolute border-2 border-primary rounded-sm"
                                style={{
                                  left: '15%',
                                  top: '20%',
                                  width: '70%',
                                  height: '60%',
                                }}
                              >
                                {/* Label */}
                                <div className="absolute -top-6 left-0 bg-primary text-primary-foreground px-2 py-0.5 rounded text-[10px] font-semibold">
                                  {selectedScan.cultivar} {selectedScan.confidence}%
                                </div>
                              </div>
                              
                              {/* Additional detection boxes for fingers (if applicable) */}
                              {idx === 0 && selectedScan.fingerCount > 5 && (
                                <>
                                  <div 
                                    className="absolute border border-emerald-500 rounded-sm"
                                    style={{
                                      left: '20%',
                                      top: '25%',
                                      width: '15%',
                                      height: '40%',
                                    }}
                                  />
                                  <div 
                                    className="absolute border border-emerald-500 rounded-sm"
                                    style={{
                                      left: '38%',
                                      top: '22%',
                                      width: '15%',
                                      height: '45%',
                                    }}
                                  />
                                  <div 
                                    className="absolute border border-emerald-500 rounded-sm"
                                    style={{
                                      left: '56%',
                                      top: '24%',
                                      width: '15%',
                                      height: '42%',
                                    }}
                                  />
                                </>
                              )}
                            </div>
                            {/* Confidence indicator */}
                            <div className="absolute top-2 right-2 bg-black/60 text-white px-2 py-1 rounded text-[10px] font-medium">
                              {selectedScan.confidence}%
                            </div>
                          </>
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                            <Banana className="w-12 h-12 text-muted-foreground/40" />
                            <span className="text-xs text-muted-foreground font-medium">{camId}</span>
                          </div>
                        )}
                      </AspectRatio>
                      <p className="text-xs text-muted-foreground mt-1 text-center">{camId}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-3 p-3 bg-muted/30 rounded-lg">
                  <div className="flex items-center gap-4 text-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-primary rounded-sm" />
                      <span className="text-muted-foreground">Main Detection</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border border-emerald-500 rounded-sm" />
                      <span className="text-muted-foreground">Finger Detection</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Detection Results Section */}
              <div>
                <Label className="text-sm font-semibold mb-3 block">Detection Results</Label>
                {editMode ? (
                  <div className="space-y-4 p-4 bg-muted/30 rounded-xl">
                    <h4 className="font-semibold text-sm">Edit Scan Data</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="cultivar">Cultivar</Label>
                        <Select value={editData.cultivar} onValueChange={(v) => {
                          const newCultivar = v as Cultivar;
                          setEditData({...editData, cultivar: newCultivar, spoilageDays: editData.ripeness ? getSpoilageDays(newCultivar, editData.ripeness) : editData.spoilageDays});
                        }}>
                          <SelectTrigger id="cultivar">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Lakatan">Lakatan</SelectItem>
                            <SelectItem value="Latundan">Latundan</SelectItem>
                            <SelectItem value="Saba">Saba</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="ripeness">Ripeness</Label>
                        <Select value={editData.ripeness} onValueChange={(v) => {
                          const newRipeness = v as Ripeness;
                          setEditData({...editData, ripeness: newRipeness, spoilageDays: editData.cultivar ? getSpoilageDays(editData.cultivar, newRipeness) : editData.spoilageDays});
                        }}>
                          <SelectTrigger id="ripeness">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Unripe">Unripe</SelectItem>
                            <SelectItem value="Ripe">Ripe</SelectItem>
                            <SelectItem value="Overripe">Overripe</SelectItem>
                            <SelectItem value="Rotten">Rotten</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="spoilageDays">Est. Spoilage (days)</Label>
                        <Input
                          id="spoilageDays"
                          type="text"
                          value={editData.spoilageDays}
                          readOnly
                          className="bg-muted"
                          placeholder="e.g. 2-3"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="fingers">Est. Finger Count</Label>
                        <Input
                          id="fingers"
                          type="number"
                          min="1"
                          max="30"
                          value={editData.fingerCount}
                          onChange={(e) => setEditData({...editData, fingerCount: e.target.value === '' ? '' : Math.max(0, parseInt(e.target.value) || 0)})}
                        />
                      </div>
                    </div>

                    {/* Change Preview */}
                    {editData && selectedScan && (
                      <ChangePreview 
                        originalData={selectedScan} 
                        editData={editData} 
                        className="mt-4"
                      />
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <Card className="bg-primary/5 border-primary/10">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Cultivar</Label>
                        <p className="text-lg font-bold text-primary mt-1">{selectedScan.cultivar}</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Ripeness</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.ripeness}</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Thermometer className="w-3.5 h-3.5"/> Temp</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.temperature?.toFixed(1) || '—'}°C</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Droplets className="w-3.5 h-3.5"/> Humidity</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.humidity?.toFixed(1) || '—'}%</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Est. Spoilage</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.spoilageDays} days</p>
                      </CardContent>
                    </Card>
                    <Card className="bg-muted/50">
                      <CardContent className="p-4">
                        <Label className="text-xs text-muted-foreground">Est. Fingers</Label>
                        <p className="text-lg font-bold mt-1">{selectedScan.fingerCount}</p>
                      </CardContent>
                    </Card>
                  </div>
                )}
                
                {!editMode && selectedScan.isOverridden && selectedScan.originalAiResult && (
                  <ChangePreview 
                    originalData={selectedScan.originalAiResult} 
                    editData={selectedScan} 
                  />
                )}
              </div>

              {/* Notes Section */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" />
                  Review Notes
                </Label>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {getScanNotes(selectedScan.id).map((note) => (
                    <div key={note.id} className="p-3 bg-muted/50 rounded-lg text-sm flex gap-3">
                      <Avatar className="w-7 h-7 shrink-0 mt-0.5">
                        <AvatarFallback className="bg-primary/10 text-primary font-semibold text-[10px]">
                          {note.author.split(' ').map(n => n[0]).join('').toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0">
                        <p className="text-foreground">{note.note}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {note.author} • {new Date(note.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  ))}
                  {getScanNotes(selectedScan.id).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No notes yet</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Add a note..."
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    className="resize-none"
                    rows={2}
                  />
                  <Button onClick={handleAddNote} disabled={!noteText.trim()}>
                    Add
                  </Button>
                </div>
              </div>
            </div>
          )}

          <DialogFooter className="px-6 pb-6 pt-4 border-t flex-col sm:flex-row gap-2">
            {editMode ? (
              <>
                <Button variant="outline" onClick={() => setEditMode(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSaveEdit}>
                  Save Changes
                </Button>
              </>
            ) : (
              <>
                <Button 
                  variant={selectedScan?.flagged ? "secondary" : "outline"}
                  onClick={() => selectedScan && handleFlag(selectedScan)}
                  className={selectedScan?.flagged ? "text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 border border-red-200" : ""}
                >
                  <Flag className={`w-4 h-4 mr-2 ${selectedScan?.flagged ? "fill-current" : ""}`} />
                  {selectedScan?.flagged ? 'Remove Flag' : 'Flag for Review'}
                </Button>
                <Button onClick={() => setEditMode(true)}>
                  <Edit className="w-4 h-4 mr-2" />
                  Edit Data
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
    </TooltipProvider>
  )
}
