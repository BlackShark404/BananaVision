"""
BananaVision Backend — FastAPI Application Entry Point.

Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.v1.router import v1_router
from app.ws.handlers import websocket_endpoint
from app.core.startup import run_startup, run_shutdown, start_background_tasks

settings = get_settings()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
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

app = FastAPI(
    title="BananaVision API",
    description=(
        "Banana Classification & Spoilage Prediction System — "
        "YOLOv8n + Random Forest Regression"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────────────
app.include_router(v1_router)

# ── WebSocket ────────────────────────────────────────────────────────────────
app.add_api_websocket_route("/api/v1/ws", websocket_endpoint)

# ── Static Files (captured images) ──────────────────────────────────────────
settings.capture_path.mkdir(parents=True, exist_ok=True)
app.mount(
    "/captures",
    StaticFiles(directory=str(settings.capture_path)),
    name="captures",
)


# ── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    from app.services.camera_manager import camera_manager
    from app.services.classification import banana_classifier
    from app.services.spoilage import spoilage_predictor
    from app.services.sensor_reader import sensor_reader

    return {
        "status": "healthy",
        "version": "0.1.0",
        "cameras_online": len(camera_manager.online_cameras),
        "cameras_total": len(settings.camera_device_ids),
        "yolo_loaded": banana_classifier.is_loaded,
        "rfr_loaded": spoilage_predictor.is_loaded,
        "sensor_connected": sensor_reader.is_connected,
    }
