import QRCode from "qrcode"

/**
 * Generates a QR code as a data URL (base64 PNG) from scan data.
 * The QR code encodes a URL pointing to the scan detail page,
 * so scanning with a phone navigates directly to the banana's tracking page.
 */
export async function generateQRCodeDataUrl(scanData: {
  id: string
  cultivar: string
  ripeness: string
  dateTime: string
  fingerCount: number
  source?: string
  operator: string
  intakeId?: string
}): Promise<string> {
  // Encode a URL that links to the scan detail page
  const baseUrl = window.location.origin
  const trackingUrl = `${baseUrl}/track/${scanData.id}`

  return QRCode.toDataURL(trackingUrl, {
    width: 256,
    margin: 2,
    color: {
      dark: "#000000",
      light: "#ffffff",
    },
    errorCorrectionLevel: "M",
  })
}

/**
 * Prints a compact QR tag (~1.5" × 1.5") designed to be attached
 * directly to a banana hand. Includes only the QR code, scan ID,
 * cultivar, and ripeness for minimal size.
 */
export function printQRTag(scan: {
  id: string
  qrCode?: string
  cultivar: string
  ripeness: string
  dateTime: string
}) {
  if (!scan.qrCode) return

  const dateStr = new Date(scan.dateTime).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  })

  const printWindow = window.open("", "_blank", "width=300,height=400")
  if (!printWindow) return

  printWindow.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>QR Tag — ${scan.id}</title>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700&display=swap');

        * { margin: 0; padding: 0; box-sizing: border-box; }

        @page {
          size: auto;
          margin: 5mm;
        }

        body {
          font-family: 'Inter', system-ui, -apple-system, sans-serif;
          display: flex;
          justify-content: center;
          align-items: flex-start;
          padding: 0;
          background: #fff;
        }

        .tag {
          width: 40mm;
          border: 0.5mm solid #000;
          border-radius: 2mm;
          padding: 2mm;
          text-align: center;
          page-break-inside: avoid;
        }

        .tag-brand {
          font-size: 6pt;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: #333;
          margin-bottom: 1mm;
        }

        .qr-img {
          width: 30mm;
          height: 30mm;
          display: block;
          margin: 0 auto;
        }

        .tag-id {
          font-family: 'Courier New', monospace;
          font-size: 6pt;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-top: 1mm;
          color: #111;
        }

        .tag-info {
          font-size: 6pt;
          font-weight: 600;
          color: #333;
          margin-top: 0.5mm;
        }


        .tag-date {
          font-size: 5pt;
          color: #888;
          margin-top: 0.5mm;
        }

        @media print {
          body { padding: 0; }
          .tag { border: 0.5mm solid #000; }
        }
      </style>
    </head>
    <body>
      <div class="tag">
        <div class="tag-brand">BananaVision</div>
        <img class="qr-img" src="${scan.qrCode}" alt="QR" />
        <div class="tag-id">${scan.id}</div>
        <div class="tag-info">${scan.cultivar} · ${scan.ripeness}</div>
        <div class="tag-date">${dateStr}</div>
      </div>
    </body>
    </html>
  `)

  printWindow.document.close()

  printWindow.onload = () => {
    setTimeout(() => {
      printWindow.print()
    }, 300)
  }
}
