"""Capture backend inventory and administrator access with isolated fixtures."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1 import cameras
from app.models import SystemConfig
from app.services import camera_discovery
from tests.test_time_and_writes import application  # noqa: F401


@pytest.mark.parametrize('preference, api', [('auto', 700), ('dshow', 700), ('msmf', 1400)])
def test_names_use_capture_backend_indices_and_distinguish_identical_cameras(
    monkeypatch, preference, api,
):
    monkeypatch.setattr(camera_discovery.sys, 'platform', 'win32')
    monkeypatch.setattr(camera_discovery.get_settings(), 'camera_backend', preference)
    enumerator = Mock(return_value=[
        SimpleNamespace(index=0, name='ACER HD User Facing', path='builtin'),
        SimpleNamespace(index=1, name='EMEET SmartCam C100 2K', path='usb-port-one'),
        SimpleNamespace(index=2, name='EMEET SmartCam C100 2K', path='usb-port-two'),
    ])
    monkeypatch.setattr(camera_discovery, '_enumerate_backend', enumerator)
    capture = Mock(side_effect=AssertionError('Discovery must never open video streams'))
    monkeypatch.setattr(camera_discovery.cv2, 'VideoCapture', capture)
    result = camera_discovery.discover_camera_devices()
    enumerator.assert_called_once_with(api)
    capture.assert_not_called()
    assert result['error'] is None
    assert [device['device_id'] for device in result['devices']] == [0, 1, 2]
    assert result['devices'][1]['name'] == result['devices'][2]['name']
    assert result['devices'][1]['device_uid'] != result['devices'][2]['device_uid']
    assert all('path' not in device for device in result['devices'])


@pytest.mark.parametrize('error', [ImportError('unavailable'), RuntimeError('driver failure')])
def test_enumeration_failure_keeps_manual_configuration_available(monkeypatch, error):
    monkeypatch.setattr(camera_discovery.sys, 'platform', 'win32')
    monkeypatch.setattr(camera_discovery, '_enumerate_backend', Mock(side_effect=error))
    result = camera_discovery.discover_camera_devices()
    assert result['devices'] == []
    assert result['error']


def test_non_windows_does_not_guess_indices(monkeypatch):
    monkeypatch.setattr(camera_discovery.sys, 'platform', 'linux')
    enumerator = Mock()
    monkeypatch.setattr(camera_discovery, '_enumerate_backend', enumerator)
    assert camera_discovery.discover_camera_devices()['error']
    enumerator.assert_not_called()


def test_discovery_includes_unassigned_device_and_actual_saved_health(application, monkeypatch):  # noqa: F811
    application.app.include_router(cameras.router, prefix='/api/v1')
    with Session(application.engine) as db:
        saved = db.scalar(select(SystemConfig))
        saved.camera_device_ids = [0, 1, 3, 4]
        db.commit()
    inventory = {'backend': 'dshow', 'error': None, 'devices': [
        {'device_id': index, 'name': f'Device {index}', 'device_uid': str(index)}
        for index in range(4)
    ]}
    enumerate_devices = Mock(return_value=inventory)
    monkeypatch.setattr(cameras, 'discover_camera_devices', enumerate_devices)
    monkeypatch.setattr(cameras, 'camera_manager', SimpleNamespace(
        _device_ids=[0, 1, 3, 4],
        _logical_ids=['CAM-001', 'CAM-002', 'CAM-003', 'CAM-004'], online_cameras=[0, 1, 3],
    ))
    response = application.client.get('/api/v1/cameras/discovery')
    assert response.status_code == 200, response.text
    devices = response.json()['devices']
    assert len(devices) == 4
    assert devices[2]['configured_camera_id'] is None
    assert devices[2]['online'] is False  # Detected does not imply a verified video feed.
    assert devices[3]['configured_camera_id'] == 'CAM-003'
    assert devices[3]['online'] is True


def test_operator_cannot_enumerate_device_inventory(application, monkeypatch):  # noqa: F811
    application.app.include_router(cameras.router, prefix='/api/v1')
    application.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=application.ids.operator, role=SimpleNamespace(name='Operator'),
    )
    enumerator = Mock()
    monkeypatch.setattr(cameras, 'discover_camera_devices', enumerator)
    assert application.client.get('/api/v1/cameras/discovery').status_code == 403
    enumerator.assert_not_called()
