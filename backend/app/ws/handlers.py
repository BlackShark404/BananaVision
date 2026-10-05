"""
WebSocket endpoint handler.

AUTH-03: All connections require a valid, non-revoked JWT for an active account.
Room subscriptions are authorized by role:
  - Operators may join: kiosk
  - Admins may join: kiosk, dashboard, devices, admin
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect, Query

from app.core.security import decode_access_token
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)

# Rooms that operators are allowed to subscribe to.
OPERATOR_ALLOWED_ROOMS = {"kiosk"}
# Admins can join any room.
ALL_ROOMS = {"kiosk", "dashboard", "devices", "admin"}


def _authorize_rooms(role: str, requested: list[str]) -> list[str]:
    """Filter requested rooms to those the user's role permits."""
    if role == "Admin":
        return [r for r in requested if r in ALL_ROOMS] or ["kiosk"]
    # Operators and any other role — restricted to kiosk only.
    return [r for r in requested if r in OPERATOR_ALLOWED_ROOMS] or ["kiosk"]


async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    rooms: str = Query(default="kiosk,dashboard"),
):
    """
    Main WebSocket endpoint.

    Connect: ws://host:port/api/v1/ws?token=JWT&rooms=kiosk,dashboard

    AUTH-03: A valid JWT is **required**. Anonymous connections are rejected.
    """
    # ── Require a token ──────────────────────────────────────────────────
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return

    user_data = decode_access_token(token)
    if not user_data or user_data.get("scope", "access") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return

    # ── Token version + active status check (AUTH-02 / AUTH-03) ───────────
    try:
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.user_account import UserAccount
        from app.schemas.enums import ActiveStatusEnum

        token_version = user_data.get("tv")
        user_id = uuid.UUID(user_data["sub"])
        user_role = user_data.get("role", "Operator")

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

    # ── Authorize rooms ──────────────────────────────────────────────────
    requested_rooms = [r.strip() for r in rooms.split(",") if r.strip()]
    authorized_rooms = _authorize_rooms(user_role, requested_rooms)

    await ws_manager.connect(websocket, authorized_rooms)

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
                    # Client can dynamically subscribe to rooms — still authorized.
                    new_rooms = msg.get("data", {}).get("rooms", [])
                    if new_rooms and isinstance(new_rooms, list):
                        authorized_new = _authorize_rooms(user_role, new_rooms)
                        if authorized_new:
                            ws_manager.disconnect(websocket)
                            await ws_manager.connect(websocket, authorized_new)

            except json.JSONDecodeError:
                pass  # Ignore malformed messages

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        ws_manager.disconnect(websocket)
