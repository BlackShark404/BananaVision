"""Compare demo records and the real trigger route using disposable PG and mocked hardware."""

import csv
import io
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import seed
from app.api.deps import get_current_user
from app.api.v1 import scans as routes
from app.api.v1.intakes import list_intakes
from app.core.database import get_db
from app.models import Scan, UserAccount
from app.schemas.scan_logs import ScanLogQuery
from app.services import analytics, dashboard, scan_logs, scan_records, scan_service
from app.services.feature_engineering import calc_vpd
from app.services import spoilage
from tests.test_seed import empty_seed_database, pytestmark  # noqa: F401


@pytest.mark.parametrize("readings,linked", [
    ("seed", True), ("zero", True), ("missing", False), ("trained", True),
])
async def test_seed_and_kiosk_records_agree_across_consumers(
    empty_seed_database, monkeypatch, readings, linked,  # noqa: F811 - imported pytest fixture
):
    trained = None
    if readings == "trained":
        weights = Path(seed.__file__).parent / "app/ml/weights/spoilage_rfr.joblib"
        if not weights.is_file():
            pytest.skip("Local trained RFR artifact is unavailable")
        monkeypatch.setattr(spoilage.settings, "rfr_model_path", str(weights))
        trained = spoilage.SpoilagePredictor()
        trained.load()
        assert trained._model is not None
        # Deterministic summation for exact cross-run comparisons in this test.
        trained._model.n_jobs = 1
        monkeypatch.setattr(trained, "load", lambda: None)
        monkeypatch.setattr(seed, "SpoilagePredictor", lambda: trained)
    await seed.main()
    async with empty_seed_database.sessions() as db:
        demo = next(s for s in (await db.scalars(select(Scan))).all()
                    if s.status_logs[-1].inventory_status == "In Stock")
        admin = await db.scalar(select(UserAccount).where(UserAccount.username == "seed_admin"))
        operator = demo.operator.account
        account = SimpleNamespace(id=operator.id, full_name=operator.full_name, role=operator.role,
                                  operator_profile=SimpleNamespace(id=demo.operator_id))
        c = demo.classification
        now = demo.date_time
        result = SimpleNamespace(
            cultivar=c.cultivar.value, ripeness=c.ripeness.value,
            confidence=float(c.confidence) if readings in ("seed", "trained") else 0,
            finger_count=c.finger_count, detections=[], inference_time_ms=1,
            auto_flagged=False, conflict_detected=False, camera_count=1,
        )
        temperature = float(c.temperature) if readings in ("seed", "trained") else 0
        humidity = float(c.humidity) if readings in ("seed", "trained") else 100
        sensor = (None if readings == "missing" else
                  SimpleNamespace(temperature=temperature, humidity=humidity))
        expected_vpd = None if sensor is None else calc_vpd(temperature, humidity)
        capture = SimpleNamespace(camera_id="CAM-001", camera_label="Top",
                                  frame=None, file_path=None)

        async def capture_all():
            return [capture]

        async def config(_db):
            return SimpleNamespace(
                confidence_threshold=85,
                camera_slots=[SimpleNamespace(slot_index=0)],
            )

        completed, predictions = [], []

        async def send(_room, event, data, **_kwargs):
            if event == "scan:completed":
                completed.append(data)

        def predict(**kwargs):
            predictions.append(kwargs)
            return trained.predict(**kwargs) if trained else c.spoilage_days

        monkeypatch.setattr(scan_service, "get_config", config)
        monkeypatch.setattr(scan_service, "now_manila", lambda: now)
        monkeypatch.setattr(dashboard, "now_manila", lambda: now)
        monkeypatch.setattr(scan_records, "now_manila", lambda: now)
        monkeypatch.setattr(scan_service, "camera_manager", SimpleNamespace(
            online_cameras=[0], capture_all=capture_all, save_captures=lambda frames, _: frames,
        ))
        monkeypatch.setattr(scan_service, "banana_pre_detector", SimpleNamespace(
            detect=lambda _: SimpleNamespace(banana_detected=True),
        ))
        monkeypatch.setattr(scan_service, "banana_classifier", SimpleNamespace(
            predict=lambda _, **kwargs: result,
        ))
        monkeypatch.setattr(scan_service, "fusion_engine", SimpleNamespace(
            fuse=lambda _, **kwargs: result,
        ))
        monkeypatch.setattr(scan_service, "sensor_reader", SimpleNamespace(latest=sensor))
        monkeypatch.setattr(scan_service, "spoilage_predictor", SimpleNamespace(predict=predict))
        monkeypatch.setattr(scan_service.ws_manager, "send_to_room", send)
        monkeypatch.setattr(routes, "get_settings",
                            lambda: SimpleNamespace(bananavision_auto_print=False))
        monkeypatch.setattr(scan_service, "remove_scan_captures", lambda *_: None)

        async def database():
            async with empty_seed_database.sessions() as session:
                yield session

        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: account
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://fixture") as client:
            response = await client.post("/api/v1/scans/trigger", json={
                "intake_id": str(demo.intake_id) if linked else None,
            })
            assert response.status_code == 200, response.text
            saved = response.json()
            detail = (await client.get(f"/api/v1/scans/{saved['id']}")).json()
            track = (await client.get(f"/api/v1/scans/{saved['id']}/track")).json()

        expected_source = demo.source_text if linked else None
        assert saved["source_text"] == expected_source
        assert detail["source_text"] == track["source_text"] == expected_source
        fields = ("cultivar", "ripeness", "confidence", "temperature", "humidity", "vpd",
                  "treatment", "spoilage_days", "finger_count", "date_time", "inventory_status")
        for key in fields:
            assert saved[key] == detail[key] == track[key], key
        assert saved["vpd"] == expected_vpd
        assert saved["temperature"] == (temperature if sensor else None)
        assert saved["treatment"] == (c.treatment.value if linked else None)
        assert saved["intake_provenance"] == ("linked" if linked else "unlinked")
        assert saved["inventory_eligible"] is True
        assert predictions[0]["vpd"] == expected_vpd
        assert predictions[0]["treatment"] == saved["treatment"]
        for event in completed:
            for key in fields:
                assert event[key] == saved[key], key
            assert event["source_text"] == expected_source
            for key in ("original_ai_result", "intake_provenance", "intake_origin_id",
                        "inventory_eligible", "remaining_days"):
                assert event.get(key) == saved[key], key
        assert "operator_name" not in track and "history" not in track  # Public boundary.
        history = detail["history"]
        assert len(history) == 1 and history[0]["actor_id"] == str(account.id)
        assert history[0]["actor_name"] == account.full_name and not history[0]["legacy"]

        live = await db.get(Scan, UUID(saved["id"]))
        assert live.date_time == live.status_logs[0].updated_at
        assert live.date_time == live.original_ai_result.created_at
        assert live.original_ai_result.spoilage_days == c.spoilage_days
        if readings in ("seed", "trained"):
            demo_data = scan_records.serialize_scan(demo, admin).model_dump(mode="json")
            for key in fields:
                assert saved[key] == demo_data[key], key
        if trained:
            assert float(saved["spoilage_days"]) == saved["remaining_days"]
            for stored in (await db.scalars(select(Scan))).all():
                sc = stored.classification
                inputs = {
                    "cultivar_encoded": trained._cultivar_map[sc.cultivar.value],
                    "ripeness_encoded": trained._ripeness_map[sc.ripeness.value],
                    "treatment_encoded": trained._treatment_map[sc.treatment.value],
                    "temperature": float(sc.temperature), "humidity": float(sc.humidity),
                    "vpd": float(sc.vpd),
                }
                direct = trained._model.predict([[inputs[k] for k in trained._feature_columns]])[0]
                assert float(sc.spoilage_days) == pytest.approx(direct)
                assert stored.original_ai_result.spoilage_days == sc.spoilage_days

        # Consumers must read persisted values even after sensors/predictor/account change.
        monkeypatch.setattr(scan_service, "sensor_reader", SimpleNamespace(
            latest=SimpleNamespace(temperature=40, humidity=10),
        ))
        operator.full_name = "Renamed account"
        await db.commit()
        later = now + timedelta(days=1)
        monkeypatch.setattr(dashboard, "now_manila", lambda: later)
        monkeypatch.setattr(scan_records, "now_manila", lambda: later)
        logs = await scan_logs.list_scan_logs(db, admin, ScanLogQuery(page_size=100))
        log = next(row for row in logs.items if str(row.id) == saved["id"])
        reread = await scan_records.serialize_detail(db, live, admin)
        for key in (
            "confidence", "temperature", "humidity", "vpd", "spoilage_days", "finger_count",
        ):
            assert getattr(log, key) == getattr(reread, key) == saved[key], key
        assert log.operator_name == saved["operator_name"]
        assert log.source_name == (expected_source or "Unknown")
        assert log.remaining_days == pytest.approx(saved["remaining_days"] - 1, abs=0.0001)
        expected_risk = set()
        for row in logs.items:
            stored = await db.get(Scan, row.id)
            serialized = scan_records.serialize_scan(stored, admin)
            assert "at_risk" not in row.model_dump()
            if (
                serialized.inventory_eligible and serialized.remaining_days is not None
                and serialized.remaining_days <= 2
            ):
                expected_risk.add(row.id)
        assert logs.at_risk_count == len(expected_risk)
        risk_rows = await scan_logs.list_scan_logs(
            db, admin, ScanLogQuery(attention="at-risk", page_size=100),
        )
        assert {row.id for row in risk_rows.items} == expected_risk
        dash = await dashboard.list_scans(db, admin, view="all", page_size=100)
        dash_scan = next(row for row in dash.items if row.id == live.id)
        assert dash_scan.remaining_days == log.remaining_days
        summary = await analytics.get_summary(db, admin, date_range="all")
        assert summary.total_scans == summary.confidence_sample_count == 26
        assert summary.current_stock_count == 16  # Ten sold demo scans excluded.
        registry = await list_intakes(db, admin)
        assert sum(item.scan_count for item in registry) == (26 if linked else 25)
        content = await scan_logs.export_scan_logs(db, admin, ScanLogQuery())
        exported = list(csv.DictReader(io.StringIO(
            "".join([part async for part in content]).lstrip("\ufeff"),
        )))
        row = next(item for item in exported if item["Scan ID"] == saved["id"])
        assert row["VPD (kPa)"] == ("" if expected_vpd is None else f"{expected_vpd:.3f}")
        assert row["Est. Original Shelf Life (days)"] == saved["spoilage_days"]
        assert row["Source"] == log.source_name
        assert row["Scanned At (UTC+08:00)"] == saved["date_time"]
        assert len(predictions) == 1  # Reads never rerun predictions.
