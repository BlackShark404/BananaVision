"""
Aggregated v1 API router.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.activity import router as activity_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.config import router as config_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.devices import router as devices_router
from app.api.v1.intakes import router as intakes_router
from app.api.v1.maintenance import router as maintenance_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.printing import router as printing_router
from app.api.v1.quality import router as quality_router
from app.api.v1.scan_logs import router as scan_logs_router
from app.api.v1.scans import router as scans_router
from app.api.v1.sensors import router as sensors_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.system import router as system_router
from app.api.v1.users import router as users_router

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
v1_router.include_router(cameras_router)
v1_router.include_router(system_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(scan_logs_router)
v1_router.include_router(printing_router)
v1_router.include_router(maintenance_router)
