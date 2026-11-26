"""
Quality control routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.models.operator_profile import OperatorProfile
from app.models.scan import Scan

router = APIRouter(prefix="/quality", tags=["Quality"])


@router.get("/flagged")
async def get_flagged_scans(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get all flagged scans for quality review."""
    query = (
        select(Scan)
        .options(
            selectinload(Scan.classification),
            selectinload(Scan.operator).selectinload(OperatorProfile.account),
        )
        .where(Scan.flagged == True)  # noqa: E712
        .order_by(desc(Scan.date_time), desc(Scan.id))
    )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    scans = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "scanned_at": s.date_time.isoformat(),
                "cultivar": s.classification.cultivar if s.classification else None,
                "ripeness": s.classification.ripeness if s.classification else None,
                "confidence": float(s.classification.confidence) if s.classification else None,
                "finger_count": s.classification.finger_count if s.classification else 0,
                "operator_name": s.operator.account.full_name if s.operator and s.operator.account else "Unknown",
                "flagged": s.flagged,
            }
            for s in scans
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
