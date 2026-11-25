/**
 * Excel (.xlsx) and PDF (.pdf) export helpers shared by the client-side exports
 * (Quality Control, Delivery Intakes, Activity Log).
 *
 * ExcelJS's Node stream-based writer never resolves inside the browser, so the
 * XLSX workbook is assembled directly from OpenXML parts, mirroring
 * backend/app/core/xlsx.py: text wrapping, auto-calculated column widths,
 * dynamic row heights, typed cells and inlineStr escaping that keeps
 * user-authored "=" / "+" / "@" text from being interpreted as formulas.
 */

import type { ScanResult } from "@/types"
import { fingerCountIsEstimate, fingerCountText } from "./estimates"
import { remainingStockDays } from "./inventoryRisk"
import { formatManilaDateTime } from "./manilaTime"
import { buildPdfBlob, type PdfExportOptions } from "./pdfExport"
import { liveShelfLife } from "./shelfLifeWindow"
import { closedStockSpoilageLabel, formatSpoilageDays } from "./spoilageDisplay"

const NS_SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

export interface StyledNumericCell {
  value: number
  display: string
  style: number
}

export type ExportCellValue = string | number | boolean | null | undefined | StyledNumericCell

/** Deterministic short scan code derived from scan.id, e.g. "SCAN-DEB78E6B". */
export function formatScanRef(scanId: string | null | undefined): string {
  if (!scanId) return ""
  const cleaned = scanId.trim().replace(/-/g, "")
  return cleaned ? `SCAN-${cleaned.slice(0, 8).toUpperCase()}` : ""
}

/** Deterministic short intake code derived from intake.id, e.g. "INT-A1B2C3D4". */
export function formatIntakeRef(intakeId: string | null | undefined): string {
  if (!intakeId) return ""
  const cleaned = intakeId.trim().replace(/-/g, "")
  return cleaned ? `INT-${cleaned.slice(0, 8).toUpperCase()}` : ""
}

function fixed1Cell(value: number | null | undefined): ExportCellValue {
  if (value === null || value === undefined || !Number.isFinite(value)) return ""
  const display = value.toFixed(1)
  return { value: Number(display), display, style: 3 }
}

/** Canonical human-friendly scan export columns shared with backend exports. */
export const SCAN_EXPORT_HEADERS: string[] = [
  "Scan Ref",
  "Date & Time",
  "Source / Supplier",
  "Cultivar",
  "Ripeness",
  "Est. Fingers",
  "Est. Shelf Life (Original)",
  "Est. Time Left / Freshness",
  "Inventory Status",
  "Review Status",
  "Confidence (%)",
  "Temperature (°C)",
  "Humidity (%)",
  "Operator",
]

function formatScanFreshness(scan: ScanResult, now: number): string {
  const status = scan.inventoryStatus || "In Stock"
  if (closedStockSpoilageLabel(status) !== null) return status
  const live = liveShelfLife(scan.shelfLifeWindow, now)
  if (live) {
    if (live.state === "final_day") return "Final day"
    if (live.state === "expired") {
      return `Overdue by ${live.daysPast} ${live.daysPast === 1 ? "day" : "days"}`
    }
    return live.remainingMin === live.remainingMax
      ? `${live.remainingMax} ${live.remainingMax === 1 ? "day" : "days"} left`
      : `${live.remainingMin}–${live.remainingMax} days left`
  }
  const remaining = remainingStockDays(scan, now)
  if (remaining !== null) {
    if (remaining < 0) {
      const daysPast = Math.max(1, Math.ceil(-remaining))
      return `Overdue by ${daysPast} ${daysPast === 1 ? "day" : "days"}`
    }
    const label = formatSpoilageDays(remaining)
    return label === "Unknown" ? "" : `${label} left`
  }
  return ""
}

/** Formats one scan into the 14 human-friendly cells matching SCAN_EXPORT_HEADERS. */
export function formatScanExportRow(scan: ScanResult, now: number): ExportCellValue[] {
  const shelfLife = formatSpoilageDays(scan.spoilageDays)
  const hasFingerCount = typeof scan.fingerCount === "number"
    && Number.isInteger(scan.fingerCount) && scan.fingerCount >= 0
  return [
    formatScanRef(scan.id),
    formatManilaDateTime(scan.dateTime),
    scan.source?.trim() || "",
    scan.cultivar && scan.cultivar !== "Unknown" ? scan.cultivar : "",
    scan.ripeness && scan.ripeness !== "Unknown" ? scan.ripeness : "",
    hasFingerCount ? fingerCountText(scan.fingerCount, fingerCountIsEstimate(scan)) : "",
    shelfLife === "Unknown" ? "" : shelfLife,
    formatScanFreshness(scan, now),
    scan.inventoryStatus || "In Stock",
    scan.flagged ? "Needs Review" : "Approved",
    fixed1Cell(scan.confidence),
    fixed1Cell(scan.temperature),
    fixed1Cell(scan.humidity),
    scan.operator || "",
  ]
}

// ── In-browser XLSX builder ──────────────────────────────────────────────────

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

const encoder = new TextEncoder()

interface ZipEntry { name: string, data: string }

/** Builds a valid ZIP archive with stored (uncompressed) UTF-8 entries. */
function buildZip(entries: ZipEntry[]): Uint8Array {
  const u16 = (value: number): Uint8Array => new Uint8Array([value & 0xff, (value >>> 8) & 0xff])
  const u32 = (value: number): Uint8Array => new Uint8Array([
    value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff,
  ])

  const parts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  let offset = 0
  for (const { name, data } of entries) {
    const nameBytes = encoder.encode(name)
    const dataBytes = encoder.encode(data)
    const crc = crc32(dataBytes)
    const local = [
      u32(0x04034b50), u16(20), u16(0x0800), u16(0), u16(0), u16(0),
      u32(crc), u32(dataBytes.length), u32(dataBytes.length),
      u16(nameBytes.length), u16(0), nameBytes,
    ]
    const headerLength = local.reduce((size, part) => size + part.length, 0)
    const central = [
      u32(0x02014b50), u16(20), u16(20), u16(0x0800), u16(0), u16(0), u16(0),
      u32(crc), u32(dataBytes.length), u32(dataBytes.length),
      u16(nameBytes.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset), nameBytes,
    ]
    parts.push(...local, dataBytes)
    centralParts.push(...central)
    offset += headerLength + dataBytes.length
  }

  const centralSize = centralParts.reduce((size, part) => size + part.length, 0)
  const eocd = [
    u32(0x06054b50), u16(0), u16(0),
    u16(entries.length), u16(entries.length),
    u32(centralSize), u32(offset), u16(0),
  ]

  const total = parts.reduce((size, part) => size + part.length, 0) +
    centralSize + eocd.reduce((size, part) => size + part.length, 0)
  const archive = new Uint8Array(total)
  let cursor = 0
  for (const part of [...parts, ...centralParts, ...eocd]) {
    archive.set(part, cursor)
    cursor += part.length
  }
  return archive
}

/** Applies the Excel sheet-name rules: 31 characters, no reserved characters. */
function safeSheetName(name: string): string {
  const cleaned = name.replace(/[:\\/?*[\]]/g, " ").trim() || "Sheet1"
  return cleaned.slice(0, 31)
}

function colLetter(colIndex: number): string {
  let index = colIndex
  let result = ""
  while (index > 0) {
    const remainder = (index - 1) % 26
    result = String.fromCharCode(65 + remainder) + result
    index = Math.floor((index - 1) / 26)
  }
  return result
}

// Control characters invalid in XML 1.0 except tab, CR, LF.
// eslint-disable-next-line no-control-regex
const INVALID_XML_CHARS = /[\x00-\x08\x0b\x0c\x0e-\x1f]/g

function escapeXml(value: string): string {
  return value
    .replace(INVALID_XML_CHARS, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;")
}

/** Approximate visible cell width, counting wide CJK characters as two. */
function displayWidth(value: string): number {
  let width = 0
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0
    const wide =
      (code >= 0x1100 && code <= 0x115f) ||
      (code >= 0x2e80 && code <= 0xa4cf) ||
      (code >= 0xac00 && code <= 0xd7a3) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xfe10 && code <= 0xfe19) ||
      (code >= 0xfe30 && code <= 0xfe6f) ||
      (code >= 0xff00 && code <= 0xff60) ||
      (code >= 0xffe0 && code <= 0xffe6) ||
      (code >= 0x1f300 && code <= 0x1faff)
    width += wide ? 2 : 1
  }
  return width
}

/** Estimate how many wrapped lines a value occupies in a column. */
function wrappedLineCount(value: string, columnWidth: number): number {
  const available = Math.max(1, Math.floor(columnWidth) - 2)
  return value.split("\n").reduce(
    (lines, line) => lines + Math.max(1, Math.ceil(displayWidth(line) / available)),
    0,
  )
}

type XlsxCell =
  | { value: string, display: string, type: "s", style?: number }
  | { value: number | string, display: string, type: "n", style?: number }
  | { value: string, display: string, type: "b", style?: number }
  | null

function isStyledCell(raw: ExportCellValue): raw is StyledNumericCell {
  return typeof raw === "object" && raw !== null && "display" in raw && "value" in raw
}

function cellDisplayText(raw: ExportCellValue): string {
  if (raw === null || raw === undefined || raw === "") return ""
  if (isStyledCell(raw)) return raw.display
  return `${raw}`
}

function cellOf(raw: ExportCellValue): XlsxCell {
  if (raw === null || raw === undefined || raw === "") return null
  if (isStyledCell(raw)) {
    if (!Number.isFinite(raw.value)) return { value: raw.display, display: raw.display, type: "s" }
    return { value: raw.display, display: raw.display, type: "n", style: raw.style }
  }
  if (typeof raw === "string") return { value: raw, display: raw, type: "s" }
  if (typeof raw === "boolean") {
    const val = raw ? "1" : "0"
    return { value: val, display: val, type: "b" }
  }
  if (!Number.isFinite(raw)) return { value: `${raw}`, display: `${raw}`, type: "s" }
  const text = raw.toString()
  return { value: text, display: text, type: "n" }
}

function renderCell(cell: XlsxCell, ref: string, defaultStyle: number): string {
  if (!cell) return `<c r="${ref}" s="${defaultStyle}"/>`
  const style = cell.style ?? defaultStyle
  if (cell.type === "s") {
    return `<c r="${ref}" t="inlineStr" s="${style}"><is><t xml:space="preserve">${escapeXml(cell.value)}</t></is></c>`
  }
  return `<c r="${ref}" t="${cell.type}" s="${style}"><v>${escapeXml(String(cell.value))}</v></c>`
}

/**
 * Generates an OpenXML SpreadsheetML workbook with the styling contract shared
 * with the backend exports: white data style with top-aligned wrapping (cellXfs
 * index 1) from which Excel derives implicit column widths and dynamic row
 * heights, bold wrapped headers (index 2), 1-decimal numeric style (index 3),
 * and typed number/boolean/string cells.
 */
export function buildXlsxXml(headers: string[], rows: ExportCellValue[][]): string {
  const numCols = headers.length

  const columnWidths: number[] = []
  for (let c = 0; c < numCols; c++) {
    let maxWidth = displayWidth(headers[c])
    for (const row of rows) {
      const text = cellDisplayText(row[c])
      if (!text) continue
      for (const line of text.split("\n")) {
        maxWidth = Math.max(maxWidth, displayWidth(line))
      }
    }
    columnWidths.push(Math.min(81, Math.max(12, maxWidth + 3)))
  }
  const colsXml = columnWidths.map((width, i) =>
    `<col min="${i + 1}" max="${i + 1}" width="${width.toFixed(1)}" customWidth="1"/>`).join("")

  let headerLines = 1
  const headerCells = headers
    .map((header, i) => {
      headerLines = Math.max(headerLines, wrappedLineCount(header, columnWidths[i]))
      return renderCell(cellOf(header), `${colLetter(i + 1)}1`, 2)
    })
    .join("")
  const headerHeight = Math.min(409, Math.max(24, headerLines * 18))
  const rowXmls = [`<row r="1" ht="${headerHeight.toFixed(1)}" customHeight="1">${headerCells}</row>`]

  for (let r = 0; r < rows.length; r++) {
    const ref = r + 2
    let visualLines = 1
    const cells = headers.map((_, c) => {
      const cell = cellOf(rows[r][c])
      if (cell) visualLines = Math.max(visualLines, wrappedLineCount(cell.display, columnWidths[c]))
      return renderCell(cell, `${colLetter(c + 1)}${ref}`, 1)
    }).join("")
    const height = Math.min(409, Math.max(16, visualLines * 18))
    rowXmls.push(`<row r="${ref}" ht="${height.toFixed(1)}" customHeight="1">${cells}</row>`)
  }

  return (
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n` +
    `<worksheet xmlns="${NS_SPREADSHEET}">` +
    `<cols>${colsXml}</cols>` +
    `<sheetData>${rowXmls.join("")}</sheetData>` +
    `</worksheet>`
  )
}

/** Packages the OpenXML parts into a downloadable .xlsx blob. */
function buildXlsx(name: string, sheetXml: string): Blob {
  const sheetName = safeSheetName(name)
  const files: [string, string][] = [
    ["[Content_Types].xml", (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
      '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
      '</Types>'
    )],
    ["_rels/.rels", (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
      '</Relationships>'
    )],
    ["xl/workbook.xml", (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
      `<sheets><sheet name="${escapeXml(sheetName)}" sheetId="1" r:id="rId1"/></sheets>` +
      '</workbook>'
    )],
    ["xl/_rels/workbook.xml.rels", (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' +
      '</Relationships>'
    )],
    ["xl/styles.xml", (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
      '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
      '<numFmts count="1"><numFmt numFmtId="164" formatCode="0.0"/></numFmts>' +
      '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>' +
      '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
      '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
      '<cellXfs count="4">' +
      '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
      '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>' +
      '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>' +
      '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>' +
      '</cellXfs>' +
      '</styleSheet>'
    )],
    ["xl/worksheets/sheet1.xml", sheetXml],
  ]
  const archive = buildZip(files.map(([name, data]) => ({ name, data })))
  return new Blob([new Uint8Array(archive)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  })
}

function triggerDownload(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.setAttribute("download", filename)
  link.style.visibility = "hidden"
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Downloads data as a styled XLSX spreadsheet with auto-fitted columns and text wrapping.
 */
export async function downloadXlsx(
  filename: string,
  sheetName: string,
  headers: string[],
  rows: ExportCellValue[][],
): Promise<void> {
  const sheetXml = buildXlsxXml(headers, rows)
  const blob = buildXlsx(sheetName, sheetXml)
  triggerDownload(filename.endsWith(".xlsx") ? filename : `${filename}.xlsx`, blob)
}

/**
 * Downloads data as a formatted tabular PDF report with Asia/Manila export timestamp.
 */
export async function downloadPdf(
  filename: string,
  headers: string[],
  rows: ExportCellValue[][],
  options: PdfExportOptions,
): Promise<void> {
  const blob = buildPdfBlob(headers, rows, options)
  triggerDownload(filename.endsWith(".pdf") ? filename : `${filename}.pdf`, blob)
}
