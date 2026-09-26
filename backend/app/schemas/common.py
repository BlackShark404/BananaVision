"""
Pydantic schemas for devices, sensors, suppliers, intakes, analytics, activity, and config.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from .enums import ActiveStatusEnum, DeviceStatusEnum, IntakeStatusEnum, InventoryStatusEnum


# ── Device ───────────────────────────────────────────────────────────────────

class DeviceResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    label: str
    status: DeviceStatusEnum
    resolution: str | None = None
    last_seen: datetime | None = None

    model_config = {"from_attributes": True}


# ── Sensor ───────────────────────────────────────────────────────────────────

class SensorReadingResponse(BaseModel):
    temperature: float
    humidity: float
    recorded_at: datetime
    source: str = "DHT22"

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
    date_added: datetime

    model_config = {"from_attributes": True}


# ── Intake ───────────────────────────────────────────────────────────────────

class IntakeCreate(BaseModel):
    supplier_id: uuid.UUID
    batch_number: str | None = None
    source: str = "Kiosk"
    treatment: str | None = "Natural"  # "Natural" or "Ethephon"
    harvested_at: datetime | None = None
    treated_at: datetime | None = None

class IntakeResponse(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    supplier_name: str | None = None
    batch_number: str | None = None
    qr_code: str | None = None
    intake_date: date
    status: IntakeStatusEnum
    treatment: str | None = None
    harvested_at: datetime | None = None
    treated_at: datetime | None = None
    spoiled_at: datetime | None = None
    scan_count: int = 0
    created_at: datetime


class IntakeStatusUpdate(BaseModel):
    status: IntakeStatusEnum


class IntakeBulkInventoryUpdate(BaseModel):
    inventory_status: InventoryStatusEnum


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


class AnalyticsSummary(BaseModel):
    total_scans: int
    avg_confidence: float
    most_common_cultivar: str
    ripeness_distribution: list[RipenessDistribution]
    cultivar_counts: list[CultivarCount]
    scan_trend: list[ScanTrend]


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
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogResponse]
    total: int
    page: int
    page_size: int


# ── Config ───────────────────────────────────────────────────────────────────

class SystemConfigResponse(BaseModel):
    camera_ids: str
    confidence_threshold: float
    data_retention_enabled: bool


class SystemConfigUpdate(BaseModel):
    camera_ids: str | None = None
    confidence_threshold: float | None = None
    data_retention_enabled: bool | None = None
