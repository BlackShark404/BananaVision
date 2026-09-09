"""
System metrics routes — returns live host information via psutil.
"""

from __future__ import annotations

import platform
import time

import psutil
from fastapi import APIRouter

from app.api.deps import CurrentUser

router = APIRouter(prefix="/system", tags=["System"])


def _format_uptime(seconds: float) -> str:
    """Convert seconds to a human-readable uptime string."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _get_cpu_name() -> str:
    """Best-effort CPU brand string."""
    # macOS / Linux with /proc/cpuinfo
    try:
        import subprocess
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
                timeout=2,
            ).strip()
            if out:
                return out
        elif system == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown"


def _get_cpu_temp() -> float | None:
    """Return CPU temperature in °C, or None if unavailable."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Common Linux keys
        for key in ("coretemp", "cpu_thermal", "cpu-thermal", "k10temp", "zenpower"):
            if key in temps and temps[key]:
                return temps[key][0].current
        # Fallback: first available sensor
        first = next(iter(temps.values()))
        if first:
            return first[0].current
    except Exception:
        pass
    return None


@router.get("/metrics")
async def system_metrics(user: CurrentUser):
    """Return live system metrics from the host machine."""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)

    # Memory
    mem = psutil.virtual_memory()
    mem_used_gb = round(mem.used / (1024 ** 3), 1)
    mem_total_gb = round(mem.total / (1024 ** 3), 1)

    # Disk
    disk = psutil.disk_usage("/")
    disk_used_gb = round(disk.used / (1024 ** 3), 0)
    disk_total_gb = round(disk.total / (1024 ** 3), 0)

    # Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time

    # Temperature (may be None on macOS)
    cpu_temp = _get_cpu_temp()

    return {
        "cpu_name": _get_cpu_name(),
        "cpu_percent": cpu_percent,
        "memory_used_gb": mem_used_gb,
        "memory_total_gb": mem_total_gb,
        "memory_percent": mem.percent,
        "disk_used_gb": int(disk_used_gb),
        "disk_total_gb": int(disk_total_gb),
        "disk_percent": disk.percent,
        "uptime": _format_uptime(uptime_seconds),
        "cpu_temp": cpu_temp,
    }
