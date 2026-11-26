"""Restorable private archives; only disposable SQLite and temporary files."""
import asyncio
import errno
import hashlib
import importlib
import json
import stat
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import bcrypt
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import Base
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, compiler, **kwargs):
    return "JSON"


class AsyncDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


def test_archive_api_exists():
    assert importlib.util.find_spec("app.services.backup_archive"), "archive service is missing"


@pytest.fixture
def archive_module():
    assert importlib.util.find_spec("app.services.backup_archive"), "archive service is missing"
    return importlib.import_module("app.services.backup_archive")


@pytest.fixture
def station(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    root = tmp_path / "captures"
    scan_id = uuid4()
    evidence = root / str(scan_id)
    evidence.mkdir(parents=True)
    (evidence / "camera.jpg").write_bytes(b"captured frame")
    (evidence / "thumbnail.jpg").write_bytes(b"thumbnail")
    instant = datetime(2025, 1, 1, 16, 30, tzinfo=UTC)
    with Session(engine) as db:
        db.add(m.UserRole(id=1, name="Admin"))
        db.flush()
        user = m.UserAccount(username="admin", full_name="Admin", role_id=1,
                             password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt(4)).decode())
        db.add(user)
        db.flush()
        admin = m.AdminProfile(account_id=user.id)
        operator = m.OperatorProfile(account_id=user.id, pin_hash="original-pin-hash")
        supplier = m.Supplier(name="Supplier")
        db.add_all([admin, operator, supplier])
        db.flush()
        intake = m.Intake(source="Supplier", supplier_id=supplier.id, intake_date=date(2025, 1, 2))
        db.add(intake)
        db.flush()
        db.add(m.IntakeExpectedStock(
            intake_id=intake.id, cultivar=CultivarEnum.LAKATAN, expected_bunches=5,
        ))
        db.add(m.Scan(id=scan_id, operator_id=operator.id, intake_id=intake.id, date_time=instant))
        db.flush()
        db.add_all([
            m.ScanEvent(scan_id=scan_id, revision=1, kind="created", actor_id=user.id,
                        actor_name="Historical Admin", new_values={"inventory_status": "In Stock"}),
            m.ScanMutation(request_id=uuid4(), actor_id=user.id, fingerprint="a" * 64,
                           response={"revision": 1}),
            m.ScanTombstone(scan_id=uuid4(), owner_account_id=user.id),
            m.ScanClassification(scan_id=scan_id, cultivar=CultivarEnum.LAKATAN,
                ripeness=RipenessEnum.RIPE, confidence=Decimal("91.25"), finger_count=5,
                spoilage_days="3", thumbnail_url=f"/captures/{scan_id}/thumbnail.jpg"),
            m.ScanOriginalAiResult(scan_id=scan_id, cultivar=CultivarEnum.LAKATAN,
                ripeness=RipenessEnum.RIPE, confidence=Decimal("90.25"), finger_count=4),
            m.ScanStatusLog(scan_id=scan_id, inventory_status=InventoryStatusEnum.IN_STOCK),
            m.ScanImage(scan_id=scan_id, camera_id="CAM-001", file_path=str(evidence / "camera.jpg")),
            m.ScanDetection(scan_id=scan_id, camera_id="CAM-001", camera_label="Top",
                bounding_boxes=[{"xyxy": [1, 2, 3, 4], "confidence": 0.9125, "extra": None}]),
            m.ScanNote(scan_id=scan_id, text="Preserve note", author_name="Admin"),
            m.Device(camera_id="CAM-001", label="Top", slot_index=0, device_index=0),
            m.SystemConfig(updated_by_admin=admin.id),
            m.ActivityLog(
                user_id=user.id, action="LOGIN", details="Preserve audit", actor_name="Admin"
            ),
            m.SensorReading(temperature=25.75, humidity=80.5),
            m.PrintJob(
                prediction_id=scan_id, owner_id=user.id, quantity=1,
                printer_name="Fixture printer", width_mm=40, height_mm=30,
                label_data={}, status="QUEUED",
            ),
        ])
        notification = m.AppNotification(
            type="scan", title="Ready", message="Preserve notification",
            user_id=user.id,
        )
        db.add(notification)
        db.flush()
        db.add(m.AppNotificationRead(
            notification_id=notification.id, user_id=user.id,
        ))
        db.commit()
        yield db, root, scan_id, instant
    engine.dispose()


def backup(archive_module, station, tmp_path):
    db, root, *_ = station
    path = tmp_path / "backup.zip"
    asyncio.run(archive_module.create_archive(AsyncDB(db), root, path))
    return path


def rewrite(path, *, edit_manifest=None, edit_row=None, extra=None, omit=None):
    """Corrupt a real archive, updating hashes to test validation beyond checksums."""
    with zipfile.ZipFile(path) as source:
        members = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(members["manifest.json"])
    if edit_row:
        table, change = edit_row
        name = f"tables/{table}.jsonl"
        rows = [json.loads(line) for line in members[name].splitlines()]
        change(rows)
        members[name] = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
        manifest["tables"][table].update(count=len(rows), size=len(members[name]),
                                         sha256=hashlib.sha256(members[name]).hexdigest())
    if edit_manifest:
        edit_manifest(manifest)
    members["manifest.json"] = json.dumps(manifest).encode()
    if omit:
        members.pop(omit)
    with zipfile.ZipFile(path, "w") as target:
        for name, data in members.items():
            target.writestr(name, data)
        if extra:
            target.writestr(*extra)


def test_complete_all_table_roundtrip_preserves_values_and_instants(archive_module, station, tmp_path):
    path = backup(archive_module, station, tmp_path)
    validated = archive_module.validate_archive(path, tmp_path / "staging")
    assert validated.manifest["version"] == 6
    assert len(validated.manifest["tables"]) == 23
    assert all(t["count"] == 1 for t in validated.manifest["tables"].values())
    assert "maintenance_state" not in validated.manifest["tables"]
    assert "scan_label_print_job" not in validated.manifest["tables"]
    assert set(validated.evidence) == {f"{station[2]}/camera.jpg", f"{station[2]}/thumbnail.jpg"}
    assert validated.evidence[f"{station[2]}/camera.jpg"].read_bytes() == b"captured frame"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as restored:
        asyncio.run(archive_module.restore_rows(AsyncDB(restored), validated))
        restored.commit()
        assert restored.scalar(select(m.Scan)).date_time == station[3]
        assert restored.scalar(select(m.ScanClassification)).confidence == Decimal("91.25")
        assert restored.scalar(select(m.ActivityLog)).actor_name == "Admin"
        assert restored.scalar(select(m.ScanClassification)).cultivar == CultivarEnum.LAKATAN
        assert restored.scalar(select(m.IntakeExpectedStock)).expected_bunches == 5
        assert restored.scalar(select(m.ScanDetection)).bounding_boxes == [
            {"xyxy": [1, 2, 3, 4], "confidence": 0.9125, "extra": None}]
        assert restored.scalar(select(m.ScanImage)).file_path == f"/captures/{station[2]}/camera.jpg"
        assert restored.scalar(select(m.OperatorProfile)).pin_hash == "original-pin-hash"
        assert restored.scalar(select(m.UserAccount)).password_hash == station[0].scalar(select(m.UserAccount)).password_hash
        for table in Base.metadata.sorted_tables:
            if table.name not in (
                "maintenance_state", "scan_browse_snapshot", "scan_label_print_job",
            ):
                assert len(restored.execute(select(table)).all()) == 1
        assert restored.scalar(select(m.PrintJob)) is None  # Never restore/replay label work.
    engine.dispose()


def legacy_backup(archive_module, station, tmp_path, *, bad_null=False, version=1,
                  camera_ids='CAM-001', camera_device_ids=(0,)):
    path = backup(archive_module, station, tmp_path)
    with zipfile.ZipFile(path) as source:
        members = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(members['manifest.json'])
    legacy = json.loads(
        Path(archive_module.__file__).with_name(f"archive_schema_v{version}.json").read_text()
    )
    manifest.update(version=version, schema=legacy)
    for table in list(manifest['tables']):
        name = f'tables/{table}.jsonl'
        if table not in legacy:
            del manifest['tables'][table]
            del members[name]
            continue
        rows = [{key: value for key, value in json.loads(line).items() if key in legacy[table]}
                for line in members[name].splitlines()]
        if version < 4 and table == 'system_config':
            for row in rows:
                row.update(camera_ids=camera_ids, camera_device_ids=list(camera_device_ids))
        if table == 'operator_profile':
            for row in rows:
                row.update(total_scans=0, flagged_scans=0)
        if table == 'app_notification':
            for row in rows:
                row.setdefault('is_read', False)
        if bad_null and table == 'scan_original_ai_result':
            rows[0]['confidence'] = None
        members[name] = b''.join(json.dumps(row).encode() + b'\n' for row in rows)
        manifest['tables'][table] = dict(count=len(rows), size=len(members[name]),
                                         sha256=hashlib.sha256(members[name]).hexdigest())
    members['manifest.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(path, 'w') as target:
        for name, data in members.items():
            target.writestr(name, data)
    return path


def test_v1_backup_upgrades_without_inventing_history(archive_module, station, tmp_path):
    path = legacy_backup(archive_module, station, tmp_path)
    validated = archive_module.validate_archive(path, tmp_path / 'legacy-staging')
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as restored:
        asyncio.run(archive_module.restore_rows(AsyncDB(restored), validated))
        restored.commit()
        scan = restored.scalar(select(m.Scan))
        assert scan.revision == 1 and scan.date_time == station[3]
        assert scan.operator_name_snapshot is scan.source_name_snapshot is None
        assert restored.scalar(select(m.ScanOriginalAiResult)).spoilage_days is None
        assert not restored.scalars(select(m.ScanEvent)).all()
        assert not restored.scalars(select(m.ScanMutation)).all()
        assert not restored.scalars(select(m.ScanTombstone)).all()
        device = restored.scalar(select(m.Device))
        assert (device.camera_id, device.slot_index, device.device_index) == ('CAM-001', 0, 0)
    engine.dispose()


def test_v4_backup_upgrades_without_actor_name(archive_module, station, tmp_path):
    path = legacy_backup(archive_module, station, tmp_path, version=4)
    validated = archive_module.validate_archive(path, tmp_path / "v4-upgrade")
    assert validated.manifest["version"] == 4
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as restored:
        asyncio.run(archive_module.restore_rows(AsyncDB(restored), validated))
        restored.commit()
        log = restored.scalar(select(m.ActivityLog))
        assert log.actor_name is None
        assert log.details == "Preserve audit"
        device = restored.scalar(select(m.Device))
        assert (device.camera_id, device.slot_index, device.device_index) == ('CAM-001', 0, 0)
    engine.dispose()


@pytest.mark.parametrize('version', [1, 2, 3])
def test_legacy_camera_arrays_become_normalized_device_slots(
    archive_module, station, tmp_path, version,
):
    path = legacy_backup(archive_module, station, tmp_path, version=version,
                         camera_ids='CAM-002, CAM-001', camera_device_ids=[3, 1])
    validated = archive_module.validate_archive(path, tmp_path / 'camera-slots')
    devices = {row['camera_id']: row for row in validated.iter_rows('device')}
    assert (devices['CAM-002']['slot_index'], devices['CAM-002']['device_index']) == (0, 3)
    assert (devices['CAM-001']['slot_index'], devices['CAM-001']['device_index']) == (1, 1)
    assert all('camera_ids' not in row and 'camera_device_ids' not in row
               for row in validated.iter_rows('system_config'))
    assert all('total_scans' not in row and 'flagged_scans' not in row
               for row in validated.iter_rows('operator_profile'))


def test_v3_backup_still_validates_recorded_camera_columns(
    archive_module, station, tmp_path,
):
    path = legacy_backup(archive_module, station, tmp_path, version=3, camera_ids=123)
    with pytest.raises(archive_module.ArchiveError):
        archive_module.validate_archive(path, tmp_path / 'invalid-v3')


def test_v1_backup_still_enforces_legacy_required_values(archive_module, station, tmp_path):
    path = legacy_backup(archive_module, station, tmp_path, bad_null=True)
    with pytest.raises(archive_module.ArchiveError, match='Null'):
        archive_module.validate_archive(path, tmp_path / 'bad-legacy')


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_archive_quarantines_unknown_provenance(archive_module, station, tmp_path, version):
    station[0].execute(m.Scan.__table__.update().values(intake_id=None))
    station[0].commit()
    path = legacy_backup(archive_module, station, tmp_path, version=version)
    validated = archive_module.validate_archive(path, tmp_path / 'legacy-provenance')
    rows = list(validated.iter_rows("scan"))
    assert rows[0]['intake_provenance'] == 'unverified'
    assert rows[0]['intake_origin_id'] is None


@pytest.mark.parametrize("mutation", ["version", "schema", "count", "hash", "unknown", "missing", "traversal", "duplicate", "symlink", "case_collision", "bad_type", "bad_enum", "bad_fk", "bad_unique", "no_admin", "naive_time"])
def test_untrusted_archive_is_rejected_without_live_changes(archive_module, station, tmp_path, mutation):
    path = backup(archive_module, station, tmp_path)
    if mutation == "version":
        rewrite(path, edit_manifest=lambda m: m.update(version=999))
    elif mutation == "schema":
        rewrite(path, edit_manifest=lambda m: m["schema"]["user_role"].pop("name"))
    elif mutation in ("count", "hash"):
        rewrite(path, edit_manifest=lambda m: m["tables"]["scan"].update(
            {"count": 2} if mutation == "count" else {"sha256": "0" * 64}))
    elif mutation == "unknown":
        rewrite(path, extra=("payload.sql", b"DROP TABLE scan"))
    elif mutation == "missing":
        rewrite(path, omit=f"evidence/{station[2]}/camera.jpg")
    elif mutation == "traversal":
        rewrite(path, extra=("../escaped.txt", b"evil"))
    elif mutation == "duplicate":
        with pytest.warns(UserWarning):
            rewrite(path, extra=("manifest.json", b"{}"))
    elif mutation == "case_collision":
        rewrite(path, extra=("MANIFEST.JSON", b"{}"))
    elif mutation == "symlink":
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        rewrite(path, extra=(info, b"/etc/passwd"))
    elif mutation == "bad_type":
        rewrite(path, edit_row=("system_config", lambda rows: rows[0].update(confidence_threshold=True)))
    elif mutation == "bad_enum":
        rewrite(path, edit_row=("scan_classification", lambda rows: rows[0].update(cultivar="invalid")))
    elif mutation == "bad_fk":
        rewrite(path, edit_row=("scan", lambda rows: rows[0].update(operator_id=str(uuid4()))))
    elif mutation == "bad_unique":
        rewrite(path, edit_row=("user_role", lambda rows: rows.append(dict(rows[0], id=2))))
    elif mutation == "no_admin":
        rewrite(path, edit_row=("user_account", lambda rows: rows[0].update(status="Inactive")))
    elif mutation == "naive_time":
        rewrite(path, edit_row=("scan", lambda rows: rows[0].update(date_time="2025-01-02T00:30:00")))
    staging = tmp_path / "validation"
    with pytest.raises(archive_module.ArchiveError):
        archive_module.validate_archive(path, staging)
    assert not (tmp_path / "escaped.txt").exists()
    assert not staging.exists() or not list(staging.iterdir())
    assert station[0].scalar(select(m.Scan)).date_time == station[3]


def test_missing_referenced_evidence_never_publishes(archive_module, station, tmp_path):
    (station[1] / str(station[2]) / "thumbnail.jpg").unlink()
    with pytest.raises(archive_module.ArchiveError, match="evidence"):
        backup(archive_module, station, tmp_path)
    assert not (tmp_path / "backup.zip").exists()


def test_disk_full_never_publishes_or_removes_existing_files(archive_module, station, tmp_path, monkeypatch):
    destination = tmp_path / "backup.zip"
    destination.write_bytes(b"existing backup")
    original = zipfile.ZipFile.open

    def no_space(self, name, mode="r", *args, **kwargs):
        if mode == "w":
            raise OSError(errno.ENOSPC, "disk full")
        return original(self, name, mode, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", no_space)
    with pytest.raises(archive_module.ArchiveError):
        asyncio.run(archive_module.create_archive(AsyncDB(station[0]), station[1], destination))
    assert destination.read_bytes() == b"existing backup"
    assert not list(tmp_path.glob(".backup-*"))


def test_expanded_size_limit_rejects_before_staging(archive_module, station, tmp_path, monkeypatch):
    path = backup(archive_module, station, tmp_path)
    monkeypatch.setattr(archive_module, "MAX_EXPANDED_BYTES", 10)
    with pytest.raises(archive_module.ArchiveError, match="limit"):
        archive_module.validate_archive(path, tmp_path / "validation")


def test_truncated_zip_is_a_validation_error(archive_module, tmp_path):
    path = tmp_path / "broken.zip"
    path.write_bytes(b"PK\x03\x04broken")
    with pytest.raises(archive_module.ArchiveError):
        archive_module.validate_archive(path, tmp_path / "validation")


def test_backup_records_model_identity_without_including_weights(station, archive_module, tmp_path, monkeypatch):
    from app.config import get_settings
    weights = tmp_path / 'classifier.pt'; weights.write_bytes(b'model identity')
    monkeypatch.setattr(get_settings(), 'yolo_model_path', str(weights))
    result = backup(archive_module, station, tmp_path)
    with zipfile.ZipFile(result) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['prerequisites']['models']['classifier']['sha256'] == hashlib.sha256(b'model identity').hexdigest()
        assert not any(n.endswith('.pt') for n in z.namelist())


def test_backup_hashes_resolved_packaged_rfr_bundle(archive_module, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.services import spoilage

    app_dir = tmp_path / "app"
    (app_dir / "services").mkdir(parents=True)
    (app_dir / "ml").mkdir()
    bundle = app_dir / "ml" / "spoilage_rfr.joblib"
    bundle.write_bytes(b"packaged RFR identity")
    monkeypatch.setattr(spoilage, "__file__", str(app_dir / "services" / "spoilage.py"))
    monkeypatch.setattr(get_settings(), "rfr_model_path", "app/ml/weights/spoilage_rfr.joblib")
    monkeypatch.chdir(tmp_path)

    models = archive_module.model_prerequisites()

    assert models["spoilage"] == {
        "filename": bundle.name,
        "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize('cost', ['00', '99'])
def test_archive_rejects_unusable_administrator_bcrypt_cost(station, archive_module, tmp_path, cost):
    result = backup(archive_module, station, tmp_path)
    def invalid_hash(rows):
        rows[0]['password_hash'] = '$2b$'+cost+'$'+rows[0]['password_hash'][7:]
    rewrite(result, edit_row=('user_account', invalid_hash))
    with pytest.raises(archive_module.ArchiveError, match='usable active administrator'):
        archive_module.validate_archive(result, tmp_path / 'invalid-cost')


@pytest.mark.parametrize('values', [
    {'intake_provenance': 'invented'},
    {'intake_provenance': 'linked', 'intake_origin_id': None},
    {'intake_provenance': 'unlinked'},
    {'intake_provenance': 'unverified', 'intake_origin_id': None},
    {'intake_provenance': 'linked', 'intake_origin_id': str(uuid4())},
])
def test_current_archive_rejects_inconsistent_provenance(archive_module, station, tmp_path, values):
    path = backup(archive_module, station, tmp_path)
    rewrite(path, edit_row=('scan', lambda rows: rows[0].update(values)))
    with pytest.raises(archive_module.ArchiveError):
        archive_module.validate_archive(path, tmp_path / 'invalid-provenance')
