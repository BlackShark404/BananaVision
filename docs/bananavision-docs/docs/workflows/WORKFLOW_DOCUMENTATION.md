# BananaVision Program Workflows

BananaVision is a browser-based banana inventory and quality-control system using React/Vite frontend, FastAPI backend, REST endpoints under `/api/v1`, and WebSocket events for real-time updates.

## Kiosk Workflow

![Kiosk Workflow](workflow_kiosk.svg)

The BananaVision Kiosk is a full-screen scan interface for banana quality assessment. Operators authenticate with a 4-digit PIN, create or select a delivery intake by supplier, batch, and ripening treatment, then start a scan. The backend captures camera frames and DHT22 sensor data, runs YOLO26 detection, fuses multi-camera results, calculates environmental features, and uses Random Forest Regression to predict spoilage days. The result includes classification data, images, inventory updates, QR metadata, and audit records.

After the result is saved, the system generates and prints a spoilage estimation report through the connected printer. Operators review the result, flag it for quality control when necessary, or continue to the next scan. The kiosk also displays the five most recent scans and supports operator swapping through PIN re-authentication.

## Operator Dashboard

![Operator Workflow](workflow_operator.svg)

The BananaVision Operator Dashboard provides a role-limited web interface tailored for daily quality inspection, inventory tracking, and edge scanning operations without administrative overhead. Operators authenticate with a username and password to access the central Operator Dashboard, which consolidates shift throughput metrics, recent scan activity, and real-time alert notifications received over WebSocket connections. From this central hub, operators navigate core operational modules: Profile (self-service password updates, four-digit kiosk PIN OTP configuration, theme toggles, and avatar management), Scan Logs and Scan Detail (multi-criteria filtering, multi-camera inspection with YOLO26 bounding boxes, DHT22 microclimate telemetry, QR code tracking, CSV/XLSX exports, and inventory status transitions with mandatory reason logging), Analytics (quality distributions, cultivar breakdowns for Lakatan, Latundan, and Cardaba, daily volume trends, and operator shift throughput), Inventory (First-In, First-Out queue recommendations, two-day spoilage warnings, and hand/finger stock counts), and Device Status (four-camera health grid, Arduino DHT22 ambient readings, and edge Mini PC host metrics).

Operators can also launch the isolated Kiosk Mode for high-throughput banana scanning, authenticating with their four-digit PIN to select delivery intakes, initiate parallel multi-camera capture and Random Forest Regression spoilage prediction, generate and auto-print thermal labels, and perform in-place operator swapping. All administrative modules—including user management, delivery intake management, supplier registration, quality overrides, activity logs, and system configuration—are guarded by role-based route protections that prevent operator access and redirect unauthorized attempts back to the dashboard.


## Administrator Dashboard

![Admin Workflow](workflow_admin.svg)

The BananaVision Administrator Dashboard provides system-wide operational governance through shared monitoring views and six exclusive administrative modules. Administrators authenticate with a username and password to access the central dashboard, which consolidates operational KPIs, real-time alert notifications, and recent activity timelines. From this central hub, administrators oversee shared core pages—including global, role-unrestricted Scan Logs with multi-camera evidence and CSV/XLSX export, system analytics, FIFO inventory tracking with two-day spoilage alerts, and live camera and DHT22 sensor telemetry.

Administrative control is organized into six dedicated modules. User Management handles role-based account creation with auto-generated temporary passwords and four-digit kiosk PINs for physical handoff, user editing, credential resets, and account status toggling. Delivery Intakes manages batch tracking, generates printable batch QR code labels, and coordinates bulk inventory transitions with reason logging and revision conflict resolution. Supplier Management maintains the vendor directory with duplicate name validation and active/inactive status toggles. Quality Control provides a dedicated inspection queue for flagged and low-confidence scans, presenting multi-camera bounding box overlays and sensor data, manual classification overrides protected by mandatory reasons and revision locks, and audit note logging. Activity Log maintains a comprehensive audit trail of system events with multi-attribute filtering, 24-hour activity metrics, and export capabilities. Finally, System Config enforces station-level control across four tabs: camera discovery and live feed calibration, detection review confidence threshold tuning, automatic data retention cleanup and station backup/restore archives, and safe edge Mini PC shutdown and restart controls.


## IoT and AI Pipeline

![IoT Workflow](workflow_iot.svg)

The BananaVision edge hardware and AI pipeline coordinates the edge Mini PC, a 4-camera multi-view array, an Arduino Uno DHT22 microclimate sensor, and a USB thermal label printer. When an operator triggers a scan via the full-screen kiosk touch interface or REST endpoint (`POST /api/v1/scans`), the Mini PC acquires the station lock and initiates parallel frame capture across all configured cameras—`CAM-001` (Top anchor), `CAM-002` (Left), `CAM-003` (Right), and `CAM-004` (Rear)—with automatic sequential fallback to prevent USB bus bandwidth contention. Concurrently, the backend retrieves real-time ambient temperature ($T$) and relative humidity ($RH$) from the Arduino Uno MCU over a continuous 9600-baud USB serial polling loop.

Before running full vision inference, the system passes captured frames through a base COCO YOLO pre-detection gate (`yolo26n.pt`, Class 46) to verify banana presence on the tray; if no banana is detected or foreign objects are present, the pipeline aborts gracefully with operator instructions to reposition the bunch. Validated frames then proceed to custom YOLO detection (`best.pt`), which extracts cultivar predictions (Lakatan, Latundan, Cardaba), ripeness stages (Unripe, Semi-Ripe, Ripe, Overripe), detection confidences, bounding boxes, and per-camera finger counts. The Confidence-Weighted Multi-Camera Fusion engine combines predictions across all views, utilizing `CAM-001` (Top) as the authoritative cultivar anchor, computing bunch finger count as the maximum across camera views to eliminate double-counting, and enforcing botanical cultivar harmonization to reconcile dissenting views. Scans with cross-view disagreement or confidence below the configured review threshold are automatically flagged for administrative quality control.

In the environmental feature engineering stage, temperature and humidity telemetry are processed using the Magnus-Tetens formula to compute Vapor Pressure Deficit (VPD in kPa), which is combined with the delivery intake ripening treatment (Natural vs. Ethephon) and visual classifications into a 6-feature vector. A Random Forest Regression (RFR) model (`spoilage_rfr.joblib`) estimates remaining shelf life in days, with a literature-grounded rule fallback ensuring continuity if the ML model is offline. All scan results, evidence images (`/captures/<scan_id>/`), classifications, detection coordinates, audit logs, and notification records persist transactionally to PostgreSQL 17+. Finally, the Mini PC broadcasts real-time progress and completion events over WebSocket connections (`/api/v1/ws`) to update the Kiosk UI and Web Dashboards, updates FIFO inventory queues with 2-day spoilage alerts, and dispatches an auto-print job to the station thermal printer to generate a spoilage report label complete with batch QR code metadata.

## Tech Stack

- **Frontend:** React, Vite, TypeScript
- **Backend:** FastAPI, PostgreSQL
- **Hardware:** OpenCV (multi-camera), Arduino (DHT22 sensor), Mini PC
- **AI:** YOLO26 detection, multi-camera fusion, Random Forest Regression (spoilage prediction)

---

_BananaVision Capstone Project | Cebu Technological University_
