"""
BananaVision Backend — FastAPI Application Entry Point.

Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from app.core.http import CorsFastAPI
from app.api.v1.scan_evidence import router as scan_evidence_router

from app.config import get_settings
from app.api.v1.router import v1_router
from app.ws.handlers import websocket_endpoint
from app.core.startup import run_startup, run_shutdown, start_background_tasks
from app.core.time import manila_struct_time
from app.services.runtime_operations import StationAdmissionMiddleware

settings = get_settings()

# ── Logging (Console + File) ────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
log_level = logging.DEBUG if settings.app_debug else logging.INFO
# Every log line is stamped in Asia/Manila, whatever zone the server or container uses.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S +08:00"
logging.Formatter.converter = staticmethod(manila_struct_time)

logging.basicConfig(
    level=log_level,
    format=log_format,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),                          # Console output
        RotatingFileHandler(                              # File output → logs/bananavision.log
            os.path.join(LOG_DIR, "bananavision.log"),
            maxBytes=5 * 1024 * 1024,                     # 5 MB per file
            backupCount=5,                                # Keep 5 rotated backups
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("bananavision")


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    # Startup
    await run_startup()
    background_tasks = await start_background_tasks()

    yield  # App is running

    # Shutdown
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await run_shutdown()


# ── App Factory ──────────────────────────────────────────────────────────────

# API docs describe every route and are not published with the public dashboard.
_docs_enabled = not settings.is_production

app = CorsFastAPI(
    title="BananaVision API",
    description=(
        "Banana Classification & Spoilage Prediction System — "
        "YOLO + Random Forest Regression"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# CorsFastAPI wraps both admission and the server error handler.
app.add_middleware(StationAdmissionMiddleware)

# ── Routes ───────────────────────────────────────────────────────────────────
app.include_router(v1_router)

# ── WebSocket ────────────────────────────────────────────────────────────────
app.add_api_websocket_route("/api/v1/ws", websocket_endpoint)

# Stored evidence shares scan ownership authorization.
app.include_router(scan_evidence_router)


# ── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    from app.services.camera_manager import camera_manager
    from app.services.classification import banana_classifier
    from app.services.banana_detector import banana_pre_detector
    from app.services.spoilage import spoilage_predictor
    from app.services.sensor_reader import freshness_window_seconds, sensor_reader
    from app.core.time import now_manila

    models_ready = banana_classifier.is_loaded and banana_pre_detector.is_loaded
    cameras_ok = len(camera_manager.online_cameras) > 0

    if models_ready and cameras_ok:
        status = "healthy"
    elif models_ready:
        status = "degraded"  # Models loaded but no cameras
    else:
        status = "degraded"  # Critical models not loaded

    return {
        "status": status,
        "version": "0.1.0",
        "cameras_online": len(camera_manager.online_cameras),
        "cameras_total": len(camera_manager._device_ids),
        "banana_pre_detector_loaded": banana_pre_detector.is_loaded,
        "yolo_loaded": banana_classifier.is_loaded,
        "rfr_loaded": spoilage_predictor.is_loaded,
        "sensor_connected": sensor_reader.is_connected,
        "sensor_recorded_at": (
            sensor_reader.latest.recorded_at.isoformat() if sensor_reader.latest else None
        ),
        "sensor_stale_after_seconds": freshness_window_seconds(),
        "server_time": now_manila().isoformat(),
    }
