"""The public QR page gets only the scanned data, never internal evidence paths.

Anyone who scans a QR code can call GET /api/v1/scans/{id}/track without logging in.
"""
from sqlalchemy.orm import Session

from app.models import ScanImage
from tests.test_time_and_writes import application  # noqa: F401

PUBLIC_FIELDS = {
    "id", "date_time", "cultivar", "ripeness", "confidence", "spoilage_days",
    "remaining_days", "risk_as_of", "shelf_life_window", "ripeness_projection",
    "storage_exposure", "finger_count", "temperature",
    "humidity", "vpd", "treatment", "source_text", "inventory_status", "flagged", "images",
}


def test_public_track_sends_scan_data_but_no_capture_paths(application):  # noqa: F811
    with Session(application.engine) as db:
        db.add(ScanImage(scan_id=application.ids.scan, camera_id="CAM-001",
                         file_path=f"{application.ids.scan}/top.jpg"))
        db.commit()
    url = f"/api/v1/scans/{application.ids.scan}"

    public = application.client.get(f"{url}/track")
    assert public.status_code == 200, public.text
    body = public.json()
    # Same response shape as before; the photo list is simply always empty now.
    assert set(body) == PUBLIC_FIELDS
    assert body["images"] == []
    assert "CAM-001" not in public.text and "top.jpg" not in public.text
    assert (body["cultivar"], body["ripeness"], body["finger_count"]) == ("Lakatan", "Ripe", 5)

    # Staff pages still receive the evidence.
    staff = application.client.get(url)
    assert staff.status_code == 200, staff.text
    assert [image["camera_id"] for image in staff.json()["images"]] == ["CAM-001"]
