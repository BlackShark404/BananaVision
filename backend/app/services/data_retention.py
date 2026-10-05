"""
RETENTION-01: Data retention background task.

Periodically checks if data_retention_enabled is True in SystemConfig,
and if so, deletes scans (with related records and capture files) older
than the configured retention period (default 30 days).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.services.capture_cleanup import remove_scan_captures
from app.core.database import async_session_factory
from app.core.time import now_manila
from app.models.system_config import SystemConfig
from app.models.scan import Scan
from app.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)
settings = get_settings()

# Run every 6 hours
RETENTION_CHECK_INTERVAL_SECONDS = 6 * 60 * 60


async def data_retention_worker():
    """Background task that enforces the data retention policy.

    Runs periodically:
    1. Reads SystemConfig.data_retention_enabled from the database.
    2. If disabled, sleeps until next check.
    3. If enabled, finds scans older than max_captures_retention_days
       and deletes them along with related DB records and capture files.
    """
    while True:
        try:
            await _run_retention_cycle()
        except asyncio.CancelledError:
            logger.info("Data retention worker cancelled")
            return
        except Exception as exc:
            logger.error(f"Data retention worker error: {exc}")

        await asyncio.sleep(RETENTION_CHECK_INTERVAL_SECONDS)


async def _run_retention_cycle():
    """Execute a single retention check and cleanup cycle."""
    async with async_session_factory() as db:
        # Check if retention is enabled
        config_result = await db.execute(select(SystemConfig).limit(1))
        config = config_result.scalar_one_or_none()

        if not config or not config.data_retention_enabled:
            logger.debug("Data retention is disabled — skipping cleanup")
            return

        retention_days = settings.max_captures_retention_days
        cutoff = now_manila() - timedelta(days=retention_days)

        logger.info(
            f"Data retention: cleaning records older than {retention_days} days "
            f"(before {cutoff.isoformat()})"
        )

        # Find scans older than the cutoff
        old_scans_result = await db.execute(
            select(Scan)
            .options(
                selectinload(Scan.classification),
                selectinload(Scan.status_logs),
                selectinload(Scan.images),
            )
            .where(Scan.date_time < cutoff)
        )
        old_scans = old_scans_result.scalars().all()

        expired_ids = [str(scan.id) for scan in old_scans]
        for scan in old_scans:
            await db.delete(scan)

        old_logs = (await db.execute(
            select(ActivityLog).where(ActivityLog.timestamp < cutoff)
        )).scalars().all()
        for log in old_logs:
            await db.delete(log)

        # Remove files only after the database transaction succeeds. A later cycle
        # retries failed file deletion because those directories are now orphans.
        await db.commit()
        files_removed = sum(remove_scan_captures(settings.capture_path, sid) for sid in expired_ids)
        referenced = {str(sid) for sid in (await db.execute(select(Scan.id))).scalars().all()}
        files_removed += remove_expired_orphans(settings.capture_path, referenced, cutoff.timestamp())
        logger.info("Data retention complete: %s scans, %s activity logs, %s capture directories removed",
                    len(expired_ids), len(old_logs), files_removed)


def remove_expired_orphans(root, referenced: set[str], cutoff_timestamp: float) -> int:
    """Only old UUID directories with no persisted scan qualify for orphan cleanup."""
    import uuid
    removed = 0
    if not root.exists():
        return removed
    for directory in root.iterdir():
        try:
            name = str(uuid.UUID(directory.name))
            if directory.name != name or name in referenced or directory.is_symlink() or not directory.is_dir():
                continue
            # Include children so an old directory containing a recent capture is retained.
            newest = max([directory.stat().st_mtime] + [p.stat().st_mtime for p in directory.rglob("*")])
            if newest < cutoff_timestamp:
                removed += remove_scan_captures(root, name)
        except (ValueError, OSError):
            logger.debug("Skipping unrecognized/unreadable capture directory %s", directory)
    return removed
