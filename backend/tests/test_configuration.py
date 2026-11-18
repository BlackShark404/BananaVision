"""Saved configuration, real inference arguments, and camera health contracts."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.v1 import config as config_api
from app.models import Device, SystemConfig
from app.schemas.common import SystemConfigUpdate
from app.services.camera_manager import CameraManager
from app.services.classification import BananaClassifier
from tests.test_time_and_writes import application, SessionAdapter  # noqa: F401


@pytest.mark.parametrize('changes', [
    {'confidence_threshold': 85.5}, {'confidence_threshold': True},
    {'confidence_threshold': '85'}, {'camera_ids': 'LEFT,,RIGHT'},
    {'camera_ids': 'A, B, C, D, E'}, {'camera_ids': 'A' * 51},
    {'confidence_threshold': None},
])
def test_invalid_configuration_cannot_be_saved(changes):
    with pytest.raises(ValidationError):
        SystemConfigUpdate(expected_revision=1, **changes)


def test_revision_is_required():
    with pytest.raises(ValidationError):
        SystemConfigUpdate(confidence_threshold=75)


@pytest.fixture
def configured(application, monkeypatch):
    with Session(application.engine) as db:
        db.execute(delete(Device))
        db.add_all([
            Device(camera_id='LEFT', label='Left', slot_index=0, device_index=0),
            Device(camera_id='RIGHT', label='Right', slot_index=1, device_index=1),
        ])
        db.commit()
    monkeypatch.setattr(config_api.camera_manager, '_device_ids', [0, 1])
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'camera_device_ids', [0, 1])
    return application


def test_stale_revision_does_not_overwrite_saved_threshold(configured):
    initial = configured.client.get('/api/v1/config')
    assert initial.status_code == 200, initial.text
    revision = initial.json().get('revision', 1)
    first = configured.client.patch('/api/v1/config', json={
        'expected_revision': revision, 'confidence_threshold': 63})
    assert first.status_code == 200, first.text
    stale = configured.client.patch('/api/v1/config', json={
        'expected_revision': revision, 'confidence_threshold': 22})
    assert stale.status_code == 409, stale.text
    assert configured.client.get('/api/v1/config').json()['confidence_threshold'] == 63


def test_failed_persistence_does_not_publish_camera_names(configured, monkeypatch):
    revision = configured.client.get('/api/v1/config').json().get('revision', 1)
    changed = []
    monkeypatch.setattr(config_api.camera_manager, 'set_logical_ids', changed.append)
    configured.state.fail_commit = True
    response = configured.client.patch('/api/v1/config', json={
        'expected_revision': revision, 'camera_ids': 'BACK, FRONT'})
    assert response.status_code == 500
    assert changed == []
    with Session(configured.engine) as db:
        assert [(d.camera_id, d.slot_index) for d in db.scalars(
            select(Device).where(Device.slot_index.is_not(None)).order_by(Device.slot_index)
        )] == [('LEFT', 0), ('RIGHT', 1)]


@pytest.mark.asyncio
async def test_latest_legacy_configuration_selected_without_deleting_history(configured):
    from app.services import configuration
    with Session(configured.engine) as db:
        db.add(SystemConfig(confidence_threshold=72))
        db.commit()
    async with SessionAdapter(configured.engine, configured.state) as db:
        result = await configuration.get_config(db)
        assert result.confidence_threshold == 72
        assert [slot.camera_id for slot in result.camera_slots] == ['LEFT', 'RIGHT']
        assert result.legacy_conflict is True
        await db.commit()
    with Session(configured.engine) as db:
        assert len(db.scalars(select(SystemConfig)).all()) == 2


@pytest.mark.asyncio
async def test_invalid_legacy_configuration_is_not_promoted(configured):
    from app.services import configuration
    with Session(configured.engine) as db:
        db.add(SystemConfig(confidence_threshold=0, data_retention_enabled=True))
        db.commit()
    async with SessionAdapter(configured.engine, configured.state) as db:
        result = await configuration.get_config(db)
        # The old bootstrap default (85) is auto-migrated to the current
        # default (80) when no admin has explicitly saved the threshold.
        assert result.confidence_threshold == 80
        assert result.legacy_conflict is True
        await db.commit()


def test_classifier_receives_explicit_saved_threshold():
    classifier = BananaClassifier()
    calls = []
    classifier._model = SimpleNamespace(predict=lambda image, **kwargs: calls.append(kwargs) or [])
    result = classifier.predict(np.zeros((4, 4, 3), dtype=np.uint8), confidence_threshold=0.63)
    assert result.finger_count == 0
    assert calls[0]['conf'] == 0.63


def test_open_handle_without_usable_frame_is_offline():
    manager = CameraManager()
    manager._device_ids = [0]
    manager._cameras = {0: SimpleNamespace(isOpened=lambda: True, read=lambda: (True, np.zeros((4, 4, 3), dtype=np.uint8)))}
    manager._locks = {0: threading.RLock()}
    assert manager.probe_all() == {0: False}
    assert manager.online_cameras == []


def test_capture_rejects_unusable_frames():
    manager = CameraManager()
    manager._device_ids = [0]
    manager._cameras = {0: SimpleNamespace(isOpened=lambda: True, read=lambda: (True, np.zeros((4, 4, 3), dtype=np.uint8)))}
    manager._locks = {0: threading.RLock()}
    from app.core.exceptions import CameraError
    with pytest.raises(CameraError):
        manager._capture_single(0)


@pytest.mark.asyncio
async def test_scan_snapshots_detection_cutoff_separately_from_review(configured, monkeypatch):
    from app.services import scan_service
    from app.core.exceptions import ModelInferenceError
    with Session(configured.engine) as db:
        db.scalar(select(SystemConfig)).confidence_threshold = 63
        db.commit()
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    captures = [SimpleNamespace(camera_id=name, camera_label=name, frame=frame, file_path=None)
                for name in ['LEFT', 'RIGHT']]
    monkeypatch.setattr(scan_service, 'camera_manager', SimpleNamespace(
        online_cameras=[0, 1], capture_all=AsyncMock(return_value=captures), save_captures=lambda values, _: values))
    monkeypatch.setattr(scan_service, 'banana_pre_detector', SimpleNamespace(detect=lambda _: SimpleNamespace(banana_detected=True)))
    classifier = BananaClassifier()
    calls = []
    loop_thread = threading.get_ident()
    def model_predict(image, **kwargs):
        calls.append((kwargs['conf'], threading.get_ident() != loop_thread))
        return []
    classifier._model = SimpleNamespace(predict=model_predict)
    monkeypatch.setattr(scan_service, 'banana_classifier', classifier)
    monkeypatch.setattr(scan_service.ws_manager, 'send_to_room', AsyncMock())
    async with SessionAdapter(configured.engine, configured.state) as db:
        with pytest.raises(ModelInferenceError):
            await scan_service.execute_scan_pipeline(db, configured.ids.profile, configured.ids.operator, 'Operator')
    assert calls == [(0.50, True), (0.50, True)]


def test_slot_count_mismatch_does_not_save(configured):
    revision = configured.client.get('/api/v1/config').json()['revision']
    result = configured.client.patch('/api/v1/config', json={'expected_revision': revision, 'camera_ids': 'ONLY'})
    assert result.status_code == 422
    with Session(configured.engine) as db:
        assert [(d.camera_id, d.slot_index) for d in db.scalars(
            select(Device).where(Device.slot_index.is_not(None)).order_by(Device.slot_index)
        )] == [('LEFT', 0), ('RIGHT', 1)]


def test_saved_mapping_reports_partial_hardware_failure_without_env_write(configured, monkeypatch, tmp_path):
    from app.api.v1 import cameras
    from app.services import configuration
    import importlib
    camera_module = importlib.import_module('app.services.camera_manager')
    frame = np.tile(np.arange(64, dtype=np.uint8), (64, 1)) * 4
    frame = np.stack([frame] * 3, axis=2)
    class Handle:
        def __init__(self, index, *args): self.index = index
        def isOpened(self): return True
        def set(self, *_): pass
        def read(self): return True, frame if self.index == 2 else np.zeros_like(frame)
        def release(self): pass
    monkeypatch.setattr(camera_module.cv2, 'VideoCapture', Handle)
    manager = CameraManager()
    monkeypatch.setattr(configuration, 'camera_manager', manager)
    monkeypatch.setattr(cameras, 'camera_manager', manager)
    configured.app.include_router(cameras.router, prefix='/api/v1')
    monkeypatch.chdir(tmp_path)
    revision = configured.client.get('/api/v1/config').json()['revision']
    result = configured.client.post('/api/v1/cameras/mapping', json={'expected_revision': revision, 'device_ids': [2, 0], 'operation_id': str(__import__('uuid').uuid4())})
    assert result.status_code == 200, result.text
    value = result.json()
    assert value['camera_device_ids'] == [2, 0]
    assert value['application_status'] == 'partial'
    assert value['application_error']
    assert manager.online_cameras == [2]
    assert not (tmp_path / '.env').exists()
    with Session(configured.engine) as db:
        assert [(d.camera_id, d.device_index) for d in db.scalars(
            select(Device).where(Device.slot_index.is_not(None)).order_by(Device.slot_index)
        )] == [('LEFT', 2), ('RIGHT', 0)]


def test_rename_drops_only_colliding_unassigned_device(configured, monkeypatch):
    from app.services import configuration
    with Session(configured.engine) as db:
        db.add_all([
            Device(camera_id='TOP', label='Unassigned top'),
            Device(camera_id='SPARE', label='Unassigned spare'),
        ])
        db.commit()
    monkeypatch.setattr(configuration, 'apply_camera_config', AsyncMock())
    revision = configured.client.get('/api/v1/config').json()['revision']
    result = configured.client.patch('/api/v1/config', json={
        'expected_revision': revision, 'camera_ids': 'TOP, RIGHT',
    })
    assert result.status_code == 200, result.text
    with Session(configured.engine) as db:
        rows = db.scalars(select(Device)).all()
        assert {d.camera_id: d.slot_index for d in rows} == {
            'TOP': 0, 'RIGHT': 1, 'SPARE': None,
        }
        assert all(not d.camera_id.startswith('pending-') for d in rows)


def test_logical_rename_preserves_slot_uuid(configured, monkeypatch):
    from app.services import configuration
    with Session(configured.engine) as db:
        left = db.scalar(select(Device).where(Device.slot_index == 0))
        right = db.scalar(select(Device).where(Device.slot_index == 1))
        left_id, right_id = left.id, right.id
    monkeypatch.setattr(configuration, 'apply_camera_config', AsyncMock())
    revision = configured.client.get('/api/v1/config').json()['revision']
    result = configured.client.patch('/api/v1/config', json={'expected_revision': revision, 'camera_ids': 'RIGHT, LEFT'})
    assert result.status_code == 200, result.text
    with Session(configured.engine) as db:
        assert db.get(Device, left_id).camera_id == 'RIGHT'
        assert db.get(Device, right_id).camera_id == 'LEFT'


def test_expand_two_slots_to_four_persists_and_lists_every_camera(configured, monkeypatch):
    from app.api.v1 import cameras
    from app.services import configuration

    apply = AsyncMock()
    monkeypatch.setattr(configuration, 'apply_camera_config', apply)
    configured.app.include_router(cameras.router, prefix='/api/v1')
    revision = configured.client.get('/api/v1/config').json()['revision']
    response = configured.client.patch('/api/v1/config', json={
        'expected_revision': revision, 'camera_ids': 'LEFT, RIGHT, TOP, REAR',
        'camera_device_ids': [1, 2, 3, 4],
    })
    assert response.status_code == 200, response.text
    apply.assert_awaited_once()
    assert response.json()['camera_device_ids'] == [1, 2, 3, 4]
    listed = configured.client.get('/api/v1/cameras').json()
    assert [camera['device_id'] for camera in listed] == [1, 2, 3, 4]
    assert [camera['camera_id'] for camera in listed] == ['LEFT', 'RIGHT', 'TOP', 'REAR']
    with Session(configured.engine) as db:
        assert [(d.camera_id, d.slot_index, d.device_index) for d in db.scalars(
            select(Device).where(Device.slot_index.is_not(None)).order_by(Device.slot_index)
        )] == [('LEFT', 0, 1), ('RIGHT', 1, 2), ('TOP', 2, 3), ('REAR', 3, 4)]
