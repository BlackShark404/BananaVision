"""Shared filter/response contracts for Scan Logs and its complete CSV export."""

from datetime import date
from app.schemas.timestamps import Timestamp
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.dashboard import DashboardScan
from app.schemas.enums import CultivarEnum, InventoryStatusEnum, RipenessEnum


class ScanLogQuery(BaseModel):
    business_date: date | None = None
    source_key: str | None = None
    source: str | None = None
    operator_id: UUID | None = None
    intake_id: UUID | None = None
    cultivar: CultivarEnum | None = None
    ripeness: RipenessEnum | None = None
    inventory_status: InventoryStatusEnum | None = None
    flagged_only: bool = False
    attention: Literal["all", "at-risk", "review"] = "all"
    search: str | None = Field(None, max_length=200)
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=100)
    sort: Literal["date_time", "cultivar", "confidence", "spoilage_days", "finger_count"] = "date_time"
    direction: Literal["asc", "desc"] = "desc"


class ScanLogRow(DashboardScan):
    revision: int
    temperature: float | None
    humidity: float | None
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
