"""Windows multi-camera initialization without opening physical devices."""
import asyncio
import importlib

import numpy as np
import pytest

camera_module = importlib.import_module('app.services.camera_manager')


@pytest.mark.parametrize('backend, expected', [('auto', 'CAP_DSHOW'), ('msmf', 'CAP_MSMF')])
def test_four_windows_cameras_use_requested_backend(monkeypatch, backend, expected):
    monkeypatch.setattr(camera_module.sys, 'platform', 'win32')
    monkeypatch.setattr(camera_module.settings, 'camera_backend', backend)
    monkeypatch.setattr(camera_module.settings, 'camera_warmup_frames', 0)
    opened = []
    frame = np.tile(np.arange(64, dtype=np.uint8) * 4, (64, 1))
    frame = np.stack([frame] * 3, axis=2)

    class Handle:
        def __init__(self, index, api):
            self.index, self.api, self.properties = index, api, {}
            self.released = False
            opened.append(self)

        def isOpened(self):  # noqa: N802 - OpenCV handle interface
            return not self.released

        def set(self, prop, value):
            self.properties[prop] = value
            return True

        def read(self):
            return True, frame

        def release(self):
            self.released = True

    monkeypatch.setattr(camera_module.cv2, 'VideoCapture', Handle)
    manager = camera_module.CameraManager()
    assert manager.configure(['TOP', 'LEFT', 'RIGHT', 'REAR'], [1, 2, 3, 4]) == dict.fromkeys(
        [1, 2, 3, 4], True,
    )
    assert manager.online_cameras == [1, 2, 3, 4]
    assert [handle.index for handle in opened] == [1, 2, 3, 4]
    assert all(handle.api == getattr(camera_module.cv2, expected) for handle in opened)
    assert all(handle.properties[camera_module.cv2.CAP_PROP_FOURCC]
               == camera_module.cv2.VideoWriter_fourcc(*'MJPG') for handle in opened)
    assert all(handle.properties[camera_module.cv2.CAP_PROP_FPS] == 15 for handle in opened)
    assert not any(handle.released for handle in opened)
    captures = asyncio.run(manager.capture_all())
    assert [capture.camera_index for capture in captures] == [1, 2, 3, 4]
    assert [capture.camera_id for capture in captures] == ['TOP', 'LEFT', 'RIGHT', 'REAR']
    manager.release_all()
    assert all(handle.released for handle in opened)


def test_failed_windows_open_releases_handle_without_warmup(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(camera_module.sys, 'platform', 'win32')
    handle = Mock()
    handle.isOpened.return_value = False
    monkeypatch.setattr(camera_module.cv2, 'VideoCapture', Mock(return_value=handle))
    manager = camera_module.CameraManager()
    assert manager.configure(['TOP'], [4]) == {4: False}
    handle.release.assert_called_once()
    handle.read.assert_not_called()
    assert manager.online_cameras == []


def test_non_windows_retains_default_backend(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(camera_module.sys, 'platform', 'linux')
    monkeypatch.setattr(camera_module.settings, 'camera_backend', 'auto')
    handle = Mock()
    handle.isOpened.return_value = False
    factory = Mock(return_value=handle)
    monkeypatch.setattr(camera_module.cv2, 'VideoCapture', factory)
    camera_module.CameraManager().configure(['TOP'], [4])
    factory.assert_called_once_with(4)


def test_directshow_fps_reset_does_not_undo_final_mjpg(monkeypatch):
    monkeypatch.setattr(camera_module.sys, 'platform', 'win32')
    monkeypatch.setattr(camera_module.settings, 'camera_warmup_frames', 0)
    frame = np.tile(np.arange(64, dtype=np.uint8) * 4, (64, 1))
    frame = np.stack([frame] * 3, axis=2)

    class DirectShow:
        codec = camera_module.cv2.VideoWriter_fourcc(*'YUY2')

        def isOpened(self):  # noqa: N802 - OpenCV interface
            return True

        def set(self, prop, value):
            if prop == camera_module.cv2.CAP_PROP_FPS:
                self.codec = camera_module.cv2.VideoWriter_fourcc(*'YUY2')
            elif prop == camera_module.cv2.CAP_PROP_FOURCC:
                self.codec = value
            return True

        def read(self):
            compressed = self.codec == camera_module.cv2.VideoWriter_fourcc(*'MJPG')
            return True, frame if compressed else np.zeros_like(frame)

        def release(self):
            pass

    monkeypatch.setattr(camera_module.cv2, 'VideoCapture', lambda *_: DirectShow())
    manager = camera_module.CameraManager()
    assert manager.configure(['A', 'B', 'C', 'D'], [0, 1, 3, 2]) == dict.fromkeys(
        [0, 1, 3, 2], True,
    )
