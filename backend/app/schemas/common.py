"""
Pydantic schemas for devices, sensors, suppliers, intakes, analytics, activity, and config.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator, model_validator

from app.core.time import now_manila
from app.schemas.timestamps import InputTimestamp, Timestamp

from .enums import (
    ActiveStatusEnum,
    CultivarEnum,
    DeviceStatusEnum,
    IntakeStatusEnum,
    InventoryStatusEnum,
)

# ── Device ───────────────────────────────────────────────────────────────────

class DeviceResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    label: str
    status: DeviceStatusEnum
    resolution: str | None = None
    last_seen: Timestamp | None = None

    model_config = {"from_attributes": True}


# ── Sensor ───────────────────────────────────────────────────────────────────

class SensorReadingResponse(BaseModel):
    temperature: float
    humidity: float
    recorded_at: Timestamp
    source: str = "DHT22"
    # Server clock evidence lets clients detect stale readings without trusting
    # a possibly skewed workstation clock. Three missed polls is the default.
    server_time: Timestamp = Field(default_factory=now_manila)
    stale_after_seconds: int = 15

    model_config = {"from_attributes": True}


class SensorHistoryResponse(BaseModel):
    items: list[SensorReadingResponse]
    total: int


# ── Supplier ─────────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    contact_person: str | None = None
    contact_phone: str | None = None
    status: ActiveStatusEnum = ActiveStatusEnum.ACTIVE


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    status: ActiveStatusEnum | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact_person: str | None = None
    contact_phone: str | None = None
    status: ActiveStatusEnum
    date_added: Timestamp
    updated_at: Timestamp

    model_config = {"from_attributes": True}


# ── Intake ───────────────────────────────────────────────────────────────────

class IntakeCreate(BaseModel):
    supplier_id: uuid.UUID
    batch_number: str | None = None
    source: str = "Kiosk"
    treatment: str | None = "Natural"  # "Natural" or "Ethephon"
    harvested_at: InputTimestamp | None = None
    treated_at: InputTimestamp | None = None

class IntakeExpectedStockItem(BaseModel):
    cultivar: CultivarEnum
    expected_bunches: Annotated[int, Field(ge=1, le=1_000_000, strict=True)]


class IntakeExpectedStockUpdate(BaseModel):
    items: list[IntakeExpectedStockItem] = Field(default_factory=list, max_length=3)

    @field_validator("items")
    @classmethod
    def unique_cultivars(cls, items):
        cultivars = [item.cultivar for item in items]
        if len(cultivars) != len(set(cultivars)):
            raise ValueError("Each variety may appear only once")
        return items

    model_config = {"extra": "forbid"}


class IntakeExpectedStockResponse(BaseModel):
    cultivar: CultivarEnum
    expected_bunches: int

    model_config = {"from_attributes": True}


class IntakeResponse(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    supplier_name: str | None = None
    source: str | None = None
    batch_number: str | None = None
    qr_code: str | None = None
    intake_date: date
    status: IntakeStatusEnum
    treatment: str | None = None
    harvested_at: Timestamp | None = None
    treated_at: Timestamp | None = None
    spoiled_at: Timestamp | None = None
    scan_count: int = 0
    expected_stock: list[IntakeExpectedStockResponse] = Field(default_factory=list)
    created_at: Timestamp
    updated_at: Timestamp


class IntakeStatusUpdate(BaseModel):
    status: IntakeStatusEnum


class IntakeBulkInventoryUpdate(BaseModel):
    inventory_status: InventoryStatusEnum
    request_id: uuid.UUID
    expected_revisions: dict[uuid.UUID, Annotated[int, Field(ge=1, strict=True)]]
    reason: str = Field(min_length=1, max_length=2000)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


# ── Analytics ────────────────────────────────────────────────────────────────

class RipenessDistribution(BaseModel):
    name: str
    value: int


class CultivarCount(BaseModel):
    name: str
    count: int


class ScanTrend(BaseModel):
    date: str
    count: int


class CultivarRipeness(BaseModel):
    """Per-cultivar breakdown of ripeness counts."""
    name: str
    Unripe: int = 0
    Semi_Ripe: int = Field(0, alias="Semi Ripe")
    Ripe: int = 0
    Overripe: int = 0

    model_config = {"populate_by_name": True}


class RipenessConfidence(BaseModel):
    """Avg confidence and count per ripeness level."""
    ripeness: str
    avgConfidence: float
    count: int


class SourceCount(BaseModel):
    """Scan count per source/supplier."""
    name: str
    count: int


class HourlyCount(BaseModel):
    """Scan count per hour-of-day."""
    hour: str
    count: int


class AnalyticsSummary(BaseModel):
    total_scans: int
    avg_confidence: float
    most_common_cultivar: str
    low_confidence_count: int = 0
    low_confidence_rate: float = 0.0
    at_risk_count: int = 0
    ripeness_distribution: list[RipenessDistribution]
    cultivar_counts: list[CultivarCount]
    scan_trend: list[ScanTrend]
    cultivar_ripeness: list[CultivarRipeness] = []
    ripeness_confidence: list[RipenessConfidence] = []
    scans_by_source: list[SourceCount] = []
    hourly_distribution: list[HourlyCount] = []


class OperatorPerformance(BaseModel):
    operator_id: uuid.UUID
    name: str
    total_scans: int
    avg_confidence: float
    flagged_scans: int
    flag_rate: float
    overridden_scans: int


class OperatorPerformanceList(BaseModel):
    items: list[OperatorPerformance]
    total_operators: int


# ── Activity ─────────────────────────────────────────────────────────────────

class ActivityLogResponse(BaseModel):
    id: uuid.UUID
    user_name: str | None = None
    action: str
    details: str | None = None
    ip_address: str | None = None
    created_at: Timestamp


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogResponse]
    total: int
    page: int
    page_size: int
    # The boundary the page was read at; pass it back as ``as_of`` for later pages.
    as_of: Timestamp


# ── Config ───────────────────────────────────────────────────────────────────

class SystemConfigResponse(BaseModel):
    camera_ids: str
    camera_device_ids: list[int]
    confidence_threshold: int
    detection_confidence_threshold: float
    data_retention_enabled: bool
    revision: int
    applied_camera_ids: str | None
    applied_camera_device_ids: list[int]
    applied_revision: int | None
    application_status: str
    application_error: str | None
    restart_required: bool
    retention_days: int
    retention_policy: str
    legacy_conflict: bool


class SystemConfigUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    camera_ids: str | None = None
    camera_device_ids: list[StrictInt] | None = Field(None, min_length=1, max_length=4)
    confidence_threshold: StrictInt | None = Field(None, ge=1, le=100)
    data_retention_enabled: StrictBool | None = None

    @model_validator(mode='before')
    @classmethod
    def reject_explicit_null(cls, values):
        if isinstance(values, dict) and any(value is None for value in values.values()):
            raise ValueError('Configuration fields cannot be null')
        return values

    @field_validator('camera_device_ids')
    @classmethod
    def validate_physical_ids(cls, ids):
        if ids is not None and (len(ids) != len(set(ids)) or any(value < 0 for value in ids)):
            raise ValueError('Camera indices must be distinct and nonnegative')
        return ids

    @field_validator("camera_ids")
    @classmethod
    def validate_camera_ids(cls, v: str | None) -> str | None:
        if v is None:
            return v
        ids = [s.strip() for s in v.split(",")]
        if not 1 <= len(ids) <= 4 or any(not value or len(value) > 50 for value in ids):
            raise ValueError("Provide 1–4 nonempty camera IDs, each at most 50 characters")
        if len(ids) != len(set(ids)):
            raise ValueError("Camera IDs must be unique")
        return ", ".join(ids)
