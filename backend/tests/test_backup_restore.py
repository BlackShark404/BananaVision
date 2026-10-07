"""Restore recovery operates only on temporary SQLite databases and directories."""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserAccount, MaintenanceState
from tests.test_backup_archive import station, archive_module, AsyncDB  # noqa: F401


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
