"""
Arduino DHT22 sensor reader via serial port.

Reads temperature and humidity from an Arduino connected via USB serial.
Runs as a background asyncio task, broadcasting updates via WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_settings
from app.core.exceptions import SensorError

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SensorData:
    """Parsed sensor reading."""
    temperature: float
    humidity: float
    recorded_at: datetime


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
        self._task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def latest(self) -> SensorData | None:
        return self._latest

    def connect(self) -> bool:
        """Open serial connection to Arduino. Call once at boot."""
        try:
            import serial

            self._serial = serial.Serial(
                port=settings.sensor_serial_port,
                baudrate=settings.sensor_baud_rate,
                timeout=2,
            )
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
        """Read a single sensor measurement from serial."""
        if not self._connected or self._serial is None:
            return None

        try:
            line = self._serial.readline().decode("utf-8").strip()
            if not line:
                return None

            return self._parse_line(line)
        except Exception as exc:
            logger.warning(f"Sensor read error: {exc}")
            return None

    def _parse_line(self, line: str) -> SensorData | None:
        """
        Parse Arduino serial output.
        Expected format: TEMP:26.5,HUM:72.3
        """
        try:
            parts = {}
            for segment in line.split(","):
                key, value = segment.split(":")
                parts[key.strip().upper()] = float(value.strip())

            if "TEMP" in parts and "HUM" in parts:
                data = SensorData(
                    temperature=parts["TEMP"],
                    humidity=parts["HUM"],
                    recorded_at=datetime.now(timezone.utc),
                )
                self._latest = data
                return data

            logger.warning(f"Unexpected sensor format: {line}")
            return None
        except (ValueError, KeyError) as exc:
            logger.warning(f"Failed to parse sensor data '{line}': {exc}")
            return None


    async def start_polling(self, on_reading=None):
        """
        Start background polling loop.

        Args:
            on_reading: Optional async callback called with each SensorData.
                        Used to broadcast via WebSocket and persist to DB.
        """
        logger.info(
            f"Sensor polling started (interval: {settings.sensor_read_interval_s}s)"
        )

        while True:
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, self.read_once)

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
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Sensor serial port closed")
        self._connected = False


# Singleton instance
sensor_reader = SensorReader()
