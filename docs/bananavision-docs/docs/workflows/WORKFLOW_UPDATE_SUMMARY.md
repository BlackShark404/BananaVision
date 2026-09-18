# BananaVision Workflow Diagrams - Change History

**Updated:** September 13, 2026
**Scope:** Operator, kiosk, administrator, and IoT workflow diagrams
**Source of truth:** Implemented backend/frontend code, plus `docs/BANANAVISION_CONTEXT.md`

## Purpose

This file records what the workflow diagrams showed previously and what was changed to bring them in line with the current BananaVision implementation. The diagrams are documentation only; application behavior is controlled by the source files listed below.

## Previous Workflow State

The earlier diagrams described the main research concept correctly, but several details were based on an older design:

- The kiosk flow ended with “Accept or Flag” and did not make persistence behavior clear.
- Kiosk source selection was shown as supplier selection only, without the delivery-intake and treatment step.
- The scan pipeline was described as four broad stages: capture, detect, analyze, and calculate.
- The IoT diagram used generic YOLOv8/RFR wording and did not show multi-camera fusion or engineered environmental features.
- Camera positions and labels did not match the configured order in the backend.
- Operator and admin diagrams used stale page/access wording and did not clearly represent notifications, live status, or the REST/WebSocket boundary.
- The IoT diagram did not clearly distinguish per-camera inference from final fused scan output.

## Current Implementation Changes

### Kiosk Workflow

`workflow_kiosk.drawio` now documents:

- Active-operator selection and four-digit PIN authentication.
- Required PIN change for new or reset operator accounts.
- Selection or creation of an active delivery intake, including supplier and ripening treatment (`Natural` or `Ethephon`).
- Full-screen kiosk scanning through a REST trigger with WebSocket progress updates.
- Configured camera capture with sensor context.
- Per-camera detection followed by multi-camera fusion and engineered feature analysis.
- RFR spoilage prediction using sensor values and intake treatment.
- A persisted scan result containing QR metadata, evidence, status, and audit information.
- Post-result continuation or flagging for quality review and notification.
- Recent scans and operator swapping.

### IoT and AI Workflow

`workflow_iot.drawio` now documents:

- The configured camera order: Top, Back, Left, and Right according to the current settings/registration flow.
- Arduino serial communication with the DHT22 temperature/humidity sensor.
- Image capture and buffering on the Mini PC edge node.
- YOLOv8n per-camera detection, including finger count and cultivar/ripeness classification.
- Confidence-weighted multi-camera fusion, with conflict and low-confidence flagging.
- Dew point, VPD, and heat-index feature engineering.
- RFR spoilage prediction using classification, environmental data, and treatment.
- Persistence of scan classification, original AI result, camera detections, images, inventory status, activity, and notifications.
- PostgreSQL/database output, image storage, React dashboard synchronization, and live kiosk events.
- `sensor:update` and WebSocket-driven dashboard/kiosk updates.

### Operator Workflow

`workflow_operator.drawio` now documents the current role-limited application surface:

- Username/password login and the role-aware operator dashboard.
- Own-scan metrics and alert/notification visibility.
- Profile actions: password change, kiosk PIN change, avatar upload, and theme toggle.
- Scan logs with filtering, detail navigation, CSV export, QR actions, and inventory status visibility.
- Scan detail review with camera evidence, flags, notes, original AI values, and QR tracking.
- Operator-filtered analytics, FIFO inventory, spoilage alerts, and inventory status summaries.
- Device status showing configured cameras, live sensor readings, health state, and system metrics.
- Standalone kiosk entry with intake creation and scan initiation.

### Administrator Workflow

`workflow_admin.drawio` now documents:

- Admin login and a role-aware overview with notifications.
- Shared operator pages plus the six admin-only modules: users, delivery intakes, suppliers, quality control, activity log, and system configuration.
- User creation/update, account status changes, password reset, and operator PIN reset behavior.
- Delivery intake status and inventory transitions, supplier/treatment data, and QR-linked intake records.
- Flagged-scan quality review, scan overrides, notes, and review actions.
- Scan detail, CSV export, and inventory status updates.
- Audit/activity filtering and notification-driven operational awareness.
- Camera ID configuration, confidence threshold, data retention, database export, restart, and shutdown controls.

## Implementation References

- Frontend routing and role guards: `frontend/src/App.tsx`
- Kiosk UI and intake/PIN flow: `frontend/src/pages/Kiosk.tsx`
- Scan event handling and WebSocket rooms: `frontend/src/context/ScanContext.tsx`
- Intake and supplier state: `frontend/src/context/InventoryContext.tsx`
- User, device, activity, and system configuration state: `frontend/src/context/AdminContext.tsx`
- Backend scan orchestration: `backend/app/services/scan_service.py`
- Camera capture: `backend/app/services/camera_manager.py`
- YOLOv8n inference: `backend/app/services/classification.py`
- Multi-camera fusion: `backend/app/services/fusion_engine.py`
- Sensor polling: `backend/app/services/sensor_reader.py`
- API and WebSocket registration: `backend/app/api/v1/router.py` and `backend/app/main.py`
- Project-wide implementation context: `docs/BANANAVISION_CONTEXT.md`

## Validation

The four `.drawio` files were checked after the update:

- All files parse successfully as XML.
- All edge source and target references resolve to existing nodes.
- `git diff --check` found no whitespace errors.

Open the diagrams in [draw.io](https://app.diagrams.net/) to review their visual layout and export them for the research document.

---

**Status:** ✅ Complete  
**Next Steps:** Export diagrams to SVG/PNG for final documentation
