"""Authorized delivery of persisted camera evidence; no directory/static bypass."""
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.services.backup_archive import ArchiveError, _evidence_name, _no_links, _safe_name
from app.services.scan_records import load_authorized_scan

router = APIRouter(tags=["Scan evidence"])


@router.get("/captures/{scan_id}/{filename}")
async def get_evidence(scan_id: UUID, filename: str, db: DbSession, user: CurrentUser):
    scan = await load_authorized_scan(db, scan_id, user)
    root = get_settings().capture_path.absolute()
    try:
        relative = _safe_name(f"{scan_id}/{filename}")
        allowed = set()
        values = [image.file_path for image in scan.images]
        if scan.classification:
            values.append(scan.classification.thumbnail_url)
        for value in values:
            if value:
                try:
                    allowed.add(_evidence_name(value, root))
                except (ArchiveError, ValueError, OSError):
                    continue
        if relative not in allowed:
            raise HTTPException(404, "Image evidence is unavailable")
        path = root / str(scan_id) / filename
        _no_links(path)
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise HTTPException(404, "Image evidence is unavailable")
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
            Path(filename).suffix.lower()
        )
        if mime is None:
            raise HTTPException(404, "Image evidence is unavailable")
    except (ArchiveError, ValueError, OSError):
        raise HTTPException(404, "Image evidence is unavailable") from None
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
