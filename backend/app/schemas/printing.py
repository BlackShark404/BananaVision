"""Label submission contracts."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PrinterInfo(BaseModel):
    name: str
    driver_name: str | None = None
    port_name: str | None = None
    status: str
    is_ready: bool
    is_grozziie: bool
    is_usb: bool


class PrintJobResponse(BaseModel):
    id: uuid.UUID
    status: Literal["QUEUED", "SUBMITTED", "FAILED"]
    printer_name: str
    windows_job_id: int | None = None
    error: str | None = None
    attempt_count: int
    quantity: int


class LabelPrintRequest(BaseModel):
    request_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=10, strict=True)
    model_config = {"extra": "forbid"}


class RetryPrintRequest(BaseModel):
    expected_attempt: int = Field(ge=1, strict=True)


class LabelPreviewResponse(BaseModel):
    payload: str
    panel: tuple[str, ...]
    printer_name: str
    max_quantity: int
    width_mm: float
    height_mm: float
