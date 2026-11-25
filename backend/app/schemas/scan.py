"""
Pydantic schemas for scan-related requests/responses.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal
from app.schemas.timestamps import Timestamp

from pydantic import BaseModel, Field, StringConstraints, field_validator

from .enums import CultivarEnum, InventoryStatusEnum, RipenessEnum
from .printing import PrintJobResponse
from .shelf_life import RipenessProjection, ShelfLifeWindow


# ── Requests ─────────────────────────────────────────────────────────────────

class ScanTriggerRequest(BaseModel):
    source_text: str | None = Field(default=None, max_length=100)
    intake_id: uuid.UUID | None = None


class ScanMutationRequest(BaseModel):
    request_id: uuid.UUID
    expected_revision: int = Field(ge=1, strict=True)
    model_config = {"extra": "forbid"}


Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ScanFlagRequest(ScanMutationRequest):
    flagged: bool
    reason: Reason | None = None


class ScanOverrideRequest(ScanMutationRequest):
    reason: Reason
    cultivar: CultivarEnum | None = None
    ripeness: RipenessEnum | None = None
    finger_count: int | None = Field(default=None, ge=1)
    spoilage_days: str | None = Field(default=None, max_length=20)
    source_text: str | None = Field(default=None, max_length=100)

    @field_validator("finger_count")
    @classmethod
    def count_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Finger count must be a positive integer")
        if value < 1:
            raise ValueError("Finger count must be at least 1")
        return value


class ScanNoteCreate(ScanMutationRequest):
    note: Reason


class ScanStatusUpdate(ScanMutationRequest):
    reason: Reason
    inventory_status: InventoryStatusEnum


class ScanProvenanceReview(ScanMutationRequest):
    reason: Reason
    intake_provenance: Literal["unlinked", "excluded"]


# ── Responses ────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    cls: str
    conf: float
    counts_as_finger: bool | None = None


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

    model_config = {"from_attributes": True}


class ScanNoteWriteResponse(ScanNoteResponse):
    revision: int


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
    revision: int
    print_job: PrintJobResponse | None = None
    print_error: str | None = None
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
    intake_origin_id: uuid.UUID | None = None
    intake_provenance: str = "unverified"
    inventory_eligible: bool = False
    remaining_days: float | None = None
    risk_as_of: Timestamp | None = None
    shelf_life_window: ShelfLifeWindow | None = None
    ripeness_projection: RipenessProjection | None = None
    status_updated_at: Timestamp | None = None
    flagged: bool = False
    is_overridden: bool = False
    original_ai_result: OriginalAiResult | None = None
    thumbnail_url: str | None = None
    has_notes: bool = False
    images: list[ScanImageRef] = []
    updated_at: Timestamp

    model_config = {"from_attributes": True}


class ScanHistoryResponse(BaseModel):
    id: str
    kind: str
    timestamp: Timestamp
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    reason: str | None = None
    previous_values: dict | None = None
    new_values: dict
    revision: int | None = None
    legacy: bool = False


class ScanDetailResponse(ScanResponse):
    detections: list[ScanDetectionResponse] = []
    images: list[ScanImageResponse] = []
    notes: list[ScanNoteResponse] = []
    history: list[ScanHistoryResponse] = []


class PublicScanImageRef(BaseModel):
    camera_id: str
    file_path: str


class PublicScanResponse(BaseModel):
    """Public-facing scan summary for QR code tracking — no PII or admin data."""
    id: uuid.UUID
    date_time: Timestamp
    cultivar: CultivarEnum | None
    ripeness: RipenessEnum | None
    confidence: float | None
    spoilage_days: str | None
    remaining_days: float | None = None
    risk_as_of: Timestamp | None = None
    shelf_life_window: ShelfLifeWindow | None = None
    ripeness_projection: RipenessProjection | None = None
    finger_count: int
    temperature: float | None = None
    humidity: float | None = None
    vpd: float | None = None
    treatment: str | None = None
    source_text: str | None = None
    inventory_status: InventoryStatusEnum
    flagged: bool = False
    images: list[PublicScanImageRef] = []


class ScanListResponse(BaseModel):
    snapshot_id: uuid.UUID | None = None
    snapshot_expires_at: Timestamp | None = None
    items: list[ScanResponse]
    total: int
    page: int
    page_size: int
