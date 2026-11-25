"""Shared filter/response contracts for Scan Logs and its Excel/PDF exports."""

from datetime import date
from app.schemas.timestamps import Timestamp
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.dashboard import DashboardScan
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum


class ScanLogQuery(BaseModel):
    format: Literal["xlsx", "pdf"] = "xlsx"
    stable: bool = False
    snapshot_id: UUID | None = None
    business_date: date | None = None
    source_key: str | None = None
    source: str | None = None
    operator_id: UUID | None = None
    intake_id: UUID | None = None
    cultivar: CultivarEnum | None = None
    ripeness: RipenessEnum | None = None
    ripeness_scope: Literal["scanned", "current"] = "scanned"
    inventory_status: InventoryStatusEnum | None = None
    stock_eligible: bool = False
    flagged_only: bool = False
    attention: Literal["all", "at-risk", "review", "success"] = "all"
    search: str | None = Field(None, max_length=200)
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=100)
    limit: int | None = Field(None, ge=1, le=100, description="Alias for page_size")
    sort: Literal["date_time", "cultivar", "confidence", "spoilage_days", "finger_count"] = "date_time"
    direction: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def sync_limit(self):
        if self.limit is not None and self.page_size == 10:
            self.page_size = self.limit
        return self


class ScanLogRow(DashboardScan):
    revision: int
    temperature: float | None
    humidity: float | None
    vpd: float | None = None
    finger_count: int
    thumbnail_url: str | None
    intake_id: UUID | None
    is_overridden: bool
    status_updated_at: Timestamp | None


class SourceOption(BaseModel):
    key: str
    name: str


class OperatorOption(BaseModel):
    operator_id: UUID
    name: str
    username: str


class ScanLogOptions(BaseModel):
    sources: list[SourceOption]
    operators: list[OperatorOption]


class ScanLogList(BaseModel):
    snapshot_id: UUID | None = None
    snapshot_expires_at: Timestamp | None = None
    items: list[ScanLogRow]
    total: int
    page: int
    page_size: int
    avg_confidence: float | None
    at_risk_count: int
    review_count: int
    flagged_count: int
    generated_at: Timestamp
    confidence_threshold: float
    options: ScanLogOptions


class ScanLogPending(BaseModel):
    """Live count of committed scans newer than an immutable browse snapshot."""

    snapshot_id: UUID
    new_count: int
    generated_at: Timestamp


class ScanLogReconciliation(BaseModel):
    """Current authorized values for a frozen page, plus live whole-filter metrics."""

    snapshot_id: UUID
    items: list[ScanLogRow]
    at_risk_ids: list[UUID]
    total: int
    avg_confidence: float | None
    at_risk_count: int
    review_count: int
    flagged_count: int
    confidence_threshold: float
    generated_at: Timestamp
