"""
WebSocket endpoint handler.
"""

from __future__ import annotations

import json
import logging
import uuid

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

        # ── Token version check (AUTH-02 fix) ────────────────────────────
        # Reject WebSocket connections with revoked tokens.
        try:
            from sqlalchemy import select
            from app.core.database import async_session_factory
            from app.models.user_account import UserAccount
            from app.schemas.enums import ActiveStatusEnum

            token_version = user_data.get("tv")
            user_id = uuid.UUID(user_data["sub"])

            async with async_session_factory() as db:
                result = await db.execute(
                    select(UserAccount.token_version, UserAccount.status)
                    .where(UserAccount.id == user_id)
                )
                row = result.one_or_none()

                if not row:
                    await websocket.close(code=4001, reason="User not found")
                    return

                db_version, status = row

                if status != ActiveStatusEnum.ACTIVE:
                    await websocket.close(code=4003, reason="Account is inactive")
                    return

                if token_version is None or token_version != db_version:
                    await websocket.close(code=4001, reason="Session revoked")
                    return
        except Exception as exc:
            logger.error(f"WebSocket token validation error: {exc}")
            await websocket.close(code=4001, reason="Token validation failed")
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
