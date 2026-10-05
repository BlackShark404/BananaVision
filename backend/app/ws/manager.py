"""Room connections with authorization checked before every delivery."""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket

from app.core.time import now_manila
from app.ws.authorization import ROLE_ROOMS, current_socket_role

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._client_rooms: dict[WebSocket, set[str]] = {}
        self._tokens: dict[WebSocket, str] = {}

    @property
    def total_connections(self) -> int:
        return len(self._client_rooms)

    async def connect(self, websocket: WebSocket, rooms: list[str], *, token: str):
        await websocket.accept()
        self._tokens[websocket] = token
        self.subscribe(websocket, rooms)

    def subscribe(self, websocket: WebSocket, rooms: list[str]):
        """Change subscriptions without accepting an already-open socket again."""
        self._remove_rooms(websocket)
        self._client_rooms[websocket] = set(rooms)
        for room in self._client_rooms[websocket]:
            self._connections.setdefault(room, []).append(websocket)

    def _remove_rooms(self, websocket: WebSocket):
        for room in self._client_rooms.pop(websocket, set()):
            self._connections[room] = [ws for ws in self._connections[room] if ws is not websocket]
            if not self._connections[room]:
                del self._connections[room]

    def disconnect(self, websocket: WebSocket):
        self._remove_rooms(websocket)
        self._tokens.pop(websocket, None)

    async def validate(self, websocket: WebSocket, room: str | None = None) -> bool:
        try:
            token = self._tokens.get(websocket)
            role = await current_socket_role(token) if token else None
            allowed = ROLE_ROOMS.get(role, set())
            subscribed = self._client_rooms.get(websocket, set())
            if role and subscribed <= allowed and (room is None or room in subscribed):
                return True
        except Exception:
            logger.exception("WebSocket authorization failed")
        self.disconnect(websocket)
        try:
            await websocket.close(code=4001, reason="Session expired or revoked")
        except Exception:
            pass
        return False

    @staticmethod
    def _message(event: str, data: dict) -> str:
        return json.dumps({"event": event, "data": data, "timestamp": now_manila().isoformat()})

    async def _send(self, websocket: WebSocket, message: str, room: str | None = None):
        if not await self.validate(websocket, room):
            return
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)

    async def send_to_room(self, room: str, event: str, data: dict):
        message = self._message(event, data)
        for websocket in list(self._connections.get(room, [])):
            await self._send(websocket, message, room)

    async def broadcast(self, event: str, data: dict):
        message = self._message(event, data)
        for websocket in list(self._client_rooms):
            await self._send(websocket, message)

    async def send_personal(self, websocket: WebSocket, event: str, data: dict):
        await self._send(websocket, self._message(event, data))


ws_manager = ConnectionManager()
