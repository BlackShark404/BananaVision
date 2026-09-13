# BananaVision Workflow Diagrams - Update Summary

**Date:** April 20, 2026  
**Updated By:** Kiro AI Assistant  
**Project:** BananaVision Capstone 1

## Overview

All four workflow diagrams have been updated to accurately reflect the current system architecture, features, and user flows as implemented in the codebase.

## Files Updated

1. `workflow_iot.drawio` - IoT Hardware Integration Workflow
2. `workflow_kiosk.drawio` - Kiosk Terminal Workflow  
3. `workflow_operator.drawio` - Operator Web Dashboard Workflow
4. `workflow_admin.drawio` - Admin Web Dashboard Workflow

## Key Changes Made

### 1. IoT Workflow (workflow_iot.drawio)

**Completely redesigned** to show the full edge processing pipeline:

- User → Mini PC Edge Node
- 4-Camera Array (Top, Side, Side, Bottom)
- Arduino MCU → DHT22 Sensor (Temperature & Humidity)
- Image Capture → Buffer
- AI Processing Pipeline (YOLOv8 + RFR):
  - Detection
  - Finger Count
  - Cultivar Classification
  - Ripeness Analysis
  - RFR Spoilage Prediction (visual + environmental features)
  - Confidence Scoring
- DHT22 env data → RFR Spoilage Prediction (dashed arrow)
- Scan Result → PostgreSQL Database
- Image Storage (local/cloud)
- Web Dashboard sync
- Kiosk Display

**Icons Used:**
- 👤 User/Operator
- 🖥️ Mini PC
- 📷 Cameras (4x)
- 🖼️ Image Capture
- 💾 Buffer/Storage
- 🧠 YOLOv8 Model
- 🔍 Detection
- # Finger Count
- 📊 Classification
- 🍌 Ripeness
- ⏰ Spoilage
- ✓ Confidence
- ✅ Result
- 💾 PostgreSQL
- 🏠 Dashboard
- 📺 Display

### 2. Kiosk Workflow (workflow_kiosk.drawio)

**Completely redesigned** to show the isolated scanning terminal flow:

- Select Operator (Active Only)
- PIN Entry (4-digit)
- PIN Change Decision (Yes/No)
- Create New Kiosk PIN (if required)
- Kiosk Terminal
- Select Supplier
- Full-Screen Scan Interface
- Scan Now Button
- AI Pipeline (4-Step):
  - Capturing (4 Cam + DHT22)
  - Detecting (YOLOv8)
  - Analyzing (Feature Vector)
  - Calculating (RFR Spoilage)
- Scan Result Display
- Decision: Accept or Flag
- Recent Scans (Last 5)
- Operator Swap

**Icons Used:**
- 👤 Select Operator
- 🔢 PIN Entry
- ❓ Decision Diamond
- 🖥️ Kiosk Terminal
- 🏢 Select Supplier
- 🔍 Scan Interface
- ▶️ Scan Now
- 📷 Capturing
- 🎯 Detecting
- 🔬 Analyzing
- 🧮 Calculating (RFR)
- ✅ Scan Result
- ✓ Accept
- ⚠️ Flag
- 📋 Recent Scans
- 🔄 Operator Swap

### 3. Operator Workflow (workflow_operator.drawio)

**Completely redesigned** to show all 10 accessible pages:

- Operator → Login (Username/Password)
- Dashboard (Central Hub)
- **Profile Branch:**
  - Update Password
  - Update Kiosk PIN
  - Theme Toggle
  - Upload Avatar
- **Scan Logs Branch (Own Scans Only):**
  - View Detail
  - Export CSV
- **Analytics Branch (Own Data):**
  - View Charts
- **Inventory Branch:**
  - FIFO List
  - Spoilage Alerts
- **Device Status Branch:**
  - 4-Camera Grid
  - System Info
- **Kiosk Branch:**
  - Scan Now

**Icons Used:**
- 👤 Operator/Profile
- 🔐 Login
- 🏠 Dashboard
- 🔑 Password
- 🔢 PIN
- 🌓 Theme
- 📷 Avatar
- 📋 Scan Logs
- 🔍 View Detail
- 📊 Export/Analytics
- 📦 Inventory
- ⚠️ Spoilage Alerts
- 📷 Device Status
- 💻 System Info
- 🖥️ Kiosk
- ▶️ Scan Now

### 4. Admin Workflow (workflow_admin.drawio)

**Updated** to maintain existing structure with accurate icons:

- Admin → Login → Dashboard (All 16 Pages)
- **User Management:**
  - Add User
  - Edit User
  - Disable User
  - Reset Password
- **Delivery Intakes:**
  - Edit Intake
  - Toggle Status
- **Quality Control:**
  - Flag Scan
  - Edit Scan Data
  - Review Notes
- **Scan Log:**
  - View Detail
  - Export CSV
  - Update Status
- **Activity Log:**
  - Filter Actions
- **System Config:**
  - Camera Settings
  - AI Settings
  - Storage Settings
  - Power Management
- **Supplier Management:**
  - Add Supplier
  - Toggle Status

**Icons Used:**
- 👤 Admin
- 🔐 Login
- 🏠 Dashboard
- 👥 User Management
- 📦 Delivery Intakes
- 🔍✓ Quality Control
- 📋 Scan Log
- 📜 Activity Log
- ⚙️ System Config
- 🏢 Supplier Management
- Plus various action icons (➕, ✏️, 🚫, 🔑, ✅, 🚩, 📝, 🔽, 📷, 🤖, 💾, ⏻)

### 5. RFR + DHT22 Integration Update (April 20, 2026)

**Kiosk (`workflow_kiosk.drawio`)**:
- Added 4th pipeline node: 🧮 Calculating (RFR Spoilage)
- Updated Capturing label to include DHT22: 📷 (4 Cam + DHT22)
- Updated Analyzing label to 🔬 (Feature Vector)
- Arrow flow: Capturing → Detecting → Analyzing → Calculating → Scan Result

**IoT (`workflow_iot.drawio`)**:
- Renamed pipeline label from "YOLOv8 + OpenCV" to "YOLOv8 + RFR"
- Renamed Spoilage node from ⏰ Spoilage Estimate to 🧮 RFR Spoilage Prediction (highlighted yellow)
- Added 🔌 Arduino MCU node (Mini PC → Arduino)
- Added 🌡️ DHT22 Sensor node (Arduino → DHT22)
- Added dashed "env data" arrow from DHT22 → RFR Spoilage Prediction

## Technical Improvements

1. **Consistent Icon Usage:** All workflows now use emoji icons for better visual clarity
2. **Proper Color Coding:**
   - Blue (#dbeafe, #2563eb) - User/Operator elements
   - Yellow (#fef3c7, #f59e0b) - Important actions/decisions
   - Red (#fee2e2, #dc2626) - Admin-only features
   - Green (#dcfce7, #22c55e) - Success/Results
   - Orange (#fff7ed, #ea580c) - Warnings/Decisions
   - Purple (#e0e7ff, #6366f1) - Secondary features

3. **Improved Layout:**
   - Logical left-to-right flow
   - Clear grouping of related features
   - Proper use of boxes for subsystems
   - Legend boxes for context

4. **Accurate Representation:**
   - All workflows match actual codebase implementation
   - Page counts accurate (10 for Operator, 16 for Admin)
   - Feature lists match `bananavision_features.md`
   - Data flows match `DATA_DICTIONARY_FINAL.md`

## Alignment with Documentation

All workflows now accurately reflect:

- ✅ `docs/SOFTWARE_SPECIFICATION.md` - Technology stack and requirements
- ✅ `docs/bananavision_features.md` - Complete feature list (16 pages)
- ✅ `docs/DATA_DICTIONARY_FINAL.md` - Database schema and entities
- ✅ `PROGRAM_SPECIFICATION_CAPSTONE1.md` - Functional requirements
- ✅ `src/pages/` - Actual page implementations
- ✅ `src/App.tsx` - Routing structure

## Verification

To verify the workflows are accurate:

1. Open each `.drawio` file in [draw.io](https://app.diagrams.net/)
2. Compare with the corresponding page implementations in `src/pages/`
3. Cross-reference with feature documentation in `docs/bananavision_features.md`
4. Validate against the database schema in `docs/DATA_DICTIONARY_FINAL.md`

## Export Instructions

To export the diagrams for documentation:

1. Open the `.drawio` file in draw.io
2. File → Export as → PNG/SVG/PDF
3. Choose appropriate resolution (300 DPI recommended for print)
4. Save to `docs/workflows/` directory

## Notes

- All diagrams use the mxGraph format compatible with draw.io
- Icons are Unicode emoji for maximum compatibility
- Color scheme follows the application's design system
- Workflows are optimized for both digital and print viewing

---

**Status:** ✅ Complete  
**Next Steps:** Export diagrams to SVG/PNG for final documentation

