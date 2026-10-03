"""
WebSocket connection manager with room/channel support.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from app.core.time import now_manila

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections organized by rooms/channels.

    Rooms:
        - "kiosk": Kiosk page clients (scan events, sensor updates)
        - "dashboard": Dashboard/admin clients (scan results, notifications)
        - "devices": Device status page (camera status)
        - "all": Broadcast to every connected client
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._client_rooms: dict[WebSocket, set[str]] = {}

    @property
    def total_connections(self) -> int:
        return len(self._client_rooms)

    async def connect(self, websocket: WebSocket, rooms: list[str] | None = None):
        """Accept a WebSocket connection and subscribe it to rooms."""
        await websocket.accept()
        target_rooms = rooms or ["all"]

        self._client_rooms[websocket] = set(target_rooms)
        for room in target_rooms:
            self._connections.setdefault(room, []).append(websocket)

        logger.info(f"WS connected. Rooms: {target_rooms}. Total: {self.total_connections}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from all rooms."""
        rooms = self._client_rooms.pop(websocket, set())
        for room in rooms:
            if room in self._connections:
                self._connections[room] = [
                    ws for ws in self._connections[room] if ws is not websocket
                ]
                if not self._connections[room]:
                    del self._connections[room]

        logger.info(f"WS disconnected. Remaining: {self.total_connections}")

    async def send_to_room(self, room: str, event: str, data: dict):
        """Send an event to all clients in a specific room."""
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": now_manila().isoformat(),
        })

        clients = self._connections.get(room, [])
        dead: list[WebSocket] = []

        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def broadcast(self, event: str, data: dict):
        """Send an event to ALL connected clients across all rooms."""
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": now_manila().isoformat(),
        })

        all_clients = set()
        for clients in self._connections.values():
            all_clients.update(clients)

        dead: list[WebSocket] = []
        for ws in all_clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, event: str, data: dict):
        """Send an event to a specific client."""
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": now_manila().isoformat(),
        })
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)


# Singleton instance
ws_manager = ConnectionManager()
