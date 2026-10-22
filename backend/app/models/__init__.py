"""
ORM model registry — import all models here so Alembic and Base.metadata discover them.
"""

from app.models.activity_log import ActivityLog
from app.models.admin_profile import AdminProfile
from app.models.app_notification import AppNotification
from app.models.app_notification_read import AppNotificationRead
from app.models.device import Device
from app.models.intake import Intake
from app.models.maintenance_state import MaintenanceState
from app.models.operator_profile import OperatorProfile
from app.models.print_job import PrintJob
from app.models.scan import Scan
from app.models.scan_classification import ScanClassification
from app.models.scan_detection import ScanDetection
from app.models.scan_history import ScanEvent, ScanMutation, ScanTombstone
from app.models.scan_image import ScanImage
from app.models.scan_note import ScanNote
from app.models.scan_original_ai_result import ScanOriginalAiResult
from app.models.scan_snapshot import ScanSnapshot
from app.models.scan_status_log import ScanStatusLog
from app.models.sensor_reading import SensorReading
from app.models.supplier import Supplier
from app.models.system_config import SystemConfig
from app.models.user_account import UserAccount
from app.models.user_role import UserRole

__all__ = [
    "UserRole",
    "UserAccount",
    "AdminProfile",
    "OperatorProfile",
    "Supplier",
    "Intake",
    "Scan",
    "ScanClassification",
    "ScanStatusLog",
    "ScanOriginalAiResult",
    "ScanDetection",
    "ScanImage",
    "ScanNote",
    "Device",
    "ActivityLog",
    "SystemConfig",
    "AppNotification",
    "AppNotificationRead",
    "SensorReading",
    "MaintenanceState",
    "ScanEvent", "ScanMutation", "ScanTombstone",
    "ScanSnapshot",
    "PrintJob",
]
