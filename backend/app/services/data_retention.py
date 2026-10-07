"""Clean old unreferenced captures; persisted history and evidence are retained."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.time import now_manila
from app.models.scan import Scan
from app.models.scan_image import ScanImage
from app.models.scan_classification import ScanClassification
from app.services.capture_cleanup import remove_scan_captures
from app.services.configuration import get_config
from app.services.maintenance_state import get_state
from app.services.runtime_operations import coordinator, run_blocking
from app.services.backup_archive import _no_links, _evidence_name, ArchiveError

logger = logging.getLogger(__name__)
settings = get_settings()
RETENTION_CHECK_INTERVAL_SECONDS = 6 * 60 * 60


async def data_retention_worker():
    while True:
        try:
            await _run_retention_cycle()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception('Retention cleanup failed; persisted records remain protected')
        await asyncio.sleep(RETENTION_CHECK_INTERVAL_SECONDS)


async def _run_retention_cycle():
    async with coordinator.exclusive('retention'):
        async with async_session_factory() as db:
            if not (await get_config(db)).data_retention_enabled:
                await db.commit()
                return
            state = await get_state(db)
            state.retention = {**(state.retention or {}), 'attempted_at': now_manila().isoformat(), 'error': None}
            await db.commit()
            try:
                referenced = {str(sid) for sid in (await db.execute(select(Scan.id))).scalars()}
                for column in (ScanImage.file_path, ScanClassification.thumbnail_url):
                    for value in (await db.execute(select(column).where(column.is_not(None)))).scalars():
                        relative = _evidence_name(value, settings.capture_path)
                        referenced.add(relative.split('/')[0])
                cutoff = now_manila() - timedelta(days=settings.max_captures_retention_days)
                removed = await run_blocking(remove_expired_orphans, settings.capture_path, referenced, cutoff.timestamp())
                state.retention = {**state.retention, 'completed_at': now_manila().isoformat(),
                                   'directories_removed': removed, 'error': None}
                await db.commit()
            except Exception:
                await db.rollback()
                state = await get_state(db)
                state.retention = {**(state.retention or {}), 'error': 'Cleanup failed; see server logs. No history was deleted.'}
                await db.commit()
                raise


def remove_expired_orphans(root, referenced: set[str], cutoff_timestamp: float) -> int:
    removed = 0
    _no_links(root.absolute())
    if not root.exists():
        return 0
    for directory in root.iterdir():
        try:
            name = str(uuid.UUID(directory.name))
        except ValueError:
            continue
        if name != directory.name or name in referenced:
            continue
        try:
            _no_links(directory.absolute())
            if not directory.is_dir():
                continue
            newest = directory.stat().st_mtime
            for child in directory.rglob('*'):
                _no_links(child.absolute())
                newest = max(newest, child.stat().st_mtime)
            if newest < cutoff_timestamp:
                if not remove_scan_captures(root, name):
                    raise OSError('Could not remove eligible orphan capture directory')
                removed += 1
        except ArchiveError:
            logger.warning('Skipping linked capture directory %s', directory.name)
    return removed
