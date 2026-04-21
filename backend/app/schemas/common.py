"""
Pydantic schemas for devices, sensors, suppliers, intakes, analytics, activity, and config.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ── Device ───────────────────────────────────────────────────────────────────

class DeviceResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    label: str
    status: str
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
    status: str = "Active"


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    status: str | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact_person: str | None = None
    contact_phone: str | None = None
    status: str
    date_added: datetime

    model_config = {"from_attributes": True}


# ── Intake ───────────────────────────────────────────────────────────────────

class IntakeResponse(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    intake_date: date
    status: str
    scan_count: int = 0
    created_at: datetime


class IntakeStatusUpdate(BaseModel):
    status: str  # "Active" | "Depleted"


class IntakeBulkInventoryUpdate(BaseModel):
    inventory_status: str  # "In Stock" | "Sold" | "For Processing" | "Spoiled"


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


class SystemConfigUpdate(BaseModel):
    camera_ids: str | None = None
    confidence_threshold: float | None = None
