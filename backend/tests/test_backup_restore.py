"""Restore recovery operates only on temporary SQLite databases and directories."""

import pytest

from tests.test_backup_archive import AsyncDB, archive_module, station  # noqa: F401


def test_restore_service_available():
    from app.services.backup_restore import MaintenanceService
    assert callable(MaintenanceService)


@pytest.mark.asyncio
async def test_recovery_chooses_files_using_committed_marker(tmp_path):
    from app.services.backup_restore import reconcile_evidence
    root = tmp_path / 'captures'
    old = tmp_path / 'old'
    new = tmp_path / 'new'
    old.mkdir(); new.mkdir()
    (old / 'old.jpg').write_bytes(b'old')
    (new / 'new.jpg').write_bytes(b'new')
    # Crash after old tree rename, before new promotion.
    reconcile_evidence(root, old, new, committed=False)
    assert (root / 'old.jpg').read_bytes() == b'old'
    root.rename(old)
    reconcile_evidence(root, old, new, committed=True)
    assert (root / 'new.jpg').read_bytes() == b'new'
    assert (old / 'old.jpg').is_file()


def test_import_does_not_create_capture_root(tmp_path, monkeypatch):
    import importlib

    from app.config import get_settings
    root = tmp_path / 'not-yet-recovered'
    monkeypatch.setattr(get_settings(), 'capture_dir', str(root))
    import app.main
    importlib.reload(app.main)
    assert not root.exists()


def test_temporary_validation_expiry_preserves_backups_and_recovery(tmp_path):
    import os
    import time
    from uuid import uuid4

    from app.services.backup_restore import MaintenanceService, atomic_json
    service = MaintenanceService(None, None, tmp_path / 'captures')
    service.root.mkdir()
    expired = service.directory(uuid4()); (expired / 'upload.zip').write_bytes(b'old')
    rollback = service.directory(uuid4()); (rollback / 'rollback.zip').write_bytes(b'evidence')
    backup = service.directory(uuid4()); (backup / 'station.zip').write_bytes(b'backup')
    active = service.directory(uuid4()); (active / 'upload.zip').write_bytes(b'active')
    recent = service.directory(uuid4()); (recent / 'upload.zip').write_bytes(b'new')
    atomic_json(service.journal, {'id':rollback.name, 'validation_id':active.name, 'phase':'restore'})
    for directory in (expired, rollback, backup, active):
        for path in [*directory.iterdir(), directory]:
            os.utime(path, (time.time()-172800, time.time()-172800))
    service.cleanup_temporary()
    assert not expired.exists()
    assert all(p.is_dir() for p in (rollback, backup, active, recent))
