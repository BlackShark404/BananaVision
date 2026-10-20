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
    """Return CPU temperature in °C, or None when no hardware sensor is accessible."""
    system = platform.system()

    # 1. psutil (Linux, FreeBSD)
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ("coretemp", "cpu_thermal", "cpu-thermal", "k10temp", "zenpower", "nvme"):
                    if key in temps and temps[key]:
                        return round(temps[key][0].current, 1)
                first = next(iter(temps.values()))
                if first:
                    return round(first[0].current, 1)
    except Exception:
        pass

    # 2. Linux fallback
    if system == "Linux":
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return round(float(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass

    # 3. Windows fallback via PowerShell CIM (wmic.exe is removed on Windows 11 24H2+ images).
    # MSAcpi thermal zone reports centi-Kelvin; the performance-counter thermal zone may
    # report Kelvin or centi-Kelvin depending on the system, so both scales are normalized.
    if system == "Windows":
        try:
            import subprocess
            script = (
                "$zone = Get-CimInstance -Namespace root/wmi "
                "-ClassName MSAcpi_ThermalZoneTemperature "
                "-ErrorAction SilentlyContinue | Select-Object -First 1;"
                "if ($zone -and $zone.CurrentTemperature -gt 2730 "
                "-and $zone.CurrentTemperature -lt 3930)"
                "{ [math]::Round($zone.CurrentTemperature / 10.0 - 273.15, 1) } "
                "else {"
                "$tz = Get-CimInstance -ClassName "
                "Win32_PerfFormattedData_Counters_ThermalZoneInformation "
                "-ErrorAction SilentlyContinue | Select-Object -First 1;"
                "if ($tz) {"
                "$t = [double]$tz.Temperature;"
                "if ($t -ge 500) { $t = $t / 10.0 };"
                "if ($t -gt 273.05 -and $t -lt 393.15) { [math]::Round($t - 273.15, 1) }"
                "}"
                "}"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                text=True, timeout=4,
            )
            value = out.strip()
            if not value:
                raise ValueError("no thermal zone data reported")
            return round(float(value.replace(",", ".")), 1)
        except Exception:
            pass

    # 4. Mac fallback (using osx-cpu-temp if installed)
    if system == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(["osx-cpu-temp"], text=True, stderr=subprocess.STDOUT, timeout=2)
            if "°C" in out:
                return round(float(out.replace("°C", "").strip()), 1)
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

    # Temperature (with cross-platform fallbacks; None when unavailable)
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
