from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.deps import CurrentUser, DbSession, StreamDbSession
from app.core.http import get_client_ip
from app.schemas.scan_logs import ScanLogList, ScanLogPending, ScanLogQuery, ScanLogReconciliation
from app.services import audit
from app.services.scan_logs import (
    check_export_snapshot,
    export_scan_logs_pdf,
    export_scan_logs_xlsx,
    list_scan_logs,
    pending_scan_count,
    reconcile_scan_logs,
)
from app.services.scan_records import is_admin, scan_scope

router = APIRouter(prefix="/scan-logs", tags=["Scan Logs"])

# Paging, sorting and snapshot bookkeeping do not change which records leave the station.
NOT_FILTERS = {"format", "stable", "snapshot_id", "page", "page_size", "limit", "sort", "direction"}
FREE_TEXT_FILTERS = {"search", "source", "source_key"}


def export_details(user, query: ScanLogQuery) -> str:
    filters = query.model_dump(mode="json", exclude_defaults=True, exclude=NOT_FILTERS)
    text = ", ".join(
        f"{name} {audit.quoted(value, 80) if name in FREE_TEXT_FILTERS else audit.clean(value, 60)}"
        for name, value in filters.items()
    )
    scope = "all accounts" if is_admin(user) else "own scans"
    snapshot = f"; snapshot {query.snapshot_id}" if query.snapshot_id else ""
    return (
        f"Exported scan logs ({query.format}, {scope}): "
        f"filters {audit.clean(text, 300) or 'none'}{snapshot}"
    )


@router.get("", response_model=ScanLogList)
async def scan_logs(db: DbSession, user: CurrentUser, query: Annotated[ScanLogQuery, Query()]):
    """No business_date means all history. All supplied filters intersect account scope."""
    return await list_scan_logs(db, user, query)


@router.get("/pending", response_model=ScanLogPending)
async def scan_logs_pending(
    db: DbSession, user: CurrentUser, query: Annotated[ScanLogQuery, Query()],
):
    """Count committed scans newer than this snapshot without changing its page."""
    if query.snapshot_id is None:
        raise HTTPException(422, "A browse snapshot is required for live scan counts.")
    return await pending_scan_count(db, user, query)


@router.get("/reconcile", response_model=ScanLogReconciliation)
async def scan_logs_reconcile(
    db: DbSession, user: CurrentUser, query: Annotated[ScanLogQuery, Query()],
):
    """Refresh page values and metrics without replacing its frozen membership."""
    if query.snapshot_id is None:
        raise HTTPException(422, "A browse snapshot is required for reconciliation.")
    return await reconcile_scan_logs(db, user, query)


@router.get("/export")
async def scan_logs_export(
    request: Request,
    db: StreamDbSession,
    user: CurrentUser,
    query: Annotated[ScanLogQuery, Query()],
):
    """Export every matching row in the same sort order; pagination is ignored."""
    scan_scope(user)  # A refused export is not logged as an export.
    # An expired, foreign or changed snapshot is refused here, before the export row; the
    # check releases its account lock.
    await check_export_snapshot(db, user, query)
    # The stream session never commits, so the row is written through its own session. It is
    # written before the export queries: a snapshot export locks this account's row, and the
    # audit insert would then wait on that lock. No audit row, no file (503).
    await audit.emit(
        audit.AuditAction.DATA_EXPORTED, export_details(user, query),
        actor=user, ip=get_client_ip(request), required=True,
    )
    if query.format == "pdf":
        pdf_bytes = await export_scan_logs_pdf(db, user, query)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="bananavision_scan_logs.pdf"'},
        )
    xlsx_bytes = await export_scan_logs_xlsx(db, user, query)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bananavision_scan_logs.xlsx"'},
    )
