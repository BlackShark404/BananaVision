"""Delete only a scan's UUID directory directly beneath the configured capture root."""
import logging
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def remove_scan_captures(root: Path, scan_id: str) -> bool:
    name = str(uuid.UUID(scan_id))
    base = root.resolve()
    directory = base / name
    if directory.is_symlink() or directory.resolve().parent != base:
        logger.warning("Refusing capture cleanup outside capture root: %s", directory)
        return False
    if not directory.exists():
        return False
    try:
        shutil.rmtree(directory)
        return True
    except OSError:
        logger.exception("Could not remove captures for scan %s", name)
        return False
