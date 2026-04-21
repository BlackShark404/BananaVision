"""
Custom exception classes for structured HTTP error handling.
"""

from __future__ import annotations

from fastapi import HTTPException, status


class CredentialsException(HTTPException):
    """401 — Invalid or expired authentication credentials."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(HTTPException):
    """403 — Insufficient permissions."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class NotFoundException(HTTPException):
    """404 — Resource not found."""

    def __init__(self, resource: str = "Resource", detail: str | None = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or f"{resource} not found",
        )


class ConflictException(HTTPException):
    """409 — Resource already exists."""

    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class CameraError(Exception):
    """Raised when a camera capture fails."""

    def __init__(self, camera_id: int | str, message: str = "Capture failed"):
        self.camera_id = camera_id
        self.message = message
        super().__init__(f"Camera {camera_id}: {message}")


class SensorError(Exception):
    """Raised when the DHT22 sensor read fails."""

    def __init__(self, message: str = "Sensor read failed"):
        self.message = message
        super().__init__(message)


class ModelInferenceError(Exception):
    """Raised when ML model inference fails."""

    def __init__(self, model_name: str, message: str = "Inference failed"):
        self.model_name = model_name
        self.message = message
        super().__init__(f"{model_name}: {message}")
