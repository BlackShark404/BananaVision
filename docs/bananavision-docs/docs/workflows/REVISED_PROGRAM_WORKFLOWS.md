# BananaVision — Revised Program Workflow Diagrams

> **BananaVision: An Intelligent System for Banana Ripeness Detection**  
> BSIT Capstone Project, Cebu Technological University

This document provides the **revised Program Workflow Diagrams** based on a thorough analysis of:

- Existing `.drawio` workflow files (`workflow_operator.drawio`, `workflow_admin.drawio`, `workflow_kiosk.drawio`, `workflow_iot.drawio`)
- Source code in `src/pages/` and `src/components/`
- Feature documentation in `docs/bananavision_features.md`

---

# BananaVision - Revised Program Workflows

> BananaVision: An Intelligent System for Banana Ripeness Detection  
> BSIT Capstone Project, Cebu Technological University

This condensed version keeps the workflow diagrams aligned with the current app routes in `src/App.tsx`, the page behavior in `src/pages/`, and the feature set documented in `docs/bananavision_features.md`.

## Figure 12B: Operator Workflow - Web Dashboard

Operator access starts with username/password login, then opens the dashboard, logs, analytics, inventory, device status, profile, scan detail, and kiosk entry point. The operator scan flow is: select batch -> scan now -> capture from 4 cameras -> YOLOv8 detect -> analyze -> result.

Key behavior:

- Scan Logs are role-filtered to the signed-in operator, not the full system.
- Operators can export CSV and update inventory status from the logs page.
- Inventory shows FIFO recommendations and spoilage alerts for items expiring within 2 days.
- Profile supports password change, theme toggle, avatar upload, and kiosk PIN change.

## Figure 13: Administrator Workflow - Web Dashboard

Administrators log in with username/password and get access to the full admin dashboard plus user management, intake management, supplier management, quality control, activity log, and system configuration.

Key behavior:

- New users are created with unique temporary credentials displayed once for handoff; operators also receive a temporary PIN.
- Password resets issue a unique temporary password; kiosk PIN resets issue a unique temporary PIN.
- Quality Control focuses on flagged or low-confidence scans, with scan review, edit, and notes support.
- System Config covers camera IDs, confidence threshold, data retention, and restart/shutdown actions.

## Figure 12A: Kiosk Workflow - Isolated Scanning Terminal

Kiosk mode is PIN-based and scan-focused. After PIN entry, the user selects a batch, scans from the full-screen kiosk interface, reviews the result, then either accepts it or flags it for review.

Key behavior:

- Only the current batch is shown, with the recent list limited to the last 5 scans.
- The kiosk exposes the 4-step AI scan pipeline: Capturing (4 Cam + DHT22) -> Detecting (YOLOv8) -> Analyzing (Feature Vector) -> Calculating (RFR Spoilage).
- Operator swap is handled through PIN re-authentication.
- Kiosk users cannot access logs, analytics, inventory, profile settings, or admin pages.

## Figure 14: IoT Hardware Integration

The IoT workflow is a linear edge pipeline: User -> Mini PC -> 4 cameras + DHT22 sensor (via Arduino MCU) -> capture buffer -> YOLOv8 detection/counting/cultivar classification/ripeness determination -> feature vector assembly (YOLOv8 outputs + DHT22 readings) -> RFR spoilage estimation -> PostgreSQL 17+ storage -> web dashboard/kiosk display. All processing occurs on the Mini PC edge node.

Output data includes:

- Cultivar: Lakatan, Latundan, or Saba
- Ripeness: Unripe, Ripe, Overripe, or Rotten
- Confidence score
- Finger count
- Spoilage estimate in days

## Summary

| Figure | Perspective                 | Main Access                                   |
| ------ | --------------------------- | --------------------------------------------- |
| 12B    | Operator web dashboard      | Read-only browsing with scan-status updates   |
| 13     | Administrator web dashboard | Full management access                        |
| 12A    | Kiosk terminal              | PIN-authenticated scan-only mode              |
| 14     | IoT hardware flow           | Edge capture, inference, storage, and display |

## Accuracy Notes

- Operator scan logs are not global; they are limited to the current operator.
- Temporary credentials for account creation and credential resets are generated uniquely and handed off securely by administrators.
- `.gitignore` already ignores `node_modules`, `dist`, and related build outputs.

_Document generated for BananaVision Capstone Project_  
_Bachelor of Science in Information Technology_  
_Cebu Technological University_
