# BananaVision — Complete Backend Integration Plan

## 1. Overview

BananaVision is a banana classification and spoilage prediction system for a capstone project. The frontend (React 19 + TypeScript + Vite + ShadCN) is already built but uses mock data. This plan designs the complete Python/FastAPI backend with PostgreSQL persistence, WebSocket real-time updates, YOLOv8n classification, Random Forest Regression spoilage prediction, and a multi-camera capture pipeline.

---

## 2. Backend Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         MINI PC (HOST)                               │
│                                                                      │
│  ┌──────────────┐    ┌───────────────────────────────────────────┐   │
│  │   Arduino     │    │           FastAPI Backend                 │   │
│  │   + DHT22     │◄──►│                                          │   │
│  │  (Serial USB) │    │  ┌─────────┐  ┌──────────┐  ┌────────┐  │   │
│  └──────────────┘    │  │  REST   │  │WebSocket │  │ Startup│  │   │
│                       │  │  API    │  │  Hub     │  │ Manager│  │   │
│  ┌──────────────┐    │  └────┬────┘  └────┬─────┘  └───┬────┘  │   │
│  │  4x USB      │    │       │             │            │        │   │
│  │  Webcams     │◄──►│  ┌────▼─────────────▼────────────▼────┐   │   │
│  │  (Top/L/R/B) │    │  │           Service Layer            │   │   │
│  └──────────────┘    │  │                                    │   │   │
│                       │  │  ┌──────────┐ ┌──────────────────┐│   │   │
│                       │  │  │ Camera   │ │  Classification  ││   │   │
│                       │  │  │ Manager  │ │  Pipeline        ││   │   │
│                       │  │  │ (OpenCV) │ │  (YOLOv8n + RFR) ││   │   │
│                       │  │  └──────────┘ └──────────────────┘│   │   │
│                       │  │  ┌──────────┐ ┌──────────────────┐│   │   │
│                       │  │  │ Sensor   │ │  Scan Fusion     ││   │   │
│                       │  │  │ Reader   │ │  Engine          ││   │   │
│                       │  │  │ (Serial) │ │  (Multi-cam)     ││   │   │
│                       │  │  └──────────┘ └──────────────────┘│   │   │
│                       │  └───────────────────┬───────────────┘   │   │
│                       │                      │                    │   │
│                       │              ┌───────▼───────┐            │   │
│                       │              │  PostgreSQL   │            │   │
│                       │              │  Database     │            │   │
│                       │              └───────────────┘            │   │
│                       └───────────────────────────────────────────┘   │
│                                           │                          │
│                                    ┌──────▼──────┐                   │
│                                    │   React     │                   │
│                                    │   Frontend  │                   │
│                                    │   (Vite)    │                   │
│                                    └─────────────┘                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Optimized Folder Structure

```
BananaVision/
├── frontend/                        # Existing React app (unchanged)
│   ├── src/
│   ├── package.json
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app entry, lifespan events
│   │   ├── config.py                # Pydantic settings, .env loader
│   │   │
│   │   ├── api/                     # ── Route Layer ──
│   │   │   ├── __init__.py
│   │   │   ├── deps.py              # Shared dependencies (get_db, get_current_user)
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py        # Aggregated v1 router
│   │   │       ├── auth.py          # POST /login, /logout, PIN swap
│   │   │       ├── scans.py         # CRUD scans, trigger scan
│   │   │       ├── devices.py       # Camera status, health checks
│   │   │       ├── sensors.py       # DHT22 latest/history
│   │   │       ├── users.py         # User management (admin)
│   │   │       ├── suppliers.py     # Supplier CRUD
│   │   │       ├── intakes.py       # Intake management
│   │   │       ├── analytics.py     # Aggregated analytics queries
│   │   │       ├── config.py        # System config get/update
│   │   │       ├── activity.py      # Activity logs
│   │   │       └── quality.py       # Quality control / flagged scans
│   │   │
│   │   ├── models/                  # ── SQLAlchemy ORM Models ──
│   │   │   ├── __init__.py
│   │   │   ├── user_account.py
│   │   │   ├── user_role.py
│   │   │   ├── operator_profile.py
│   │   │   ├── admin_profile.py
│   │   │   ├── scan.py
│   │   │   ├── scan_detection.py    # Per-camera detections
│   │   │   ├── scan_image.py        # Captured images metadata
│   │   │   ├── scan_note.py
│   │   │   ├── sensor_reading.py
│   │   │   ├── device.py
│   │   │   ├── supplier.py
│   │   │   ├── intake.py
│   │   │   ├── activity_log.py
│   │   │   └── system_config.py
│   │   │
│   │   ├── schemas/                 # ── Pydantic Request/Response ──
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── scan.py
│   │   │   ├── device.py
│   │   │   ├── sensor.py
│   │   │   ├── user.py
│   │   │   ├── supplier.py
│   │   │   ├── intake.py
│   │   │   ├── analytics.py
│   │   │   ├── activity.py
│   │   │   └── config.py
│   │   │
│   │   ├── services/                # ── Business Logic Layer ──
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py      # JWT tokens, password hashing, PIN verification
│   │   │   ├── scan_service.py      # Orchestrates full scan pipeline
│   │   │   ├── camera_manager.py    # OpenCV camera init, capture, release
│   │   │   ├── classification.py    # YOLOv8n inference wrapper
│   │   │   ├── spoilage.py          # Random Forest Regression predictor
│   │   │   ├── fusion_engine.py     # Multi-camera result merging
│   │   │   ├── sensor_reader.py     # Arduino serial DHT22 reader
│   │   │   ├── user_service.py
│   │   │   ├── supplier_service.py
│   │   │   ├── intake_service.py
│   │   │   └── analytics_service.py
│   │   │
│   │   ├── ws/                      # ── WebSocket Layer ──
│   │   │   ├── __init__.py
│   │   │   ├── manager.py           # ConnectionManager (broadcast, rooms)
│   │   │   ├── events.py            # Event type definitions & payloads
│   │   │   └── handlers.py          # WS endpoint handler
│   │   │
│   │   ├── core/                    # ── Cross-Cutting Concerns ──
│   │   │   ├── __init__.py
│   │   │   ├── security.py          # JWT encode/decode, password hashing
│   │   │   ├── database.py          # SQLAlchemy engine, session factory
│   │   │   ├── startup.py           # Boot sequence, camera lock, model warmup
│   │   │   └── exceptions.py        # Custom HTTP exceptions
│   │   │
│   │   └── ml/                      # ── Machine Learning Assets ──
│   │       ├── __init__.py
│   │       ├── yolo_model.py        # YOLOv8n model loader & inference
│   │       ├── rfr_model.py         # Random Forest model loader & predict
│   │       └── weights/             # Stored model files
│   │           ├── banana_yolov8n.pt
│   │           └── spoilage_rfr.joblib
│   │
│   ├── alembic/                     # ── Database Migrations ──
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── captures/                    # ── Captured Images (runtime) ──
│   │   └── .gitkeep
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_scans.py
│   │   ├── test_fusion.py
│   │   └── test_spoilage.py
│   │
│   ├── .env.example                 # Template for environment variables
│   ├── .env                         # Local overrides (gitignored)
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
│
├── .gitignore
└── README.md
```

---

## 4. Environment Variable Configuration (`.env`)

```ini
# ── Application ──
APP_ENV=development                  # development | staging | production
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true
APP_SECRET_KEY=change-me-to-a-secure-random-string
APP_CORS_ORIGINS=http://localhost:5173

# ── Database ──
DATABASE_URL=postgresql+asyncpg://bv_user:bv_pass@localhost:5432/bananavision
DATABASE_ECHO=false                  # SQL query logging

# ── Authentication ──
JWT_SECRET_KEY=your-jwt-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=480  # 8-hour shift

# ── Camera Configuration ──
CAMERA_DEVICE_IDS=0,1,2,3            # /dev/video0..3
CAMERA_LABELS=Top,Left,Right,Back
CAMERA_RESOLUTION_W=1920
CAMERA_RESOLUTION_H=1080
CAMERA_WARMUP_FRAMES=5               # Frames to discard on init
CAMERA_CAPTURE_TIMEOUT_MS=3000

# ── Sensor (Arduino DHT22) ──
SENSOR_SERIAL_PORT=/dev/ttyUSB0
SENSOR_BAUD_RATE=9600
SENSOR_READ_INTERVAL_S=5

# ── ML Models ──
YOLO_MODEL_PATH=app/ml/weights/banana_yolov8n.pt
YOLO_CONFIDENCE_THRESHOLD=0.50
YOLO_IOU_THRESHOLD=0.45
RFR_MODEL_PATH=app/ml/weights/spoilage_rfr.joblib

# ── Storage ──
CAPTURE_DIR=captures
MAX_CAPTURES_RETENTION_DAYS=30
```

> [!TIP]
> Use Pydantic `BaseSettings` in `app/config.py` to auto-load `.env` with type validation, defaults, and `@validator` decorators for complex parsing (e.g., splitting `CAMERA_DEVICE_IDS` into a list).

---

## 5. Database Schema

```mermaid
erDiagram
    user_role {
        uuid rl_id PK
        varchar rl_name UK
        jsonb rl_permissions
    }

    user_account {
        uuid ua_id PK
        varchar ua_username UK
        varchar ua_fullname
        uuid ua_role_id FK
        varchar ua_pwd_hash
        enum ua_status "Active | Inactive"
        varchar ua_avatar_url
        boolean ua_req_pwd_change
        varchar ua_pwd_setup_reason
        timestamp ua_last_active
        timestamp ua_created_at
        timestamp ua_updated_at
    }

    admin_profile {
        uuid ap_id PK
        uuid ap_ua_id FK
        timestamp ap_created_at
        timestamp ap_updated_at
    }

    operator_profile {
        uuid op_id PK
        uuid op_ua_id FK
        varchar op_pin_hash
        boolean op_req_pin_change
        varchar op_pin_setup_reason
        int op_total_scans
        int op_total_flagged_scans
        timestamp op_created_at
        timestamp op_updated_at
    }

    suppliers {
        uuid id PK
        varchar name UK
        varchar contact_person
        varchar contact_phone
        enum status "Active | Inactive"
        timestamp date_added
        timestamp updated_at
    }

    intakes {
        uuid id PK
        uuid supplier_id FK
        date intake_date
        enum status "Active | Depleted"
        timestamp created_at
        timestamp updated_at
    }

    scans {
        uuid id PK
        uuid operator_id FK
        uuid intake_id FK
        timestamp scanned_at
        varchar cultivar "Lakatan | Latundan | Saba"
        varchar ripeness "Unripe | Ripe | Overripe | Rotten"
        float confidence
        float temperature
        float humidity
        varchar spoilage_days
        int finger_count
        enum inventory_status "In Stock | Sold | For Processing | Spoiled"
        timestamp status_updated_at
        boolean flagged
        boolean is_overridden
        jsonb original_ai_result
        timestamp created_at
    }

    scan_detections {
        uuid id PK
        uuid scan_id FK
        varchar camera_id
        varchar camera_label
        varchar detected_cultivar
        varchar detected_ripeness
        float confidence
        int finger_count
        jsonb bounding_boxes "Array of {x,y,w,h,class,conf}"
        float inference_time_ms
        timestamp captured_at
    }

    scan_images {
        uuid id PK
        uuid scan_id FK
        varchar camera_id
        varchar file_path
        int width
        int height
        int file_size_bytes
        timestamp captured_at
    }

    scan_notes {
        uuid id PK
        uuid scan_id FK
        varchar author_name
        text note
        timestamp created_at
    }

    sensor_readings {
        uuid id PK
        float temperature
        float humidity
        timestamp recorded_at
        varchar source "DHT22"
    }

    devices {
        uuid id PK
        varchar camera_id UK
        varchar label
        enum status "Online | Offline"
        varchar resolution
        timestamp last_seen
        timestamp created_at
    }

    activity_logs {
        uuid id PK
        uuid user_id FK
        varchar action
        text details
        varchar ip_address
        timestamp created_at
    }

    system_config {
        uuid id PK
        varchar key UK
        text value
        timestamp updated_at
    }

    user_role ||--o{ user_account : "has"
    user_account ||--o| admin_profile : "has_admin"
    user_account ||--o| operator_profile : "has_operator"
    operator_profile ||--o{ scans : "operates"
    user_account ||--o{ activity_logs : "performs"
    suppliers ||--o{ intakes : "supplies"
    intakes ||--o{ scans : "contains"
    scans ||--o{ scan_detections : "has"
    scans ||--o{ scan_images : "has"
    scans ||--o{ scan_notes : "has"
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| `scan_detections` table | Stores per-camera raw detection results before fusion, enabling audit and reprocessing |
| `scan_images` table | Stores file paths (not BLOBs) for captured images, keeping DB lean |
| `sensor_readings` separate | Time-series sensor data decoupled from scans for continuous monitoring |
| `jsonb bounding_boxes` | Flexible storage for variable-count YOLO detections per image |
| `original_ai_result` on scans | Preserves AI prediction when an operator overrides the classification |
| UUIDs everywhere | Avoids sequential ID guessing, safe for API exposure |

---

## 6. Data Flow: Capture → Detection → Regression → Frontend Update

```
Operator Presses "Scan Now" on Kiosk
        │
        ▼
┌───────────────────────────┐
│ 1. POST /api/v1/scans/    │   Frontend sends { supplier_id, intake_id }
│    trigger                 │
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐        ┌─────────────────┐
│ 2. WS: scan:started       │───────►│ Frontend shows   │
│    {scan_id, status}       │        │ progress UI      │
└──────────┬────────────────┘        └─────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 3. CameraManager.capture()│   Captures from all 4 cameras
│    (parallel via threads)  │   Saves images → captures/{scan_id}/
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐        ┌─────────────────┐
│ 4. WS: scan:captured      │───────►│ Frontend updates │
│    {camera_id, image_url}  │        │ camera status    │
└──────────┬────────────────┘        └─────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 5. YOLOv8n Inference      │   Runs on each of 4 images
│    Per-camera detections   │   → Stores in scan_detections
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐        ┌─────────────────┐
│ 6. WS: scan:detected      │───────►│ Frontend shows   │
│    {detections_summary}    │        │ detection overlay │
└──────────┬────────────────┘        └─────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 7. FusionEngine.merge()   │   Merges 4-camera detections
│    → Final cultivar,       │   into single classification
│      ripeness, confidence, │   using weighted voting
│      finger_count          │
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 8. SensorReader.latest()  │   Gets latest DHT22 reading
│    → temperature, humidity │
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 9. RFR Spoilage Predict   │   Input: cultivar, ripeness,
│    → spoilage_days         │   temperature, humidity
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐        ┌─────────────────┐
│ 10. WS: scan:completed    │───────►│ Frontend shows   │
│     {full ScanResult}      │        │ result card      │
└──────────┬────────────────┘        └─────────────────┘
           │
           ▼
┌───────────────────────────┐
│ 11. Persist to PostgreSQL  │   scans, scan_detections,
│     activity_log           │   scan_images, activity_logs
└────────────────────────────┘
```

---

## 7. WebSocket Event Design

### Connection

```
ws://localhost:8000/api/v1/ws?token={jwt_token}
```

### Event Protocol

All messages use a JSON envelope:

```json
{
  "event": "scan:started",
  "data": { ... },
  "timestamp": "2026-04-21T12:00:00Z"
}
```

### Events Table

| Event | Direction | Payload | Description |
|---|---|---|---|
| `scan:started` | Server → Client | `{ scan_id, operator, supplier }` | Scan pipeline initiated |
| `scan:capturing` | Server → Client | `{ scan_id, camera_id, camera_label, index, total }` | Individual camera capturing |
| `scan:captured` | Server → Client | `{ scan_id, camera_id, image_url }` | Single camera capture done |
| `scan:detecting` | Server → Client | `{ scan_id, progress_pct }` | YOLOv8n running |
| `scan:detected` | Server → Client | `{ scan_id, camera_id, detections[], inference_ms }` | Per-camera detection results |
| `scan:analyzing` | Server → Client | `{ scan_id, progress_pct }` | Fusion + RFR running |
| `scan:completed` | Server → Client | `{ scan_id, result: ScanResult }` | Final merged result |
| `scan:failed` | Server → Client | `{ scan_id, error, stage }` | Pipeline failure |
| `sensor:update` | Server → Client | `{ temperature, humidity, recorded_at }` | Periodic DHT22 reading |
| `device:status` | Server → Client | `{ camera_id, status, last_seen }` | Camera online/offline change |
| `notification` | Server → Client | `{ type, title, message, href }` | System notifications |

### Rooms / Channels

| Room | Subscribers | Events |
|---|---|---|
| `kiosk` | Kiosk page clients | All `scan:*`, `sensor:update` |
| `dashboard` | Dashboard/admin clients | `scan:completed`, `sensor:update`, `notification` |
| `devices` | Device status page | `device:status` |

---

## 8. Capture Strategy Comparison

### Sequential Capture

```python
# Pseudocode
for camera in cameras:
    frame = camera.read()
    save(frame)
    ws_broadcast("scan:captured", camera.id)
```

| Aspect | Assessment |
|---|---|
| **Speed** | ❌ Slow — ~1s per camera × 4 = ~4s total |
| **Consistency** | ⚠️ Subject moves between captures, inconsistent angles |
| **Simplicity** | ✅ Simple loop, no threading complexity |
| **Resource usage** | ✅ Low — one camera active at a time |
| **Model reliability** | ⚠️ Temporal offset between views may cause mismatched ripeness readings |

### Parallel Capture

```python
# Pseudocode
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(camera.read) for camera in cameras]
    frames = [f.result(timeout=3) for f in futures]
    for frame, camera in zip(frames, cameras):
        save(frame)
        ws_broadcast("scan:captured", camera.id)
```

| Aspect | Assessment |
|---|---|
| **Speed** | ✅ Fast — all cameras fire simultaneously, ~1s total |
| **Consistency** | ✅ All images captured at the same instant → same banana state |
| **Complexity** | ⚠️ Requires thread-safe camera access, error handling per thread |
| **Resource usage** | ⚠️ Higher — 4 concurrent USB transfers, need adequate USB bandwidth |
| **Model reliability** | ✅ Best — identical temporal snapshot ensures consistent multi-view fusion |

### ✅ Recommendation: **Parallel Capture with Graceful Fallback**

```python
async def capture_all(cameras: list[Camera]) -> list[CaptureResult]:
    """Primary: parallel. Fallback: sequential on failure."""
    try:
        return await parallel_capture(cameras, timeout=3.0)
    except CaptureTimeoutError:
        logger.warning("Parallel capture timeout, falling back to sequential")
        return await sequential_capture(cameras)
```

**Rationale:** Parallel capture is strictly better for model reliability because all 4 views represent the exact same physical state of the banana. The fallback ensures the system never fails even if USB bandwidth is constrained.

---

## 9. Multi-Camera Fusion Strategy

### Problem
Each of the 4 cameras produces independent YOLOv8n detections. We need a single authoritative classification per banana hand.

### Strategy: Confidence-Weighted Majority Voting

```python
def fuse_detections(detections: list[CameraDetection]) -> FusedResult:
    """
    Merge detections from 4 cameras into a single classification.
    
    Steps:
      1. Collect all (cultivar, confidence) pairs across cameras
      2. Weight each vote by its detection confidence
      3. Winner = class with highest total weighted score
      4. Same process for ripeness
      5. Finger count = max across cameras (most complete view)
      6. Final confidence = weighted average of winning class confidences
    """
```

### Detailed Fusion Algorithm

```
For each classification dimension (cultivar, ripeness):

  1. COLLECT votes from all cameras:
     Camera_Top:    Lakatan  (0.94)
     Camera_Left:   Lakatan  (0.87)
     Camera_Right:  Latundan (0.72)    ← disagreement
     Camera_Back:   Lakatan  (0.91)

  2. WEIGHT by confidence:
     Lakatan:  0.94 + 0.87 + 0.91 = 2.72
     Latundan: 0.72                = 0.72

  3. SELECT winner: Lakatan (75% vote weight)

  4. FINAL confidence: mean of winning class
     = (0.94 + 0.87 + 0.91) / 3 = 0.907

  5. CONFLICT FLAG: If winner has < 60% of total weight,
     auto-flag scan for operator review
```

### Finger Count Strategy

```
finger_count = max(
    camera_top.fingers,      # Best overhead view
    camera_left.fingers,
    camera_right.fingers,
    camera_back.fingers
)
```

> [!NOTE]
> The `max()` strategy works because each camera sees at most a subset of total fingers due to occlusion. The camera with the best viewpoint captures the most complete count.

### Handling Conflicting Predictions

| Scenario | Action |
|---|---|
| 3+ cameras agree (>75% weight) | Use majority, high confidence |
| 2v2 split with similar confidence | Flag for operator review, use higher-confidence pair |
| 1 camera disagrees with low confidence | Discard outlier, use remaining 3 |
| All cameras low confidence (<50%) | Flag for manual review, suggest re-scan |
| Camera returns no detection | Exclude from fusion, note in `scan_detections` |

---

## 10. Duplicate Detection Handling

### Problem
Multiple cameras may detect the **same banana finger** from different angles, inflating the finger count and creating redundant bounding boxes.

### Strategy: Do NOT Merge Cross-Camera Boxes

Key insight: since each camera views the banana from a fundamentally different angle (top, left, right, back), the bounding boxes from different cameras are **not in the same coordinate space** and cannot be directly compared via IoU.

Instead:

```
┌───────────────────────────────────────────────────┐
│             Duplicate Handling Pipeline            │
│                                                    │
│  1. INTRA-CAMERA NMS (Non-Max Suppression)         │
│     • YOLOv8n already applies NMS per inference    │
│     • Additional IoU threshold check at 0.45       │
│     • Removes overlapping boxes from SAME camera   │
│                                                    │
│  2. PER-CAMERA FINGER COUNT                        │
│     • Each camera reports its own finger count     │
│     • count = number of "finger" class detections  │
│                                                    │
│  3. CROSS-CAMERA AGGREGATION                       │
│     • finger_count = max(per_camera_counts)        │
│     • NOT sum — avoids double-counting             │
│     • cultivar/ripeness via weighted voting (§9)   │
│                                                    │
│  4. SANITY CHECKS                                  │
│     • If max_fingers > 2× median_fingers: flag     │
│     • If any camera has 0 detections: note anomaly │
│     • banana hands typically have 5–20 fingers     │
└───────────────────────────────────────────────────┘
```

### Why `max()` instead of `mean()` or `sum()`?

| Method | Problem |
|---|---|
| `sum()` | Counts same fingers from multiple angles → inflated count |
| `mean()` | Underestimates when some cameras have partial occlusion |
| `max()` | ✅ Assumes the best-angle camera sees the most complete view |

---

## 11. System Startup / Boot Workflow

```
┌─────────────────────────────────────────────────────────┐
│                SYSTEM BOOT SEQUENCE                      │
│          (Runs in FastAPI lifespan handler)               │
│                                                          │
│  ┌─── Phase 1: Configuration ──────────────────────┐     │
│  │  1. Load .env → Pydantic Settings                │     │
│  │  2. Validate all required env vars                │     │
│  │  3. Create captures/ directory if missing         │     │
│  └──────────────────────────────────────────────────┘     │
│                       │                                   │
│                       ▼                                   │
│  ┌─── Phase 2: Database ───────────────────────────┐     │
│  │  4. Connect to PostgreSQL                         │     │
│  │  5. Run Alembic migrations (auto)                 │     │
│  │  6. Seed default admin user if empty              │     │
│  └──────────────────────────────────────────────────┘     │
│                       │                                   │
│                       ▼                                   │
│  ┌─── Phase 3: ML Models ──────────────────────────┐     │
│  │  7. Load YOLOv8n weights into memory              │     │
│  │  8. Warmup: run dummy inference (reduces          │     │
│  │     first-scan latency)                           │     │
│  │  9. Load RFR model from .joblib                   │     │
│  │ 10. Validate model outputs with test input        │     │
│  └──────────────────────────────────────────────────┘      │
│                       │                                    │
│                       ▼                                   │
│  ┌─── Phase 4: Camera Initialization ──────────────┐     │
│  │ 11. Open all 4 cameras via OpenCV                 │     │
│  │ 12. Lock device file descriptors (exclusive)      │     │
│  │ 13. Set resolution per .env config                │     │
│  │ 14. Discard warmup frames (CAMERA_WARMUP_FRAMES)  │     │
│  │ 15. Verify each camera returns valid frames       │     │
│  │ 16. Register camera status in DB (devices table)  │     │
│  │ 17. Mark failed cameras as Offline                │     │
│  └──────────────────────────────────────────────────┘     │
│                       │                                   │
│                       ▼                                   │
│  ┌─── Phase 5: Sensor Initialization ──────────────┐     │
│  │ 18. Open serial port to Arduino                   │     │
│  │ 19. Verify DHT22 data reception                   │     │
│  │ 20. Start background sensor polling task          │     │
│  │     (asyncio.create_task)                         │     │
│  └──────────────────────────────────────────────────┘     │
│                       │                                   │
│                       ▼                                   │
│  ┌─── Phase 6: Ready ─────────────────────────────┐     │
│  │ 21. WS broadcast: device:status for all cameras   │     │
│  │ 22. Log startup summary                           │     │
│  │ 23. API now accepting requests                    │     │
│  └──────────────────────────────────────────────────┘     │
│                                                          │
│  ┌─── Shutdown Hook ──────────────────────────────┐     │
│  │  • Release all camera captures                    │     │
│  │  • Close serial port                              │     │
│  │  • Close DB connection pool                       │     │
│  │  • Cancel background tasks                        │     │
│  └──────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Camera Locking Strategy

```python
class CameraManager:
    """Initializes cameras ONCE at boot, keeps handles open."""
    
    def __init__(self, device_ids: list[int]):
        self._cameras: dict[int, cv2.VideoCapture] = {}
        self._locks: dict[int, threading.Lock] = {}
    
    async def initialize(self):
        """Called once during FastAPI lifespan startup."""
        for dev_id in self.device_ids:
            cap = cv2.VideoCapture(dev_id)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_RESOLUTION_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_RESOLUTION_H)
            
            # Discard warmup frames
            for _ in range(settings.CAMERA_WARMUP_FRAMES):
                cap.read()
            
            if cap.isOpened():
                self._cameras[dev_id] = cap
                self._locks[dev_id] = threading.Lock()
            else:
                logger.error(f"Camera {dev_id} failed to initialize")
    
    def capture(self, device_id: int) -> np.ndarray:
        """Thread-safe single frame capture."""
        with self._locks[device_id]:
            ret, frame = self._cameras[device_id].read()
            if not ret:
                raise CameraError(f"Camera {device_id} read failed")
            return frame
```

> [!IMPORTANT]
> Cameras are opened **once** at boot and **never released** until shutdown. This eliminates the 1–3 second reinitialization penalty per scan that would occur if cameras were opened/closed each time.

---

## 12. REST API Routes Summary

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Public | Username + password login → JWT |
| `POST` | `/api/v1/auth/logout` | User | Invalidate session |
| `POST` | `/api/v1/auth/swap` | User | PIN-based operator swap |
| `POST` | `/api/v1/auth/change-password` | User | Password change flow |
| `POST` | `/api/v1/auth/change-pin` | User | PIN change flow |
| `POST` | `/api/v1/scans/trigger` | Operator | Trigger full scan pipeline |
| `GET` | `/api/v1/scans` | User | List scans (paginated, filterable) |
| `GET` | `/api/v1/scans/{id}` | User | Single scan detail + detections |
| `PATCH` | `/api/v1/scans/{id}` | Admin | Override classification |
| `PATCH` | `/api/v1/scans/{id}/flag` | User | Flag/unflag scan |
| `POST` | `/api/v1/scans/{id}/notes` | User | Add scan note |
| `GET` | `/api/v1/scans/{id}/notes` | User | Get scan notes |
| `GET` | `/api/v1/devices` | User | List cameras + status |
| `GET` | `/api/v1/sensors/latest` | User | Latest DHT22 reading |
| `GET` | `/api/v1/sensors/history` | User | Sensor history (time range) |
| `GET` | `/api/v1/users` | Admin | List users |
| `POST` | `/api/v1/users` | Admin | Create user |
| `PATCH` | `/api/v1/users/{id}` | Admin | Update user |
| `GET` | `/api/v1/suppliers` | Admin | List suppliers |
| `POST` | `/api/v1/suppliers` | Admin | Create supplier |
| `PATCH` | `/api/v1/suppliers/{id}` | Admin | Update supplier |
| `GET` | `/api/v1/intakes` | Admin | List intakes |
| `PATCH` | `/api/v1/intakes/{id}/status` | Admin | Bulk update intake inventory |
| `GET` | `/api/v1/analytics/summary` | User | Dashboard aggregate stats |
| `GET` | `/api/v1/analytics/trends` | User | Time-series scan trends |
| `GET` | `/api/v1/activity` | Admin | Activity logs (paginated) |
| `GET` | `/api/v1/config` | Admin | Get system config |
| `PATCH` | `/api/v1/config` | Admin | Update system config |
| `GET` | `/api/v1/quality/flagged` | Admin | Flagged scans for review |

---

## 13. Proposed Changes to Frontend

> [!NOTE]
> The frontend code changes are **not part of this plan's scope**. This section documents what will change in the frontend in a *future phase* once the backend is built.

| Current (Mock) | Future (Backend) |
|---|---|
| [AppContext.tsx](file:///Users/khensorela/BananaVision/frontend/src/context/AppContext.tsx) generates mock data | Replace with `useEffect` + `fetch()` to REST API |
| `startScan()` uses `setTimeout` simulation | POST to `/api/v1/scans/trigger`, listen to WS events |
| [getSpoilageDays()](file:///Users/khensorela/BananaVision/frontend/src/lib/utils.ts#9-62) in [utils.ts](file:///Users/khensorela/BananaVision/frontend/src/lib/utils.ts) | Server-side RFR prediction, received via WS/REST |
| Local state in `useState` | React Query (or SWR) for server state + cache |
| `useLocalStorage` for auth | JWT stored in `httpOnly` cookie or `localStorage` |
| Mock [generateDevices()](file:///Users/khensorela/BananaVision/frontend/src/lib/mock-data.ts#220-256) | `GET /api/v1/devices` with live camera status |
| No real sensor data | `sensor:update` WS events for live temp/humidity |

---

## 14. Key Python Dependencies

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30.0
alembic>=1.14.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.18
ultralytics>=8.3.0          # YOLOv8
scikit-learn>=1.6.0          # Random Forest
joblib>=1.4.0                # Model serialization
opencv-python-headless>=4.10.0
pyserial>=3.5                # Arduino serial
numpy>=2.0.0
Pillow>=11.0.0
websockets>=14.0
```

---

## 15. Verification Plan

Since this is a **planning document** (no code is being written yet), verification applies to the next phase:

### Automated Tests (to be written during implementation)
- `pytest` test suite with `httpx.AsyncClient` for API routes
- `test_fusion.py` — unit tests for the multi-camera fusion engine with known inputs/outputs
- `test_spoilage.py` — validate RFR model integration returns expected ranges
- `test_camera_manager.py` — mock OpenCV captures, verify parallel capture logic
- `test_auth.py` — JWT flow, password change, PIN swap

### Manual Verification (post-implementation)
1. Start the backend with `uvicorn app.main:app --reload`
2. Open Kiosk page → trigger a scan → verify WebSocket events arrive in browser DevTools
3. Check PostgreSQL directly to verify scan records persist
4. Verify DHT22 sensor readings appear in the dashboard
5. Test operator PIN swap flow end-to-end
6. Test the admin user management page with real API calls

---

## User Review Required

> [!IMPORTANT]
> **This is a design-only plan.** No code is being written or files created at this stage. Please review the architecture, folder structure, database schema, and strategies above. Once approved, I will proceed to scaffold the backend code.

Key decisions that need your input:

1. **Authentication**: JWT in `httpOnly` cookies vs. `localStorage` + `Authorization` header?
2. **Database hosting**: Local PostgreSQL on the mini PC, or a Docker container?
3. **Model weights**: Do you already have trained `banana_yolov8n.pt` and `spoilage_rfr.joblib` files, or should scaffolding include placeholder inference?
4. **Arduino protocol**: What format does the DHT22 data come over serial? (e.g., `"TEMP:26.5,HUM:72.3\n"`)
5. **Do you want me to scaffold the full backend code after approval**, or would you prefer to implement it incrementally module by module?
