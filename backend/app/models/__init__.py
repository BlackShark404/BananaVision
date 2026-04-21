"""
ORM model registry — import all models here so Alembic and Base.metadata discover them.
"""

from app.models.user import User
from app.models.supplier import Supplier
from app.models.intake import Intake
from app.models.scan import Scan
from app.models.scan_detection import ScanDetection
from app.models.scan_image import ScanImage
from app.models.scan_note import ScanNote
from app.models.sensor_reading import SensorReading
from app.models.device import Device
from app.models.activity_log import ActivityLog
from app.models.system_config import SystemConfig

__all__ = [
    "User",
    "Supplier",
    "Intake",
    "Scan",
    "ScanDetection",
    "ScanImage",
    "ScanNote",
    "SensorReading",
    "Device",
    "ActivityLog",
    "SystemConfig",
]
