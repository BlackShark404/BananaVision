"""Public URLs contain evidence identifiers, never station filesystem paths."""
import os
import tempfile
from pathlib import Path

import cv2

from app.config import get_settings
from app.services.backup_archive import ArchiveError, _evidence_name

THUMBNAIL_EDGE = 256
THUMBNAIL_QUALITY = 75
THUMBNAIL_DIR = ".thumbs"


def evidence_url(value):
    if not value:
        return None
    try:
        return "/captures/" + _evidence_name(value, get_settings().capture_path)
    except (ArchiveError, OSError, ValueError):
        return None


def thumbnail_url(value):
    url = evidence_url(value)
    return f"{url}?variant=thumb" if url else None


def thumbnail_file(source: Path, cache_dir: Path) -> Path:
    """Return a cached 256 px JPEG preview, generating it from the original once."""
    target = cache_dir / f"{source.stem}.jpg"
    try:
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            return target
    except OSError:
        pass
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise ValueError("Unreadable image evidence")
    height, width = frame.shape[:2]
    scale = THUMBNAIL_EDGE / max(height, width)
    if scale < 1:
        frame = cv2.resize(
            frame, (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=cache_dir, prefix=".tmp-", suffix=".jpg")
    os.close(handle)
    try:
        if not cv2.imwrite(
            temporary, frame, [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_QUALITY],
        ):
            raise ValueError("Could not write a thumbnail")
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target
