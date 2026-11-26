"""Authenticated sockets revalidate on messages, delivery, and idle intervals."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import Query, WebSocket, WebSocketDisconnect

from app.ws.authorization import authorized_rooms, current_socket_role
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)
SESSION_CHECK_INTERVAL = 15


async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    rooms: str = Query(default="kiosk,dashboard"),
):
    try:
        role = await current_socket_role(token)
    except Exception:
        logger.exception("WebSocket token validation failed")
        role = None
    if role is None:
        await websocket.close(code=4001, reason="Invalid or revoked session")
        return

    await ws_manager.connect(
        websocket, authorized_rooms(role, [room.strip() for room in rooms.split(",")]), token=token,
    )
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), SESSION_CHECK_INTERVAL)
            except TimeoutError:
                if not await ws_manager.validate(websocket):
                    break
                continue
            if not await ws_manager.validate(websocket):
                break
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("event") == "ping":
                await ws_manager.send_personal(websocket, "pong", {})
            elif message.get("event") == "subscribe":
                data = message.get("data")
                requested = data.get("rooms") if isinstance(data, dict) else None
                if isinstance(requested, list) and all(isinstance(room, str) for room in requested):
                    role = await current_socket_role(token)
                    if role is None:
                        await websocket.close(code=4001, reason="Session revoked")
                        break
                    ws_manager.subscribe(websocket, authorized_rooms(role, requested))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket handler failed")
        try:
            await websocket.close(code=4001, reason="Session validation failed")
        except Exception:
            pass
    finally:
        ws_manager.disconnect(websocket)
