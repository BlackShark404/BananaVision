/**
 * Dependency-free in-browser tabular PDF 1.4 report generator, mirroring
 * backend/app/core/pdf.py:
 * - Landscape or portrait layout with proportional Helvetica metrics
 * - Report title, Asia/Manila export timestamp, record count, optional filter summary
 * - WinAnsi encoding (degree symbol, en dash, bullet, middle dot, accented Latin chars)
 * - Word-wrapped cells, repeated page/table headers, and 'Page X of Y' footers
 */

import { formatManilaDateTime, manilaPdfTimestamp } from "./manilaTime"

export interface PdfExportOptions {
  title: string
  filters?: string[]
  exportedAt?: number | Date
  orientation?: "auto" | "landscape" | "portrait"
}

const HELVETICA_ASCII_WIDTHS: Record<number, number> = {
  32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
  40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
  48: 556, 49: 556, 50: 556, 51: 556, 52: 556, 53: 556, 54: 556, 55: 556,
  56: 556, 57: 556, 58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556,
  64: 1015, 65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778,
  72: 722, 73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778,
  80: 667, 81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944,
  88: 667, 89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556,
  96: 333, 97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556,
  104: 556, 105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556,
  111: 556, 112: 556, 113: 556, 114: 333, 115: 500, 116: 278, 117: 556,
  118: 500, 119: 722, 120: 500, 121: 500, 122: 500, 123: 334, 124: 260,
  125: 334, 126: 584,
}

const WINANSI_EXTRA_WIDTHS: Record<number, number> = {
  0x85: 1000,
  0x91: 222,
  0x92: 222,
  0x93: 333,
  0x94: 333,
  0x95: 350,
  0x96: 556,
  0x97: 1000,
  0xb0: 400,
  0xb7: 278,
  0xd1: 722,
  0xf1: 556,
}

/** Unicode code points mapped to WinAnsi (cp1252) 0x80..0x9F slots. */
const CP1252_MAP: Record<number, number> = {
  0x20ac: 0x80, 0x201a: 0x82, 0x0192: 0x83, 0x201e: 0x84, 0x2026: 0x85,
  0x2020: 0x86, 0x2021: 0x87, 0x02c6: 0x88, 0x2030: 0x89, 0x0160: 0x8a,
  0x2039: 0x8b, 0x0152: 0x8c, 0x017d: 0x8e, 0x2018: 0x91, 0x2019: 0x92,
  0x201c: 0x93, 0x201d: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
  0x02dc: 0x98, 0x2122: 0x99, 0x0161: 0x9a, 0x203a: 0x9b, 0x0153: 0x9c,
  0x017e: 0x9e, 0x0178: 0x9f,
}

const CHAR_FALLBACKS: Record<string, string> = {
  "\u00a0": " ",
  "\u202f": " ",
  "\u2009": " ",
  "\u2192": "->",
  "\u2190": "<-",
  "\u2264": "<=",
  "\u2265": ">=",
  "\u2212": "-",
}

function toWinAnsiBytes(text: string): number[] {
  const bytes: number[] = []
  for (const ch of text) {
    const fallback = CHAR_FALLBACKS[ch]
    if (fallback !== undefined) {
      for (let i = 0; i < fallback.length; i++) bytes.push(fallback.charCodeAt(i))
      continue
    }
    const code = ch.codePointAt(0) ?? 0x3f
    if (code < 32) {
      bytes.push(32)
    } else if (code <= 126) {
      bytes.push(code)
    } else if (code >= 0xa0 && code <= 0xff) {
      bytes.push(code)
    } else if (Object.prototype.hasOwnProperty.call(CP1252_MAP, code)) {
      bytes.push(CP1252_MAP[code])
    } else {
      const decomposed = ch.normalize("NFKD").replace(/[^\x20-\x7e]/g, "")
      if (decomposed) {
        for (let i = 0; i < decomposed.length; i++) bytes.push(decomposed.charCodeAt(i))
      } else {
        bytes.push(0x3f)
      }
    }
  }
  return bytes
}

function pdfEscape(text: string): string {
  const bytes = toWinAnsiBytes(text)
  let out = ""
  for (const b of bytes) {
    if (b === 0x28 || b === 0x29 || b === 0x5c) {
      out += `\\${String.fromCharCode(b)}`
    } else if (b >= 32 && b <= 126) {
      out += String.fromCharCode(b)
    } else {
      out += `\\${b.toString(8).padStart(3, "0")}`
    }
  }
  return out
}

function measureText(text: string, fontSize: number, bold = false): number {
  const bytes = toWinAnsiBytes(text)
  let total = 0
  for (const b of bytes) {
    total += HELVETICA_ASCII_WIDTHS[b] ?? WINANSI_EXTRA_WIDTHS[b] ?? 556
  }
  return (total / 1000) * fontSize * (bold ? 1.06 : 1)
}

function wrapText(text: string, maxWidth: number, fontSize: number, bold = false): string[] {
  if (!text) return [""]
  const usable = Math.max(fontSize, maxWidth)
  const lines: string[] = []
  for (const paragraph of text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n")) {
    if (!paragraph) {
      lines.push("")
      continue
    }
    const words = paragraph.split(" ")
    let current = ""
    for (const word of words) {
      if (!word) continue
      const candidate = current ? `${current} ${word}` : word
      if (measureText(candidate, fontSize, bold) <= usable) {
        current = candidate
        continue
      }
      if (current) {
        lines.push(current)
        current = ""
      }
      if (measureText(word, fontSize, bold) <= usable) {
        current = word
        continue
      }
      let chunk = ""
      for (const ch of word) {
        const next = chunk + ch
        if (chunk && measureText(next, fontSize, bold) > usable) {
          lines.push(chunk)
          chunk = ch
        } else {
          chunk = next
        }
      }
      current = chunk
    }
    if (current) lines.push(current)
  }
  return lines.length > 0 ? lines : [""]
}

function computeColumnWidths(
  headers: string[],
  rows: string[][],
  usableWidth: number,
  headerFont: number,
  bodyFont: number,
  padX: number,
): number[] {
  const numCols = headers.length
  if (numCols === 0) return []
  const sample = rows.slice(0, 200)
  const minFloor = numCols >= 12 ? 30 : numCols >= 10 ? 32 : 44
  const maxShare = numCols >= 12 ? 0.20 : numCols >= 10 ? 0.22 : numCols <= 5 ? 0.44 : 0.30
  const maxCap = usableWidth * maxShare

  const mins: number[] = []
  const ideals: number[] = []
  for (let c = 0; c < numCols; c++) {
    const header = headers[c]
    const words = header.split(/\s+/).filter(Boolean)
    const longestWord = Math.max(...(words.length ? words : [header]).map(w => measureText(w, headerFont, true)))
    const headerFull = measureText(header, headerFont, true)
    let minW = Math.max(minFloor, Math.min(maxCap, longestWord + 2 * padX + 2))

    const widths: number[] = []
    for (const row of sample) {
      const val = row[c] ?? ""
      if (val) {
        const longestLine = Math.max(...val.split("\n").map(line => measureText(line, bodyFont)))
        widths.push(longestLine + 2 * padX + 2)
      }
    }

    let idealW = Math.max(minW, Math.min(maxCap, headerFull + 2 * padX + 2))
    if (widths.length > 0) {
      widths.sort((a, b) => a - b)
      const p90 = widths[Math.min(widths.length - 1, Math.floor(widths.length * 0.9))]
      idealW = Math.max(minW, Math.min(maxCap, Math.max(headerFull + 2 * padX + 2, p90)))
      const allSingleToken = sample.every(row => {
        const val = row[c] ?? ""
        return !val.includes(" ") && !val.includes("\n")
      })
      const maxW = widths[widths.length - 1]
      if (allSingleToken && maxW <= 76) {
        minW = Math.max(minW, Math.min(maxCap, maxW))
        idealW = Math.max(idealW, minW)
      }
    }
    mins.push(minW)
    ideals.push(idealW)
  }

  const totalIdeal = ideals.reduce((sum, w) => sum + w, 0)
  if (totalIdeal <= 0) return headers.map(() => usableWidth / numCols)
  if (totalIdeal <= usableWidth) {
    const scale = usableWidth / totalIdeal
    return ideals.map(w => w * scale)
  }

  const totalMin = mins.reduce((sum, w) => sum + w, 0)
  if (totalMin >= usableWidth) {
    const scale = usableWidth / totalMin
    return mins.map(w => w * scale)
  }

  const extraBudget = usableWidth - totalMin
  const extraDemand = ideals.reduce((sum, ideal, i) => sum + Math.max(0, ideal - mins[i]), 0)
  if (extraDemand <= 0) return mins
  return mins.map((mn, i) => mn + extraBudget * (Math.max(0, ideals[i] - mn) / extraDemand))
}

const asciiEncoder = new TextEncoder()

export type PdfCellInput = string | number | boolean | null | undefined | { display: string }

/** Builds a valid PDF 1.4 document with wrapped table rows and Asia/Manila metadata. */
export function buildPdfBytes(
  headers: string[],
  rows: PdfCellInput[][],
  options: PdfExportOptions,
): Uint8Array {
  const numCols = headers.length
  const normalizedRows: string[][] = rows.map(row =>
    headers.map((_, c) => {
      const val = row[c]
      if (val === null || val === undefined) return ""
      if (typeof val === "object" && "display" in val) return val.display
      return String(val)
    }),
  )

  const orientation = options.orientation ?? "auto"
  const useLandscape = orientation === "landscape" || (orientation === "auto" && numCols >= 5)
  const pageW = useLandscape ? 792 : 612
  const pageH = useLandscape ? 612 : 792
  const marginX = 28
  const marginTop = 30
  const marginBottom = 30
  const footerH = 16
  const usableW = pageW - 2 * marginX

  const headerFont = numCols >= 12 ? 7.0 : numCols >= 10 ? 7.5 : 8.5
  const bodyFont = numCols >= 12 ? 6.8 : numCols >= 10 ? 7.2 : 8.2
  const headerLineH = headerFont + 2.4
  const bodyLineH = bodyFont + 2.5
  const padX = numCols >= 12 ? 3 : numCols >= 10 ? 3.5 : 5
  const padY = 4

  const exportedAt = options.exportedAt ?? Date.now()
  const exportedLabel = `Exported: ${formatManilaDateTime(exportedAt)} (Asia/Manila)`
  const metaLine = `${exportedLabel}   |   Total records: ${normalizedRows.length}`
  const filterItems = (options.filters ?? []).map(item => item.trim()).filter(Boolean)
  const filterLines = filterItems.length > 0
    ? wrapText(`Filters: ${filterItems.join(" · ")}`, usableW, 8.0)
    : []

  const colWidths = computeColumnWidths(headers, normalizedRows, usableW, headerFont, bodyFont, padX)
  const wrappedHeaders = headers.map((h, c) =>
    wrapText(h, Math.max(8, colWidths[c] - 2 * padX), headerFont, true),
  )
  const headerRowH = Math.max(1, ...wrappedHeaders.map(lines => lines.length)) * headerLineH + 2 * padY

  const firstBannerH = 34 + (filterLines.length > 0 ? filterLines.length * 10.5 + 4 : 0)
  const contBannerH = 20
  const maxBodyHCont = pageH - marginTop - marginBottom - footerH - contBannerH - headerRowH
  const maxLinesPerCell = Math.max(1, Math.floor((maxBodyHCont - 2 * padY) / bodyLineH))

  interface WrappedRow {
    cells: string[][]
    height: number
    rowIdx: number
  }
  const wrappedRows: WrappedRow[] = []
  for (let rowIdx = 0; rowIdx < normalizedRows.length; rowIdx++) {
    const row = normalizedRows[rowIdx]
    const cells = row.map((val, c) => wrapText(val, Math.max(8, colWidths[c] - 2 * padX), bodyFont))
    const tallest = Math.max(1, ...cells.map(lines => lines.length))
    if (tallest <= maxLinesPerCell) {
      wrappedRows.push({ cells, height: tallest * bodyLineH + 2 * padY, rowIdx })
    } else {
      for (let offset = 0; offset < tallest; offset += maxLinesPerCell) {
        const chunk = cells.map(lines => {
          const slice = lines.slice(offset, offset + maxLinesPerCell)
          return slice.length > 0 ? slice : [""]
        })
        const chunkLines = Math.max(1, ...chunk.map(lines => lines.length))
        wrappedRows.push({ cells: chunk, height: chunkLines * bodyLineH + 2 * padY, rowIdx })
      }
    }
  }

  const pages: WrappedRow[][] = []
  let currentPage: WrappedRow[] = []
  let availableH = pageH - marginTop - marginBottom - footerH - firstBannerH - headerRowH
  let usedH = 0
  for (const item of wrappedRows) {
    if (currentPage.length > 0 && usedH + item.height > availableH) {
      pages.push(currentPage)
      currentPage = []
      availableH = maxBodyHCont
      usedH = 0
    }
    currentPage.push(item)
    usedH += item.height
  }
  pages.push(currentPage)

  const totalPages = pages.length
  const pageStreams: string[] = []
  const f = (n: number) => n.toFixed(2)

  for (let p = 0; p < totalPages; p++) {
    const pageNum = p + 1
    const pageRows = pages[p]
    const ops: string[] = []
    let y = pageH - marginTop

    if (pageNum === 1) {
      ops.push("0.08 0.12 0.18 rg")
      ops.push(`BT /F2 13.5 Tf ${f(marginX)} ${f(y - 11)} Td (${pdfEscape(options.title)}) Tj ET`)
      y -= 18
      ops.push("0.30 0.36 0.44 rg")
      ops.push(`BT /F1 8.2 Tf ${f(marginX)} ${f(y - 7)} Td (${pdfEscape(metaLine)}) Tj ET`)
      y -= 13
      if (filterLines.length > 0) {
        for (const line of filterLines) {
          ops.push(`BT /F1 7.8 Tf ${f(marginX)} ${f(y - 7)} Td (${pdfEscape(line)}) Tj ET`)
          y -= 10.5
        }
        y -= 2
      }
      ops.push("0.80 0.84 0.89 RG 0.7 w")
      ops.push(`${f(marginX)} ${f(y)} m ${f(pageW - marginX)} ${f(y)} l S`)
      y -= 6
    } else {
      ops.push("0.30 0.36 0.44 rg")
      ops.push(`BT /F2 8.5 Tf ${f(marginX)} ${f(y - 8)} Td (${pdfEscape(options.title)}) Tj ET`)
      const rightW = measureText(exportedLabel, 7.8)
      const rightX = Math.max(marginX + 120, pageW - marginX - rightW)
      ops.push(`BT /F1 7.8 Tf ${f(rightX)} ${f(y - 8)} Td (${pdfEscape(exportedLabel)}) Tj ET`)
      y -= 14
      ops.push("0.80 0.84 0.89 RG 0.6 w")
      ops.push(`${f(marginX)} ${f(y)} m ${f(pageW - marginX)} ${f(y)} l S`)
      y -= 6
    }

    const tableTop = y
    const headerBottom = y - headerRowH
    ops.push("0.93 0.95 0.97 rg")
    ops.push(`${f(marginX)} ${f(headerBottom)} ${f(usableW)} ${f(headerRowH)} re f`)

    ops.push("0.08 0.12 0.18 rg")
    let x = marginX
    for (let c = 0; c < numCols; c++) {
      let textY = tableTop - padY - headerFont + 1
      for (const line of wrappedHeaders[c]) {
        if (line) {
          ops.push(`BT /F2 ${f(headerFont)} Tf ${f(x + padX)} ${f(textY)} Td (${pdfEscape(line)}) Tj ET`)
        }
        textY -= headerLineH
      }
      x += colWidths[c]
    }

    ops.push("0.68 0.73 0.80 RG 0.6 w")
    ops.push(`${f(marginX)} ${f(headerBottom)} ${f(usableW)} ${f(headerRowH)} re S`)
    x = marginX
    for (let c = 0; c < numCols - 1; c++) {
      x += colWidths[c]
      ops.push(`${f(x)} ${f(tableTop)} m ${f(x)} ${f(headerBottom)} l S`)
    }

    y = headerBottom

    if (pageRows.length === 0) {
      const emptyH = 22
      const emptyBottom = y - emptyH
      ops.push("0.86 0.89 0.93 RG 0.5 w")
      ops.push(`${f(marginX)} ${f(emptyBottom)} ${f(usableW)} ${f(emptyH)} re S`)
      const notice = "No matching records."
      const noticeW = measureText(notice, bodyFont)
      const noticeX = marginX + Math.max(padX, (usableW - noticeW) / 2)
      ops.push("0.40 0.46 0.54 rg")
      ops.push(`BT /F1 ${f(bodyFont)} Tf ${f(noticeX)} ${f(y - 14)} Td (${pdfEscape(notice)}) Tj ET`)
    } else {
      for (const { cells, height: rowH, rowIdx } of pageRows) {
        const rowBottom = y - rowH
        if (rowIdx % 2 === 1) {
          ops.push("0.975 0.982 0.99 rg")
          ops.push(`${f(marginX)} ${f(rowBottom)} ${f(usableW)} ${f(rowH)} re f`)
        }

        ops.push("0.12 0.16 0.22 rg")
        x = marginX
        for (let c = 0; c < numCols; c++) {
          let textY = y - padY - bodyFont + 1
          for (const line of cells[c]) {
            if (line) {
              ops.push(`BT /F1 ${f(bodyFont)} Tf ${f(x + padX)} ${f(textY)} Td (${pdfEscape(line)}) Tj ET`)
            }
            textY -= bodyLineH
          }
          x += colWidths[c]
        }

        ops.push("0.86 0.89 0.93 RG 0.45 w")
        ops.push(`${f(marginX)} ${f(rowBottom)} ${f(usableW)} ${f(rowH)} re S`)
        x = marginX
        for (let c = 0; c < numCols - 1; c++) {
          x += colWidths[c]
          ops.push(`${f(x)} ${f(y)} m ${f(x)} ${f(rowBottom)} l S`)
        }
        y = rowBottom
      }
    }

    const footerY = marginBottom - 10
    ops.push("0.45 0.50 0.58 rg")
    ops.push(`BT /F1 7.5 Tf ${f(marginX)} ${f(footerY)} Td (BananaVision Export Report) Tj ET`)
    const pageLabel = `Page ${pageNum} of ${totalPages}`
    const pageLabelW = measureText(pageLabel, 7.5)
    ops.push(`BT /F1 7.5 Tf ${f(pageW - marginX - pageLabelW)} ${f(footerY)} Td (${pdfEscape(pageLabel)}) Tj ET`)

    pageStreams.push(`${ops.join("\n")}\n`)
  }

  const creationDate = manilaPdfTimestamp(exportedAt)
  const pageObjIds = Array.from({ length: totalPages }, (_, i) => 6 + i * 2)
  const kidsRef = pageObjIds.map(id => `${id} 0 R`).join(" ")

  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Kids [${kidsRef}] /Count ${totalPages} >>`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    `<< /Title (${pdfEscape(options.title)}) /Creator (BananaVision) /Producer (BananaVision Export) /CreationDate (${creationDate}) >>`,
  ]

  for (let i = 0; i < totalPages; i++) {
    const streamObjId = 7 + i * 2
    const streamStr = pageStreams[i]
    const streamLen = asciiEncoder.encode(streamStr).length
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${streamObjId} 0 R >>`,
    )
    objects.push(`<< /Length ${streamLen} >>\nstream\n${streamStr}endstream`)
  }

  const chunks: Uint8Array[] = [new Uint8Array([
    0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34, 0x0a,
    0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a,
  ])]
  let cursor = chunks[0].length
  const offsets: number[] = [0]

  for (let i = 0; i < objects.length; i++) {
    offsets.push(cursor)
    const part = asciiEncoder.encode(`${i + 1} 0 obj\n${objects[i]}\nendobj\n`)
    chunks.push(part)
    cursor += part.length
  }

  const xrefOffset = cursor
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  for (let i = 1; i <= objects.length; i++) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`
  }
  xref += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`
  chunks.push(asciiEncoder.encode(xref))

  const totalLength = chunks.reduce((sum, part) => sum + part.length, 0)
  const result = new Uint8Array(totalLength)
  let pos = 0
  for (const part of chunks) {
    result.set(part, pos)
    pos += part.length
  }
  return result
}

export function buildPdfBlob(
  headers: string[],
  rows: PdfCellInput[][],
  options: PdfExportOptions,
): Blob {
  const bytes = buildPdfBytes(headers, rows, options)
  return new Blob([new Uint8Array(bytes)], { type: "application/pdf" })
}
