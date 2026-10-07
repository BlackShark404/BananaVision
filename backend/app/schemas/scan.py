"""
Pydantic schemas for scan-related requests/responses.
"""

from __future__ import annotations

import uuid
from app.schemas.timestamps import Timestamp

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .enums import CultivarEnum, InventoryStatusEnum, RipenessEnum


# ── Requests ─────────────────────────────────────────────────────────────────

class ScanTriggerRequest(BaseModel):
    source_text: str | None = None
    intake_id: uuid.UUID | None = None


class ScanMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(..., ge=1)
    request_id: uuid.UUID


class ReasonedScanMutation(ScanMutationRequest):
    reason: str = Field(..., min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A reason is required")
        return value


class ScanFlagRequest(ScanMutationRequest):
    flagged: bool


class ScanOverrideRequest(ReasonedScanMutation):
    cultivar: CultivarEnum | None = None
    ripeness: RipenessEnum | None = None
    finger_count: int | None = Field(None, ge=0)
    spoilage_days: str | None = Field(None, max_length=50)
    source_text: str | None = Field(None, max_length=100)


class ScanNoteCreate(ScanMutationRequest):
    note: str = Field(..., min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A note is required")
        return value


class ScanStatusUpdate(ReasonedScanMutation):
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
    captured_at: Timestamp

    model_config = {"from_attributes": True}


class ScanImageResponse(BaseModel):
    id: uuid.UUID
    camera_id: str
    file_path: str
    width: int | None = None
    height: int | None = None
    captured_at: Timestamp

    model_config = {"from_attributes": True}


class ScanNoteResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    text: str
    author_name: str
    timestamp: Timestamp
    revision: int | None = None

    model_config = {"from_attributes": True}


class OriginalAiResult(BaseModel):
    cultivar: CultivarEnum | None
    ripeness: RipenessEnum | None
    confidence: float | None
    finger_count: int
    spoilage_days: str | None = None

    model_config = {"from_attributes": True}


class ScanImageRef(BaseModel):
    camera_id: str
    file_path: str


class ScanResponse(BaseModel):
    id: uuid.UUID
    date_time: Timestamp
    cultivar: CultivarEnum | None
    ripeness: RipenessEnum | None
    confidence: float | None
    temperature: float | None = None
    humidity: float | None = None
    vpd: float | None = None
    treatment: str | None = None
    spoilage_days: str | None
    finger_count: int
    operator_name: str
    source_text: str | None = None
    intake_id: uuid.UUID | None = None
    inventory_status: InventoryStatusEnum
    status_updated_at: Timestamp | None = None
    flagged: bool = False
    is_overridden: bool = False
    original_ai_result: OriginalAiResult | None = None
    thumbnail_url: str | None = None
    has_notes: bool = False
    images: list[ScanImageRef] = []
    updated_at: Timestamp
    revision: int = 1

    model_config = {"from_attributes": True}


class ScanHistoryResponse(BaseModel):
    id: str
    kind: str
    timestamp: Timestamp
    actor_name: str | None = None
    reason: str | None = None
    previous_values: dict | None = None
    new_values: dict
    revision: int | None = None


class ScanDetailResponse(ScanResponse):
    detections: list[ScanDetectionResponse] = []
    images: list[ScanImageResponse] = []
    notes: list[ScanNoteResponse] = []
    history: list[ScanHistoryResponse] = []


class ScanListResponse(BaseModel):
    items: list[ScanResponse]
    total: int
    page: int
    page_size: int
