"""
Application configuration loaded from environment variables via Pydantic Settings.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, Field, field_validator
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
    app_cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    trusted_proxies: list[str] = []

    bananavision_printer_name: str = "TP870 S"
    bananavision_label_width_mm: float = Field(40, ge=20, le=110)
    bananavision_label_height_mm: float = Field(30, ge=20, le=300)
    bananavision_auto_print: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://bv_user:bv_pass@localhost:5432/bananavision"
    database_echo: bool = False

    # ── Authentication ───────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr | None = None

    # ── Camera ───────────────────────────────────────────────────────────────
    camera_device_ids: list[int] = [0, 1, 2, 3]
    camera_labels: list[str] = ["Top", "Left", "Right", "Rear"]
    camera_resolution_w: int = Field(1280, ge=1, le=7680)
    camera_resolution_h: int = Field(720, ge=1, le=4320)
    camera_resolutions: dict[str, str] = Field(default_factory=dict)
    camera_warmup_frames: int = 30
    camera_capture_timeout_ms: int = 3000
    # None preserves the driver's focus; fixed-focus webcams have no calibrated numeric focus.
    camera_autofocus: bool | None = None
    camera_manual_focus_value: int | None = Field(None, ge=0)
    camera_auto_white_balance: bool | None = True
    camera_auto_exposure: bool | None = True
    # auto uses DirectShow on Windows; explicit overrides help driver compatibility.
    camera_backend: Literal["auto", "dshow", "msmf"] = "auto"
    camera_fps: int = Field(15, ge=1, le=60)
    camera_fourcc: str = Field("MJPG", min_length=4, max_length=4)
    camera_preview_max_width: int = Field(1280, ge=1, le=3840)
    camera_preview_max_height: int = Field(720, ge=1, le=2160)
    camera_preview_jpeg_quality: int = Field(90, ge=1, le=100)
    camera_capture_jpeg_quality: int = Field(95, ge=1, le=100)

    # ── Sensor ───────────────────────────────────────────────────────────────
    sensor_serial_port: str = "/dev/ttyUSB0"
    sensor_baud_rate: int = 9600
    sensor_read_interval_s: int = 5

    # ── ML Models ────────────────────────────────────────────────────────────
    yolo_model_path: str = "app/ml/weights/banana_yolov26n.pt"
    yolo_confidence_threshold: float = Field(0.50, gt=0, le=1)
    yolo_iou_threshold: float = 0.45
    yolo_top_overlap_refinement: bool = True
    yolo_top_rotation_fallback: bool = True
    yolo_peripheral_background_filter: bool = True
    top_camera_cultivar_anchor: bool = True
    # Legacy setting retained for compatibility; counts no longer add cross-view sightings.
    multi_camera_finger_fusion: bool = True
    rfr_model_path: str = "app/ml/weights/spoilage_rfr.joblib"

    # ── Storage ──────────────────────────────────────────────────────────────
    capture_dir: str = "captures"
    max_captures_retention_days: int = Field(30, ge=1)

    # ── Validators ───────────────────────────────────────────────────────────
    @field_validator("app_cors_origins", "trusted_proxies", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return [str(x).strip() for x in json.loads(v) if str(x).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
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

    @field_validator("camera_resolutions", mode="before")
    @classmethod
    def parse_camera_resolutions(cls, v: str | dict[str, str] | None) -> dict[str, str]:
        if not v:
            return {}
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            if v.startswith("{") and v.endswith("}"):
                try:
                    import json
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        return {str(k).strip(): str(val).strip() for k, val in parsed.items()}
                except Exception:
                    pass
            result = {}
            for item in v.split(","):
                if ":" in item:
                    k, val = item.split(":", 1)
                    result[k.strip()] = val.strip()
            return result
        if isinstance(v, dict):
            return {str(k).strip(): str(val).strip() for k, val in v.items()}
        return {}

    @field_validator("camera_device_ids")
    @classmethod
    def validate_camera_ids(cls, ids: list[int]) -> list[int]:
        if not ids or len(ids) > 4 or len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Select one to four distinct nonnegative camera indices")
        return ids

    @field_validator("bootstrap_admin_password")
    @classmethod
    def validate_bootstrap_password(cls, password: SecretStr | None) -> SecretStr | None:
        if password is not None and not 12 <= len(password.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("Bootstrap password must contain 12 to 72 UTF-8 bytes")
        return password

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
