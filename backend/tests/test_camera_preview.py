"""Camera previews use synthetic frames and never acquire physical camera handles."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import cameras


@pytest.fixture
def preview(monkeypatch):
    @asynccontextmanager
    async def operation():
        yield

    async def run_blocking(function, *args):
        return function(*args)

    manager = SimpleNamespace(
        online_cameras=[7], generation=1, _capture_single=Mock(),
    )
    encoder = Mock(return_value=(True, np.array([1, 2, 3], dtype=np.uint8)))
    monkeypatch.setattr(cameras, 'camera_manager', manager)
    monkeypatch.setattr(cameras, 'coordinator', SimpleNamespace(
        operation=operation, assert_ready=Mock(),
    ))
    monkeypatch.setattr(cameras, 'run_blocking', run_blocking)
    monkeypatch.setattr(cameras, 'settings', SimpleNamespace(
        camera_preview_max_width=1280, camera_preview_max_height=720,
        camera_preview_jpeg_quality=90,
    ))
    monkeypatch.setattr(cameras.cv2, 'imencode', encoder)
    return SimpleNamespace(manager=manager, encoder=encoder)


@pytest.mark.parametrize('shape, expected_shape', [
    ((480, 640, 3), (480, 640, 3)),
    ((1080, 1920, 3), (720, 1280, 3)),
    ((1920, 1080, 3), (720, 405, 3)),
    ((1200, 1600, 3), (720, 960, 3)),
])
@pytest.mark.asyncio
async def test_preview_preserves_aspect_ratio_without_upscaling(
    preview, monkeypatch, shape, expected_shape,
):
    frame = np.zeros(shape, dtype=np.uint8)
    preview.manager._capture_single.return_value = SimpleNamespace(frame=frame)
    resize = Mock(wraps=cameras.cv2.resize)
    monkeypatch.setattr(cameras.cv2, 'resize', resize)
    stream = cameras.generate_frames(7)
    try:
        chunk = await anext(stream)
    finally:
        await stream.aclose()
    assert chunk == b'--frame\r\nContent-Type: image/jpeg\r\n\r\n\x01\x02\x03\r\n'
    encoded = preview.encoder.call_args.args[1]
    assert encoded.shape == expected_shape
    if shape == expected_shape:
        assert encoded is frame
        resize.assert_not_called()
    else:
        assert resize.call_args.kwargs == {'interpolation': cameras.cv2.INTER_AREA}


@pytest.mark.asyncio
async def test_preview_preserves_bgr_pixels_and_uses_configured_jpeg_quality(preview):
    frame = np.array([[[255, 0, 0], [0, 0, 255], [0, 255, 0]]], dtype=np.uint8)
    original = frame.copy()
    preview.manager._capture_single.return_value = SimpleNamespace(frame=frame)
    stream = cameras.generate_frames(7)
    try:
        await anext(stream)
    finally:
        await stream.aclose()
    extension, encoded, parameters = preview.encoder.call_args.args
    assert extension == '.jpg'
    np.testing.assert_array_equal(encoded, original)
    np.testing.assert_array_equal(frame, original)
    assert parameters == [cameras.cv2.IMWRITE_JPEG_QUALITY, 90]


@pytest.mark.asyncio
async def test_preview_stops_if_mapping_changes_during_capture(preview):
    def capture(_):
        preview.manager.generation += 1
        return SimpleNamespace(frame=np.zeros((480, 640, 3), dtype=np.uint8))

    preview.manager._capture_single.side_effect = capture
    stream = cameras.generate_frames(7)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    preview.encoder.assert_not_called()


@pytest.mark.parametrize('fps', ['0', '-1', '31', '1000000000', 'inf'])
def test_preview_rejects_invalid_frame_rates_before_capture(preview, fps):
    app = FastAPI()
    app.include_router(cameras.router)
    with TestClient(app) as client:
        response = client.get(f'/cameras/preview/7?fps={fps}')
    assert response.status_code == 422
    preview.manager._capture_single.assert_not_called()
    preview.encoder.assert_not_called()
