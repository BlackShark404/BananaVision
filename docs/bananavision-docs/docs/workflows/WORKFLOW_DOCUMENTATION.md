# BananaVision Program Workflows

BananaVision is a browser-based banana inventory and quality-control system using React/Vite frontend, FastAPI backend, REST endpoints under `/api/v1`, and WebSocket events for real-time updates.

## Kiosk Workflow

![Kiosk Workflow](workflow_kiosk.svg)

The BananaVision Kiosk is a full-screen scan interface for banana quality assessment. Operators authenticate with a 4-digit PIN, create or select a delivery intake by supplier, batch, and ripening treatment, then start a scan. The backend captures camera frames and DHT22 sensor data, runs YOLO26 detection, fuses multi-camera results, calculates environmental features, and uses Random Forest Regression to predict spoilage days. The result includes classification data, images, inventory updates, QR metadata, and audit records.

After the result is saved, the system generates and prints a spoilage estimation report through the connected printer. Operators review the result, flag it for quality control when necessary, or continue to the next scan. The kiosk also displays the five most recent scans and supports operator swapping through PIN re-authentication.

## Operator Dashboard

![Operator Workflow](workflow_operator.svg)

The BananaVision Operator Dashboard is a secure, role-based web system with 10 pages: Dashboard (metrics, recent scans, notifications), Scan Logs (filtering, CSV export, QR actions), Scan Detail (camera evidence, QR tracking, flags, notes, AI values), Analytics (charts, confidence trends, cultivar summaries), Inventory (FIFO, spoilage alerts), Device Status (camera health, DHT22 readings), and Profile (account settings, kiosk PIN, avatar, theme).

## Administrator Dashboard

![Admin Workflow](workflow_admin.svg)

The BananaVision Administrator Dashboard provides system-wide operational governance through shared monitoring views and six exclusive administrative modules. Administrators authenticate with a username and password to access the central dashboard, which consolidates operational KPIs, real-time alert notifications, and recent activity timelines. From this central hub, administrators oversee shared core pages—including global, role-unrestricted Scan Logs with multi-camera evidence and CSV/XLSX export, system analytics, FIFO inventory tracking with two-day spoilage alerts, and live camera and DHT22 sensor telemetry.

Administrative control is organized into six dedicated modules. User Management handles role-based account creation with auto-generated temporary passwords and four-digit kiosk PINs for physical handoff, user editing, credential resets, and account status toggling. Delivery Intakes manages batch tracking, generates printable batch QR code labels, and coordinates bulk inventory transitions with reason logging and revision conflict resolution. Supplier Management maintains the vendor directory with duplicate name validation and active/inactive status toggles. Quality Control provides a dedicated inspection queue for flagged and low-confidence scans, presenting multi-camera bounding box overlays and sensor data, manual classification overrides protected by mandatory reasons and revision locks, and audit note logging. Activity Log maintains a comprehensive audit trail of system events with multi-attribute filtering, 24-hour activity metrics, and export capabilities. Finally, System Config enforces station-level control across four tabs: camera discovery and live feed calibration, detection review confidence threshold tuning, automatic data retention cleanup and station backup/restore archives, and safe edge Mini PC shutdown and restart controls.


## IoT and AI Pipeline

![IoT Workflow](workflow_iot.svg)

The BananaVision edge hardware and AI pipeline coordinates the Mini PC, multi-camera array, and Arduino DHT22 sensor. When the kiosk triggers a scan via REST API, the Mini PC activates the camera system to capture frames from all configured cameras and retrieves temperature and humidity sensor data from the Arduino via serial connection.

The AI detection stage runs YOLO26 inference on each camera image to extract cultivar, ripeness, confidence score, finger count, and bounding-box evidence per image. Confidence-weighted multi-camera fusion then combines cultivar and ripeness predictions across cameras while using the maximum finger count to avoid double counting. Low confidence or cross-camera disagreement automatically flags the scan for manual review.

The feature engineering stage calculates environmental metrics—dew point, VPD (vapor pressure deficit), and heat index—from the DHT22 sensor data. The spoilage prediction stage uses a Random Forest Regression model trained on visual classification, environmental features, and intake ripening treatment to estimate spoilage days. Results persist with classification, detections, images, inventory status updates, activity logs, and notifications, then broadcast to kiosk and dashboard via WebSocket for real-time user feedback.

## Tech Stack

- **Frontend:** React, Vite, TypeScript
- **Backend:** FastAPI, PostgreSQL
- **Hardware:** OpenCV (multi-camera), Arduino (DHT22 sensor), Mini PC
- **AI:** YOLO26 detection, multi-camera fusion, Random Forest Regression (spoilage prediction)

---

_BananaVision Capstone Project | Cebu Technological University_
