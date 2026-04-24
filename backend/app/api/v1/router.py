"""
Aggregated v1 API router.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.scans import router as scans_router
from app.api.v1.routes import (
    devices_router,
    sensors_router,
    users_router,
    suppliers_router,
    intakes_router,
    analytics_router,
    activity_router,
    config_router,
    quality_router,
    notifications_router,
)

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(scans_router)
v1_router.include_router(devices_router)
v1_router.include_router(sensors_router)
v1_router.include_router(users_router)
v1_router.include_router(suppliers_router)
v1_router.include_router(intakes_router)
v1_router.include_router(analytics_router)
v1_router.include_router(activity_router)
v1_router.include_router(config_router)
v1_router.include_router(quality_router)
v1_router.include_router(notifications_router)
