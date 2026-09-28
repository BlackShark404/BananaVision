"""
Application configuration loaded from environment variables via Pydantic Settings.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, auto-populated from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="None",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True
    app_secret_key: str = "change-me"
    app_cors_origins: list[str] = ["*"]

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://bv_user:bv_pass@localhost:5432/bananavision"
    database_echo: bool = False

    # ── Authentication ───────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

    # ── Camera ───────────────────────────────────────────────────────────────
    camera_device_ids: list[int] = [0, 1, 2, 3]
    camera_labels: list[str] = ["Front", "Left", "Right", "Top"]
    camera_resolution_w: int = 640
    camera_resolution_h: int = 480
    camera_warmup_frames: int = 30
    camera_capture_timeout_ms: int = 3000
    camera_autofocus: bool = False
    camera_manual_focus_value: int = 25

    # ── Sensor ───────────────────────────────────────────────────────────────
    sensor_serial_port: str = "/dev/ttyUSB0"
    sensor_baud_rate: int = 9600
    sensor_read_interval_s: int = 5

    # ── ML Models ────────────────────────────────────────────────────────────
    yolo_model_path: str = "app/ml/weights/banana_yolov26n.pt"
    yolo_confidence_threshold: float = 0.50
    yolo_iou_threshold: float = 0.45
    rfr_model_path: str = "app/ml/weights/spoilage_rfr.joblib"

    # ── Storage ──────────────────────────────────────────────────────────────
    capture_dir: str = "captures"
    max_captures_retention_days: int = 30

    # ── Validators ───────────────────────────────────────────────────────────
    @field_validator("app_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("camera_device_ids", mode="before")
    @classmethod
    def parse_camera_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",")]
        return v

    @field_validator("camera_labels", mode="before")
    @classmethod
    def parse_camera_labels(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v

    # ── Derived Properties ───────────────────────────────────────────────────
    @property
    def capture_path(self) -> Path:
        return Path(self.capture_dir)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
