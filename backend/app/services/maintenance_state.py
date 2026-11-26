"""Durable maintenance outcomes and a non-restored session generation."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.maintenance_state import MaintenanceState

# Populated before accepting traffic; tests and newly initialized stations start here.
auth_generation = "initial"


async def get_state(db, *, lock=False) -> MaintenanceState:
    query = select(MaintenanceState).where(MaintenanceState.id == 1).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    state = await db.scalar(query)
    if state is None:
        state = MaintenanceState(id=1, auth_generation="initial", operations={})
        db.add(state)
        await db.flush()
    return state


async def generation_matches(db, payload: dict) -> bool:
    generation = await db.scalar(select(MaintenanceState.auth_generation).where(MaintenanceState.id == 1))
    return payload.get("sg") == (generation if generation is not None else "initial")


def publish_generation(generation: str):
    global auth_generation
    auth_generation = generation


async def advance_generation(db, marker: str):
    state = await get_state(db, lock=True)
    state.auth_generation = uuid.uuid4().hex
    state.restore_marker = marker
    await db.flush()
    return state.auth_generation


async def record_operation(db, operation_id: str, result: dict):
    state = await get_state(db, lock=True)
    state.operations = {**state.operations, operation_id: result}
    await db.flush()


async def operation_result(db, operation_id: str):
    state = await get_state(db)
    return state.operations.get(operation_id)
