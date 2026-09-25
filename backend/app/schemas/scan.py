"""
Pydantic schemas for scan-related requests/responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from .enums import CultivarEnum, InventoryStatusEnum, RipenessEnum


# ── Requests ─────────────────────────────────────────────────────────────────

class ScanTriggerRequest(BaseModel):
    source_text: str | None = None
    intake_id: uuid.UUID | None = None


class ScanFlagRequest(BaseModel):
    flagged: bool


class ScanOverrideRequest(BaseModel):
    cultivar: CultivarEnum | None = None
    ripeness: RipenessEnum | None = None
    finger_count: int | None = None


class ScanNoteCreate(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class ScanStatusUpdate(BaseModel):
    inventory_status: InventoryStatusEnum


# ── Responses ────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    cls: str
    conf: float


class ScanDetectionResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    camera_label: str
    detected_cultivar: CultivarEnum | None = None
    detected_ripeness: RipenessEnum | None = None
    confidence: float | None = None
    finger_count: int = 0
    bounding_boxes: list[BoundingBox] = []
    inference_time_ms: float | None = None
    captured_at: datetime

    model_config = {"from_attributes": True}


class ScanImageResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    file_path: str
    width: int | None = None
    height: int | None = None
    captured_at: datetime

    model_config = {"from_attributes": True}


class ScanNoteResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    text: str
    author_name: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class OriginalAiResult(BaseModel):
    cultivar: CultivarEnum
    ripeness: RipenessEnum
    confidence: float
    finger_count: int

    model_config = {"from_attributes": True}


class ScanImageRef(BaseModel):
    camera_id: str
    file_path: str


class ScanResponse(BaseModel):
    id: uuid.UUID
    date_time: datetime
    cultivar: CultivarEnum
    ripeness: RipenessEnum
    confidence: float
    temperature: float | None = None
    humidity: float | None = None
    dew_point: float | None = None
    vpd: float | None = None
    heat_index: float | None = None
    treatment: str | None = None
    spoilage_days: str
    finger_count: int
    operator_name: str
    source_text: str | None = None
    intake_id: uuid.UUID | None = None
    inventory_status: InventoryStatusEnum
    status_updated_at: datetime | None = None
    flagged: bool = False
    is_overridden: bool = False
    original_ai_result: OriginalAiResult | None = None
    thumbnail_url: str | None = None
    has_notes: bool = False
    images: list[ScanImageRef] = []
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanDetailResponse(ScanResponse):
    detections: list[ScanDetectionResponse] = []
    images: list[ScanImageResponse] = []
    notes: list[ScanNoteResponse] = []


class ScanListResponse(BaseModel):
    items: list[ScanResponse]
    total: int
    page: int
    page_size: int
