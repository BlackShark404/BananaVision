"""Auto-flag rule: a scan is flagged only when its confidence is below the saved threshold.

Station report (2026-11-18): kiosk scans were flagged although their confidence was above
the threshold. The system also flagged for different finger counts between cameras, camera
disagreements, missing captures and dropped boxes. User decision: "only flag when the
confidence is below the threshold". The other signals are still recorded (history of the
result, activity log), but they never flag a scan.

All tests use the isolated SQLite fixture; no live station database, camera or model.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models import ActivityLog, AppNotification, Scan, ScanEvent, SystemConfig
from app.services import scan_service
from app.services.classification import ClassificationResult, Detection
from app.services.fusion_engine import FusionEngine
from tests.test_scan_trigger import scan_station  # noqa: F401
from tests.test_time_and_writes import application  # noqa: F401

LABELS = ["Top", "Left", "Right", "Rear"]


def view(cultivar="Lakatan", ripeness="Ripe", confidence=92.0, count=7, **extra):
    label = f"{cultivar}_{ripeness}".lower().replace(" ", "_")
    return ClassificationResult(
        cultivar=cultivar, ripeness=ripeness, confidence=confidence, finger_count=count,
        detections=[Detection(i * 30, 0, 20, 80, label, confidence / 100) for i in range(count)],
        **extra,
    )


def fuse(*results, threshold=0.80, expected=None):
    return FusionEngine().fuse(
        [(f"CAM-{i + 1:03}", LABELS[i], result) for i, result in enumerate(results)],
        expected_camera_count=expected, review_confidence_threshold=threshold,
    )


def notes(result):
    return [observation.code for observation in result.observations]


# ── Fusion rule ───────────────────────────────────────────────────────────────

def test_confidence_below_the_threshold_is_the_only_flag():
    at_threshold = fuse(*(view(confidence=80.0) for _ in range(4)), threshold=0.80)
    assert at_threshold.auto_flagged is False and at_threshold.flag_reason is None
    below = fuse(*(view(confidence=79.9) for _ in range(4)), threshold=0.80)
    assert below.auto_flagged is True
    assert below.flag_reason == "Confidence 79.9% is below the 80% threshold"
    stricter = fuse(*(view(confidence=82.0) for _ in range(4)), threshold=0.85)
    assert stricter.auto_flagged is True
    assert stricter.flag_reason == "Confidence 82% is below the 85% threshold"


def test_different_finger_counts_between_views_do_not_flag():
    result = fuse(view(count=10), view(count=7), view(count=7), view(count=9))
    assert result.confidence == pytest.approx(92)
    assert result.finger_count >= 10
    assert result.auto_flagged is False and result.flag_reason is None
    assert "count_views_differ" in notes(result)
    same = fuse(*(view(count=7) for _ in range(4)))
    assert same.auto_flagged is False and notes(same) == []


def test_cameras_that_disagree_on_the_cultivar_are_noted_not_flagged():
    result = fuse(view("Lakatan", confidence=85, count=2), view("Latundan", confidence=95),
                  view("Latundan", confidence=95), view("Latundan", confidence=95))
    assert result.cultivar_conflict is True and result.conflict_detected is True
    assert "cultivar_conflict" in notes(result)
    assert result.auto_flagged is False


def test_cameras_that_disagree_on_the_ripeness_are_noted_not_flagged():
    result = fuse(view(ripeness="Ripe"), view(ripeness="Ripe"),
                  view(ripeness="Semi Ripe"), view(ripeness="Semi Ripe"))
    assert result.conflict_detected is True
    assert "ripeness_conflict" in notes(result)
    assert result.auto_flagged is False


def test_a_view_whose_own_boxes_disagree_is_noted_with_its_camera():
    result = fuse(view(), view(conflict_detected=True), view(), view())
    assert result.auto_flagged is False
    [note] = result.observations
    assert (note.code, note.text) == (
        "view_conflict", "The Left camera's own boxes disagree or overlap")


def test_missing_or_unsupported_views_are_noted_not_flagged():
    empty = ClassificationResult()
    sparse = fuse(view(), empty, empty, empty, expected=4)
    assert "insufficient_views" in notes(sparse) and sparse.auto_flagged is False
    missing = fuse(view(), view(), expected=4)
    assert notes(missing) == ["missing_captures"] and missing.auto_flagged is False
    assert missing.observations[0].text == "Only 2 of 4 cameras returned a result"


def test_a_result_without_a_label_or_camera_is_below_any_threshold():
    nothing = FusionEngine().fuse([], expected_camera_count=4)
    assert nothing.confidence == 0 and nothing.auto_flagged is True
    unlabelled = fuse(ClassificationResult(), ClassificationResult(), expected=2)
    assert unlabelled.cultivar == "Unknown" and unlabelled.auto_flagged is True


def test_a_conflict_with_low_confidence_is_flagged_for_the_confidence_only():
    result = fuse(view(ripeness="Ripe", confidence=70), view(ripeness="Ripe", confidence=70),
                  view(ripeness="Semi Ripe", confidence=70),
                  view(ripeness="Semi Ripe", confidence=70))
    assert result.auto_flagged is True
    assert result.flag_reason == "Confidence 70% is below the 80% threshold"
    assert "ripeness_conflict" in notes(result)


# ── Saved scans ───────────────────────────────────────────────────────────────

def as_operator(app):
    app.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=app.ids.operator, full_name="Fixture Operator", role=SimpleNamespace(name="Operator"),
        operator_profile=SimpleNamespace(id=app.ids.profile),
    )


def run_scan(app, monkeypatch, views, threshold=None):
    """Trigger one scan through the real fusion engine with the given per-camera results."""
    if threshold is not None:
        with Session(app.engine) as db:
            db.scalars(select(SystemConfig)).one().confidence_threshold = threshold
            db.commit()
    predictions = iter(views)
    monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(
        predict=lambda _, **kwargs: next(predictions),
    ))
    monkeypatch.setattr(scan_service, "fusion_engine", FusionEngine())
    sent = []

    async def capture(_room, event, data, **_kwargs):
        sent.append((event, data))

    monkeypatch.setattr(scan_service.ws_manager, "send_to_room", capture)
    as_operator(app)
    response = app.client.post("/api/v1/scans/trigger", json={"intake_id": str(app.ids.intake)})
    assert response.status_code == 200, response.text
    return response.json(), sent


def saved(app, scan_id):
    with Session(app.engine) as db:
        scan = db.get(Scan, UUID(scan_id))
        event = db.scalars(select(ScanEvent).where(
            ScanEvent.scan_id == UUID(scan_id), ScanEvent.kind == "created")).one()
        details = db.scalars(select(ActivityLog.details).where(
            ActivityLog.action == "scan_created",
            ActivityLog.details.contains(scan_id))).one()
        notices = db.scalars(select(AppNotification).where(
            AppNotification.type == "scan_flagged",
            AppNotification.href == f"/scans/{scan_id}")).all()
        return SimpleNamespace(flagged=scan.flagged, event=event, details=details,
                               notices=notices)


def test_confident_scan_with_different_view_counts_is_saved_unflagged(scan_station, monkeypatch):  # noqa: F811
    app, _ = scan_station
    data, sent = run_scan(
        app, monkeypatch, [view(confidence=91, count=count) for count in (10, 7, 7, 9)],
        threshold=80,
    )
    assert data["flagged"] is False
    completed = [payload for name, payload in sent if name == "scan:completed"]
    assert completed and all(payload["flagged"] is False for payload in completed)
    assert not [payload for name, payload in sent if name == "notification"]
    record = saved(app, data["id"])
    assert record.flagged is False and record.notices == []
    assert "flagged" not in record.details
    assert "flagged" not in record.event.new_values and record.event.reason is None


def test_the_saved_threshold_decides_the_flag(scan_station, monkeypatch):  # noqa: F811
    app, _ = scan_station
    above, _ = run_scan(app, monkeypatch, [view(confidence=82) for _ in range(4)], threshold=80)
    assert above["flagged"] is False
    equal, _ = run_scan(app, monkeypatch, [view(confidence=80) for _ in range(4)], threshold=80)
    assert equal["flagged"] is False
    below, sent = run_scan(app, monkeypatch, [view(confidence=82) for _ in range(4)],
                           threshold=85)
    assert below["flagged"] is True
    reason = "Confidence 82% is below the 85% threshold"
    record = saved(app, below["id"])
    # Scan History says why the system flagged the scan.
    assert record.event.new_values["flagged"] is True
    assert record.event.reason == f"Auto-flagged: {reason}"
    assert record.details.endswith(f"; flagged for review: {reason}")
    [notice] = record.notices
    assert notice.message.endswith(f"— flagged for review: {reason}")
    [live] = [payload for name, payload in sent if name == "notification"]
    assert live["message"] == notice.message


def test_other_signals_never_flag_a_confident_scan_but_stay_in_the_activity_log(
    scan_station, monkeypatch,  # noqa: F811
):
    app, _ = scan_station
    views = [
        view(ripeness="Ripe", colour_rejected_boxes=1), view(ripeness="Ripe"),
        view(ripeness="Semi Ripe", ood_rejected_boxes=2),
        view(ripeness="Semi Ripe", ripeness_outlier_boxes=1),
    ]
    data, sent = run_scan(app, monkeypatch, views, threshold=80)
    assert data["flagged"] is False
    assert not [payload for name, payload in sent if name == "notification"]
    record = saved(app, data["id"])
    assert record.flagged is False and record.notices == []
    assert "flagged for review" not in record.details
    # Nothing is dropped or disputed silently: the activity log keeps the notes.
    assert record.details.endswith(
        "; noted: Cameras disagree on the ripeness; "
        "2 boxes without banana evidence dropped; "
        "1 box with inconsistent ripeness dropped; "
        "1 box over non-banana colours (crown or dark background) dropped"
    )
    assert record.event.reason is None


def test_three_cameras_at_high_confidence_are_not_flagged(scan_station, monkeypatch):  # noqa: F811
    app, _ = scan_station
    empty = ClassificationResult()
    data, _ = run_scan(app, monkeypatch, [view(confidence=90), view(confidence=90),
                                         view(confidence=90), empty], threshold=80)
    assert data["flagged"] is False


def test_low_confidence_with_other_signals_is_flagged_for_confidence(scan_station, monkeypatch):  # noqa: F811
    app, _ = scan_station
    views = [view(confidence=60, ood_rejected_boxes=1), view(confidence=60),
             view(confidence=60), view(confidence=60)]
    data, _ = run_scan(app, monkeypatch, views, threshold=80)
    assert data["flagged"] is True
    record = saved(app, data["id"])
    assert record.event.reason == "Auto-flagged: Confidence 60% is below the 80% threshold"
    assert record.details.endswith(
        "; flagged for review: Confidence 60% is below the 80% threshold"
        "; noted: 1 box without banana evidence dropped"
    )
