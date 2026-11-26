"""
Arduino DHT22 sensor reader via serial port.

Reads temperature and humidity from an Arduino connected via USB serial.
Runs as a background asyncio task, broadcasting updates via WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings
from app.core.time import as_manila, now_manila

logger = logging.getLogger(__name__)
settings = get_settings()

DHT22_TEMP_MIN_C = -40.0
DHT22_TEMP_MAX_C = 80.0
DHT22_HUM_MIN_PCT = 0.0
DHT22_HUM_MAX_PCT = 100.0
MAX_SERIAL_DRAIN_LINES = 128
RECONNECT_INTERVAL_S = 30.0
FUTURE_SKEW_TOLERANCE_S = 5.0


def freshness_window_seconds() -> int:
    """Three missed polls (or at least 15s) before a reading is no longer live."""
    return max(int(settings.sensor_read_interval_s) * 3, 15)


def is_valid_dht22(temperature: float | None, humidity: float | None) -> bool:
    """Validate finite readings within the DHT22 physical specification."""
    if (
        temperature is None
        or humidity is None
        or isinstance(temperature, bool)
        or isinstance(humidity, bool)
    ):
        return False
    try:
        temp_val = float(temperature)
        hum_val = float(humidity)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(temp_val) and math.isfinite(hum_val)):
        return False
    return (
        DHT22_TEMP_MIN_C <= temp_val <= DHT22_TEMP_MAX_C
        and DHT22_HUM_MIN_PCT <= hum_val <= DHT22_HUM_MAX_PCT
    )


def trimmed_mean(values: list[float]) -> float:
    """Reject single-sample DHT22 spikes when 3 or more samples are present."""
    if len(values) >= 3:
        ordered = sorted(values)
        middle = ordered[1:-1]
        return sum(middle) / len(middle)
    return sum(values) / len(values)


def is_reading_fresh(
    recorded_at: datetime | None,
    now: datetime | None = None,
    max_age_seconds: int | None = None,
) -> bool:
    """True when `recorded_at` falls within the freshness window relative to `now`."""
    if recorded_at is None:
        return False
    current = as_manila(now) if now is not None else now_manila()
    recorded = as_manila(recorded_at)
    age_s = (current - recorded).total_seconds()
    limit = freshness_window_seconds() if max_age_seconds is None else max_age_seconds
    return -FUTURE_SKEW_TOLERANCE_S <= age_s <= limit


def _decode_serial_line(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace").strip()
    return str(raw).strip()


def _is_serial_disconnect_error(exc: Exception) -> bool:
    return isinstance(exc, OSError) or type(exc).__name__ == "SerialException"


@dataclass
class SensorData:
    """Parsed sensor reading."""
    temperature: float
    humidity: float
    recorded_at: datetime


def resolve_scan_sensor_reading(reader, now: datetime | None = None) -> SensorData | None:
    """Resolve a fresh, validated sensor reading for scan prediction.

    Uses smoothed recent samples from a live SensorReader when available, while
    preserving compatibility with legacy/test mocks that expose only ``.latest``.
    """
    if reader is None:
        return None
    get_scan_reading = getattr(reader, "get_scan_reading", None)
    if callable(get_scan_reading):
        return get_scan_reading(now=now)
    if getattr(reader, "is_connected", None) is False:
        return None
    latest = getattr(reader, "latest", None)
    if latest is None:
        return None
    temp = getattr(latest, "temperature", None)
    hum = getattr(latest, "humidity", None)
    if not is_valid_dht22(temp, hum):
        return None
    recorded_at = getattr(latest, "recorded_at", None)
    if recorded_at is not None and not is_reading_fresh(recorded_at, now=now):
        return None
    stamp = as_manila(recorded_at) if recorded_at is not None else (
        as_manila(now) if now is not None else now_manila()
    )
    return SensorData(temperature=float(temp), humidity=float(hum), recorded_at=stamp)


class SensorReader:
    """
    Reads DHT22 sensor data from Arduino via serial port.

    Expected serial format from Arduino:
        TEMP:26.5,HUM:72.3\\n
    """

    def __init__(self):
        self._serial = None
        self._connected = False
        self._latest: SensorData | None = None
        self._recent: deque[SensorData] = deque(maxlen=60)
        self._task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def latest(self) -> SensorData | None:
        return self._latest

    def connect(self) -> bool:
        """Open serial connection to Arduino. Call once at boot or reconnect."""
        if self._serial is not None:
            with contextlib.suppress(Exception):
                if getattr(self._serial, "is_open", False):
                    self._serial.close()
            self._serial = None
        try:
            import serial

            self._serial = serial.Serial(
                port=settings.sensor_serial_port,
                baudrate=settings.sensor_baud_rate,
                timeout=2,
            )
            with contextlib.suppress(Exception):
                self._serial.reset_input_buffer()
            self._connected = True
            logger.info(
                f"Sensor connected on {settings.sensor_serial_port} "
                f"at {settings.sensor_baud_rate} baud"
            )
            return True
        except ImportError:
            logger.warning("pyserial not installed — sensor reader unavailable")
            self._connected = False
            return False
        except Exception as exc:
            logger.warning(f"Sensor connection failed: {exc}. Sensor reader unavailable.")
            self._connected = False
            return False

    def read_once(self) -> SensorData | None:
        """Read the newest queued sensor measurement from serial, draining stale backlog."""
        if not self._connected or self._serial is None:
            return None

        try:
            first = self._serial.readline()
        except Exception as exc:
            if _is_serial_disconnect_error(exc):
                logger.warning(f"Sensor serial disconnected: {exc}")
                self.disconnect()
            else:
                logger.warning(f"Sensor read error: {exc}")
            return None

        lines: list[str] = []
        decoded = _decode_serial_line(first)
        if decoded:
            lines.append(decoded)

        # Drain buffered lines queued when Arduino emits faster than the poll interval.
        drained = 0
        while drained < MAX_SERIAL_DRAIN_LINES:
            try:
                waiting = int(getattr(self._serial, "in_waiting", 0) or 0)
            except Exception:
                break
            if waiting <= 0:
                break
            try:
                extra = self._serial.readline()
            except Exception as exc:
                if _is_serial_disconnect_error(exc):
                    logger.warning(f"Sensor serial disconnected while draining: {exc}")
                    self.disconnect()
                break
            drained += 1
            text = _decode_serial_line(extra)
            if text:
                lines.append(text)
            elif not extra:
                break

        if not lines:
            return None

        last_error: str | None = None
        for candidate in reversed(lines):
            if candidate.startswith("ERROR:"):
                last_error = candidate
                continue
            parsed = self._parse_line(candidate)
            if parsed is not None:
                return parsed

        if last_error is not None:
            logger.warning(f"Arduino reported a hardware issue: {last_error}")
        return None

    def _parse_line(self, line: str) -> SensorData | None:
        """
        Parse Arduino serial output.
        Expected format: TEMP:26.5,HUM:72.3
        """
        if line.startswith("ERROR:"):
            logger.warning(f"Arduino reported a hardware issue: {line}")
            return None

        try:
            parts = {}
            for segment in line.split(","):
                key, value = segment.split(":")
                parts[key.strip().upper()] = float(value.strip())

            if "TEMP" in parts and "HUM" in parts:
                raw_temp = parts["TEMP"]
                raw_hum = parts["HUM"]
                if not is_valid_dht22(raw_temp, raw_hum):
                    logger.warning(f"Out-of-range or non-finite DHT22 reading discarded: {line}")
                    return None

                temp = round(raw_temp + float(getattr(settings, "sensor_temp_offset", 0.0)), 2)
                hum = round(
                    min(
                        DHT22_HUM_MAX_PCT,
                        max(
                            DHT22_HUM_MIN_PCT,
                            raw_hum + float(getattr(settings, "sensor_humidity_offset", 0.0)),
                        ),
                    ),
                    2,
                )
                if not is_valid_dht22(temp, hum):
                    logger.warning(f"Calibrated DHT22 reading out of bounds: {temp}C, {hum}%")
                    return None

                data = SensorData(
                    temperature=temp,
                    humidity=hum,
                    recorded_at=now_manila(),
                )
                self._latest = data
                self._recent.append(data)
                return data

            logger.warning(f"Unexpected sensor format: {line}")
            return None
        except (ValueError, KeyError) as exc:
            logger.warning(f"Failed to parse sensor data '{line}': {exc}")
            return None

    def get_scan_reading(
        self,
        now: datetime | None = None,
        window: int | None = None,
    ) -> SensorData | None:
        """Return a fresh, smoothed reading from recent DHT22 samples for scan prediction."""
        if not self._connected:
            return None
        latest = self._latest
        if latest is None or not is_valid_dht22(latest.temperature, latest.humidity):
            return None
        current = as_manila(now) if now is not None else now_manila()
        if not is_reading_fresh(latest.recorded_at, now=current):
            return None

        target_window = max(
            1, int(window if window is not None else getattr(settings, "sensor_smoothing_window", 5))
        )
        max_age = max(
            freshness_window_seconds(),
            int(getattr(settings, "sensor_smoothing_max_age_s", 30)),
        )
        candidates = [
            sample
            for sample in self._recent
            if is_valid_dht22(sample.temperature, sample.humidity)
            and is_reading_fresh(sample.recorded_at, now=current, max_age_seconds=max_age)
        ]
        if not candidates:
            candidates = [latest]
        else:
            candidates = candidates[-target_window:]

        smoothed_temp = round(trimmed_mean([sample.temperature for sample in candidates]), 2)
        smoothed_hum = round(
            min(
                DHT22_HUM_MAX_PCT,
                max(
                    DHT22_HUM_MIN_PCT,
                    trimmed_mean([sample.humidity for sample in candidates]),
                ),
            ),
            2,
        )
        return SensorData(
            temperature=smoothed_temp,
            humidity=smoothed_hum,
            recorded_at=latest.recorded_at,
        )

    async def start_polling(self, on_reading=None):
        """
        Start background polling loop.

        Args:
            on_reading: Optional async callback called with each SensorData.
                        Used to broadcast via WebSocket and persist to DB.
        """
        from app.services.runtime_operations import coordinator, run_blocking

        logger.info(
            f"Sensor polling started (interval: {settings.sensor_read_interval_s}s)"
        )
        last_reconnect_attempt = time.monotonic()

        while True:
            try:
                if not self._connected:
                    now_mono = time.monotonic()
                    if now_mono - last_reconnect_attempt >= RECONNECT_INTERVAL_S:
                        last_reconnect_attempt = now_mono
                        async with coordinator.operation():
                            await run_blocking(self.connect)

                if self._connected:
                    async with coordinator.operation():
                        data = await run_blocking(self.read_once)

                    if data and on_reading:
                        await on_reading(data)

            except asyncio.CancelledError:
                logger.info("Sensor polling cancelled")
                break
            except Exception as exc:
                logger.error(f"Sensor polling error: {exc}")

            await asyncio.sleep(settings.sensor_read_interval_s)

    def disconnect(self):
        """Close serial connection."""
        if self._serial is not None:
            with contextlib.suppress(Exception):
                if getattr(self._serial, "is_open", False):
                    self._serial.close()
                    logger.info("Sensor serial port closed")
        self._serial = None
        self._connected = False


# Singleton instance
sensor_reader = SensorReader()
