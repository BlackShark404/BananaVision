"""
WebSocket event type constants and helper functions.
"""

from __future__ import annotations


# ── Scan Events ──────────────────────────────────────────────────────────────
SCAN_STARTED = "scan:started"
SCAN_CAPTURING = "scan:capturing"
SCAN_CAPTURED = "scan:captured"
SCAN_DETECTING = "scan:detecting"
SCAN_DETECTED = "scan:detected"
SCAN_ANALYZING = "scan:analyzing"
SCAN_COMPLETED = "scan:completed"
SCAN_FAILED = "scan:failed"

# ── Sensor Events ────────────────────────────────────────────────────────────
SENSOR_UPDATE = "sensor:update"

# ── Device Events ────────────────────────────────────────────────────────────
DEVICE_STATUS = "device:status"

# ── Notification Events ─────────────────────────────────────────────────────
NOTIFICATION = "notification"

# ── Room Names ───────────────────────────────────────────────────────────────
ROOM_KIOSK = "kiosk"
ROOM_DASHBOARD = "dashboard"
ROOM_DEVICES = "devices"
