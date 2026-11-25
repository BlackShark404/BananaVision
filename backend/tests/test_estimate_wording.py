"""AI-estimated numbers are labelled as estimates in exports, notifications and the log.

Human-corrected finger counts drop the Est. prefix; sensor measurements never carry Est.
"""
from app.core.export_format import format_fingers
from app.services import scan_logs
from app.services.scan_service import estimated_fingers


def test_export_headers_mark_estimated_columns_and_exclude_programmer_fields():
    headers = scan_logs.EXPORT_HEADERS
    estimated = (
        "Est. Current Ripeness",
        "Est. Fingers",
        "Est. Shelf Life (Original)",
        "Est. Time Left / Freshness",
    )
    for name in estimated:
        assert name in headers
    for old in (
        "Ripeness", "Finger Count", "Original Shelf Life (days)", "Remaining Shelf Life (days)",
        "Scan ID", "Intake ID", "Operator Username", "Overridden",
        "Status Updated At (UTC+08:00)", "VPD (kPa)",
    ):
        assert old not in headers
    # Measured, recorded, and identifier columns are not estimates.
    for exact in (
        "Scan Ref", "Date & Time", "Scanned Ripeness",
        "Temperature (°C)", "Humidity (%)", "Confidence (%)", "Operator",
    ):
        assert exact in headers
    assert headers[0] == "Scan Ref"
    assert len(headers) == len(set(headers)) == 15


def test_export_finger_count_marks_ai_estimates_only():
    assert format_fingers(13) == "Est. 13 fingers"
    assert format_fingers(1) == "Est. 1 finger"
    assert format_fingers(0) == "Est. 0 fingers"
    # Overridden on another field while finger count matches AI baseline stays Est.
    assert format_fingers(13, is_overridden=True, original_finger_count=13) == "Est. 13 fingers"
    # Overridden without baseline stays Est.
    assert format_fingers(13, is_overridden=True, original_finger_count=None) == "Est. 13 fingers"
    # Human-corrected finger count drops Est.
    assert format_fingers(15, is_overridden=True, original_finger_count=13) == "15 fingers"
    assert format_fingers(1, is_overridden=True, original_finger_count=2) == "1 finger"
    assert format_fingers(None) == ""


def test_notification_and_activity_wording_marks_the_ai_finger_count():
    # Same wording as the screens (frontend/src/lib/estimates.ts).
    assert estimated_fingers(13) == "Est. 13 fingers"
    assert estimated_fingers(1) == "Est. 1 finger"
    assert estimated_fingers(0) == "Est. 0 fingers"
