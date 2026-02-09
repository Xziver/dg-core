"""Bot API — game event submission and state queries."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import session as session_mod, timeline, world
from app.domain.dispatcher import dispatch
from app.infra.db import get_db
from app.models.event import GameEvent

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.post("/events")
async def submit_event(
    event: GameEvent,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Submit a game event to the engine dispatcher."""
    result = await dispatch(db, event)
    return result.model_dump()


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    players = await session_mod.get_session_players(db, session_id)
    return {
        "session_id": s.id,
        "name": s.name,
        "status": s.status,
        "config": json.loads(s.config_json) if s.config_json else None,
        "players": [
            {"player_id": p.player_id, "role": p.role}
            for p in players
        ],
    }


@router.get("/sessions/{session_id}/state")
async def get_world_state(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ws = await world.get_world_state(db, session_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="World state not found")
    return {
        "session_id": session_id,
        "current_sector": ws.current_sector,
        "sector_data": json.loads(ws.sector_data_json) if ws.sector_data_json else None,
        "global_flags": json.loads(ws.global_flags_json) if ws.global_flags_json else None,
    }


@router.get("/sessions/{session_id}/timeline")
async def get_timeline(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> dict:
    events = await timeline.get_timeline(db, session_id, limit=limit, offset=offset)
    return {
        "session_id": session_id,
        "events": [
            {
                "id": e.id,
                "seq": e.seq,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": json.loads(e.data_json) if e.data_json else None,
                "result": json.loads(e.result_json) if e.result_json else None,
                "narrative": e.narrative,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }
