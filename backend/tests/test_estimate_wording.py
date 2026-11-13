"""AI-estimated numbers are labelled as estimates in exports, notifications and the log.

Only the wording changes: cells and stored values stay plain numbers.
"""
from app.services import scan_logs
from app.services.scan_service import estimated_fingers


def test_export_headers_mark_estimated_columns():
    headers = scan_logs.EXPORT_HEADERS
    estimated = (
        "Est. Finger Count", "Est. Original Shelf Life (days)", "Est. Remaining Shelf Life (days)",
    )
    for name in estimated:
        assert name in headers
    for old in ("Finger Count", "Original Shelf Life (days)", "Remaining Shelf Life (days)"):
        assert old not in headers
    # Measured and recorded columns are not estimates.
    for exact in ("Scan ID", "Temperature (C)", "Humidity (%)", "VPD (kPa)", "Confidence (%)"):
        assert exact in headers
    assert len(headers) == len(set(headers)) == 19


def test_notification_and_activity_wording_marks_the_ai_finger_count():
    # Same wording as the screens (frontend/src/lib/estimates.ts).
    assert estimated_fingers(13) == "Est. 13 fingers"
    assert estimated_fingers(1) == "Est. 1 finger"
    assert estimated_fingers(0) == "Est. 0 fingers"
