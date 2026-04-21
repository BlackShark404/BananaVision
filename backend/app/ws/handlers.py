"""
WebSocket endpoint handler.
"""

from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect, Query

from app.core.security import decode_access_token
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)


async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    rooms: str = Query(default="kiosk,dashboard"),
):
    """
    Main WebSocket endpoint.

    Connect: ws://host:port/api/v1/ws?token=JWT&rooms=kiosk,dashboard
    """
    # Validate token (optional: allow unauthenticated in dev mode)
    user_data = None
    if token:
        user_data = decode_access_token(token)
        if not user_data:
            await websocket.close(code=4001, reason="Invalid token")
            return

    room_list = [r.strip() for r in rooms.split(",") if r.strip()]
    await ws_manager.connect(websocket, room_list)

    try:
        while True:
            # Listen for client messages (ping/pong, room changes, etc.)
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                event = msg.get("event", "")

                if event == "ping":
                    await ws_manager.send_personal(websocket, "pong", {})
                elif event == "subscribe":
                    # Client can dynamically subscribe to rooms
                    new_rooms = msg.get("data", {}).get("rooms", [])
                    if new_rooms:
                        # Re-register with new rooms
                        ws_manager.disconnect(websocket)
                        await ws_manager.connect(websocket, new_rooms)

            except json.JSONDecodeError:
                pass  # Ignore malformed messages

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        ws_manager.disconnect(websocket)
