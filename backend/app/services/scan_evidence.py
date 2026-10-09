"""Public URLs contain evidence identifiers, never station filesystem paths."""
from app.config import get_settings
from app.services.backup_archive import ArchiveError, _evidence_name


def evidence_url(value):
    if not value:
        return None
    try:
        return "/captures/" + _evidence_name(value, get_settings().capture_path)
    except (ArchiveError, OSError, ValueError):
        return None
