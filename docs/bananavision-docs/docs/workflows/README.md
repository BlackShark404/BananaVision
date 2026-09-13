# BananaVision Program Workflows

This folder contains **four** separate program workflow diagrams for the BananaVision system, organized by security zones.

## Security Architecture

| Interface        | Access Level | Features  | Data Access                  |
| ---------------- | ------------ | --------- | ---------------------------- |
| **Kiosk**        | 🔴 Isolated  | Scan only | Current batch (last 5 scans) |
| **Operator Web** | 🟡 Limited   | 8 pages   | All historical (read-only)   |
| **Admin Web**    | 🟢 Full      | 14 pages  | All data (read/write/delete) |

## Files

| File                       | Description                                                   |
| -------------------------- | ------------------------------------------------------------- |
| `workflow_kiosk.drawio`    | Figure 12A: Kiosk Workflow – Isolated Scanning Terminal (NEW) |
| `workflow_operator.drawio` | Figure 12B: Operator Workflow – Web Dashboard (Read-Only)     |
| `workflow_admin.drawio`    | Figure 13: Admin Workflow – Web Dashboard (Full Access)       |
| `workflow_iot.drawio`      | Figure 14: IoT Scanning – Hardware Logic                      |

## How to Use with Figma/Lucidchart

### Option 1: Import Draw.io Files (Recommended)

1. Go to [draw.io](https://app.diagrams.net/) (free)
2. File → Open from → Device → Select the `.drawio` file
3. Edit as needed, then export to PNG/SVG/PDF

### Option 2: Import SVG to Figma

1. Open Figma
2. File → Import → Select the `.svg` file
3. The diagram will be imported as editable vector shapes

### Option 3: Import SVG to Lucidchart

1. Open Lucidchart
2. File → Import → Select the `.svg` file
3. Edit and customize as needed

### Option 4: Use Online Draw.io with GitHub Integration

1. Go to https://app.diagrams.net/
2. Connect to GitHub and open the `.drawio` files directly from your repo

---

## Workflow Summaries

### 1. Kiosk Workflow (Isolated Terminal) — NEW

- **PIN-based authentication** (4-digit, not username/password)
- Select Batch → Scan Now → View Result → Accept or Flag
- **Limited visibility:** Recent scans only (last 5 from current batch)
- **BLOCKED:** Scan Logs, Analytics, Inventory, Device Status, Profile, Admin features
- Operator Swap via PIN for shift changes

### 2. Operator Workflow (Web Dashboard — Read-Only)

- **Username/Password authentication**
- Login → Dashboard → Select Batch → Scan → View Results
- **Access to (8 pages):** Scan Logs, Analytics, Inventory, Device Status, Profile
- **Cannot delete or edit** scan records
- **Cannot access:** Kiosk mode or any Admin features

### 3. Admin Workflow (Web Dashboard — Full Access)

- **All Operator features (8 pages) PLUS:**
- User Management (Add/Edit/Disable/Delete users)
- Batch Management (Create/Edit/Close/Delete batches)
- Quality Control (Flag/Review/Override scans)
- All Scans (Search/Filter/**Delete** capability)
- Activity Log (Complete audit trail)
- System Configuration (Camera, AI, Storage, Power)
- **Optional:** Kiosk access for supervision/testing

### 4. IoT Scanning Workflow (Hardware)

- Mini PC / Raspberry Pi controller
- 4-Camera sequential capture
- YOLOv8 AI detection
- Real-time classification pipeline
- Local SQLite database storage
- Web server synchronization

---

_BananaVision Capstone Project_
_Bachelor of Science in Information Technology_
_Cebu Technological University_
