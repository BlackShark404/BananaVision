"""Verify OS acceptance of a scheduled power command without claiming reboot completion."""
import asyncio
import platform
import subprocess

from fastapi import HTTPException
from app.services.runtime_operations import station_lock


async def schedule_power_action(action: str) -> None:
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan or camera configuration before scheduling power commands")
    async with station_lock:
        await _schedule_power_action(action)


async def _schedule_power_action(action: str) -> None:
    system = platform.system().lower()
    if system == "windows":
        command = ["shutdown", "/r" if action == "restart" else "/s", "/t", "10"]
    elif system in {"linux", "darwin"}:
        command = ["sudo", "-n", "shutdown", "-r" if action == "restart" else "-h", "+1"]
    else:
        raise HTTPException(503, "Power commands are unsupported on this operating system")
    try:
        result = await asyncio.to_thread(
            subprocess.run, command, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(503, f"Operating system did not confirm {action}; check host configuration") from exc
    if result.returncode != 0:
        raise HTTPException(503, f"Operating system rejected {action}; check host permissions")
