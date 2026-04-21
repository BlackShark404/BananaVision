# BananaVision Backend

Python/FastAPI backend for the BananaVision banana classification and spoilage prediction system.

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL + SQLAlchemy (async) + Alembic
- **Auth:** JWT (python-jose) + bcrypt
- **ML:** YOLOv8n (ultralytics) + Random Forest Regression (scikit-learn)
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
│   │   ├── classification.py # YOLOv8n inference
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

## Default Credentials

- **Admin:** `admin` / `admin`
- **Default PIN:** `1234`

## WebSocket

```
ws://localhost:8000/api/v1/ws?token=JWT&rooms=kiosk,dashboard
```

Events: `scan:started`, `scan:capturing`, `scan:captured`, `scan:detecting`, `scan:detected`, `scan:analyzing`, `scan:completed`, `scan:failed`, `sensor:update`, `device:status`, `notification`
