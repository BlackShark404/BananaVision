# BananaVision Backend

Python/FastAPI backend for the BananaVision banana classification and spoilage prediction system.

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL + SQLAlchemy (async) + Alembic
- **Auth:** JWT (python-jose) + bcrypt
- **ML:** YOLO26 (ultralytics) + Random Forest Regression (scikit-learn)
- **Camera:** OpenCV (multi-camera parallel capture)
- **Sensor:** Arduino DHT22 via pyserial
- **Real-time:** WebSocket with room-based pub/sub

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up PostgreSQL
createdb bananavision
# Edit .env with your DB credentials

# 4. Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Open API docs
open http://localhost:8000/docs
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry + lifespan
│   ├── config.py             # Pydantic settings (.env loader)
│   ├── api/                  # Route layer
│   │   ├── deps.py           # Shared dependencies (auth, DB)
│   │   └── v1/               # Versioned routes
│   ├── models/               # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # Business logic
│   │   ├── camera_manager.py # Multi-camera capture pipeline
│   │   ├── classification.py # YOLO26 inference
│   │   ├── spoilage.py       # RFR spoilage prediction
│   │   ├── fusion_engine.py  # Multi-camera result merging
│   │   ├── sensor_reader.py  # DHT22 serial reader
│   │   └── scan_service.py   # Scan pipeline orchestrator
│   ├── ws/                   # WebSocket layer
│   ├── core/                 # Security, DB, startup, exceptions
│   └── ml/                   # Model weights
├── captures/                 # Runtime captured images
├── tests/                    # Test suite
├── .env                      # Environment variables
└── requirements.txt          # Python dependencies
```

## API Documentation

Once running, visit:
- **Swagger:** http://localhost:8000/docs  
- **ReDoc:** http://localhost:8000/redoc  
- **Health:** http://localhost:8000/health  

## Initial administrator and temporary credentials

On an empty database, startup requires `BOOTSTRAP_ADMIN_PASSWORD` in the backend environment. Choose a unique password of 12–72 UTF-8 bytes and set `BOOTSTRAP_ADMIN_USERNAME` if the default username `admin` is unsuitable. No password is logged. Sign in with those credentials, replace the password, then remove the bootstrap secret from the environment. Existing accounts are unchanged; rotate any old shared credentials through User Management.

Account creation and administrator resets generate unique temporary credentials. The authenticated administrator sees them once in a handoff dialog and shares them privately with the owner. They are not stored in browser storage or audit logs. Owners must replace them on first use; setup authorization expires after ten minutes and cannot access normal APIs or WebSockets. An expired setup requires signing in again.

The destructive demo seed utility requires a non-production environment and the same bootstrap configuration. Its fixture operator is inactive with no usable PIN; an administrator must reset credentials and activate it for use.

## Power commands and data retention

Power endpoints check the command exit code and report OS acceptance, not proof of completed reboot. They reject requests during an active scan or camera mapping. Windows schedules power actions after ten seconds; Linux/macOS use a one-minute delay and noninteractive `sudo -n`. Configure host permissions and service autostart using [the kiosk guide](../docs/kiosk-autostart-guide.md); verify these on the deployed station.

The retention worker checks every six hours, respects the enable flag, and removes expired scan/audit rows before deleting UUID capture directories. Old capture directories without a persisted scan are retried as orphans. Failed scans remove their own captures immediately. Profile totals cover all retained rows, so enabled retention reduces historical totals. The scan-summary CSV excludes accounts, settings, audit logs and images and cannot restore the database.

## WebSocket

```
ws://localhost:8000/api/v1/ws?token=JWT&rooms=kiosk,dashboard
```

Events: `scan:started`, `scan:capturing`, `scan:captured`, `scan:detecting`, `scan:detected`, `scan:analyzing`, `scan:completed`, `scan:failed`, `sensor:update`, `device:status`, `notification`
