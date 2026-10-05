"""Serialize scans with camera reconfiguration and power scheduling on this station."""
import asyncio

station_lock = asyncio.Lock()
