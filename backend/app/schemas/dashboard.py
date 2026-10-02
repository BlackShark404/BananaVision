"""Dashboard response contracts; absent measurements remain null."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

DashboardView = Literal["today", "review", "expiring", "all"]
DashboardSort = Literal["date", "confidence"]


class DashboardScan(BaseModel):
    id: UUID
    date_time: datetime
    cultivar: str | None
    ripeness: str | None
    confidence: float | None
    operator_id: UUID
    operator_name: str
    source_key: str
    source_name: str
    inventory_status: str | None
    flagged: bool
    spoilage_days: str | None
    remaining_days: float | None


class DashboardSource(BaseModel):
    key: str
    name: str
    count: int


class DashboardOperator(BaseModel):
    operator_id: UUID
    name: str
    username: str
    scan_count: int
    avg_confidence: float | None


class DashboardSummary(BaseModel):
    generated_at: datetime
    business_date: date
    timezone: Literal["Asia/Manila"] = "Asia/Manila"
    total_scans: int
    avg_confidence: float | None
    success_rate: float | None
    active_operator_count: int
    active_source_count: int
    sources: list[DashboardSource]
    operators: list[DashboardOperator]
    recent_scans: list[DashboardScan]
    pending_review_count: int
    expiring_stock_count: int
    confidence_threshold: float


class DashboardScanList(BaseModel):
    items: list[DashboardScan]
    total: int
    page: int
    page_size: int
    generated_at: datetime
    business_date: date
    timezone: Literal["Asia/Manila"] = "Asia/Manila"
