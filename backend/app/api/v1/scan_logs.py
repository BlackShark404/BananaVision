from typing import Annotated

from fastapi import APIRouter, Query, Response
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, StreamDbSession
from app.schemas.scan_logs import ScanLogList, ScanLogQuery
from app.services.scan_logs import export_scan_logs, export_scan_logs_xlsx, list_scan_logs

router = APIRouter(prefix="/scan-logs", tags=["Scan Logs"])


@router.get("", response_model=ScanLogList)
async def scan_logs(db: DbSession, user: CurrentUser, query: Annotated[ScanLogQuery, Query()]):
    """No business_date means all history. All supplied filters intersect account scope."""
    return await list_scan_logs(db, user, query)


@router.get("/export")
async def scan_logs_export(
    db: StreamDbSession,
    user: CurrentUser,
    query: Annotated[ScanLogQuery, Query()],
):
    """Export every matching row in the same sort order; pagination is ignored."""
    if query.format == "xlsx":
        xlsx_bytes = await export_scan_logs_xlsx(db, user, query)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="bananavision_scan_logs.xlsx"'},
        )
    contents = await export_scan_logs(db, user, query)
    return StreamingResponse(
        contents, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bananavision_scan_logs.csv"'},
    )
