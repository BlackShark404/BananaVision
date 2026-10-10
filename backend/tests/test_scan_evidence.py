"""Stored evidence requires the same ownership checks as scan detail."""
from types import SimpleNamespace
from uuid import uuid4

from app.models import ScanImage
from sqlalchemy.orm import Session

from tests.test_scan_records import operator_session
from tests.test_time_and_writes import application as application


def test_evidence_auth_missing_file_and_unregistered_paths(application, tmp_path, monkeypatch):
    from app.api.v1 import scan_evidence
    app = application
    root = tmp_path / 'captures'
    image = root / str(app.ids.scan) / 'camera.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'test image')
    (image.parent / 'secret.txt').write_text('not evidence')
    monkeypatch.setattr(scan_evidence, 'get_settings', lambda: SimpleNamespace(capture_path=root))
    app.app.include_router(scan_evidence.router)
    with Session(app.engine) as db:
        db.add(ScanImage(scan_id=app.ids.scan, camera_id='Historical', file_path=str(image)))
        db.commit()
    url = f'/captures/{app.ids.scan}/camera.jpg'
    response = app.client.get(url)
    assert response.status_code == 200 and response.content == b'test image'
    assert response.headers['cache-control'] == 'private, no-store'
    assert app.client.get(f'/captures/{app.ids.scan}/secret.txt').status_code == 404
    operator_session(app, uuid4())
    assert app.client.get(url).status_code == 403
    operator_session(app, app.ids.operator)
    assert app.client.get(url).status_code == 200
    image.unlink()
    assert app.client.get(url).status_code == 404
    assert app.client.get(f'/api/v1/scans/{app.ids.scan}').status_code == 200
    app.app.dependency_overrides.clear()
    assert app.client.get(url).status_code == 401
