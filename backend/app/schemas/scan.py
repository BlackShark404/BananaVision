"""
Pydantic schemas for scan-related requests/responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Requests ─────────────────────────────────────────────────────────────────

class ScanTriggerRequest(BaseModel):
    supplier_id: uuid.UUID | None = None
    intake_id: uuid.UUID | None = None


class ScanFlagRequest(BaseModel):
    flagged: bool


class ScanOverrideRequest(BaseModel):
    cultivar: str | None = None
    ripeness: str | None = None
    finger_count: int | None = None


class ScanNoteCreate(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class ScanStatusUpdate(BaseModel):
    inventory_status: str  # "In Stock" | "Sold" | "For Processing" | "Spoiled"


# ── Responses ────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    cls: str
    confidence: float


class ScanDetectionResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    camera_label: str
    detected_cultivar: str | None = None
    detected_ripeness: str | None = None
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
    note: str
    author_name: str
    created_at: datetime


class ScanResponse(BaseModel):
    id: uuid.UUID
    scanned_at: datetime
    cultivar: str
    ripeness: str
    confidence: float
    temperature: float | None = None
    humidity: float | None = None
    spoilage_days: str
    finger_count: int
    operator_name: str
    supplier_name: str | None = None
    intake_id: uuid.UUID | None = None
    inventory_status: str
    status_updated_at: datetime | None = None
    flagged: bool = False
    is_overridden: bool = False
    original_ai_result: dict | None = None
    thumbnail_url: str | None = None
    created_at: datetime


class ScanDetailResponse(ScanResponse):
    detections: list[ScanDetectionResponse] = []
    images: list[ScanImageResponse] = []
    notes: list[ScanNoteResponse] = []


class ScanListResponse(BaseModel):
    items: list[ScanResponse]
    total: int
    page: int
    page_size: int
