"""Camera quality negotiation uses synthetic frames and disposable files only."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest

from app.config import Settings

camera_module = importlib.import_module("app.services.camera_manager")


def real_frame(width=1280, height=720):
    values = np.tile(np.arange(width, dtype=np.uint16) % 220 + 25, (height, 1))
    return np.stack([values, values // 2, 255 - values], axis=2).astype(np.uint8)


class SyntheticCamera:
    def __init__(self, max_width=1920, default_width=1920, default_height=1080, unsupported=()):
        self.max_width = max_width
        self.default_width = default_width
        self.default_height = default_height
        self.unsupported = unsupported
        self.properties = {}
        self.calls = []
        self.released = False

    def isOpened(self):  # noqa: N802 - OpenCV interface
        return not self.released

    def set(self, prop, value):
        self.calls.append((prop, value))
        if prop in self.unsupported:
            raise cv2.error("Unsupported camera control")
        self.properties[prop] = value
        return True

    def read(self):
        width = int(self.properties.get(cv2.CAP_PROP_FRAME_WIDTH, self.default_width))
        height = int(self.properties.get(cv2.CAP_PROP_FRAME_HEIGHT, self.default_height))
        if width > self.max_width:
            return False, None
        return True, real_frame(width, height)

    def release(self):
        self.released = True


def configure(monkeypatch, handle, **overrides):
    options = {"camera_warmup_frames": 0, **overrides}
    monkeypatch.setattr(camera_module, "settings", Settings(_env_file=None, **options))
    monkeypatch.setattr(camera_module.sys, "platform", "win32")
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda *_: handle)
    manager = camera_module.CameraManager()
    return manager, manager.configure(["CAM-001"], [0])


def test_native_quality_defaults_preserve_driver_focus():
    settings = Settings(_env_file=None)
    assert (settings.camera_resolution_w, settings.camera_resolution_h) == (1280, 720)
    assert settings.camera_autofocus is None
    assert settings.camera_manual_focus_value is None
    assert settings.camera_auto_white_balance is True
    assert settings.camera_auto_exposure is True
    assert settings.camera_preview_jpeg_quality == 90


def test_auto_color_controls_do_not_force_unverified_focus(monkeypatch):
    handle = SyntheticCamera()
    manager, result = configure(monkeypatch, handle)
    assert result == {0: True}
    assert handle.properties[cv2.CAP_PROP_AUTO_WB] == 1
    assert handle.properties[cv2.CAP_PROP_AUTO_EXPOSURE] == 1
    assert cv2.CAP_PROP_FOCUS not in handle.properties
    assert cv2.CAP_PROP_AUTOFOCUS not in handle.properties
    assert manager.get_resolution(0) == (1280, 720)


def test_per_camera_resolutions_support_mixed_emeet_2k_and_rapoo_1080p(monkeypatch):
    cameras = {
        0: SyntheticCamera(max_width=1920),  # Rapoo Full HD
        1: SyntheticCamera(max_width=2560),  # EMEET 2K
    }
    monkeypatch.setattr(camera_module, "settings", Settings(
        _env_file=None,
        camera_resolution_w=2560,
        camera_resolution_h=1440,
        camera_resolutions={"Top": "2560x1440", "Left": "1920x1080"},
    ))
    monkeypatch.setattr(camera_module.sys, "platform", "win32")
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda dev_id, *_: cameras[dev_id])
    manager = camera_module.CameraManager()
    result = manager.configure(["Top", "Left"], [1, 0])
    assert result == {1: True, 0: True}
    assert manager.get_resolution(1) == (2560, 1440)
    assert manager.get_resolution(0) == (1920, 1080)


def test_station_wide_2k_request_falls_back_to_1080p_for_standard_hd_cameras(monkeypatch):
    handle = SyntheticCamera(max_width=1920)
    manager, result = configure(
        monkeypatch, handle, camera_resolution_w=2560, camera_resolution_h=1440,
    )
    assert result == {0: True}
    assert manager.get_resolution(0) == (1920, 1080)
    widths = [value for prop, value in handle.calls if prop == cv2.CAP_PROP_FRAME_WIDTH]
    assert widths == [2560, 1920]


def test_unsupported_optional_controls_keep_a_working_camera_online(monkeypatch):
    handle = SyntheticCamera(unsupported=(
        cv2.CAP_PROP_AUTO_WB, cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_AUTOFOCUS,
    ))
    manager, result = configure(monkeypatch, handle, camera_autofocus=True)
    assert result == {0: True}
    assert manager.online_cameras == [0]
    assert not handle.released


def test_unusable_full_hd_falls_back_to_native_hd_and_reports_measured_size(monkeypatch):
    handle = SyntheticCamera(max_width=1280, default_width=1920, default_height=1080)
    manager, result = configure(
        monkeypatch, handle, camera_resolution_w=1920, camera_resolution_h=1080,
    )
    assert result == {0: True}
    widths = [value for prop, value in handle.calls if prop == cv2.CAP_PROP_FRAME_WIDTH]
    assert widths == [1920, 1280]
    assert manager.get_resolution(0) == (1280, 720)
    assert manager._capture_single(0).frame.shape == (720, 1280, 3)
    for index, (prop, _value) in enumerate(handle.calls):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            assert handle.calls[index - 1][0] == cv2.CAP_PROP_FPS
            assert handle.calls[index + 1][0] == cv2.CAP_PROP_FRAME_HEIGHT
            assert handle.calls[index + 2][0] == cv2.CAP_PROP_FOURCC


def test_vga_fallback_and_release_clear_measured_resolution(monkeypatch):
    manager, result = configure(monkeypatch, SyntheticCamera(max_width=640))
    assert result == {0: True}
    assert manager.get_resolution(0) == (640, 480)
    manager.release_all()
    assert manager.get_resolution(0) is None


def test_all_capture_modes_failing_release_the_handle(monkeypatch):
    handle = SyntheticCamera(max_width=0)
    manager, result = configure(monkeypatch, handle)
    assert result == {0: False}
    assert manager.online_cameras == []
    assert manager.get_resolution(0) is None
    assert handle.released


def test_explicit_legacy_manual_focus_is_preserved(monkeypatch):
    handle = SyntheticCamera()
    _manager, result = configure(
        monkeypatch, handle, camera_autofocus=False, camera_manual_focus_value=25,
    )
    assert result == {0: True}
    assert handle.properties[cv2.CAP_PROP_AUTOFOCUS] == 0
    assert handle.properties[cv2.CAP_PROP_FOCUS] == 25


def test_saved_evidence_uses_explicit_jpeg_quality_and_original_bgr(monkeypatch, tmp_path):
    handle = SyntheticCamera()
    manager, _result = configure(monkeypatch, handle, capture_dir=str(tmp_path))
    capture = manager._capture_single(0)
    original = capture.frame.copy()
    writes = []
    monkeypatch.setattr(camera_module.cv2, "imwrite", lambda path, frame, args:
                        writes.append((path, frame, args)) or True)
    manager.save_captures([capture], "isolated-scan")
    assert writes[0][1] is capture.frame
    assert writes[0][2] == [cv2.IMWRITE_JPEG_QUALITY, 95]
    np.testing.assert_array_equal(capture.frame, original)


@pytest.mark.parametrize("key,value", [
    ("camera_resolution_w", 0), ("camera_resolution_h", 0),
    ("camera_preview_jpeg_quality", 101), ("camera_capture_jpeg_quality", 0),
])
def test_invalid_quality_settings_are_rejected(key, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{key: value})


@pytest.mark.asyncio
async def test_device_status_reports_measured_resolution_after_fallback(monkeypatch):
    from app.services import configuration

    device = SimpleNamespace(camera_id="CAM-001", resolution=None, status="Offline")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: [device])),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(configuration, "camera_manager", SimpleNamespace(
        _logical_ids=["CAM-001"], _device_ids=[0], online_cameras=[0],
        get_resolution=lambda _device_id: (640, 480),
    ))
    await configuration.sync_devices(db)
    assert device.resolution == "640x480"
    assert device.status == "Online"


@pytest.mark.asyncio
async def test_startup_reports_measured_resolution_without_requested_dimensions(monkeypatch):
    from app.core import startup

    devices = []
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        add=devices.append, commit=AsyncMock(),
    )
    monkeypatch.setattr(startup, "camera_manager", SimpleNamespace(
        _get_camera_id=lambda _: "CAM-001", get_resolution=lambda _: (640, 480),
    ))
    monkeypatch.setattr(startup, "settings", SimpleNamespace(camera_labels=["Top"]))
    await startup._register_cameras(db, {0: True})
    assert devices[0].resolution == "640x480"
