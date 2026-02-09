"""World state management — sectors, global flags."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import WorldState


async def get_world_state(db: AsyncSession, session_id: str) -> WorldState | None:
    result = await db.execute(
        select(WorldState).where(WorldState.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def set_current_sector(
    db: AsyncSession, session_id: str, sector: str
) -> WorldState:
    ws = await get_world_state(db, session_id)
    if ws is None:
        raise ValueError(f"World state for session {session_id} not found")
    ws.current_sector = sector
    await db.flush()
    return ws


async def get_global_flags(db: AsyncSession, session_id: str) -> dict:
    ws = await get_world_state(db, session_id)
    if ws is None:
        return {}
    return json.loads(ws.global_flags_json) if ws.global_flags_json else {}


async def set_global_flag(
    db: AsyncSession, session_id: str, key: str, value: object
) -> dict:
    ws = await get_world_state(db, session_id)
    if ws is None:
        raise ValueError(f"World state for session {session_id} not found")
    flags = json.loads(ws.global_flags_json) if ws.global_flags_json else {}
    flags[key] = value
    ws.global_flags_json = json.dumps(flags)
    await db.flush()
    return flags
