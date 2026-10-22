  # BananaVision Project Context

> AI-oriented reference for the implemented BananaVision repository.
>
> Scope scanned: `backend/`, `frontend/`, and `docs/migrations/`. This document summarizes the current source of truth and calls out places where planning documents differ from implementation. When this document conflicts with application code, application code wins.

## 1. Project Purpose

BananaVision is a browser-based banana inventory and quality-control system. It combines:

- A React 19 + TypeScript + Vite frontend.
- A FastAPI backend with SQLAlchemy models and PostgreSQL-oriented configuration.
- Multi-camera capture through OpenCV.
- Banana classification through a YOLO model when model weights are available.
- Multi-camera result fusion.
- Spoilage prediction using a regression model when weights are available.
- DHT22 temperature/humidity readings from an Arduino serial connection.
- Operator and administrator workflows, scan history, inventory, quality review, analytics, notifications, device status, and system controls.

The current repository is an actively implemented foundation. See `docs/CHANGELOG.md` for implementation status and remaining station/panel verification. Planned production features are not automatically implemented.

## 2. System Shape

```text
Browser (React/Vite)
  |
  | REST: /api/v1/* and WebSocket: /api/v1/ws
  v
FastAPI application (backend/app/main.py)
  |
  +-- API routers: auth, scans, devices, sensors, users, suppliers,
  |   intakes, analytics, activity, config, quality, notifications,
  |   cameras, system
  +-- Services: auth, camera, classification, fusion, spoilage,
  |   feature engineering, scan orchestration, sensor reader
  +-- SQLAlchemy ORM models
  +-- Runtime camera/sensor/ML resources
  v
PostgreSQL-compatible database and local captures/ directory
```

Application entry point: `backend/app/main.py` (`app = FastAPI(...)`).
Frontend entry point: `frontend/src/main.tsx`, rendering `frontend/src/App.tsx`.

## 3. Source Manifest

### 3.1 Backend root

| File                       | Role                                                                             |
| -------------------------- | -------------------------------------------------------------------------------- |
| `backend/.env.example`     | Environment variable template.                                                   |
| `backend/pyproject.toml`   | Python project/tool configuration.                                               |
| `backend/requirements.txt` | Python runtime dependencies.                                                     |
| `backend/README.md`        | Backend setup and run notes.                                                     |
| `backend/seed.py`          | Database/user seed utility.                                                      |
| `backend/app/__init__.py`  | Backend package marker.                                                          |
| `backend/app/config.py`    | Pydantic settings, environment parsing, derived paths.                           |
| `backend/app/main.py`      | FastAPI app, lifespan, CORS, routes, WebSocket, captures mount, health endpoint. |

### 3.2 Backend API

| File                                  | Role                                                                 |
| ------------------------------------- | -------------------------------------------------------------------- |
| `backend/app/api/__init__.py`         | API package marker.                                                  |
| `backend/app/api/deps.py`             | Database and authenticated-user dependencies, including role checks. |
| `backend/app/api/v1/__init__.py`      | Versioned API package marker.                                        |
| `backend/app/api/v1/router.py`        | Includes all version 1 routers under `/api/v1`.                      |
| `backend/app/api/v1/auth.py`          | Login, logout, operator swap, password/PIN changes.                  |
| `backend/app/api/v1/scans.py`         | Trigger, list, detail, flag, override, status, and note operations.  |
| `backend/app/api/v1/devices.py`       | Device listing/status.                                               |
| `backend/app/api/v1/cameras.py`       | Camera-specific operations/status.                                   |
| `backend/app/api/v1/sensors.py`       | Latest and historical sensor readings.                               |
| `backend/app/api/v1/users.py`         | Administrator user management.                                       |
| `backend/app/api/v1/suppliers.py`     | Supplier listing and mutations.                                      |
| `backend/app/api/v1/intakes.py`       | Delivery intake listing and mutations.                               |
| `backend/app/api/v1/analytics.py`     | Aggregate analytics.                                                 |
| `backend/app/api/v1/activity.py`      | Activity log listing.                                                |
| `backend/app/api/v1/config.py`        | System configuration, CSV export, shutdown/restart controls.         |
| `backend/app/api/v1/quality.py`       | Flagged scan review.                                                 |
| `backend/app/api/v1/notifications.py` | Notification listing and read state.                                 |
| `backend/app/api/v1/system.py`        | System metrics.                                                      |

### 3.3 Backend core, services, models, schemas, WebSocket

| Area      | Files and responsibility                                                                                                                                                                                                                                                                                                                                                                        |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core      | `core/database.py` creates the async database engine/session; `core/security.py` handles password/PIN hashing and JWT concerns; `core/startup.py` owns boot/shutdown/background tasks; `core/exceptions.py` defines application errors.                                                                                                                                                         |
| Services  | `services/auth_service.py`, `camera_manager.py`, `classification.py`, `feature_engineering.py`, `fusion_engine.py`, `scan_service.py`, `sensor_reader.py`, and `spoilage.py` implement the main domain behavior.                                                                                                                                                                                |
| Models    | `models/user_account.py`, `user_role.py`, `operator_profile.py`, `admin_profile.py`, `device.py`, `supplier.py`, `intake.py`, `scan.py`, `scan_classification.py`, `scan_detection.py`, `scan_image.py`, `scan_note.py`, `scan_original_ai_result.py`, `scan_status_log.py`, `sensor_reading.py`, `activity_log.py`, `app_notification.py`, `app_notification_read.py`, and `system_config.py` are SQLAlchemy ORM entities. |
| Schemas   | `schemas/auth.py`, `common.py`, `enums.py`, `scan.py`, and `user.py` define Pydantic request/response models and domain enums.                                                                                                                                                                                                                                                                  |
| WebSocket | `ws/manager.py` tracks connections/rooms and broadcasts; `ws/events.py` defines event names/rooms; `ws/handlers.py` accepts WebSocket clients and dispatches events.                                                                                                                                                                                                                            |
| ML assets | `ml/__init__.py` and `ml/weights/.gitkeep`. Weight files exist in the local workspace but are ignored by Git; a fresh checkout requires separately provisioned model assets. Filename alone does not verify model architecture or accuracy.                                                                                                                                                                                                                                                               |

### 3.4 Frontend

| File/group                                                                                                                                                 | Role                                                                                                                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/App.tsx`                                                                                                                                     | Application route/layout composition and role-aware page selection.                                                                                             |
| `frontend/src/main.tsx`                                                                                                                                    | React bootstrap and providers.                                                                                                                                  |
| `frontend/src/index.css`                                                                                                                                   | Global styles, theme tokens, layout styles.                                                                                                                     |
| `frontend/src/layouts/AppLayout.tsx`                                                                                                                       | Authenticated shell with sidebar/header/content.                                                                                                                |
| `frontend/src/components/AppHeader.tsx`, `AppSidebar.tsx`, `AppSidebarHeader.tsx`, `AppSidebarFooter.tsx`                                                  | Navigation shell and user controls.                                                                                                                             |
| `frontend/src/components/AppPageHeader.tsx`, `AppActionButton.tsx`, `AppChangePreview.tsx`                                                                 | Page headings and common actions/preview UI.                                                                                                                    |
| `frontend/src/components/AppDataTable.tsx`, `AppTableFilters.tsx`                                                                                          | Tables, filtering, pagination-oriented UI.                                                                                                                      |
| `frontend/src/components/AppStatsCard.tsx`, `AppStatusBadge.tsx`, `AppNotifications.tsx`                                                                   | Dashboard statistics, statuses, and notifications.                                                                                                              |
| `frontend/src/components/theme-provider.tsx`                                                                                                               | Theme state/provider.                                                                                                                                           |
| `frontend/src/components/ui/*`                                                                                                                             | Reusable UI primitives based on the configured component system: buttons, cards, dialogs, forms, menus, tables, tabs, charts, tooltips, and related primitives. |
| `frontend/src/context/AuthContext.tsx`                                                                                                                     | Login state, current user, token/session behavior.                                                                                                              |
| `frontend/src/context/AppContext.tsx`                                                                                                                      | Shared application state and dashboard-level behavior.                                                                                                          |
| `frontend/src/context/ScanContext.tsx`                                                                                                                     | Scan state and scan actions.                                                                                                                                    |
| `frontend/src/context/InventoryContext.tsx`                                                                                                                | Inventory/intake state and actions.                                                                                                                             |
| `frontend/src/context/AdminContext.tsx`                                                                                                                    | Administrator state and management operations.                                                                                                                  |
| `frontend/src/hooks/useLocalStorage.ts`                                                                                                                    | Persistent browser state helper.                                                                                                                                |
| `frontend/src/hooks/useIsMobile.ts`                                                                                                                        | Responsive breakpoint hook.                                                                                                                                     |
| `frontend/src/hooks/useWebSocket.ts`                                                                                                                       | WebSocket connection/event helper.                                                                                                                              |
| `frontend/src/lib/api.ts`                                                                                                                                  | Central REST client; attaches bearer token and handles 401 redirects.                                                                                           |
| `frontend/src/lib/auth.ts`                                                                                                                                 | Browser token/auth storage helpers.                                                                                                                             |
| `frontend/src/lib/qrcode.ts`                                                                                                                               | QR-related utility behavior.                                                                                                                                    |
| `frontend/src/lib/utils.ts`                                                                                                                                | Shared formatting and spoilage/helper functions.                                                                                                                |
| `frontend/src/pages/Landing.tsx`, `Login.tsx`                                                                                                              | Public landing and authentication pages.                                                                                                                        |
| `frontend/src/pages/Dashboard.tsx`, `Logs.tsx`, `ScanDetail.tsx`, `Analytics.tsx`, `Inventory.tsx`, `DeviceStatus.tsx`, `Kiosk.tsx`, `Profile.tsx`         | Operator/user application pages.                                                                                                                                |
| `frontend/src/pages/admin/ActivityLog.tsx`, `DeliveryIntake.tsx`, `QualityControl.tsx`, `SupplierManagement.tsx`, `SystemConfig.tsx`, `UserManagement.tsx` | Administrator-only workflows.                                                                                                                                   |
| `frontend/src/types/index.ts`                                                                                                                              | Shared frontend domain types.                                                                                                                                   |
| `frontend/package.json`, `vite.config.ts`, `tsconfig*.json`, `eslint.config.js`, `components.json`                                                         | Build, TypeScript, linting, and UI tooling configuration.                                                                                                       |

## 4. Backend Configuration

`backend/app/config.py` loads `.env` with Pydantic Settings. Important defaults:

| Setting                  | Default/meaning                                               |
| ------------------------ | ------------------------------------------------------------- |
| `app_env`                | `development`                                                 |
| `app_host` / `app_port`  | `0.0.0.0` / `8000`                                            |
| `app_debug`              | `true`                                                        |
| `app_cors_origins`       | `[*]`; comma-separated values are parsed.                     |
| `database_url`           | PostgreSQL async URL on localhost database `bananavision`.    |
| `jwt_algorithm` / expiry | `HS256` / 480 minutes.                                        |
| `camera_device_ids`      | `[0, 1, 2, 3]`; comma-separated values are parsed.            |
| `camera_labels`          | `Front, Left, Right, Top`.                                    |
| camera resolution        | `640x480` in implemented settings.                            |
| sensor                   | `/dev/ttyUSB0`, baud `9600`, interval `5` seconds.            |
| ML paths                 | `app/ml/weights/banana_yolo26m.pt` and `spoilage_rfr.joblib`. |
| storage                  | `captures`, retention default `30` days.                      |

`main.py` configures console plus rotating file logging, mounts `/captures`, adds CORS, includes `/api/v1`, registers `/api/v1/ws`, and exposes `/health`.

## 5. REST API Contract

All endpoints are rooted at `/api/v1` unless stated otherwise. Authentication is normally a bearer JWT. Exact authorization is enforced by dependencies in `app/api/deps.py` and each router.

| Area            | Implemented operations                                                                                                                                                                                |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth            | `POST /auth/login`, `/auth/logout`, `/auth/swap`, `/auth/change-password`, `/auth/change-pin`, `/auth/setup-password`, `/auth/setup-pin` (limited setup proof required).                                                                                                        |
| Scans           | `POST /scans/trigger`; `GET /scans`; `GET /scans/{id}`; `PATCH /scans/{id}` for override; `PATCH /scans/{id}/flag`; `PATCH /scans/{id}` for inventory status; notes via `GET/POST /scans/{id}/notes`. |
| Devices/cameras | `GET /devices` and camera endpoints in `cameras.py`.                                                                                                                                                  |
| Sensors         | `GET /sensors/latest`, `GET /sensors/history`.                                                                                                                                                        |
| Admin data      | User, supplier, intake, activity, configuration, and quality routes are grouped in their respective router modules.                                                                                   |
| Analytics       | `GET /analytics/summary` and related analytics router operations.                                                                                                                                     |
| Notifications   | `GET /notifications`, `PATCH /notifications/{id}/read`, `POST /notifications/read-all`.                                                                                                               |
| System          | `GET /system/metrics`.                                                                                                                                                                                |
| Health          | `GET /health` returns API version, online/total camera counts, YOLO/RFR loaded flags, and sensor connection status.                                                                                   |

The frontend client in `frontend/src/lib/api.ts` uses `VITE_API_URL` or `http://<browser-host>:8000`, sends JSON, attaches `Authorization: Bearer`, redirects to `/login` on HTTP 401, and handles 204 responses.

## 6. Operator Scan Workflow

1. Operator authenticates through login or PIN-based swap.
2. Kiosk or scan UI calls `POST /api/v1/scans/trigger` with optional `source_text` and `intake_id`.
3. `scan_service.execute_scan_pipeline` creates a scan UUID and broadcasts `scan:started`.
4. `camera_manager.capture_all()` captures available cameras and saves files below the configured capture directory.
5. Capture progress is broadcast per camera.
6. The classifier runs for each image; per-camera detection records are assembled.
7. `fusion_engine.fuse` combines cultivar/ripeness/confidence and uses the fused finger count.
8. If the result is unknown, the pipeline raises a model inference error and reports failure rather than persisting a normal result.
9. The latest sensor reading supplies temperature/humidity.
10. Feature engineering calculates VPD in kPa when both scan temperature and humidity exist. The current pipeline leaves dew point and heat index null.
11. Linked intake treatment is read when `intake_id` is supplied.
12. The spoilage predictor receives classification, sensor features, and treatment.
13. Scan, classification, original AI result, status log, camera detections, images, activity log, and notifications are persisted.
14. `scan:completed` is broadcast with the result. Errors are broadcast as `scan:failed` with the failing stage/message.

### Fusion rules

- Cultivar and ripeness are confidence-weighted across camera results.
- The winning class confidence is based on the winning observations.
- Finger count uses the maximum per-camera count to avoid cross-camera double counting.
- Low confidence/disagreement can mark a scan as flagged.
- Cross-camera bounding boxes are not IoU-merged because camera coordinate spaces differ.

## 7. WebSocket Contract

Endpoint: `/api/v1/ws?token=<jwt>`.

Messages use an event/data envelope and timestamp. Rooms defined by `ws/events.py` include `kiosk`, `dashboard`, and `devices`.

| Event family                       | Meaning                                                  |
| ---------------------------------- | -------------------------------------------------------- |
| `scan:started`                     | Pipeline began; includes scan/operator/supplier context. |
| `scan:capturing` / `scan:captured` | Camera capture progress and image path.                  |
| `scan:detecting` / `scan:detected` | ML progress and per-camera result.                       |
| `scan:analyzing`                   | Fusion/spoilage analysis progress.                       |
| `scan:completed` / `scan:failed`   | Final result or controlled failure.                      |
| `sensor:update`                    | Periodic temperature/humidity update.                    |
| `device:status`                    | Camera online/offline state.                             |
| `notification`                     | User-facing notification event.                          |

## 8. Database Model

The ORM model set represents these relationships:

```text
user_role 1--many user_account
user_account 1--0/1 admin_profile
user_account 1--0/1 operator_profile
operator_profile 1--many scan
supplier 1--many delivery_intake
intake 1--many scan (optional intake on scan)
scan 1--1 scan_classification
scan 1--many scan_detection
scan 1--many scan_image
scan 1--many scan_note
scan 1--1 scan_original_ai_result
scan 1--many scan_status_log
user_account 1--many activity_log
user_account 1--many app_notification
app_notification 1--many app_notification_read
user_account 1--many app_notification_read
```

Important scan data includes cultivar, ripeness, confidence, temperature, humidity, spoilage days, finger count, thumbnail, engineered features, treatment, current inventory status history, original AI output, notes, and per-camera evidence.

The current schema DDL is `docs/bananavision_schema_current.sql`, maintained at Alembic revision `0010_notification_read_receipts`. The companion data dictionary in `docs/schema_tables.md` lists all 25 application tables, enum types, keys, constraints and indexes. Actual PostgreSQL identifiers are lowercase snake_case; the dictionary uppercases them for ERD readability. `docs/bananavision_schema_final2.sql` is retained as the historical pre-normalization reference only.

## 9. Migration: `docs/migrations/001_feature_engineering.sql`

This is the historical manual SQL script. The versioned Alembic migration
`backend/migrations/versions/0002_feature_engineering.py` adds the nullable VPD
column without backfilling it. The 2026-10-18 Logs/Details integration only reads
stored values; it does not run either migration or derive missing historical VPD.

The migration:

1. Creates enum `treatmentenum` with `Natural` and `Ethephon` if absent.
2. Adds `treatment`, `harvested_at`, `treated_at`, and `spoiled_at` to `delivery_intake`.
3. Adds `dew_point`, `vpd`, `heat_index`, and `treatment` to `scan_classification`.
4. Backfills engineered features for existing rows with non-null temperature/humidity.

Formula intent:

- Dew point uses a Magnus-style logarithmic humidity calculation.
- VPD is saturation vapor pressure minus humidity-adjusted vapor pressure.
- Heat index converts Celsius to Fahrenheit, applies the heat-index approximation, and converts back.

The migration is additive and idempotent for columns/types, but it assumes the existing table names and columns already exist.

## 10. Frontend Pages and User Workflows

### Public/authenticated

- `Landing`: public entry screen.
- `Login`: username/password authentication and session initialization.
- `Dashboard`: current operator/admin summary, scan statistics, alerts, and shortcuts.
- `Kiosk`: scan-now workflow and live capture/result progress.
- `Logs`: scan history with filters and navigation to detail.
- `ScanDetail`: evidence, classification, notes, flags, status, and review data.
- `Analytics`: charts/aggregates for scan and quality trends.
- `Inventory`: intake/FIFO/spoilage-oriented inventory view.
- `DeviceStatus`: camera/system health view.
- `Profile`: profile/avatar, password/PIN, and theme-related controls.

### Administrator

- `UserManagement`: create/update users and roles.
- `SupplierManagement`: supplier records.
- `DeliveryIntake`: intake batches, supplier, treatment, and lifecycle information.
- `QualityControl`: flagged scans and review/override actions.
- `ActivityLog`: audit history.
- `SystemConfig`: camera/configuration, export, shutdown/restart controls.

Navigation visibility and page access are driven by authentication/role state in `AuthContext`, `App.tsx`, and the app shell.

## 11. Runtime Startup and Shutdown

FastAPI lifespan calls `run_startup()`, starts background tasks, yields while serving, cancels tasks, then calls `run_shutdown()`.

Expected runtime responsibilities include database initialization, camera setup, model loading, sensor polling, and cleanup. The currently implemented startup path uses SQLAlchemy metadata creation rather than a full Alembic migration runner. Camera/model/sensor readiness is exposed through `/health`.

## 12. Setup and Commands

### Backend

From `backend/`, use the project README and configuration files as the source of truth. Typical development command:

```text
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend requires a compatible Python environment, installed `requirements.txt`, a configured `.env`, and a reachable database for persistence. Real camera hardware, Arduino serial access, and model weight files are optional only for limited/mock or health-only development; the full scan pipeline needs them.

### Frontend

From `frontend/`:

```text
npm install
npm run dev
```

The frontend uses Vite. Set `VITE_API_URL` when the backend is not at the browser-host-derived default.

## 13. Verified Gaps and Consistency Warnings

These are important for any future AI or developer session:

- `docs/backend_plan.md` describes proposed architecture and files that are not all present. Treat it as design guidance, not an implementation inventory.
- The current backend startup uses `Base.metadata.create_all`; it does not automatically run the SQL migration file as an Alembic migration.
- Model weights exist locally under `backend/app/ml/weights/` but are ignored by Git. Provision them separately and verify metadata/hash for the deployed station.
- Frontend API typing is permissive in several places (`any`) and may not exactly match backend response schemas.
- Frontend scan trigger/client behavior and backend response details must be checked together when changing scan flows.
- Account creation/edit/reset, profile avatars and configuration saves await backend results; rejected requests must not publish local success. Keep failed-input/persistence behavior covered when changing other workflows.
- The frontend analytics experience primarily derives/display metrics locally in parts of the implementation even though backend analytics endpoints exist.
- Database naming/documentation has multiple naming conventions (`scan` vs `SCAN`, `intake` vs `DELIVERY_INTAKE`); confirm ORM `__tablename__` before writing SQL.
- WebSocket authentication and browser token handling should be reviewed together before production deployment.
- The backend package includes more routers than the original workflow diagram, including notifications, cameras, and system metrics.

## 14. How Future AI Sessions Should Use This File

Start here for project orientation, then open only the specific implementation file named by the task. Use the source files for exact code changes and this document for relationships, workflows, contracts, and known mismatches. After changing routes, schemas, models, or frontend API calls, update this document if the public behavior or architecture changed.
